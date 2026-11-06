"""Unscripted Audio 中转：Pocket FM 式音频连载 App 的后端（接口见 CONTRACT.md）。
- 第 1 集：data/ep1/<id>.<lang>.json 的剧本，第一次有人播时逐句合成（ElevenLabs v4，按 data/voices.json 配音）、
  拼成一条 mp3 + 环境声 + 逐句字幕，传到 Waku 存储（CDN 比隧道快得多），缓存到 cache/ep1/。
- 第 2 集起：她选了什么 → 编剧层按世界卡（data/world/<id>.json）写下一集，逐行流式输出，每写完一句就送去合成。
  编剧：DIRECTOR_CLI 设了就用本机 Claude Code（Opus 5.5），失败退回 OpenRouter（WRITER_FALLBACK，默认 GLM-5.3-prime）。
用法：python3 unscripted_audio_server.py <token> <port>（名字故意起得独一无二：别的会话会按 server.py 之类的通用名批量杀进程）"""
import json, os, queue, random, re, string, subprocess, sys, threading, time, traceback, base64
import urllib.request as U
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from wakumcp import WakuMCP

ROOT = Path(__file__).resolve().parent
APP, DATA, CACHE, LOGS = ROOT / 'app', ROOT / 'data', ROOT / 'cache', ROOT / 'logs'
for d in (CACHE / 'ep1', CACHE / 'amb', LOGS / 'sessions'): d.mkdir(parents=True, exist_ok=True)
TOKEN, PORT = sys.argv[1], int(sys.argv[2])
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
FP = FF.replace('ffmpeg', 'ffprobe')
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
try:
    import claude_cli as CC
except Exception:
    CC = None

BASE = {s['id']: s for s in json.load(open(DATA / 'series_base.json'))}
VOICES = json.load(open(DATA / 'voices.json'))
WORLD = {sid: json.load(open(DATA / 'world' / f'{sid}.json')) for sid in BASE}
MOTION = json.load(open(DATA / 'motion.json')) if (DATA / 'motion.json').exists() else {}  # 播放器动态封面（build_motion.py）
VIS = {sid: json.load(open(DATA / 'visuals' / f'{sid}.json')) for sid in BASE if (DATA / 'visuals' / f'{sid}.json').exists()}  # 画面库（build_visuals.py）


def vis_card(sid):
    v = VIS.get(sid)
    return {'clips': {c['id']: c['src'] for c in v['clips']}, 'pool': v['pool']} if v else None


def ep1_with_visuals(ep, series, lang):
    """第 1 集按逐句字幕时间配画面（build_ep1_visuals.py 的逐句映射），相邻同一片段合并成一段"""
    f = DATA / 'ep1_visuals' / f'{series}.{lang}.json'
    if not ep or not f.exists(): return ep
    m = {x['line']: x['clip'] for x in json.load(open(f))}; tl = []
    for i, c in enumerate(ep.get('cues') or []):
        clip = m.get(i)
        if not clip: continue
        if tl and tl[-1]['clip'] == clip: tl[-1]['e'] = c['e']
        else: tl.append({'s': c['s'] if tl else 0.0, 'e': c['e'], 'clip': clip})
    for a, b in zip(tl, tl[1:]): a['e'] = b['s']  # 时间轴连续，句间停顿不黑屏
    if tl: tl[-1]['e'] = max(tl[-1]['e'], ep.get('dur') or 0)
    return dict(ep, visuals=tl)
STATS = {'magnus': ('2.4M', 4.9), 'rafael': ('1.1M', 4.8), 'rowan': ('640K', 4.7), 'rian': ('890K', 4.8), 'island': ('1.6M', 4.7), 'lena': ('720K', 4.8), 'mii': ('530K', 4.9),
         'kael': ('1.9M', 4.9), 'villa': ('1.4M', 4.8), 'dorian': ('2.1M', 4.9), 'hear': ('980K', 4.8), 'mask': ('760K', 4.7), 'milo': ('610K', 4.8)}  # perhaps-worlds 6 部  # 展示用
MODEL_TTS = 'elevenlabs/eleven-v4'
FALLBACK = os.environ.get('WRITER_FALLBACK', 'z-ai/glm-5.3-prime')
MAX_EPS = 12

POOL = queue.Queue()
for _ in range(10): POOL.put(WakuMCP())
SESS, JOBS, EP1_LOCK = {}, {}, {}
op = U.build_opener(U.ProxyHandler({}))


def rid(n=10): return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def log(sid, rec):
    with open(LOGS / 'sessions' / f'{sid}.jsonl', 'a') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')


# ---------------- 配音 ----------------
def voice_of(series, who, lang):
    v = VOICES['NARR'] if who == 'NARR' else VOICES[series].get(who) or VOICES['NARR']
    return v[lang], v.get('lead', False)


def tts_text(text, lead, lang):
    """中文：去掉编剧写的标签，主角句首统一 [quietly]（11-05 她认可的低声感）；省略号保留。英文：标签照用。"""
    if lang == 'zh':
        t = re.sub(r'\[[^\]]*\]\s*', '', text).strip()
        return ('[quietly] ' + t) if lead else t
    return text.strip()


def waku(model, params, timeout=120):
    m = POOL.get()
    try:
        return m.tool('multimodal_run_model', {'capability': 'multimodal.generate.audio', 'model_id': model, 'parameters': params}, timeout=timeout)
    except TimeoutError:
        try: m.p.kill()
        except Exception: pass
        m = WakuMCP(); raise
    finally:
        POOL.put(m)


def tts(series, who, text, lang):
    vid, lead = voice_of(series, who, lang)
    params = dict(text=tts_text(text, lead, lang), voice_id=vid, stability=0.4, similarity=0.8)
    err = None
    for attempt in range(3):
        try:
            r = waku(MODEL_TTS, params)
            if r.get('asset_url'): return r['asset_url']
            err = r.get('error') or r
        except Exception as e:
            err = e
        if attempt == 1: params['text'] = re.sub(r'\[[^\]]*\]\s*', '', params['text'])  # 标签导致参数错误时去标签再试
    raise RuntimeError(f'tts failed: {str(err)[:200]}')


def tts_hedged(series, who, text, lang, n):
    """同一句发 n 条，谁先好用谁"""
    done = threading.Event(); box = {}; errs = []

    def one():
        try:
            u = tts(series, who, text, lang)
            if not done.is_set(): box['u'] = u; done.set()
        except Exception as e:
            errs.append(e)
            if len(errs) >= n: done.set()
    for _ in range(n): threading.Thread(target=one, daemon=True).start()
    done.wait(150)
    if 'u' in box: return box['u']
    raise RuntimeError(str(errs[:1]))


def download(url, path):
    with op.open(url, timeout=90) as r, open(path, 'wb') as f: f.write(r.read())


def dur(path):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True).stdout.strip() or 0)


def upload(path, ctype='audio/mpeg'):
    m = POOL.get()
    try:
        r = m.tool('polyverse_upload_local_asset', {'filename': Path(path).name, 'content_type': ctype, 'data_base64': base64.b64encode(open(path, 'rb').read()).decode(), 'asset_kind': 'audio'}, timeout=180)
    finally:
        POOL.put(m)
    return r.get('public_url') or r.get('asset_url') or r.get('url')


def ambience(series, prompt):
    """每部剧一条可循环的环境声（ElevenLabs SFX），缓存"""
    f = CACHE / 'amb' / f'{series}.mp3'
    if f.exists(): return f
    try:
        r = waku('elevenlabs/sound-effects-v2', dict(prompt=('Quiet ambient background loop, no voices, no music: ' + prompt)[:440], duration=20, loop=True, prompt_influence=0.4), timeout=150)
        if r.get('asset_url'): download(r['asset_url'], f); return f
    except Exception:
        traceback.print_exc()
    return None


# ---------------- 第 1 集：预制 ----------------
def ep1_script(series, lang):
    return json.load(open(DATA / 'ep1' / f'{series}.{lang}.json'))


def ep1_cached(series, lang):
    f = CACHE / 'ep1' / f'{series}.{lang}.json'
    return json.load(open(f)) if f.exists() else None


def produce_ep1(series, lang, job=None):
    """逐句合成 → 拼接（句间停顿）→ 铺环境声 → 统一响度 → 上传；返回 ep 结构并缓存"""
    lock = EP1_LOCK.setdefault((series, lang), threading.Lock())
    with lock:
        c = ep1_cached(series, lang)
        if c: return c
        s = ep1_script(series, lang); lines = s['lines']
        work = CACHE / 'ep1' / f'{series}.{lang}.parts'; work.mkdir(exist_ok=True)
        files = [None] * len(lines)

        def one(i):
            p = work / f'{i:03d}.mp3'
            if not p.exists(): download(tts(series, lines[i]['who'], lines[i]['text'], lang), p)
            files[i] = p
            if job is not None: job['progress'] = sum(1 for x in files if x) / len(files)
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(8) as ex: list(ex.map(one, range(len(lines))))
        amb = ambience(series, s.get('amb') or 'night room tone')
        # 拼接：每句前后留白，换说话人停 0.45 秒，同一人连续 0.3 秒；开头 0.8 秒只有环境声
        cues, t, inputs, fc = [], 0.8, [], ''
        for i, (l, p) in enumerate(zip(lines, files)):
            d = dur(p); gap = 0.3 if i + 1 < len(lines) and lines[i + 1]['who'] == l['who'] else 0.45
            cues.append({'s': round(t, 2), 'e': round(t + d, 2), 'who': l['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', l['text'])})
            inputs += ['-i', str(p)]; fc += f'[{i}:a]aformat=sample_rates=44100:channel_layouts=mono,apad=pad_dur={gap}[a{i}];'
            t += d + gap
        total = t + 1.2
        n = len(lines)
        fc += ''.join(f'[a{i}]' for i in range(n)) + f'concat=n={n}:v=0:a=1,adelay=800,apad=pad_dur=1.2[v];'
        if amb:
            inputs += ['-stream_loop', '-1', '-i', str(amb)]
            fc += f'[{n}:a]aformat=sample_rates=44100:channel_layouts=mono,volume=-24dB,atrim=0:{total:.2f},afade=t=in:d=1.5,afade=t=out:st={total - 2:.2f}:d=2[b];[v][b]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-17:TP=-1.5:LRA=11[o]'
        else:
            fc += '[v]loudnorm=I=-17:TP=-1.5:LRA=11[o]'
        out = CACHE / 'ep1' / f'{series}.{lang}.mp3'
        subprocess.run([FF, '-v', 'error', '-y', *inputs, '-filter_complex', fc, '-map', '[o]', '-ar', '44100', '-ac', '1', '-b:a', '96k', str(out)], check=True)
        url = upload(out)
        ep = {'n': 1, 'title': s['title'], 'kind': 'produced', 'audio': url, 'dur': round(dur(out), 1), 'cues': cues, 'prompt': s['prompt'], 'choices': s['choices']}
        json.dump(ep, open(CACHE / 'ep1' / f'{series}.{lang}.json', 'w'), ensure_ascii=False, indent=1)
        return ep


# ---------------- 第 2 集起：实时写 ----------------
RULES = {
 'zh': '''写法（中文有声连载剧，每集 60–90 秒）：
- 纯音频，听众就是女主“你”。旁白 NARR 用第二人称“你”、现在时、短句，贴着耳朵讲；写声音、气味、触感、距离。
- 女主不配音：她说的话由旁白转述，最多偶尔一句很短的引语。
- 角色叫她时用她的名字「{name}」（不是资料包里的名字），每集叫 1–2 次就够。
- 所有旁白和台词都用中文，只有人名保留英文；不要英文句子，不要“亲爱的/宝贝”。
- 先接住她上一集结尾的选择/她说的话（第一句就回应），再往前推一步剧情（按 story_map，她有明确导向时按她的来，不插预设事件、不替她说身份）。
- 一集 9–13 句，旁白和台词交替，每句不超过 45 个字；有一个小高潮，结尾停在角色出的招上。
- 可以在句首少量用音频标签：[softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering]，每 4 句最多 1 个。''',
 'en': '''Writing rules (English serialized audio drama, 60–90 seconds per episode):
- Pure audio; the listener IS the heroine "you". Narrator NARR in second person, present tense, short, close to the ear; sound, smell, touch, distance.
- The heroine is not voiced: the narrator reports what she says, at most a very short quote now and then.
- Characters call her by her name "{name}" (not the name in the source material), once or twice per episode.
- First line answers her choice/what she said at the end of the last episode; then move the story one step (follow story_map, but if she steers, follow her; never invent her identity).
- 9–13 lines per episode, alternate narrator and dialogue, each line under 30 words; one small peak; end on a move the character makes.
- Sparse ElevenLabs tags at line start: [softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering], at most 1 per 4 lines. No "baby/darling".'''}

FORMAT = '''OUTPUT FORMAT — plain lines only, in this order, nothing else:
TITLE: <episode title{t}>
<Speaker>: <line>        (Speaker is NARR or one of: {cast})
... 9–13 lines ...
PROMPT: <one line above the choice: the situation, addressed to "you"/“你”>
C1: <her possible reply/action, first person, short>
C2: <another, clearly different>
END: no            (yes only when this is a true ending of the story)'''


def system_prompt(sess):
    s, lang, w = sess['series'], sess['lang'], WORLD[sess['series']]
    cast = [k for k in VOICES[s] if not k.startswith('_')]
    head = ('你是女性向有声连载剧（Pocket FM 那一类）的编剧，正在为一位听众实时写下一集。' if lang == 'zh' else
            'You are the writer of a women-focused serialized audio drama (Pocket FM style), writing the next episode live for one listener.')
    return '\n\n'.join([head, '世界卡（内部资料，真相按节奏揭晓，不提前剧透）：\n' + json.dumps(w, ensure_ascii=False),
                        RULES[lang].replace('{name}', sess['name']),
                        FORMAT.replace('{cast}', ', '.join(cast)).replace('{t}', '，6–10 字' if lang == 'zh' else ', 2–5 words')])


MAPPER = os.environ.get('CLIP_MAPPER', 'deepseek/deepseek-v4.1-flash')  # 实测 3 句约 4 秒


def map_clips(series, ctx, items):
    """items=[(i, who, text)] → {i: clip}。编剧不再管画面（省掉画面库那几千字提示词），台词一出来就交给快模型配。"""
    v = VIS.get(series)
    if not v or not items: return {}
    lib = '\n'.join(f"{c['id']}: {c['cap'][:90]}" for c in v['clips'])
    prompt = (f'画面库（id：画面内容）：\n{lib}\n\n前情（最近几句）：\n{ctx}\n\n给下面每句台词挑最匹配的画面 id（按动作、地点、人物、情绪；没有合适的用 s 开头的剧照或 idle；'
              f'同一片段不要连用超过 3 句）。只输出 JSON 对象，如 {{"3":"c12"}}：\n' + '\n'.join(f'{i} {w}: {t}' for i, w, t in items))
    body = {'model': MAPPER, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 300, 'temperature': 0, 'reasoning': {'enabled': False}}
    req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                    headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
    t = json.loads(op.open(req, timeout=30).read())['choices'][0]['message']['content']
    j = json.loads(t[t.find('{'):t.rfind('}') + 1]); ids = {c['id'] for c in v['clips']}
    return {int(k): c for k, c in j.items() if str(k).isdigit() and c in ids}


def clip_library(sid):
    v = VIS.get(sid)
    if not v: return ''
    return 'CLIP LIBRARY（画面库：播放器在这句台词播放时显示的静音画面，按画面内容挑）：\n' + '\n'.join(f"{c['id']}: {c['cap'][:110]}" for c in v['clips'])


def story_so_far(sess):
    parts = []
    for ep in sess['eps'][-3:]:
        txt = '\n'.join(f"{l['who']}: {l['text']}" for l in ep['lines'])
        parts.append(f"=== 第 {ep['n']} 集 {ep['title']} ===\n{txt}\n【选择点】{ep.get('prompt', '')}\n【她的回应】{ep.get('her', '（还没回应）')}")
    older = [f"第 {e['n']} 集：{e['title']}（她：{e.get('her', '')}）" for e in sess['eps'][:-3]]
    return ('更早：' + '；'.join(older) + '\n\n' if older else '') + '\n\n'.join(parts)


def her_said(text, via, lang):
    if via == 'silence' or not text.strip(): return '她没有说话，只是沉默。' if lang == 'zh' else 'She stays silent.'
    if lang != 'zh':
        return f'She chooses: {text}' if via == 'option' else f'She says ({"spoken" if via == "voice" else "typed"}): {text}'
    if via == 'option': return f'她选择：{text}'
    return f'她自己说（{"语音" if via == "voice" else "打字"}）：{text}'


KEYS_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 ._-]{0,24}|NARR|TITLE|PROMPT|C1|C2|END|LINE|HANGUP)\s*[:：]\s*(.+)$')


def openrouter_stream(model, sysm, user_msg, feed, max_tokens=1400, temperature=0.85, extra=None):
    body = {'model': model, 'max_tokens': max_tokens, 'temperature': temperature, 'stream': True,
            'messages': [{'role': 'system', 'content': sysm}, {'role': 'user', 'content': user_msg}], **(extra or {})}
    req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                    headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
    out = ''
    with op.open(req, timeout=60) as r:
        for line in r:
            line = line.decode('utf8', 'ignore').strip()
            if not line.startswith('data:') or line.endswith('[DONE]'): continue
            try: c = json.loads(line[5:])['choices'][0]['delta'].get('content') or ''
            except Exception: continue
            out += c; feed(c)
    feed('\n')
    return out


def write_episode(sess, user_msg, on_line, sysm=None, fast_model=None):
    """逐行流式；on_line(key, value) 每写完一行回调一次。返回全文。sysm 不给就用剧集编剧的系统提示词（通话传自己的）。
    fast_model：先用这个 OpenRouter 快模型（通话第 2 轮起用，第一句约 3 秒），失败再走 Claude Code。"""
    sysm = sysm or system_prompt(sess)
    buf = {'b': ''}

    def feed(chunk):
        buf['b'] += chunk
        while '\n' in buf['b']:
            ln, buf['b'] = buf['b'].split('\n', 1)
            m = KEYS_RE.match(ln)
            if m: on_line(m.group(1).strip(), m.group(2).strip())
    if fast_model:
        try:
            rz = {'effort': 'low'} if 'glm' in fast_model else {'enabled': False}  # GLM 不允许关推理（400），用 low
            txt = openrouter_stream(fast_model, sysm, user_msg, feed, max_tokens=1400, temperature=0.8, extra={'reasoning': rz})
            sess['writer'] = fast_model
            return txt
        except Exception:
            traceback.print_exc(); buf['b'] = ''
            if sess.get('_got_lines'): raise
    if CC and os.environ.get('DIRECTOR_CLI'):
        try:
            txt = CC.stream_text(sysm, user_msg, feed, timeout=120, effort='low')
            if buf['b']: feed('\n')
            sess['writer'] = 'claude-code'
            return txt
        except Exception:
            traceback.print_exc()
            buf['b'] = ''
            if sess.get('_got_lines'): raise
    # 兜底：OpenRouter 流式
    body = {'model': FALLBACK, 'max_tokens': 1400, 'temperature': 0.85, 'stream': True,
            'messages': [{'role': 'system', 'content': sysm}, {'role': 'user', 'content': user_msg}]}
    req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                    headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
    out = ''
    with U.urlopen(req, timeout=60) as r:
        for line in r:
            line = line.decode('utf8', 'ignore').strip()
            if not line.startswith('data:') or line.endswith('[DONE]'): continue
            try: c = json.loads(line[5:])['choices'][0]['delta'].get('content') or ''
            except Exception: continue
            out += c; feed(c)
    feed('\n'); sess['writer'] = FALLBACK
    return out


EP_FAST = os.environ.get('EP_FAST_MODEL', 'z-ai/glm-5.3-prime')
SPEC_LINES = 4  # 预先生成先配几句：2 句点选项后第 3 句要等 ~13 秒，4 句（约 15–20 秒音频）能盖住其余句子的配音时间  # 她自由输入时写下一集：11-06 实测第一句 2.8 秒（本机 Opus 8–13 秒）


def next_msg(sess, her):
    """按“她对上一集的回应”拼下一集的写作请求（不改 sess：预先生成时她还没选）"""
    eps = sess['eps'][:-1] + [dict(sess['eps'][-1], her=her)]
    n = len(eps) + 1; lang = sess['lang']
    pace = ''
    if n >= MAX_EPS - 2: pace = '\n（快到这条线的结局了：接下来 1–2 集内收束主要悬念。）' if lang == 'zh' else '\n(Approaching the end of this route: resolve the main thread within 1–2 episodes.)'
    if n >= MAX_EPS: pace = '\n（这是最后一集：给一个有余味的结局，END: yes。）' if lang == 'zh' else '\n(This is the final episode: give a resonant ending, END: yes.)'
    so_far = story_so_far(dict(sess, eps=eps))
    return (f'到目前为止：\n{so_far}\n\n现在写第 {n} 集。{pace}' if lang == 'zh' else f'Story so far:\n{so_far}\n\nNow write episode {n}.{pace}')


def run_episode(job, sess, user_msg, spec=None, her=None):
    """写一集并逐句配音。spec={'base': 集数}：预先生成（她还没选）——Opus 慢慢写，只先配前两句，不记进剧情；她点了这个选项（commit_ep_spec）才配完其余句、记进剧情。
    不是预先生成（她自由输入）时用快模型 EP_FAST 写，第一句约 3 秒。"""
    t0 = time.time(); n = len(sess['eps']) + 1; lang = sess['lang']; series = sess['series']
    job['_her'] = her; job['_n'] = n; job['_started'] = set(); job['_raw'] = {}
    cast = set(k for k in VOICES[series] if not k.startswith('_'))
    ep = {'n': n, 'title': '', 'kind': 'live', 'lines': [], 'prompt': '', 'choices': [], 'ending': False}
    job['ep'] = ep; job['t'] = {}; ths = []
    mq = {'pending': [], 'done': False}; mev = threading.Event()

    def mapper():
        while True:
            mev.wait(2); mev.clear()
            time.sleep(0.35)  # 攒一小批再配（第一句单独先配，开播那句尽快有画面）
            batch, mq['pending'] = mq['pending'], []
            if batch:
                ctx = '\n'.join(f"{l['who']}: {l['text']}" for l in ep['lines'][max(0, batch[0][0] - 3):batch[0][0]])
                try:
                    for i, c in map_clips(series, ctx, batch).items():
                        if i < len(ep['lines']) and not ep['lines'][i].get('clip'): ep['lines'][i]['clip'] = c
                    job['t'].setdefault('clip0', round(time.time() - t0, 2))
                except Exception:
                    traceback.print_exc()
            elif mq['done']: return
    if VIS.get(series): mth = threading.Thread(target=mapper, daemon=True); mth.start()
    else: mth = None

    def synth(i, who, text):
        first = i == 0
        try:
            u = tts_hedged(series, who, text, lang, (2 if spec else 3) if first else (2 if (i == 1 and not spec) or (spec and i == SPEC_LINES) else 1))
            ep['lines'][i]['url'] = u
        except Exception:
            ep['lines'][i]['url'] = ''
        job['t'][f'l{i}'] = round(time.time() - t0, 2)
    job['_synth'] = synth; job['_ths'] = ths; job['_mq'] = (mq, mev); job['_mth'] = None

    def on_line(k, v):
        if k == 'TITLE': ep['title'] = v; return
        if k == 'PROMPT': ep['prompt'] = v; return
        if k in ('C1', 'C2'): ep['choices'].append(v); return
        if k == 'END': ep['ending'] = v.lower().startswith('y'); return
        who = 'NARR' if k.upper() == 'NARR' else (k if k in cast else None)
        if not who or not v: return
        m = re.search(r'\s*\{([A-Za-z0-9_]+)\}\s*$', v); clip = None
        if m:
            v = v[:m.start()].strip(); clip = m.group(1) if VIS.get(series) and m.group(1) in {c['id'] for c in VIS[series]['clips']} else None
        if len(ep['lines']) >= 16: return
        i = len(ep['lines']); ep['lines'].append({'who': who, 'text': re.sub(r'\[[^\]]*\]\s*', '', v), 'url': None, 'clip': clip})
        job['status'] = 'voicing'; job['_got_lines'] = True
        job['t'].setdefault('first_line', round(time.time() - t0, 2))
        job['_raw'][i] = (who, v)
        if not spec or i < SPEC_LINES or job.get('_committed'):  # 预先生成只先配前几句（够她听到其余句子配好）
            job['_started'].add(i)
            th = threading.Thread(target=synth, args=(i, who, v), daemon=True); th.start(); ths.append(th)
        if not clip: mq['pending'].append((i, who, ep['lines'][i]['text'])); mev.set()
    job['_mth'] = mth
    try:
        wctx = {'_got_lines': False}
        write_episode(wctx, user_msg, lambda k, v: (on_line(k, v), wctx.__setitem__('_got_lines', True)), sysm=system_prompt(sess), fast_model=None if spec else EP_FAST)
        job['writer'] = wctx.get('writer')
        job['t']['writer'] = round(time.time() - t0, 2)
        mq['done'] = True; mev.set()
        if len(ep['lines']) < 3: raise RuntimeError('writer returned too few lines')
        if not ep['choices']: ep['choices'] = ['……', '……'] if lang == 'zh' else ['…', '…']
        if not ep['title']: ep['title'] = (f'第 {n} 集' if lang == 'zh' else f'Episode {n}')
        if n >= MAX_EPS: ep['ending'] = True
        if spec:
            with sess.setdefault('_lock', threading.Lock()):
                if not job.get('_committed'):
                    [x.join(timeout=150) for x in ths]; job['status'] = 'ready'; return  # 等她选
        finish_episode(job, sess)
    except Exception as e:
        mq['done'] = True; mev.set()  # 别让配画面线程空转
        job['status'] = 'error'; job['error'] = str(e)[:300]
        log(sess['sid'], {'ep': n, 'error': traceback.format_exc()[-800:]})


def finish_episode(job, sess):
    """配完还没配的句子，记进剧情，然后按这一集的两个选项预先生成下一集"""
    ep = job['ep']; ths = list(job['_ths'])
    for i, (who, raw) in sorted(job['_raw'].items()):
        if i not in job['_started']:
            job['_started'].add(i); th = threading.Thread(target=job['_synth'], args=(i, who, raw), daemon=True); th.start(); ths.append(th)
    job['status'] = 'voicing'
    [x.join(timeout=150) for x in ths]
    if job.get('_mth'): job['_mth'].join(timeout=20)
    for l in ep['lines']:
        if l['url'] is None: l['url'] = ''
    if job.get('_her') is not None: sess['eps'][-1]['her'] = job['_her']
    sess['eps'].append({'n': ep['n'], 'title': ep['title'], 'lines': [{'who': l['who'], 'text': l['text']} for l in ep['lines']], 'prompt': ep['prompt'], 'choices': ep['choices']})
    job['status'] = 'done'
    log(sess['sid'], {'ep': ep['n'], 'writer': job.get('writer'), 'spec': bool(job.get('_committed')), 't': job['t'], 'ep_out': {k: v for k, v in ep.items() if k != 'lines'}, 'lines': [{k: l.get(k) for k in ('who', 'text', 'url', 'clip')} for l in ep['lines']], 'at': time.strftime('%F %T')})
    if not ep.get('ending'): start_ep_specs(sess)


def start_ep_specs(sess):
    """她听这一集的时候（1–3 分钟），按两个选项先把下一集写好、前两句配好音；她点选项就直接开播"""
    last = sess['eps'][-1]; sess['spec'] = {}
    if len(sess['eps']) >= MAX_EPS: return
    for ch in (last.get('choices') or [])[:2]:
        jid = rid(); JOBS[jid] = {'id': jid, 'status': 'writing', 'error': None}
        her = her_said(ch, 'option', sess['lang'])
        sess['spec'][ch] = {'job': jid, 'base': len(sess['eps'])}
        threading.Thread(target=run_episode, args=(JOBS[jid], sess, next_msg(sess, her), {'base': len(sess['eps'])}, her), daemon=True).start()


def commit_ep_spec(sess, text):
    sp = (sess.get('spec') or {}).get(text); sess['spec'] = {}
    if not sp or sp['base'] != len(sess['eps']): return None
    job = JOBS.get(sp['job'])
    if not job or job['status'] == 'error': return None
    with sess.setdefault('_lock', threading.Lock()):
        job['_committed'] = True; ready = job['status'] == 'ready'
    if ready: threading.Thread(target=finish_episode, args=(job, sess), daemon=True).start()
    return sp['job']


# ---------------- 和主角语音通话（参考之前的 Magnus 午夜来电）----------------
CALLS = {}
MAX_CALL_TURNS = 12
FILLERS = {'zh': ['嗯。', '嗯，我在听。', '我在。', '嗯，我知道。'], 'en': ['Mm.', "I'm listening.", "I'm here.", 'Yeah. I know.']}
THINKS = {'zh': ['让我想想。', '你这么问……', '嗯……我在想怎么跟你说。', '……这个问题。'], 'en': ['Let me think.', 'You asking me that…', "Mm… I'm figuring out how to say this.", '…That question.']}


def callers(sid):
    """能打电话的主角（voices.json 里 lead=true 的角色；三真四假有 Wes 和 Jasper 两个）"""
    w = WORLD[sid]; out = []
    for key, v in VOICES[sid].items():
        if key.startswith('_') or not v.get('lead'): continue
        ch = next((c for c in w['characters'] if c['name'].split()[0] == key or c['name'] == key), {})
        out.append({'key': key, 'name': key, 'name_zh': ch.get('name_zh') or key, 'role_zh': ch.get('role_zh', ''), 'role_en': ch.get('role_en', '')})
    return out


def call_fillers(series, who, lang):
    """垫场声：她说完立刻播一句“嗯，我在听”，盖住他“想”的那几秒（11-05 她说这几句的音色最好）。第一次用时合成，之后缓存。"""
    f = CACHE / 'fillers' / f'{series}.{who}.{lang}.json'
    if f.exists():
        d = json.load(open(f))
        if isinstance(d, dict): return d
        d = {'urls': d}  # 旧缓存只有垫场声，补上思考声
    else: d = None
    f.parent.mkdir(parents=True, exist_ok=True)
    import concurrent.futures as cf
    say = lambda t: tts(series, who, ('[quietly] ' + t) if lang == 'en' else t, lang)
    with cf.ThreadPoolExecutor(4) as ex:
        urls = d['urls'] if d else list(ex.map(say, FILLERS[lang]))
        think = list(ex.map(say, THINKS[lang]))
    d = {'urls': urls, 'think': think}
    json.dump(d, open(f, 'w')); return d


CALL_RULES = {
 'zh': """这是一通电话，纯语音。你只演 {who}（{role}），对面是她（听众本人），她叫「{name}」。
- 只写 {who} 对着电话说的话，口语、短句，像真人深夜打电话；不要旁白、不要动作描写、不要括号。
- 每轮 1–3 句，每句 8–40 个字；第一句先接住她刚说的话（她沉默就回应沉默）。
- 严格按人设和说话方式说话；只说他这时候知道的事，世界卡里的真相按节奏透露，不一次说破。
- 记得你们在剧里经历过的事（见“剧里到目前为止”），可以提起具体细节；她有明确想聊的方向就跟着她。
- 每轮往前推一点：问她一个问题、提出一个约定、说出一点心里话或一个小秘密。偶尔叫她的名字，不要每句都叫。
- 一律中文（人名保留英文），不要“亲爱的/宝贝”。可以在句首少量用 [softly] [quietly] [sighs] [chuckles softly] [exhales]，每轮最多 1 个。
- 通话到第 10 轮左右自然收尾，给一个让她想再打来的钩子，HANGUP: yes。""",
 'en': """This is a phone call, voice only. You play only {who} ({role}); on the other end is her (the listener), named "{name}".
- Write only what {who} says into the phone: short, natural late-night phone talk; no narration, no actions, no brackets.
- 1–3 lines per turn, each under 25 words; the first line answers what she just said (if she is silent, respond to the silence).
- Stay strictly in character; only say what he knows now; reveal the world-card truths gradually, never all at once.
- Remember what you've been through in the story (see "story so far") and bring up specifics; if she steers, follow her.
- Each turn moves things a little: ask her something, make a promise, admit a feeling or a small secret. Use her name now and then, not every line.
- No "baby/darling". Sparse tags at line start allowed: [softly] [quietly] [sighs] [chuckles softly] [exhales], at most one per turn.
- Around turn 10, wrap up naturally with a hook that makes her want to call again, HANGUP: yes."""}
CALL_FORMAT = """OUTPUT FORMAT — plain lines only, nothing else:
LINE: <what he says>
LINE: <optional second line>
LINE: <optional third line>
C1: <a short reply she might say, first person>
C2: <a different short reply>
HANGUP: no"""


CALL_FAST = os.environ.get('CALL_FAST_MODEL', 'deepseek/deepseek-v4.1-flash')  # 11-06 实测第一句 2.7 秒（本机 Opus 19–22 秒）


def call_system(c, lite=False):
    s, lang, w = c['series'], c['lang'], WORLD[c['series']]
    ch = next((x for x in w['characters'] if x['name'].split()[0] == c['who'] or x['name'] == c['who']), w['characters'][0])
    if lite: w = {k: w[k] for k in ('premise_zh', 'premise_en', 'her', 'truths', 'tone', 'rules') if k in w}  # 快模型用精简版，提示词短一半
    role = ch.get('role_zh' if lang == 'zh' else 'role_en') or ch.get('role_zh', '')
    head = (f'你是女性向互动音频剧的角色演员，现在在电话里演 {c["who"]}。' if lang == 'zh' else f'You are voicing {c["who"]} live on a phone call in a women-focused interactive audio drama.')
    return '\n\n'.join([head, '世界卡（内部资料）：\n' + json.dumps(w, ensure_ascii=False),
                        '这个角色：\n' + json.dumps(ch, ensure_ascii=False),
                        CALL_RULES[lang].format(who=c['who'], role=role, name=c['name']), CALL_FORMAT])


def call_context(c):
    sess = SESS.get(c.get('sid') or '')
    story = story_so_far(sess) if sess else ('（她还没听这部剧，就当你们刚认识不久，按第 1 集的处境打电话）' if c['lang'] == 'zh' else "(She hasn't started the series; call as if you've only just met, in Episode 1's situation.)")
    turns = '\n'.join((f'她：{t["her"]}\n{c["who"]}：' + ' / '.join(t['lines'])) for t in c['turns'])
    return story, turns


def run_call(job, c, her, spec=None):
    """一轮通话。spec={'base': 轮数}：预先生成（她还没选）——只合成第一句，不记进通话；她点了这条快捷回复（commit_spec）才补合成其余句并记进通话。"""
    t0 = time.time(); lang = c['lang']; n = len(c['turns']) + 1
    out = {'lines': [], 'choices': [], 'hangup': False}; job['call'] = out; job['t'] = {}; ths = []; raws = []
    job['_raws'] = raws; job['_her'] = her; job['_n'] = n; job['_ths'] = ths; job['_started'] = set()

    def synth(i, text):
        try: out['lines'][i]['url'] = tts_hedged(c['series'], c['who'], text, lang, (2 if spec else 3) if i == 0 else 1)
        except Exception: out['lines'][i]['url'] = ''
        job['t'][f'l{i}'] = round(time.time() - t0, 2)
    job['_synth'] = synth

    def on_line(k, v):
        if k == 'LINE' and v and len(out['lines']) < 4:
            i = len(out['lines']); out['lines'].append({'who': c['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', v), 'url': None}); raws.append(v)
            job['status'] = 'voicing'; job['t'].setdefault('first_line', round(time.time() - t0, 2))
            if spec and i > 0 and not job.get('_committed'): return  # 预先生成只配第一句，其余等她真选了再配
            job['_started'].add(i)
            th = threading.Thread(target=synth, args=(i, v), daemon=True); th.start(); ths.append(th)
        elif k in ('C1', 'C2') and v: out['choices'].append(v)
        elif k == 'HANGUP': out['hangup'] = v.lower().startswith('y')
    story, turns = call_context(c)
    if c['direction'] == 'incoming' and n == 1:
        ask = '他主动打给她。电话刚接通，他先开口。' if lang == 'zh' else 'He is calling her. The call just connected; he speaks first.'
    elif n == 1:
        ask = '她主动打给他。他接起电话，先开口。' if lang == 'zh' else 'She is calling him. He picks up and speaks first.'
    else:
        ask = her
    pace = ''
    if n >= MAX_CALL_TURNS - 2: pace = '（该收尾了，1–2 轮内挂断。）' if lang == 'zh' else '(Time to wrap up within 1–2 turns.)'
    if n >= MAX_CALL_TURNS: pace = '（这是最后一轮，说再见，HANGUP: yes。）' if lang == 'zh' else '(Last turn: say goodbye, HANGUP: yes.)'
    msg = (f'剧里到目前为止：\n{story}\n\n这通电话到目前为止：\n{turns or "（刚接通）"}\n\n第 {n} 轮。{ask}{pace}' if lang == 'zh' else
           f'Story so far:\n{story}\n\nThis call so far:\n{turns or "(just connected)"}\n\nTurn {n}. {ask}{pace}')
    try:
        c['_got_lines'] = False
        fast = CALL_FAST if n > 1 else None  # 第 1 轮响铃时间够长，用 Opus 写开场；之后每轮用快模型
        write_episode(c, msg, on_line, sysm=call_system(c, lite=bool(fast)), fast_model=fast)
        job['t']['writer'] = round(time.time() - t0, 2); job['writer'] = c.get('writer')
        if not out['lines']: raise RuntimeError('writer returned no lines')
        if n >= MAX_CALL_TURNS: out['hangup'] = True
        if not out['choices']: out['choices'] = ['嗯。', '你继续说。'] if lang == 'zh' else ['Mm.', 'Keep talking.']
        job['_written'] = True
        if spec:
            with c.setdefault('_lock', threading.Lock()):
                if not job.get('_committed'):
                    [x.join(timeout=150) for x in ths]; job['status'] = 'ready'; return  # 等她选
            finish_spec(job, c)  # 写的过程中她已经选了这条
            return
        finish_turn(job, c, ths)
    except Exception as e:
        job['status'] = 'error'; job['error'] = str(e)[:300]
        log('call-' + c['cid'], {'turn': n, 'error': traceback.format_exc()[-800:]})


def finish_turn(job, c, ths):
    out = job['call']
    [x.join(timeout=150) for x in ths]
    for l in out['lines']:
        if l['url'] is None: l['url'] = ''
    n = job['_n']; her = job['_her']
    c['turns'].append({'her': her if n > 1 else '（接通）', 'lines': [l['text'] for l in out['lines']]})
    job['status'] = 'done'
    log('call-' + c['cid'], {'turn': n, 'her': her, 'writer': job.get('writer'), 'spec': bool(job.get('_committed')), 't': job['t'], 'out': out, 'at': time.strftime('%F %T')})
    if not out['hangup'] and c['cid'] in CALLS: start_specs(c, out['choices'])


def finish_spec(job, c):
    """她点了预先生成的这条：补合成第一句以外的句子，记进通话"""
    out = job['call']; ths = list(job['_ths'])
    for i, raw in enumerate(job['_raws']):
        if i not in job['_started']:
            job['_started'].add(i)
            th = threading.Thread(target=job['_synth'], args=(i, raw), daemon=True); th.start(); ths.append(th)
    job['status'] = 'voicing'
    finish_turn(job, c, ths)


def start_specs(c, choices):
    """他这轮说完、她还在听/读的时候，按两个快捷回复先把他下一轮写好、第一句配好音"""
    c['spec'] = {}
    for ch in choices[:2] + ['__silence__']:  # 两个快捷回复 + 沉默，都是能猜到的回应
        jid = rid(); JOBS[jid] = {'id': jid, 'status': 'writing', 'error': None, '_spec': True}
        c['spec'][ch] = {'job': jid, 'base': len(c['turns'])}
        her = her_said('', 'silence', c['lang']) if ch == '__silence__' else her_said(ch, 'option', c['lang'])
        threading.Thread(target=run_call, args=(JOBS[jid], c, her, {'base': len(c['turns'])}), daemon=True).start()


def commit_spec(c, text):
    """她点的快捷回复有预先生成的结果就直接用，返回 job id；没有返回 None"""
    sp = (c.get('spec') or {}).get(text); c['spec'] = {}
    if not sp or sp['base'] != len(c['turns']): return None
    job = JOBS.get(sp['job'])
    if not job or job['status'] == 'error': return None
    with c.setdefault('_lock', threading.Lock()):
        job['_committed'] = True; ready = job['status'] == 'ready'
    if ready: threading.Thread(target=finish_spec, args=(job, c), daemon=True).start()
    return sp['job']


def start_job(fn, *a):
    jid = rid(); JOBS[jid] = {'id': jid, 'status': 'writing', 'error': None}
    threading.Thread(target=fn, args=(JOBS[jid], *a), daemon=True).start()
    return jid


def ep1_job(job, series, lang):
    try:
        job['status'] = 'voicing'; job['ep'] = ep1_with_visuals(produce_ep1(series, lang, job), series, lang); job['status'] = 'done'
    except Exception as e:
        job['status'] = 'error'; job['error'] = str(e)[:300]; traceback.print_exc()


# ---------------- 接口 ----------------
def series_card(sid, lang):
    b, w = BASE[sid], WORLD[sid]; c = ep1_cached(sid, lang)
    pl, ra = STATS.get(sid, ('100K', 4.7))
    return {'id': sid, 'title': b['title'][lang], 'lead': (b.get('lead') or {}).get(lang, ''), 'hook': b['hook'][lang],
            'tags': [t[lang] for t in b.get('tags', [])], 'genres': b['genres'], 'accent': b['accent'], 'cover': b['cover'], 'avatar': b['avatar'], 'motion': MOTION.get(sid), 'visuals': vis_card(sid),
            'callers': [{'key': x['key'], 'name': x['name'] if lang == 'en' else x['name_zh'], 'role': x['role_en'] if lang == 'en' else x['role_zh']} for x in callers(sid)],
            'stats': {'plays': pl, 'rating': ra}, 'ep1': {'title': w[f'ep1_title_{lang}'], 'dur': c['dur'] if c else None, 'ready': bool(c)}}


def series_detail(sid, lang):
    d = series_card(sid, lang); w = WORLD[sid]
    d['synopsis'] = w.get(f'synopsis_{lang}') or w.get(f'premise_{lang}')
    cast = []
    for ch in w['characters']:
        v = VOICES[sid].get(ch['name'].split()[0]) or VOICES[sid].get(ch['name'])
        if not v: continue
        cast.append({'name': ch['name'] if lang == 'en' else (ch.get('name_zh') or ch['name']), 'role': ch.get(f'role_{lang}') or ch.get('role_zh', ''),
                     'voice': v.get('zh_name') if lang == 'zh' else v.get('en')})
    cast.append({'name': 'Narrator' if lang == 'en' else '旁白', 'role': 'Narrator' if lang == 'en' else '旁白', 'voice': VOICES['NARR']['zh_name'] if lang == 'zh' else VOICES['NARR']['en']})
    d['cast'] = cast
    return d


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a): pass

    def _send(self, code, body, ctype='application/json', cache='no-store'):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', cache); self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST'); self.send_header('Content-Length', '0'); self.end_headers()

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); g = lambda k, d='': q.get(k, [d])[0]
        lang = 'zh' if g('lang') == 'zh' else 'en'
        if u.path == '/health': return self._send(200, {'ok': True, 'sessions': len(SESS)})
        if u.path.startswith('/api/'):
            if g('k') != TOKEN: return self._send(403, {'error': 'bad key'})
            if u.path == '/api/series': return self._send(200, [series_card(s, lang) for s in BASE])
            if u.path.startswith('/api/series/'):
                sid = u.path.split('/')[-1]
                return self._send(200, series_detail(sid, lang)) if sid in BASE else self._send(404, {'error': 'no series'})
            if u.path == '/api/call/fillers':
                sid, who = g('series'), g('who')
                if sid not in BASE or who not in VOICES[sid]: return self._send(404, {'error': 'no caller'})
                try: return self._send(200, call_fillers(sid, who, lang))
                except Exception as e: return self._send(500, {'error': str(e)[:200]})
            if u.path == '/api/specs':  # 她还在听这一集时，前端先取两个选项预先写好的下一集（前两句已配音），点选项就本地直接播，省掉公网往返
                sess = SESS.get(g('sid') or '')
                out = {}
                for ch, sp in ((sess or {}).get('spec') or {}).items():
                    j = JOBS.get(sp['job'])
                    if not j or sp['base'] != len(sess['eps']) or j.get('status') == 'error' or not j.get('ep'): continue
                    L = j['ep']['lines']
                    if not (L and L[0].get('url')): continue
                    out[ch] = {'job': sp['job'], 'n': j['ep']['n'], 'ep': dict(j['ep'], lines=[dict(x) for x in L])}
                return self._send(200, {'n': len(sess['eps']) + 1 if sess else 0, 'specs': out})
            if u.path == '/api/job':
                j = JOBS.get(g('id'))
                if j and j.get('status') == 'ready': j = dict(j, status='voicing')  # 预先生成好了但还没被选：对外当作还在合成
                return self._send(200 if j else 404, {k: v for k, v in j.items() if not k.startswith('_')} if j else {'error': 'no job'})
            return self._send(404, {'error': 'not found'})
        p = u.path if u.path != '/' else '/index.html'
        f = (APP / p.lstrip('/')).resolve()
        if APP.resolve() in f.parents and f.is_file():
            ct = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.jpg': 'image/jpeg',
                  '.png': 'image/png', '.svg': 'image/svg+xml', '.mp3': 'audio/mpeg', '.json': 'application/json', '.webp': 'image/webp'}.get(f.suffix, 'application/octet-stream')
            return self._send(200, f.read_bytes(), ct, 'no-cache' if f.suffix in ('.html', '.js', '.css') else 'public, max-age=86400')
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        u = urlparse(self.path)
        try: body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        except Exception: return self._send(400, {'error': 'bad json'})
        if body.get('k') != TOKEN: return self._send(403, {'error': 'bad key'})
        lang = 'zh' if body.get('lang') == 'zh' else 'en'
        if u.path == '/api/play':
            series = body.get('series')
            if series not in BASE: return self._send(404, {'error': 'no series'})
            name = (body.get('name') or ('你' if lang == 'zh' else 'you')).strip()[:24]
            sid = time.strftime('%m%d%H%M') + rid(4)
            sc = ep1_script(series, lang)
            sess = SESS[sid] = {'sid': sid, 'series': series, 'lang': lang, 'name': name,
                                'eps': [{'n': 1, 'title': sc['title'], 'lines': [{'who': l['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', l['text'])} for l in sc['lines']], 'prompt': sc['prompt'], 'choices': sc['choices']}]}
            log(sid, {'start': True, 'series': series, 'lang': lang, 'name': name, 'at': time.strftime('%F %T')})
            c = ep1_cached(series, lang)
            if not body.get('prewarm'): threading.Thread(target=start_ep_specs, args=(sess,), daemon=True).start()  # 她听第 1 集的 3 分钟里，第 2 集已经按两个选项写好（批量预热第 1 集时不做）
            return self._send(200, {'sid': sid, 'ep': ep1_with_visuals(c, series, lang)} if c else {'sid': sid, 'job': start_job(ep1_job, series, lang)})
        if u.path == '/api/call/start':
            series = body.get('series')
            if series not in BASE: return self._send(404, {'error': 'no series'})
            cs = callers(series); who = body.get('who') if body.get('who') in [x['key'] for x in cs] else cs[0]['key']
            name = (body.get('name') or ('你' if lang == 'zh' else 'you')).strip()[:24]
            sess = SESS.get(body.get('sid') or '')
            cid = 'c' + time.strftime('%m%d%H%M') + rid(4)
            c = CALLS[cid] = {'cid': cid, 'series': series, 'lang': lang, 'name': name, 'who': who, 'sid': sess['sid'] if sess and sess['series'] == series else None,
                              'direction': 'incoming' if body.get('direction') == 'incoming' else 'outgoing', 'turns': []}
            log('call-' + cid, {'start': True, 'series': series, 'who': who, 'lang': lang, 'name': name, 'sid': c['sid'], 'direction': c['direction'], 'at': time.strftime('%F %T')})
            return self._send(200, {'cid': cid, 'who': who, 'job': start_job(run_call, c, '')})
        if u.path == '/api/call/turn':
            c = CALLS.get(body.get('cid'))
            if not c: return self._send(404, {'error': 'call ended'})
            text = (body.get('text') or '').strip()[:400]; via = body.get('via') or 'free'
            jid = commit_spec(c, text) if via == 'option' else (commit_spec(c, '__silence__') if via == 'silence' or not text else None)
            if not jid: c['spec'] = {}
            return self._send(200, {'job': jid or start_job(run_call, c, her_said(text, via, c['lang']))})
        if u.path == '/api/call/end':
            c = CALLS.pop(body.get('cid'), None)
            if c: log('call-' + c['cid'], {'end': True, 'seconds': body.get('seconds'), 'turns': len(c['turns']), 'at': time.strftime('%F %T')})
            return self._send(200, {'ok': True})
        if u.path == '/api/next':
            sess = SESS.get(body.get('sid'))
            if not sess: return self._send(404, {'error': 'session expired'})
            text = (body.get('text') or '').strip()[:400]; via = body.get('via') or 'free'
            her = her_said(text, via, sess['lang']); n = len(sess['eps']) + 1
            jid = commit_ep_spec(sess, text) if via == 'option' else None
            if not jid: sess['spec'] = {}
            log(sess['sid'], {'her': text, 'via': via, 'next': n, 'spec': bool(jid), 'at': time.strftime('%F %T')})
            return self._send(200, {'job': jid or start_job(run_episode, sess, next_msg(sess, her), None, her)})
        self._send(404, {'error': 'not found'})


if __name__ == '__main__':
    print(f'unscripted audio on {PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
