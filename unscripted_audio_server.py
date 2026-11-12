"""Unscripted Audio 中转：Pocket FM 式音频连载 App 的后端（接口见 CONTRACT.md）。
- 第 1 集：data/ep1/<id>.<lang>.json 的剧本，第一次有人播时逐句合成（ElevenLabs v4，按 data/voices.json 配音）、
  拼成一条 mp3 + 环境声 + 逐句字幕，传到 Waku 存储（CDN 比隧道快得多），缓存到 cache/ep1/。
- 第 2 集起：她选了什么 → 编剧层按世界卡（data/world/<id>.json）写下一集，逐行流式输出，每写完一句就送去合成。
  编剧：DIRECTOR_CLI 设了就用本机 Claude Code（Opus 5.5），失败退回 OpenRouter（WRITER_FALLBACK，默认 GLM-5.3-prime）。
用法：python3 unscripted_audio_server.py <token> <port>（名字故意起得独一无二：别的会话会按 server.py 之类的通用名批量杀进程）"""
import hashlib, json, os, queue, shutil, random, re, string, subprocess, sys, threading, time, traceback, base64
import urllib.request as U
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from wakumcp import WakuMCP
import audio_level as AL
import sfx_lib as SFX

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
    return {'clips': {c['id']: c['src'] for c in v['clips']}, 'pool': v['pool'], 'prefer': v.get('prefer')} if v else None


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
# 配音引擎（11-08 测试开关，链接带 &tts=）：v4 默认；turbo = Eleven v4 Turbo（低延迟版，同一批声线，中文测试用）；flash = Eleven Turbo v2.5（实时向）。
# 11-08 同一句中文经 MCP 各测 3 次：v4 7.3–9.0 秒、v4-turbo 6.0–8.5、turbo-v2.5 4.8–8.1（Waku 批量任务本身约 4–5 秒，模型差别被盖住）
TTS_ENGINES = {'v4': 'elevenlabs/eleven-v4', 'turbo': 'elevenlabs/eleven-v4-turbo', 'flash': 'elevenlabs/turbo-v2.5'}
def tts_engine(x): return x if x in TTS_ENGINES else 'v4'
FALLBACK = os.environ.get('WRITER_FALLBACK', 'z-ai/glm-5.3-prime')
MAX_EPS = 12

POOL = queue.Queue()
def _mcp():
    for k in range(6):  # 11-09：shim 偶尔初始化失败，原来一失败中转就起不来（launchd 反复重启）
        try: return WakuMCP()
        except Exception as e: print('waku mcp init', k, repr(e)[:100], flush=True); time.sleep(2 + 2 * k)
    return WakuMCP()
def _fill_pool(n):
    for _ in range(n):
        try: POOL.put(_mcp())
        except Exception as e: print('pool', repr(e)[:100], flush=True)
# 11-11 配音通道放到后台建（3 路并行，共 10 条）：原来 10 条串行建完才开始接请求，网络慢的时候重启一次线上要断几分钟；
# 现在重启后页面、剧目列表、第 1 集文字稿马上能用，要配音的请求等第一条通道建好（POOL.get 会等）
for _n in (4, 3, 3): threading.Thread(target=_fill_pool, args=(_n,), daemon=True).start()
CALL_HEDGE = [int(x) for x in os.environ.get('CALL_HEDGE', '3,2').split(',')]  # 11-10 Waku 每句 3–6 秒波动大：第 1 句三路、第 2 句两路取最快  # 正文第 1、2 句各发几路
CALL_POOL = queue.Queue()  # 11-09 通话专用配音通道：剧集在后台整集配音时，通话不跟它排队（原来排到 20 秒）
CALL_POOL_N = [0]
def _fill_call_pool(n):
    for _ in range(n):
        for k in range(3):  # waku mcp shim 偶尔初始化失败（机器上 shim 太多时），重试
            try: CALL_POOL.put(WakuMCP()); CALL_POOL_N[0] += 1; break
            except Exception as e: print('call pool', repr(e)[:100], flush=True); time.sleep(3)
threading.Thread(target=_fill_call_pool, args=(int(os.environ.get('CALL_POOL', '8')),), daemon=True).start()  # 后台建，不拖慢重启；11-09 实测 14 条 + 三路并发并不更快（Waku 端排队）
SESS, JOBS, EP1_LOCK = {}, {}, {}
CALL_KEYS = {}
op = U.build_opener(U.ProxyHandler({}))


def rid(n=10): return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def log(sid, rec):
    with open(LOGS / 'sessions' / f'{sid}.jsonl', 'a') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')


LINE_CACHE = ROOT / 'cache' / 'lines'
LINE_CACHE.mkdir(parents=True, exist_ok=True)
GCS_PREFIX = 'https://storage.googleapis.com/waku-core-aicap/'


def cache_line(u, timeout=25):
    """每句配音（谷歌存储，不带跨域头、国内首字节 1–2.5 秒）下载到本机，/api/a 带跨域头转给手机：
    手机整集提前取成本地 blob，句与句之间不再等网络。配完音就在后台先下好，手机来取时直接给。"""
    if not u or not u.startswith(GCS_PREFIX): return None
    f = LINE_CACHE / (hashlib.sha1(u.encode()).hexdigest() + '.mp3')
    if f.exists() and f.stat().st_size > 0: return f
    try:
        b = op.open(U.Request(u), timeout=timeout).read()
        if b:
            tmp = f.with_suffix('.part' + rid(4)); tmp.write_bytes(b)
            try: AL.level_file(tmp)   # 11-11 每句拉到同一响度：旁白和各角色、第 1 集和后面几集不再忽大忽小（约 0.15 秒）
            except Exception as e: print('level failed', repr(e)[:80], flush=True)
            tmp.rename(f); return f
    except Exception as e:
        print(time.strftime('%m-%d %H:%M:%S'), 'cache_line failed', u[-40:], repr(e)[:80], flush=True)
    return None


SID_RE = re.compile(r'^[0-9]{8}[a-z0-9]{4}$')
REVIVE_LOCK = threading.Lock()


def get_sess(sid):
    """会话在内存里就直接用；中转重启后内存丢了，就按 logs/sessions/<sid>.jsonl 重建（她手机上还在听的那条线不会“session expired”/一直转圈）。
    已写完的集（含每句配音地址）放进 sess['_full']，/api/ep 用它把丢了任务的那集直接还给前端。"""
    sid = sid or ''
    if sid in SESS: return SESS[sid]
    if not SID_RE.match(sid): return None
    p = LOGS / 'sessions' / f'{sid}.jsonl'
    if not p.exists(): return None
    with REVIVE_LOCK:
        if sid in SESS: return SESS[sid]
        sess, her = None, None
        for line in p.read_text().splitlines():
            try: r = json.loads(line)
            except Exception: continue
            if r.get('start'):
                if r.get('series') not in BASE: return None
                lang = r.get('lang') or 'en'; sc = ep1_script(r['series'], lang)
                sess = {'sid': sid, 'series': r['series'], 'lang': lang, 'name': r.get('name') or '', 'me': r.get('me') or '', 'tts': tts_engine(r.get('tts')), '_full': {},
                        'eps': [{'n': 1, 'title': sc['title'], 'lines': [{'who': l['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', l['text'])} for l in sc['lines']], 'prompt': sc['prompt'], 'choices': sc['choices']}]}
            elif not sess: continue
            elif 'her' in r and 'via' in r:
                via, m = r.get('via'), r.get('matched')
                her = her_said(m, 'option', sess['lang']) if m and via != 'option' else her_said(r.get('her') or '', via, sess['lang'])
            elif r.get('ep') and r.get('lines') and r['ep'] == len(sess['eps']) + 1:
                eo = r.get('ep_out') or {}
                if her is not None: sess['eps'][-1]['her'] = her
                her = None
                sess['eps'].append({'n': r['ep'], 'title': eo.get('title') or '', 'lines': [{'who': l['who'], 'text': l['text']} for l in r['lines']], 'prompt': eo.get('prompt') or '', 'choices': eo.get('choices') or []})
                sess['_full'][r['ep']] = dict(eo, n=r['ep'], kind='live', lines=r['lines'])
                if eo.get('ending'): sess['eps'][-1]['ending'] = True
        if not sess: return None
        SESS[sid] = sess
        print(time.strftime('%m-%d %H:%M:%S'), 'revived session', sid, 'eps', len(sess['eps']), flush=True)
    if not sess['eps'][-1].get('ending'): threading.Thread(target=start_ep_specs, args=(sess,), daemon=True).start()
    return sess


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


def waku(model, params, timeout=120, pool=None):
    if pool is CALL_POOL and not CALL_POOL_N[0]: pool = POOL  # 通话通道还没建好就先用公共的
    pool = pool or POOL
    _w = time.time(); m = pool.get()
    if TTS_DEBUG and time.time() - _w > 0.3: print('waku pool wait', round(time.time() - _w, 2), 'call' if pool is CALL_POOL else 'main', flush=True)
    try:
        return m.tool('multimodal_run_model', {'capability': 'multimodal.generate.audio', 'model_id': model, 'parameters': params}, timeout=timeout)
    except TimeoutError:
        try: m.p.kill()
        except Exception: pass
        m = WakuMCP(); raise
    finally:
        pool.put(m)


_CREDIT_T = [0]
def credit_alarm():
    """配音报余额不足：马上跑一次额度守护（低于线就充 30usd），1 分钟内只跑一次（11-09）"""
    if time.time() - _CREDIT_T[0] < 60: return
    _CREDIT_T[0] = time.time()
    g = Path(__file__).resolve().parents[2] / 'tools' / 'credit-guard' / 'credit_guard.py'
    if g.exists(): subprocess.Popen([sys.executable, str(g), '--now'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


TTS_DEBUG = os.environ.get('TTS_DEBUG', '0') == '1'  # 排查配音慢时设 1
def tts(series, who, text, lang, engine='v4', pool=None):
    vid, lead = voice_of(series, who, lang)
    params = dict(text=tts_text(text, lead, lang), voice_id=vid, stability=0.4, similarity=0.8)
    if engine == 'flash': params = dict(text=re.sub(r'\[[^\]]*\]\s*', '', params['text']), voice_id=vid)  # v2.5 不认表演标签，会念出来
    model = TTS_ENGINES.get(engine, MODEL_TTS)
    err = None
    for attempt in range(3):
        try:
            _t = time.time(); r = waku(model, params, pool=pool)
            if TTS_DEBUG: print(time.strftime('%H:%M:%S'), 'tts', engine, 'call' if pool is CALL_POOL else 'main', who, round(time.time() - _t, 2), 'ok' if r.get('asset_url') else str(r)[:80], text[:12], flush=True)
            if r.get('asset_url'): return r['asset_url']
            err = r.get('error') or r
            if 'insufficient_credit' in str(err): credit_alarm()
        except Exception as e:
            err = e
        if attempt == 1: params['text'] = re.sub(r'\[[^\]]*\]\s*', '', params['text'])  # 标签导致参数错误时去标签再试
    raise RuntimeError(f'tts failed: {str(err)[:200]}')


def tts_hedged(series, who, text, lang, n, engine='v4', pool=None):
    """同一句发 n 条，谁先好用谁"""
    done = threading.Event(); box = {}; errs = []

    def one():
        try:
            u = tts(series, who, text, lang, engine, pool)
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
    """第 1 集成品。音频走 App 同域名（app/ep1/，Pages 的 CDN）：云存储首字节约 3 秒、拖进度条每次都要等，同域名秒开、拖动不卡。"""
    f = CACHE / 'ep1' / f'{series}.{lang}.json'
    if not f.exists(): return None
    ep = json.load(open(f))
    if (APP / 'ep1' / f'{series}.{lang}.mp3').exists(): ep = dict(ep, audio=f'ep1/{series}.{lang}.mp3', audio_cdn=ep.get('audio'))
    return ep


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
        (APP / 'ep1').mkdir(exist_ok=True); shutil.copy(out, APP / 'ep1' / out.name)  # 同域名一份（publish.sh 推到 Pages）
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
- 她可能用中文也可能用英文回答（打字或说话，语音识别可能有错字），都照样理解她的意思；你的输出始终全部用中文。
- 可以在句首少量用音频标签：[softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering]，每 4 句最多 1 个。''',
 'en': '''Writing rules (English serialized audio drama, 60–90 seconds per episode):
- Pure audio; the listener IS the heroine "you". Narrator NARR in second person, present tense, short, close to the ear; sound, smell, touch, distance.
- The heroine is not voiced: the narrator reports what she says, at most a very short quote now and then.
- Characters call her by her name "{name}" (not the name in the source material), once or twice per episode.
- First line answers her choice/what she said at the end of the last episode; then move the story one step (follow story_map, but if she steers, follow her; never invent her identity).
- 9–13 lines per episode, alternate narrator and dialogue, each line under 30 words; one small peak; end on a move the character makes.
- She may answer in English or Chinese (typed or spoken; speech recognition may have typos). Understand her either way; your output is always entirely in English.
- Sparse ElevenLabs tags at line start: [softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering], at most 1 per 4 lines. No "baby/darling".'''}

FORMAT = '''OUTPUT FORMAT — plain lines only, in this order, nothing else:
TITLE: <episode title{t}>
<Speaker>: <line>        (Speaker is NARR or one of: {cast})
... 9–13 lines ...
PROMPT: <one line above the choice: the situation, addressed to "you"/“你”>
C1: <her possible reply/action, first person, short>
C2: <another, clearly different>
END: no            (yes only when this is a true ending of the story)'''


def me_block(me, lang):
    """个性化（11-06 阿炫提的 Manifest 思路）：她在个人页写的“想成为的人 / 想要的生活 / 想被怎样对待”。是心愿不是剧情事实。"""
    me = (me or '').strip()
    if not me: return ''
    if lang == 'zh':
        return ('她写给自己的心愿（想成为的人、想要的生活、想被怎样对待）：\n' + me +
                '\n用法：这是她的向往，不是剧情事实。不违背世界卡的前提下，让故事慢慢回应它——角色怎么看她、她身上的细节、她做到的事、她被怎样对待。'
                '不要生硬复述原话，不要每集都提，自然地把她放进她向往的样子里。')
    return ('What she wrote about herself (who she wants to become, the life she wants, how she wants to be treated):\n' + me +
            '\nUse: these are wishes, not story facts. Without breaking the world card, let the story answer them over time — how characters see her, '
            'details about her, what she achieves, how she is treated. Never quote it back verbatim; not every episode; let her live inside who she wants to be.')


# 11-10 Prota Top10 的 8 部：保持原作性别（女主角色是女性），听众“你”不指定性别（世界卡 pov=neutral）
neutral = lambda sid: (WORLD.get(sid) or {}).get('pov') == 'neutral'
POV_NOTE = {'zh': '听众性别不限：别给“你”加性别——不用“他/她”“先生/小姐”“男孩/女孩”“兄弟/姐妹”这类词指代你，旁人提到你时用名字或“这位新生/新室友”这类说法。下面资料里写的“她”只是指听众，不代表性别。',
            'en': 'The listener\'s gender is unspecified: never gender "you" (no he/she, sir/miss, boy/girl, bro/sis for the listener); others refer to you by name or by role ("the new student", "my roommate"). Where these notes say "she/her" they just mean the listener.'}


def pov_text(t, lang):
    """把为女性听众写的规则改成性别不限的说法"""
    for a, b in (('听众就是女主“你”', '听众就是故事主角“你”（性别不限）'), ('女主不配音：她说的话', '主角（听众）不配音：你说的话'), ('角色叫她时用她的名字', '角色叫你时用你的名字'),
                 ('the listener IS the heroine "you"', 'the listener IS the protagonist "you" (gender unspecified)'), ('The heroine is not voiced: the narrator reports what she says', 'The protagonist is not voiced: the narrator reports what you say'),
                 ('Characters call her by her name', 'Characters call you by your name')):
        t = t.replace(a, b)
    return t + '\n- ' + POV_NOTE[lang]


def system_prompt(sess):
    s, lang, w = sess['series'], sess['lang'], WORLD[sess['series']]
    cast = [k for k in VOICES[s] if not k.startswith('_')]
    nt = neutral(s)
    head = (('你是有声连载剧（Pocket FM 那一类）的编剧，正在为一位听众实时写下一集。' if nt else '你是女性向有声连载剧（Pocket FM 那一类）的编剧，正在为一位听众实时写下一集。') if lang == 'zh' else
            ('You are the writer of a serialized audio drama (Pocket FM style), writing the next episode live for one listener.' if nt else 'You are the writer of a women-focused serialized audio drama (Pocket FM style), writing the next episode live for one listener.'))
    rules = RULES[lang].replace('{name}', sess['name'])
    return '\n\n'.join([head, '世界卡（内部资料，真相按节奏揭晓，不提前剧透）：\n' + json.dumps(w, ensure_ascii=False),
                        pov_text(rules, lang) if nt else rules,
                        me_block(sess.get('me'), lang),
                        FORMAT.replace('{cast}', ', '.join(cast)).replace('{t}', '，6–10 字' if lang == 'zh' else ', 2–5 words')])


MAPPER = os.environ.get('CLIP_MAPPER', 'deepseek/deepseek-v4.1-flash')  # 实测 3 句约 4 秒


def map_clips(series, ctx, items):
    """items=[(i, who, text)] → {i: clip}。编剧不再管画面（省掉画面库那几千字提示词），台词一出来就交给快模型配。"""
    v = VIS.get(series)
    if not v or not items: return {}
    pref = bool(v.get('prefer'))  # 有预设完整版切片（build_preset_visuals.py）：p 开头优先，实时测试片段不再给
    lib = '\n'.join(f"{c['id']}: {c['cap'][:90]}" for c in v['clips'] if not (pref and c['kind'] in ('card', 'open', 'still')))
    prompt = (f'画面库（id：画面内容）：\n{lib}\n\n前情（最近几句）：\n{ctx}\n\n给下面每句台词挑最匹配的画面 id（按动作、地点、人物、情绪；'
              + ('p 开头是预设完整版成片镜头，优先用；只有预设镜头里完全没有对应场景时才用 idle；' if pref else '没有合适的用 s 开头的剧照或 idle；') +
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
    return 'CLIP LIBRARY（画面库：播放器在这句台词播放时显示的静音画面，按画面内容挑' + ('；p 开头是预设完整版镜头，优先用' if v.get('prefer') else '') + '）：\n' + '\n'.join(f"{c['id']}: {c['cap'][:110]}" for c in v['clips'] if not (v.get('prefer') and c['kind'] in ('card', 'open', 'still')))


def story_so_far(sess):
    parts = []
    for ep in sess['eps'][-3:]:
        txt = '\n'.join(f"{l['who']}: {l['text']}" for l in ep['lines'])
        parts.append(f"=== 第 {ep['n']} 集 {ep['title']} ===\n{txt}\n【选择点】{ep.get('prompt', '')}\n【她的回应】{ep.get('her', '（还没回应）')}")
    older = [f"第 {e['n']} 集：{e['title']}（她：{e.get('her', '')}）" for e in sess['eps'][:-3]]
    return ('更早：' + '；'.join(older) + '\n\n' if older else '') + '\n\n'.join(parts)


def her_said(text, via, lang):
    if via == 'auto':
        return ('她没有回应——她只是闭着眼在听。按角色自己的意志和主线往下推进一步，不替她做重大决定，也不要写“你没说话”。' if lang == 'zh'
                else "She doesn't answer — she's just listening with her eyes closed. Move the story one step on the characters' own will and the main line; don't make big decisions for her, and don't mention that she stayed quiet.")
    if via == 'silence' or not text.strip(): return '她没有说话，只是沉默。' if lang == 'zh' else 'She stays silent.'
    if lang != 'zh':
        if via == 'voice': return f'She says (speech recognition — may contain misheard words; infer what she meant from sound and context, she may also speak Chinese): {text}'
        return f'She chooses: {text}' if via == 'option' else f'She says (typed): {text}'
    if via == 'option': return f'她选择：{text}'
    if via == 'voice': return f'她自己说（语音识别，可能有同音错字或漏字：按读音和上下文理解她的真实意思，别照字面误会）：{text}'
    return f'她自己说（打字）：{text}'


KEYS_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 ._-]{0,24}|NARR|TITLE|PROMPT|C1|C2|END|LINE|HANGUP)\s*[:：]\s*(.+)$')


# ---------------- OpenRouter 长连接（11-10）----------------
# 从这台机器直连 OpenRouter，每次新建 HTTPS 光握手约 1 秒、偶尔超时（理解她的话那一步 2.6 秒内常失败）。
# 常驻几条握好手的连接，用完放回，空闲时每 40 秒保活一次。
import http.client, queue as _queue
_ORQ = _queue.LifoQueue()


def _or_conn():
    c = http.client.HTTPSConnection('openrouter.ai', timeout=20); c.connect(); return c


def _or_warm(n=6):
    for _ in range(n):
        try: _ORQ.put((_or_conn(), time.time()))
        except Exception: pass
    while True:
        time.sleep(20)
        keep = []
        while True:
            try: keep.append(_ORQ.get_nowait())
            except _queue.Empty: break
        for c, t in keep:
            try:
                if time.time() - t > 15:
                    c.request('GET', '/api/v1/key', headers={'Authorization': 'Bearer ' + os.environ.get('OPENROUTER_API_KEY', '')}); c.getresponse().read()
                _ORQ.put((c, time.time()))
            except Exception:
                try: c.close()
                except Exception: pass
        for _ in range(max(0, n - _ORQ.qsize())):
            try: _ORQ.put((_or_conn(), time.time()))
            except Exception: pass


threading.Thread(target=_or_warm, daemon=True).start()


class OrResp:
    """http.client 响应的包装：读完放回连接池，中途不要了就关掉连接"""
    def __init__(self, conn, resp): self.c, self.r, self.ok = conn, resp, False
    def __iter__(self):
        while True:
            line = self.r.readline()
            if not line: break
            yield line
        self.ok = True
    def read(self): b = self.r.read(); self.ok = True; return b
    def __enter__(self): return self
    def __exit__(self, *a):
        if self.ok and not self.r.will_close: _ORQ.put((self.c, time.time()))
        else:
            try: self.c.close()
            except Exception: pass


def or_post(body, timeout):
    """POST /api/v1/chat/completions，优先用池里握好手的连接（失败自动换新连接重试一次）"""
    data = json.dumps(body).encode(); hdr = {'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'}
    for attempt in range(3):
        c = None
        if attempt == 0:  # 第一次用池里的；断了（服务器关掉了空闲连接）就新开
            try: c = _ORQ.get_nowait()[0]
            except _queue.Empty: c = None
        try:
            if c is None: c = http.client.HTTPSConnection('openrouter.ai', timeout=timeout)
            c.timeout = timeout
            if c.sock: c.sock.settimeout(timeout)
            c.request('POST', '/api/v1/chat/completions', body=data, headers=hdr)
            r = c.getresponse()
            if r.status != 200:
                b = r.read(); c.close(); raise RuntimeError(f'openrouter {r.status}: {b[:200]!r}')
            return OrResp(c, r)
        except (http.client.HTTPException, ConnectionError, OSError) as e:
            try: c.close()
            except Exception: pass
            if attempt == 2: raise
    raise RuntimeError('openrouter unreachable')


def openrouter_stream(model, sysm, user_msg, feed, max_tokens=1400, temperature=0.85, extra=None, timeout=60):
    body = {'model': model, 'max_tokens': max_tokens, 'temperature': temperature, 'stream': True,
            'messages': [{'role': 'system', 'content': sysm}, {'role': 'user', 'content': user_msg}], **(extra or {})}
    out = ''
    with or_post(body, timeout) as r:
        for line in r:
            line = line.decode('utf8', 'ignore').strip()
            if not line.startswith('data:') or line.endswith('[DONE]'): continue
            try: c = json.loads(line[5:])['choices'][0]['delta'].get('content') or ''
            except Exception: continue
            out += c; feed(c)
    feed('\n')
    return out


class _Lost(Exception): pass


def openrouter_hedged(models, sysm, user_msg, feed, max_tokens=1400, temperature=0.8):
    """同时让两个快模型写，谁先写完第一行就用谁，另一个立刻断开（11-09：单个快模型时快时慢，1.3 秒到 22 秒都有）"""
    lock = threading.Lock(); win = {'m': None}; bufs = {}; res = {}
    def rz(m): return {'reasoning': {'effort': 'low'} if 'glm' in m else {'enabled': False}, 'provider': {'sort': 'latency'}}  # 11-09 选首字最快的供应商
    def run(m):
        bufs[m] = ''
        def f(chunk):
            with lock:
                if win['m'] is None:
                    bufs[m] += chunk
                    if re.search(r'[A-Za-z0-9 ._-]{1,24}\s*[:：].+\n', bufs[m]): win['m'] = m; feed(bufs[m])
                elif win['m'] == m: feed(chunk)
                else: raise _Lost()
        try:
            txt = openrouter_stream(m, sysm, user_msg, f, max_tokens=max_tokens, temperature=temperature, extra=rz(m), timeout=15)
            with lock:
                if win['m'] is None and bufs[m].strip(): win['m'] = m; feed(bufs[m])
            if win['m'] == m: res['txt'] = txt; res['model'] = m
        except _Lost: pass
        except Exception as e:
            res.setdefault('errs', []).append(repr(e)[:120])
            if win['m'] == m: res['txt'] = bufs[m]; res['model'] = m + ' (cut)'  # stalled mid-turn: keep the lines it already gave
    ths = [threading.Thread(target=run, args=(m,), daemon=True) for m in models]
    [t.start() for t in ths]; [t.join(90) for t in ths]
    if 'txt' not in res: raise RuntimeError('hedged writers failed: ' + '; '.join(res.get('errs', [])))
    return res['txt'], res['model']


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
    if isinstance(fast_model, (list, tuple)):
        try:
            txt, m = openrouter_hedged(fast_model, sysm, user_msg, feed, max_tokens=1400, temperature=0.8)
            sess['writer'] = m
            return txt
        except Exception:
            traceback.print_exc(); buf['b'] = ''
            if sess.get('_got_lines'): raise
        fast_model = None
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


EP_FAST = tuple(os.environ.get('EP_FAST_MODEL', 'z-ai/glm-5.3-prime,deepseek/deepseek-v4.1-flash,moonshotai/kimi-k3,qwen/qwen3.6-flash').split(','))  # 11-09 加 qwen：OpenRouter 时快时慢（首字 1.3–10 秒），多一路更稳  # 11-09 三个同时写，谁先写完第一行用谁
SPEC_LINES = 4  # 预先生成先配几句：2 句点选项后第 3 句要等 ~13 秒，4 句（约 15–20 秒音频）能盖住其余句子的配音时间  # 她自由输入时写下一集：11-06 实测第一句 2.8 秒（本机 Opus 8–13 秒）


def next_msg(sess, her, bridge=None):
    """按“她对上一集的回应”拼下一集的写作请求（不改 sess：预先生成时她还没选）。
    bridge：她说完后旁白已经先说的那句过渡（预先配好音，0 等待），这一集从它后面接着写。"""
    eps = sess['eps'][:-1] + [dict(sess['eps'][-1], her=her)]
    n = len(eps) + 1; lang = sess['lang']
    pace = ''
    if n >= MAX_EPS - 2: pace = '\n（快到这条线的结局了：接下来 1–2 集内收束主要悬念。）' if lang == 'zh' else '\n(Approaching the end of this route: resolve the main thread within 1–2 episodes.)'
    if n >= MAX_EPS: pace = '\n（这是最后一集：给一个有余味的结局，END: yes。）' if lang == 'zh' else '\n(This is the final episode: give a resonant ending, END: yes.)'
    so_far = story_so_far(dict(sess, eps=eps))
    w = [x for x in (sess.get('wishes') or []) if x]
    if w:  # 她在听上一集时随口说的话（“对故事说话”）：下一集要接住
        pace += ('\n她在听上一集的时候还对故事说过：' + ' / '.join(f'“{x}”' for x in w) + '。这一集要明显回应、照她想要的方向走。') if lang == 'zh' else \
                ('\nWhile listening to the last episode she also told the story: ' + ' / '.join(f'"{x}"' for x in w) + '. This episode must clearly answer that and go where she wants.')
    if re.match(r'^(她自己说|She says)', her or ''):  # 11-10 她自由说的话：这一集按她的指令演，不绕回预设
        pace += ('\n【最重要】她这次没有选现成的选项，而是自己说了上面那句话。这一集的主线就是执行/回应她这句话：第一句就接住；她要做的事这一集就让它发生、她问的问题角色要正面回答、她要角色做的事角色要有明确反应；'
                 '不要只回应一句又绕回原来的剧情，不要改成两个选项里的做法，不要替她换成别的意思。语音识别可能有错字，按读音和上下文理解。'
                 '\n严格照做：她话里点到的每一件具体的事——谁、做什么、对谁、在哪、拿什么、说什么——都要在前三句里按她说的原样发生，一件不漏、不换说法、不打折扣；'
                 '她说了几步就按她的顺序写几步；角色可以有自己的反应，但不能拦下、否定或改写她已经做出的动作。这一集后面的内容是这件事带来的后果，结尾的提问和两个选项也从这件事往下生出来。'
                 '写完自查一遍：把她那句话拆成几个要点，逐个确认正文里都有，没有的补上。' if lang == 'zh' else
                 '\n[MOST IMPORTANT] She did not pick a ready-made option; she said the line above in her own words. This episode is about carrying out / answering exactly that: answer it in the first line; '
                 'if she does something, it happens; if she asks something, the character answers it directly; if she tells a character to do something, they clearly react. Do not answer once and drift back to the planned plot, '
                 'do not swap in one of the two options, do not change her meaning. Speech recognition may contain misheard words: infer from sound and context.'
                 '\nFollow it to the letter: every concrete thing she named — who, does what, to whom, where, with what, says what — must happen as she said it within the first three lines, nothing left out, reworded into something else or watered down; '
                 'if she gave several steps, write them in her order; characters may react, but may not block, deny or rewrite an action she has taken. The rest of the episode is the consequence of it, and the closing prompt and both choices grow out of it too. '
                 'Before you finish, check: break her line into its points and make sure each one is in the text; add any that are missing.')
    if bridge:
        pace += (f'\n她回答之后，旁白已经先说了一句：「{bridge}」。这一集紧接着这句往下写，别重复这句的内容。' if lang == 'zh'
                 else f'\nRight after she answered, the narrator already said: "{bridge}". Continue straight from that line without repeating it.')
    return (f'到目前为止：\n{so_far}\n\n现在写第 {n} 集。{pace}' if lang == 'zh' else f'Story so far:\n{so_far}\n\nNow write episode {n}.{pace}')


OPEN_MODELS = ('deepseek/deepseek-v4.1-flash', 'qwen/qwen3.6-flash', 'moonshotai/kimi-k3')  # 11-09 小提示词首字 1.3–1.5 秒（整集编剧 2.2–4.9 秒）


def quick_open(sess, her, done_ev=None):
    """她说完现写的那集：先用小提示词让快模型只写开头两句（主角对她这句话的直接回应 + 一句旁白），1.5 秒左右出来，马上配音；
    整集编剧拿着这两句接着往下写。返回 [(who, text)]，没写出来返回 []。"""
    lang = sess['lang']; s = sess['series']; b = BASE.get(s, {})
    cast = [k for k in VOICES[s] if not k.startswith('_')]
    last = sess['eps'][-1]; tail = '\n'.join(f"{l['who']}: {l['text']}" for l in (last.get('lines') or [])[-6:])
    br = (sess.get('_brsel') or {}).get(last['n'])
    lead = (b.get('lead') or {}).get(lang, '') if isinstance(b.get('lead'), dict) else b.get('lead', '')
    hook = (b.get('hook') or {}).get(lang, '') if isinstance(b.get('hook'), dict) else b.get('hook', '')
    if lang == 'zh':
        sysm = ('你是有声连载剧的编剧' if neutral(s) else '你是女性向有声连载剧的编剧') + '，正在实时接着写。只输出两行，每行格式“角色名: 台词”，角色名只能用：' + '、'.join(cast + ['NARR']) + '。不要别的文字。'
        user = (f'剧：{lead}。{hook}\n' + ('听众本人就是主角（用“你”称呼，性别不限，别给你加性别）。\n' if neutral(s) else '听众本人就是女主（用“你”称呼）。\n') + f'上一集最后几句：\n{tail}\n选择点：{last.get("prompt", "")}\n'
                + (f'旁白刚说：「{br["text"]}」\n' if br else '') + f'{her}\n\n'
                '写这一集最开头的两行：第一行是此刻在场、最该回应她的那个角色（通常是主角）对她这句话的直接回应，12 个字以内，口语、符合人设；'
                '第二行是 NARR 旁白，写这个角色的一个动作或神情，20 个字以内。不要替她做决定，不要一下推进大剧情。'
                '她说的是她要做的事 / 要问的话 / 给角色的要求：第一行必须针对这件事本身回应（她做了什么就承认她做了，她问了什么就正面答），不能答非所问，不能把她的做法换成别的。')
    else:
        sysm = 'You write a women-focused serialized audio drama, live. Output exactly two lines, each "Name: line", names only from: ' + ', '.join(cast + ['NARR']) + '. Nothing else.'
        user = (f'Show: {lead}. {hook}\n' + ('The listener is the protagonist ("you"), gender unspecified: never gender them.\n' if neutral(s) else 'The listener is the heroine ("you").\n') + f'Last lines of the previous episode:\n{tail}\nChoice point: {last.get("prompt", "")}\n'
                + (f'The narrator just said: "{br["text"]}"\n' if br else '') + f'{her}\n\n'
                'Write the first two lines of the new episode: line 1 is the character in the scene who should answer her (usually the lead), replying directly to what she said, under 10 words, spoken, in character; '
                'line 2 is NARR: one action or look of his, under 16 words. Don\'t decide for her and don\'t jump the plot ahead. '
                'What she said is what she does / asks / tells a character to do: line 1 must respond to exactly that (acknowledge the action she took, answer the question she asked), never something beside the point, never a different action in its place.')
    got = []; ev = threading.Event(); buf = {'b': ''}
    def feed(c):
        buf['b'] += c
        while '\n' in buf['b']:
            ln, buf['b'] = buf['b'].split('\n', 1)
            m = KEYS_RE.match(ln)
            if m and len(got) < 2:
                who = 'NARR' if m.group(1).strip().upper() == 'NARR' else m.group(1).strip()
                if who in cast or who == 'NARR': got.append((who, m.group(2).strip()))
            if len(got) >= 2: ev.set()
    def run():
        try: openrouter_hedged(OPEN_MODELS, sysm, user, feed, max_tokens=120, temperature=0.75)
        except Exception as e: print('quick_open', repr(e)[:120], flush=True)
        finally: ev.set()
    threading.Thread(target=run, daemon=True).start()
    return ev, got


def race_write(job, sess, user_msg, her, on_line):
    """现写的那集（11-09 再提速）：快模型写开头两句 和 整集编剧 同时开跑，谁先出第一句用谁——
    开头两句先到：马上配音，整集编剧带着这两句重新接着写；整集编剧先到：直接用它，开头两句不要了。不会因为哪一路慢而干等。"""
    lang = sess['lang']; sysm = system_prompt(sess)
    lock = threading.Lock(); mode = {'m': 'pending'}; buf = []; first = threading.Event(); sdone = threading.Event(); res = {}
    def sline(k, v):
        with lock:
            if mode['m'] == 'dead': raise _Lost()
            if mode['m'] == 'live': on_line(k, v); return
            buf.append((k, v)); first.set()
    pb = {'b': ''}
    def sfeed(c):
        pb['b'] += c
        while '\n' in pb['b']:
            ln, pb['b'] = pb['b'].split('\n', 1)
            m = KEYS_RE.match(ln)
            if m: sline(m.group(1).strip(), m.group(2).strip())
    plain = user_msg + ('\n第一句就回应她的话，而且要短（10 个字以内），第二句 20 个字以内。' if lang == 'zh' else '\nThe first line answers her and is short (under 8 words), the second under 16 words.')
    def shadow():
        try: res['txt'], res['model'] = openrouter_hedged(EP_FAST, sysm, plain, sfeed, max_tokens=1400, temperature=0.8)
        except Exception as e: res['err'] = repr(e)[:160]
        finally: sdone.set(); first.set()
    threading.Thread(target=shadow, daemon=True).start()
    oev, got = quick_open(sess, her)
    t0 = time.time()
    while time.time() - t0 < 12:
        if oev.is_set() and got and not buf: break  # 开头两句先写好
        if buf or sdone.is_set(): break
        first.wait(0.05); oev.wait(0.02)
    with lock:
        use_open = bool(got) and not buf
        mode['m'] = 'dead' if use_open else 'live'
        pend = [] if use_open else list(buf)
    job['t']['race'] = 'open' if use_open else 'writer'
    if not use_open:
        for k, v in pend: on_line(k, v)
        sdone.wait(90)
        if res.get('txt') or pend: sess_w = res.get('model'); job['writer'] = sess_w; return
        # 整集编剧这一路失败了：走原来的整套兜底
        return write_episode({'_got_lines': False}, plain, on_line, sysm=sysm, fast_model=EP_FAST)
    lines = list(got[:2])
    for w, v in lines: on_line(w, v)
    shown = ' / '.join(f'{w}: {v}' for w, v in lines)
    more = (f'\n这一集开头两行已经写好、正在播出：{shown}。从第三行接着写（输出里不要再写这两行，也别再回答一遍她的话），TITLE/PROMPT/C1/C2/END 照常写。' if lang == 'zh'
            else f'\nThe first two lines of this episode are already written and playing: {shown}. Continue from line three (do not output those two lines again or re-answer her); TITLE/PROMPT/C1/C2/END as usual.')
    wctx = {'_got_lines': True}
    out = write_episode(wctx, user_msg + more, on_line, sysm=sysm, fast_model=EP_FAST)
    job['writer'] = wctx.get('writer'); return out


def run_episode(job, sess, user_msg, spec=None, her=None, gate=None):
    """写一集并逐句配音。spec={'base': 集数}：预先生成（她还没选）——Opus 慢慢写，只先配前两句，不记进剧情；她点了这个选项（commit_ep_spec）才配完其余句、记进剧情。
    不是预先生成（她自由输入）时用快模型 EP_FAST 写，第一句约 3 秒。"""
    t0 = time.time(); n = len(sess['eps']) + 1; lang = sess['lang']; series = sess['series']
    job['_bridge'] = ((sess.get('_brsel') or {}).get(n - 1) or {}).get('text') if not spec else None
    job['_her'] = her; job['_n'] = n; job['_started'] = set(); job['_raw'] = {}
    job['_gate'] = gate   # 11-12 边说边预写：{'tts': Event, 'ok': Event}——配音等 tts，记进剧情等 ok（她说完、识别结果就是这句）；没等到就作废
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

    first_ev = threading.Event()

    def synth(i, who, text):
        first = i == 0
        try:
            if gate and not gate['tts'].is_set() and not gate['tts'].wait(26): ep['lines'][i]['url'] = ''; return   # 预写的：文字还可能变，先不花配音；一直没放行就不配
            eng = 'flash' if not spec else sess.get('tts', 'v4')
            if not spec and i >= 3: first_ev.wait(4)  # 11-10：二十多句同时提交会在 Waku 排队、把第一句也拖到 10 秒；第 4 句起等第一句配好（最多 4 秒）再提交  # 11-09 她说完现写的那集：整集用低延迟配音（同一批声线，约 3.4 秒 vs 5–7 秒），句句赶在播放前配好
            if job.get('_cancel'): ep['lines'][i]['url'] = ''; return
            # 她说完现写的那集：前三句走专用配音通道（不跟后台预写、过渡句排队；11-09 实测排队时第一句要 7–8 秒，单独 3–4 秒）
            # 11-10 卡顿：后台在预写下一集的两个分支（30 多句配音），正在播的这集第 4 句起跟它们排同一个队就会断——整集都走专用通道，第 4–6 句也两路
            u = tts_hedged(series, who, text, lang, (2 if spec else 3) if first else (3 if (i == 1 and not spec) else 2 if (i < 6 and not spec) or (spec and i == SPEC_LINES) else 1), eng,
                           pool=CALL_POOL if (not spec or job.get('_committed')) else None)  # 她已经选了这条预写分支：剩下的句子也走专用通道
            ep['lines'][i]['url'] = u
            if first: first_ev.set()
            threading.Thread(target=cache_line, args=(u,), daemon=True).start()
        except Exception:
            ep['lines'][i]['url'] = ''
            if first: first_ev.set()
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
        if len(ep['lines']) >= 22: return  # 11-10：原来 16 句就截，编剧多写的后半段被丢、选择点却还在说后面的事；放宽到 22
        if not spec and not ep['lines'] and k.upper() == 'NARR' and job.get('_bridge'):  # 编剧把旁白过渡句又写了一遍：不要，过渡句刚放过
            import difflib
            if difflib.SequenceMatcher(None, re.sub(r'\W', '', v), re.sub(r'\W', '', job['_bridge'])).ratio() > 0.55: return
        i = len(ep['lines']); ep['lines'].append({'who': who, 'text': re.sub(r'\[[^\]]*\]\s*', '', v), 'url': None, 'clip': clip})
        if who == 'NARR':   # 11-11 关键处的音效：旁白写到“有声音发生”的句子（门砰地关上、雷声、心跳……），每集最多 4 个、不连着两句都放
            sx = [j for j, l in enumerate(ep['lines']) if l.get('sfx')]
            k_sfx = SFX.sfx_of(ep['lines'][i]['text'], lang) if len(sx) < 4 and (not sx or i - sx[-1] >= 2) else None
            if k_sfx and k_sfx not in {ep['lines'][j]['sfx'] for j in sx}: ep['lines'][i]['sfx'] = k_sfx
        job['status'] = 'voicing'; job['_got_lines'] = True
        job['t'].setdefault('first_line', round(time.time() - t0, 2))
        job['_raw'][i] = (who, v)
        if not spec or i < SPEC_LINES or job.get('_committed'):  # 预先生成只先配前几句（够她听到其余句子配好）
            job['_started'].add(i)
            th = threading.Thread(target=synth, args=(i, who, v), daemon=True); th.start(); ths.append(th)
        if not clip: mq['pending'].append((i, who, ep['lines'][i]['text'])); mev.set()
    job['_mth'] = mth
    try:
        if not spec and her:  # 现写的那集：快模型开头 和 整集编剧 赛跑
            race_write(job, sess, user_msg, her, on_line)
        else:
            wctx = {'_got_lines': False}
            write_episode(wctx, user_msg, lambda k, v: (on_line(k, v), wctx.__setitem__('_got_lines', True)), sysm=system_prompt(sess), fast_model=None if spec else EP_FAST)
            job['writer'] = wctx.get('writer')
        job['t']['writer'] = round(time.time() - t0, 2)
        mq['done'] = True; mev.set()
        if len(ep['lines']) < 3: raise RuntimeError('writer returned too few lines')
        if not ep['choices']: ep['choices'] = ['……', '……'] if lang == 'zh' else ['…', '…']
        if not ep['title']: ep['title'] = (f'第 {n} 集' if lang == 'zh' else f'Episode {n}')
        if n >= MAX_EPS: ep['ending'] = True
        if gate and not job.get('_cancel') and not gate['ok'].wait(25): job['_cancel'] = True   # 预写的这集没被认领（她接着说了别的）：不记进剧情
        if job.get('_cancel'): job['status'] = 'cancelled'; return  # 她说的其实是某个选项：用了预先写好的那集，这条现写的作废
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
    sess.setdefault('_full', {})[ep['n']] = {k: v for k, v in ep.items()}
    job['status'] = 'done'
    log(sess['sid'], {'ep': ep['n'], 'writer': job.get('writer'), 'spec': bool(job.get('_committed')), 't': job['t'], 'ep_out': {k: v for k, v in ep.items() if k != 'lines'}, 'lines': [{k: l.get(k) for k in ('who', 'text', 'url', 'clip')} for l in ep['lines']], 'at': time.strftime('%F %T')})
    if not ep.get('ending'): start_ep_specs(sess)


def start_ep_specs(sess):
    """她听这一集的时候（1–3 分钟），按两个选项先把下一集写好、前两句配好音；她点选项就直接开播"""
    last = sess['eps'][-1]; sess['spec'] = {}
    if len(sess['eps']) >= MAX_EPS: return
    if (sess['sid'], last['n']) not in BRIDGE_EP: threading.Thread(target=ep_bridge, args=(sess, last['n']), daemon=True).start()
    beat_card(sess)  # 第一次用这部剧/这个主角时在后台配好
    for ch in (last.get('choices') or [])[:2]:
        jid = rid(); JOBS[jid] = {'id': jid, 'status': 'writing', 'error': None}
        her = her_said(ch, 'option', sess['lang'])
        sess['spec'][ch] = {'job': jid, 'base': len(sess['eps'])}
        threading.Thread(target=run_episode, args=(JOBS[jid], sess, next_msg(sess, her), {'base': len(sess['eps'])}, her), daemon=True).start()


def fast_chat(prompt, max_tokens=200, timeout=8, model=None):
    body = {'model': model or MAPPER, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': 0, 'reasoning': {'enabled': False}}
    with or_post(body, timeout) as r:  # 长连接池（省掉每次约 1 秒的握手）
        return json.loads(r.read())['choices'][0]['message']['content'].strip()


_LET_ZH = re.compile(r'^(大写)?(我|那)?(就|还是|要)?(选|要|挑|走|谁|学|宣|旋|悬|许|须|雪|血)?(选项)?(?P<k>a|ａ|b|ｂ|1|2|一|二|第一个|第二个|第一|第二|前面那个|后面那个|前一个|后一个|上面那个|下面那个|左边那个|右边那个)(个|吧|八|8|呀|啊|哦|嘛|了|好了|这个|那个)*$')
_LET_ZH2 = re.compile(r'^(我|那)?(就|还是|要)?(选|挑|上|宣|旋|悬|学)(选项)?(?P<k>诶|欸|哎|唉|地|比|必|逼|币|笔|臂|壁|毕|闭|鼻|避|碧|彼)(吧|八|呀|啊|了)*$')  # 中文识别常把单念的 A/B 写成同音字，只在前面有“选”时认
_LET_EN = re.compile(r"^(i ?(ll|will|d|would)? ?(choose|pick|go with|take|select|say|want)|(let ?s|lets) go with|go with|choose|pick|take|select|maybe)? ?(option|letter|choice|the)? ?(?P<k>a|b|ay|bee|be|1|2|one|two|first|second|first one|second one|top one|bottom one|left one|right one)( one| option)?( please)?$")


def pick_letter(text):
    """她说“A / 选A / 第一个 / option B / the second one” → 0 或 1；不是这种说法 → None（11-09 她要求说字母和点选项一样）"""
    t = (text or '').strip().lower()
    z = re.sub(r'[\s，。！？、,.!?~…“”"\'：:]+', '', t)
    m = _LET_ZH.match(z) or _LET_ZH2.match(z)
    if m:
        k = m.group('k')
        return 0 if k in ('a', 'ａ', '1', '一', '第一个', '第一', '前面那个', '前一个', '上面那个', '左边那个', '诶', '欸', '哎', '唉', '地') else 1
    e = re.sub(r'[^a-z0-9 ]+', ' ', t.replace("'", '')); e = re.sub(r'\s+', ' ', e).strip()
    m = _LET_EN.match(e)
    if m:
        k = m.group('k')
        return 0 if k in ('a', 'ay', '1', 'one', 'first', 'first one', 'top one', 'left one') else 1
    return None


def match_choice(sess, text, timeout=6):
    """她用语音/打字回了一句：意思就是 C1 或 C2（没有多出来的要求）→ 直接用预先写好的那集；“继续/你决定/随便” → AUTO；否则 None（现写）。约 1–2 秒。"""
    ch = (sess['eps'][-1].get('choices') or [])[:2]
    if len(ch) < 2 or not text.strip(): return None
    k = pick_letter(text)
    if k is not None:
        print('match_choice letter', repr(text[:40]), '->', 'C%d' % (k + 1), flush=True); return ch[k]
    # 11-09：她锁屏说“等他自己过来拿。”被判成 AUTO、“Sure.”也是 → 播了默认那集，她的话被丢掉。现在只认“几乎同义”的 C1/C2，其余一律 FREE（按她的原话现写）。
    pr = (f'选择点的两个选项：\nC1: {ch[0]}\nC2: {ch[1]}\n\n听众用语音回答（可能有识别错字）：“{text}”\n\n'
          '判断：她用字母或序号指某个选项（A/B、选A、第一个、第二个、option B 等）→ 输出对应的 C1 或 C2；她的回答和 C1 或 C2 说的是同一个动作/同一句话（同义转述也算，但没有新的内容或要求）→ 输出 C1 或 C2；'
          '其他所有情况——她说了别的做法、换了说法带出不同意思、只说了“好/嗯/Sure”这类含糊的话、或你拿不准——一律输出 FREE。只输出一个词。')
    try:
        r = fast_chat(pr, 8, timeout).upper()
    except Exception as e:
        print('match_choice failed', repr(e)[:200], flush=True); return None
    print('match_choice', repr(text[:40]), '->', r, flush=True)
    if 'C1' in r: return ch[0]
    if 'C2' in r: return ch[1]
    return None


# ---------------- 她说完马上接上（11-09）----------------
# 她回答完：前端先放“好，按你说的来”，紧接着旁白说一句预先配好音的过渡（这句贴着这一集的情境，但不猜她说了什么），
# 同时中转已经按她的话开写下一集；过渡说完，新一集的第一句基本就配好了。
GEN_BRIDGES = {'zh': ['你的话音刚落，四周像是安静了一瞬。', '这句话一说出口，空气好像都轻轻顿了一下。', '你说完，时间仿佛慢了半拍。', '话音落下，有什么东西，正在悄悄改变。'],
               'en': ['Your words land, and for a moment, everything goes still.', 'The moment you say it, the air seems to pause.', 'You say it, and time slows, just a little.', 'Your answer hangs in the air, and something begins to shift.']}
GEN_BRIDGE_URLS = {}
BRIDGE_EP = {}  # (sid, n) -> {'text','url'}
_BR_EV = {}


def generic_bridges(lang, make=True):
    """通用过渡句（旁白声，各剧通用），缓存在 cache/bridge/generic.<lang>.json"""
    if GEN_BRIDGE_URLS.get(lang): return GEN_BRIDGE_URLS[lang]
    f = CACHE / 'bridge' / f'generic.{lang}.json'
    if f.exists():
        GEN_BRIDGE_URLS[lang] = json.load(open(f)); return GEN_BRIDGE_URLS[lang]
    if not make: return []
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(4) as ex:
        urls = list(ex.map(lambda t: tts('magnus', 'NARR', t, lang), GEN_BRIDGES[lang]))
    d = [{'text': t, 'url': u} for t, u in zip(GEN_BRIDGES[lang], urls) if u]
    f.parent.mkdir(parents=True, exist_ok=True); json.dump(d, open(f, 'w'), ensure_ascii=False)
    GEN_BRIDGE_URLS[lang] = d; return d


def ep_bridge(sess, n):
    """第 n 集选择点专用的过渡句：她一开口回答，旁白马上说的那句（画面 + 对方的反应，不猜她的回答）。第 1 集按剧/语言存盘。"""
    key = (sess['sid'], n)
    if key in BRIDGE_EP: return BRIDGE_EP[key]
    ev = _BR_EV.get(key)
    if ev: ev.wait(20); return BRIDGE_EP.get(key)
    ev = _BR_EV[key] = threading.Event()
    try:
        f = CACHE / 'bridge' / f'ep1.{sess["series"]}.{sess["lang"]}.json' if n == 1 else None
        if f and f.exists(): BRIDGE_EP[key] = json.load(open(f)); return BRIDGE_EP[key]
        ep = next((e for e in sess['eps'] if e['n'] == n), None)
        if not ep: return None
        lang = sess['lang']; tail = '\n'.join(f"{l['who']}: {l['text']}" for l in (ep.get('lines') or [])[-5:])
        if lang == 'zh':
            pr = (f'有声连载剧的集尾，旁白刚问完听众“你”一个选择。\n情境：{ep.get("prompt", "")}\n最后几句：\n{tail}\n\n'
                  '现在她开口回答了——她可能说任何话（同意、拒绝、反问、别的做法）。写旁白在她回答之后立刻说的一句过渡，16–28 个字：'
                  '只写这一刻静下来、对方在听她说话的样子（停住、看着你、呼吸一顿、周围的声音），不能写任何靠近或离开、松手或抓紧、笑或皱眉这类带倾向的动作和情绪，'
                  '不要猜她说了什么或选了什么，不要评价，不要替任何人说台词，不要写“你选择了”。用“你”指听众，人名照用。只输出这一句。')
        else:
            pr = (f'End of an audio-drama episode; the narrator has just asked the listener ("you") to choose.\nSituation: {ep.get("prompt", "")}\nLast lines:\n{tail}\n\n'
                  'Now she starts answering, and she may say anything (yes, no, a question, something else). Write the one narrator line spoken right after she answers, 10–20 words: '
                  "only the moment going still while the other person listens (they pause, look at you, a breath held, the sounds around). No movement toward or away, no letting go or "
                  "holding tighter, no smile or frown, no emotion that leans any way. Don't guess what she said or chose, no judgement, no dialogue, never \"you chose\". Call the listener \"you\"; keep names. Output only that line.")
        t = fast_chat(pr, 120, 10).strip().strip('"“”「」')
        if not (6 < len(t) < 140): return None
        u = tts_hedged(sess['series'], 'NARR', t, lang, 2, sess.get('tts', 'v4'))
        d = {'text': t, 'url': u}; BRIDGE_EP[key] = d
        threading.Thread(target=cache_line, args=(u,), daemon=True).start()
        if f: f.parent.mkdir(parents=True, exist_ok=True); json.dump(d, open(f, 'w'), ensure_ascii=False)
        return d
    except Exception as e:
        print('ep_bridge', repr(e)[:160], flush=True); return None
    finally:
        ev.set(); _BR_EV.pop(key, None)


# 旁白过渡说完、新一集还没好时，主角先接半句（预先配好音，不写进剧情，任何回答都接得上）：她问了问题用 q，否则 s
EP_BEATS = {'zh': {'q': ['你问这个……', '……你真想知道？', '这个问题啊……'], 's': ['……我听见了。', '……好。', '嗯……']},
            'en': {'q': ['You want to know that…', '…You really want to know?', 'That question…'], 's': ['…I heard you.', '…Okay.', 'Mm…']}}
BEATS = {}
_BEAT_MAKING = set()


def lead_now(sess):
    """这一刻在场的主角：只有一个主角就是他；多主角的剧取上一集说话最多的那个"""
    s = sess['series']; leads = [k for k, v in VOICES[s].items() if isinstance(v, dict) and v.get('lead')]
    if len(leads) <= 1: return leads[0] if leads else None
    cnt = {k: 0 for k in leads}
    for l in (sess['eps'][-1].get('lines') or []):
        if l['who'] in cnt: cnt[l['who']] += 1
    return max(leads, key=lambda k: cnt[k])


def beats(series, who, lang, make=True):
    key = (series, who, lang)
    if key in BEATS: return BEATS[key]
    f = CACHE / 'beats' / f'{series}.{who}.{lang}.json'
    if f.exists(): BEATS[key] = json.load(open(f)); return BEATS[key]
    if not make or key in _BEAT_MAKING: return None
    _BEAT_MAKING.add(key)
    try:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(6) as ex:
            d = {k: [{'text': t, 'url': u} for t, u in zip(v, ex.map(lambda t: tts(series, who, t, lang), v))] for k, v in EP_BEATS[lang].items()}
        f.parent.mkdir(parents=True, exist_ok=True); json.dump(d, open(f, 'w'), ensure_ascii=False)
        BEATS[key] = d; return d
    except Exception as e:
        print('beats', repr(e)[:120], flush=True); return None
    finally:
        _BEAT_MAKING.discard(key)


def beat_card(sess):
    who = lead_now(sess)
    if not who: return None
    d = beats(sess['series'], who, sess['lang'], make=False)
    if not d: threading.Thread(target=beats, args=(sess['series'], who, sess['lang']), daemon=True).start(); return None
    return dict(d, who=who)


def sel_bridge(sess, n, lock=True):
    """第 n 集选择点用哪句过渡：她回答时（lock）选定就固定，前端放的和编剧接着写的是同一句。专用句没好就用通用句。
    lock=False：前端提前取来预载，不定下来（专用句可能稍后才好）。"""
    sel = sess.setdefault('_brsel', {})
    if n in sel: return sel[n]
    d = BRIDGE_EP.get((sess['sid'], n))
    if not d:
        g = generic_bridges(sess['lang'], make=False)
        d = g[(n + len(sess['sid'])) % len(g)] if g else None
    if d and lock: sel[n] = d
    return d


UNDERSTAND_MODELS = ('deepseek/deepseek-v4.1-flash', 'qwen/qwen3.6-flash', 'moonshotai/kimi-k3')


def understand(sess, text, timeout=2.4):
    """11-10 她说：交互点语音识别不准，自由输入要优先理解、按她的指令响应。
    结合此刻的剧情、角色名和两个选项，先把识别的同音错字改对，再判断：选了 C1/C2，还是自由说了别的（FREE）。
    返回 {'kind','heard','intent'}；失败返回 None。约 1–1.5 秒。"""
    ep = sess['eps'][-1]; ch = (ep.get('choices') or [])[:2]; lang = sess['lang']
    names = [k for k in VOICES.get(sess['series'], {}) if not k.startswith('_')][:6]
    tail = '\n'.join(f"{l['who']}: {l['text']}" for l in (ep.get('lines') or [])[-4:])
    pr = (f'有声互动剧的选择点。剧里的角色：{"、".join(names)}；听众名字：{sess.get("name") or "（未知）"}。\n'
          f'此刻的情境：{ep.get("prompt", "")}\n最后几句：\n{tail}\n\n两个选项：\nC1: {ch[0] if ch else ""}\nC2: {ch[1] if len(ch) > 1 else ""}\n\n'
          f'听众用语音回答，语音识别结果（可能有同音错字、漏字、人名听错）：“{text}”\n\n'
          '1. 结合情境、角色名和读音，把识别结果改成她最可能真正说的话（heard，保持她的原意和口吻，只改明显的识别错误；本来就通顺就原样保留）。'
          '例如“谁一/学二”多半是“选一/选二”，人名按读音改成剧里的角色名。\n'
          '2. 判断 kind：她用字母或序号指某个选项（A/B、第一个、第二个）→ C1 或 C2；她把某个选项的原话几乎逐字念了出来 → C1 或 C2；'
          '其余一律 FREE：只要她是用自己的话说的（哪怕意思和某个选项接近），或说了别的做法/问题/要求、或只说了“好/嗯”这类含糊的话，都是 FREE。拿不准就 FREE。\n'
          '3. intent：用一句话（' + ('中文' if lang == 'zh' else 'English') + '）说清她想做什么、想问谁什么、想让谁做什么；她话里的“你/他/她/那个电话/那件事”分别指剧里的哪个人、哪件事，要写明（FREE 时必填）。\n'
          '只输出 JSON：{"heard":"...","kind":"C1|C2|FREE","intent":"..."}')
    # 三个快模型同时问，谁先给出有效 JSON 用谁（11-10 单发时连 OpenRouter 握手超时，理解失败就又按原话误会了）
    box, ev = {}, threading.Event()
    def ask(m):
        try:
            r = fast_chat(pr, 220, timeout, m); j = json.loads(r[r.find('{'):r.rfind('}') + 1])
            if j.get('heard') is not None and not ev.is_set(): box['j'] = j; box['m'] = m; ev.set()
        except Exception as e: box.setdefault('err', repr(e)[:120])
    for m in UNDERSTAND_MODELS: threading.Thread(target=ask, args=(m,), daemon=True).start()
    ev.wait(timeout + 0.3)
    try:
        if 'j' not in box: raise RuntimeError(box.get('err') or 'timeout')
        j = box['j']
        if j.get('kind') not in ('C1', 'C2', 'FREE'): j['kind'] = 'FREE'
        print('understand', box.get('m'), repr(text[:40]), '->', j.get('kind'), repr((j.get('heard') or '')[:40]), repr((j.get('intent') or '')[:50]), flush=True)
        return j
    except Exception as e:
        print('understand failed', repr(e)[:160], flush=True); return None


# ---- 11-12 语音输入判停（她说：稍微停一下就被当成说完了，其实还要接着说；停顿时长也不要太久）----
# 参考的做法：OpenAI Realtime 的 semantic_vad（按“说完了”的概率决定等多久，话没说完就多等）、AssemblyAI（先等一小段安静再看内容，
# 最长 1.28–2.56 秒强制结束）、LiveKit（最短 0.5 秒、最长 3 秒）。这里：中转在每个中间识别结果上给一个判断 eou，
# 手机按它决定安静多久算说完——done 0.7 秒（说了 2.5 秒以上 1.1 秒）、unk 1.3 秒（1.6 秒）、open 2.6 秒；快模型的判断只用来多等（open），不用来提前结束。
_EOU_OPEN_ZH = re.compile(r'(然后|但是|可是|不过|因为|所以|而且|并且|还有|或者|以及|如果|要是|虽然|就是|就是说|那个|这个|那么|比如|比如说|另外|同时|接着|之后|我想|我要|想要|我觉得|我希望|希望|'
                          r'能不能|可不可以|你能不能|我想让他|我想让她|让他|让她|叫他|叫她|告诉他|告诉她|问他|问她|先|再|和|跟|与|把|被|让|给|对着|为了|关于|嗯|呃|额|那)$')
_EOU_DONE_ZH = re.compile(r'(吧|吗|呢|了|啊|呀|哦|嘛|啦|好|好的|行|可以|对|是的|不要|不行|不用|谢谢|就这样|就这些|好了|说完了|选[一二12ABab]|第[一二12]个|选项[一二12ABab]|^[ABab]$)$')
_EOU_OPEN_EN = re.compile(r"\b(and|but|or|so|because|then|if|when|while|with|to|of|for|in|on|at|from|about|the|a|an|my|your|his|their|is|are|was|were|be|i|we|he|she|they|"
                          r"want|wanna|gonna|like|um|uh|er|well|also|plus|maybe|let|let's|lets|tell|ask|make|can|could|would|should|will|i'm|i'd|i'll|just|into|than|as)$", re.I)
_EOU_DONE_EN = re.compile(r"(^(yes|yeah|yep|no|nope|okay|ok|sure|fine|a|b|one|two|option (a|b|one|two)|the (first|second)( one)?|first( one)?|second( one)?)$|\b(please|thanks|thank you|that's it|that's all|right now|go ahead)$)", re.I)


def eou_heur(text, lang, choices=()):
    """中间识别结果 → 'done'（像是说完了）/ 'open'（明显只说了一半）/ 'unk'。只看文字，零延迟。"""
    raw = (text or '').strip()
    if not raw: return 'open'
    comma = bool(re.search(r'[，、：,:;；]$', raw))
    t = re.sub(r'[\s。，、！？!?,.:：;；…]+$', '', raw)
    if len(t) <= 1 and not re.fullmatch(r'[ABab好行对不]', t or ''): return 'open'   # 刚开口
    zh = bool(re.search(r'[一-鿿]', t))
    if zh:
        if _EOU_OPEN_ZH.search(t) or comma: return 'open'
    elif _EOU_OPEN_EN.search(t) or comma:
        if not _EOU_DONE_EN.search(t): return 'open'
    for c in choices or ():   # 把某个选项几乎原样念出来了
        c2 = re.sub(r'[\s。，、！？!?,.]+', '', c or '').lower(); t2 = re.sub(r'[\s。，、！？!?,.]+', '', t).lower()
        if c2 and len(t2) >= max(4, len(c2) * 0.8) and (t2 in c2 or c2 in t2): return 'done'
    if (_EOU_DONE_ZH if zh else _EOU_DONE_EN).search(t): return 'done'
    return 'unk'


def eou_llm(sess, text, lang, timeout=1.6):
    """规则拿不准时问快模型：这句话说完整了没有。三个同时问，谁先答用谁；失败返回 None。"""
    ctx = ''
    if sess:
        ep = sess['eps'][-1]; ch = (ep.get('choices') or [])[:2]
        ctx = f'（情境：有声互动剧的选择点，问题是“{ep.get("prompt", "")}”，两个选项：A {ch[0] if ch else ""}；B {ch[1] if len(ch) > 1 else ""}。听众可以选，也可以自由说想让剧情怎么走。）\n'
    pr = (f'语音输入的中间识别结果（说话人刚停顿了一下，可能有同音错字）：“{text}”\n{ctx}'
          '判断：这句话是不是已经说完整了（一个完整的回答、选择或指令，可以直接拿去执行）？还是明显只说了一半、后面还要接着说'
          '（比如停在连接词或“我想让他”上、动词后面缺宾语、列举到一半、句子意思悬着）？拿不准时，短句当作说完，长句里结尾悬着的当作没说完。\n'
          '只输出 JSON：{"done": true} 或 {"done": false}')
    box, ev = {}, threading.Event()
    def ask(m):
        try:
            r = fast_chat(pr, 20, timeout, m); j = json.loads(r[r.find('{'):r.rfind('}') + 1])
            if isinstance(j.get('done'), bool) and not ev.is_set(): box['v'] = j['done']; ev.set()
        except Exception: pass
    for m in UNDERSTAND_MODELS: threading.Thread(target=ask, args=(m,), daemon=True).start()
    ev.wait(timeout + 0.2)
    return None if 'v' not in box else ('done' if box['v'] else 'open')


def her_understood(text, u, via, lang):
    """她自由说的话 + 理解后的意思，给编剧（按她的指令写）"""
    heard = ((u or {}).get('heard') or '').strip() or text
    her = her_said(heard, via, lang)
    if u and u.get('intent'):
        her += (f'\n（理解：{u["intent"]}）' if lang == 'zh' else f'\n(Meaning: {u["intent"]})')
    if heard != text:
        her += (f'（原始识别：“{text}”）' if lang == 'zh' else f' (raw recognition: "{text}")')
    return her


def same_words(a, b):
    """她说的和选项是不是几乎逐字相同（去标点空格大小写后相似度 ≥ 0.82，且长度相差不到三成）"""
    import difflib
    x = re.sub(r'[\W_]+', '', (a or '').lower()); y = re.sub(r'[\W_]+', '', (b or '').lower())
    if not x or not y or abs(len(x) - len(y)) > 0.3 * max(len(x), len(y)): return False
    return x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.82


def prepare_next(sess, text, via, gate=None):
    """她用语音/打字回了一句：先理解（改同音错字、判断是不是选项、概括她的意图，最多 2.6 秒），再按理解后的版本开写下一集。
    11-10：先按原话写时，编剧把“她问 Sienna 刚才那通电话是谁”写反成了“你的电话”——意图必须一起给编剧。返回 {'n','text','matched','free','her'}。"""
    n = len(sess['eps']) + 1; ch = (sess['eps'][-1].get('choices') or [])[:2]
    out = {'n': n, 'text': text, 'matched': None, 'free': None}
    k = pick_letter(text) if len(ch) >= 2 else None
    if k is not None: out['matched'] = ch[k]; return out
    u = understand(sess, text, 2.0) if text and len(ch) >= 2 else None  # 长连接后通常 0.9–1.5 秒；最多等 2 秒，超时按原话写
    heard = ((u or {}).get('heard') or '').strip()
    # 11-11 她要求：严格按她说的写。原来模型觉得“意思差不多”就换成现成选项（她说“我就不走，今天就待在这了”，被换成选项
    # “我不上车，我要站在这儿亲眼看看下来的是什么人”，后面按选项写，她的话就没了）。现在只有她几乎逐字念了选项才算选项，其余一律按她的原话现写。
    if u and u['kind'] in ('C1', 'C2'):
        c = ch[0 if u['kind'] == 'C1' else 1]
        if same_words(text, c) or same_words(heard, c): out['matched'] = c; return out
        u['kind'] = 'FREE'
    k = pick_letter(heard) if heard and len(ch) >= 2 else None
    if k is not None: out['matched'] = ch[k]; return out
    br = sel_bridge(sess, n - 1)
    her = her_understood(text, u, via, sess['lang']) if u else her_said(text, via, sess['lang'])
    out['free'] = start_job(run_episode, sess, next_msg(sess, her, br and br['text']), None, her, gate); out['her'] = her
    return out


def pre_next(sess, text):
    """识别一出结果就开始（她手机上的往返还没回来，中转先动手，省 1–2 秒）"""
    n = len(sess['eps']) + 1
    if not text.strip() or sess['eps'][-1].get('ending') or (sess.get('_pre') or {}).get('n') == n: return
    pre = sess['_pre'] = {'n': n, 'text': text, 'ev': threading.Event(), 'res': None}
    try: pre['res'] = prepare_next(sess, text, 'voice')
    except Exception: traceback.print_exc()
    finally: pre['ev'].set()


def _norm_said(t): return re.sub(r'[\s。，、！？!?,.:：;；…"“”\'‘’]+', '', (t or '')).lower()


def spec_pre(sess, text, live=False):
    """她还在说（或刚说完）就开始准备下一集：理解 + 开写。返回 pre 对象（/api/next 认领它）。
    live=False：边说边预写——配音和“记进剧情”都先拦着（gate），等 asr_stream 确认；live=True：她已经说完，照常全速。"""
    pre = {'n': len(sess['eps']) + 1, 'text': text, 'ev': threading.Event(), 'res': None, 'dead': False, 't0': time.time(),
           'gate': {'tts': threading.Event(), 'ok': threading.Event()}}
    if live: pre['gate']['tts'].set(); pre['gate']['ok'].set()
    def go():
        try: pre['res'] = prepare_next(sess, text, 'voice', pre['gate'])
        except Exception: traceback.print_exc()
        finally:
            pre['ev'].set()
            if pre['dead']: spec_kill(pre)
    threading.Thread(target=go, daemon=True).start()
    return pre


def spec_kill(pre):
    """预写作废（她接着说了别的）：取消那一集，放开等待（不会再配音、不会记进剧情）"""
    pre['dead'] = True
    jid = (pre.get('res') or {}).get('free')
    if jid: cancel_job(jid)
    pre['gate']['tts'].set(); pre['gate']['ok'].set()   # 取消标记已打：放开后各线程自己退出


def cancel_job(jid):
    j = JOBS.get(jid)
    if j: j['_cancel'] = True


CUE_OK = {}


def cue_text(sess, ep, n):
    """集尾的“旁白提问”：把选择点改写成贴着耳朵问她的一句话（闭眼听模式念给她听，然后开麦）。"""
    lang = sess['lang']; ch = (ep.get('choices') or [])[:2]
    first = n <= 2
    if lang == 'zh':
        pr = (f'有声连载剧的集尾选择点：\n情境：{ep.get("prompt", "")}\n选项一：{ch[0] if ch else ""}\n选项二：{ch[1] if len(ch) > 1 else ""}\n\n'
              '把它改写成旁白贴着耳朵问听众“你”的一段话，口语、自然、带悬念，40–70 个字：先一句点出此刻的处境，再用“是……还是……”把两个选项的意思说出来（不要念“选项一/二”，不要引号），'
              + ('最后一句告诉她：直接说出来就好，也可以说别的；不出声，故事也会自己往下走。' if first else '最后用一句很短的话请她回答。') + '只输出这段话。')
    else:
        pr = (f'End-of-episode choice in an audio drama:\nSituation: {ep.get("prompt", "")}\nOption one: {ch[0] if ch else ""}\nOption two: {ch[1] if len(ch) > 1 else ""}\n\n'
              'Rewrite it as the narrator asking the listener "you", close to the ear: spoken, natural, suspenseful, 25–45 words. One line on the moment, then "...or..." with the meaning of both options (no "option one", no quotes), '
              + ('and finish by telling her she can just say it out loud, or say anything else; if she stays quiet, the story will carry on.' if first else 'and a very short invitation to answer.') + ' Output only that.')
    try:
        t = fast_chat(pr, 220, 10).strip().strip('"“”')
        if len(t) > 8: return t
    except Exception:
        pass
    if lang == 'zh':
        return f'{ep.get("prompt", "")}……{ch[0] if ch else ""}？还是，{ch[1] if len(ch) > 1 else ""}？' + ('直接说出来就好；不出声，故事也会自己往下走。' if first else '你说。')
    return f'{ep.get("prompt", "")} {ch[0] if ch else ""}? Or… {ch[1] if len(ch) > 1 else ""}?' + (' Just say it out loud — or stay quiet, and the story carries on.' if first else ' Tell me.')


def make_cue(sess, n):
    """第 n 集结尾的提问配音（旁白声）。第 1 集按剧/语言存盘复用，实时集存在会话里。"""
    ep = next((e for e in sess['eps'] if e['n'] == n), None)
    if not ep: return None
    key = (sess['sid'], n)
    if key in CUE_OK: return dict(CUE_OK[key], bridge=sel_bridge(sess, n, False))
    bth = threading.Thread(target=ep_bridge, args=(sess, n), daemon=True); bth.start()  # 过渡句和提问同时做
    f = CACHE / 'cue' / f'{sess["series"]}.{sess["lang"]}.json' if n == 1 else None
    if f and f.exists():
        CUE_OK[key] = json.load(open(f)); bth.join(3); return dict(CUE_OK[key], bridge=sel_bridge(sess, n, False))
    t = cue_text(sess, ep, n + 1)
    u = tts_hedged(sess['series'], 'NARR', t, sess['lang'], 2, sess.get('tts', 'v4'))
    d = {'url': u, 'text': t, 'n': n}
    CUE_OK[key] = d
    if f: f.parent.mkdir(parents=True, exist_ok=True); json.dump(d, open(f, 'w'), ensure_ascii=False)
    bth.join(2)  # 一般和提问一起好；没好就先给通用句，她回答时再定
    return dict(d, bridge=sel_bridge(sess, n, False))


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
MAX_CALL_TURNS = 20  # 11-09 她不说话他也接着说，每段都算一轮，放宽
FILLERS = {'zh': ['嗯。', '嗯，我在听。', '我在。', '嗯，我知道。'], 'en': ['Mm.', "I'm listening.", "I'm here.", 'Yeah. I know.']}
GREETS = {'zh': ['喂？'], 'en': ['Hey.']}
# 他每轮的第一句从这些短反应里选（预先配好音）：她说完 → 识别 → 快模型写出第一句，马上就有声音，不用等配音（11-08）
REACTS = {'zh': ['嗯？', '嗯。', '等等。', '你说。', '……真的？', '好。', '行。', '什么？', '哈。', '我在听。', '慢点说。', '……嗯。'],
          'en': ['Mm?', 'Mm.', 'Wait.', 'Go on.', '…Really?', 'Okay.', 'Yeah.', 'What?', 'Ha.', "I'm listening.", 'Slow down.', '…Yeah.']}
react_key = lambda t: re.sub(r'[\s\W_]+', '', (t or '').lower())
REACT_URLS = {}  # (series, who, lang) -> {key: url}  # 接通那一刻马上说的第一声（预先配好），盖住他第一句话的生成时间
# 11-09 她说完，他马上说的一整句过渡话（预先配好，0 等待；不是单个语气词）。模型从这句后面接着写。
BRIDGES = {  # 约 4 秒一句，盖住第一句正文的配音时间
 'zh': {'q': ['你问这个啊……好，那我就跟你说实话，你听了别笑我。', '这个问题，我其实想过很多遍了，我得好好回答你。', '你这么问，那我也不瞒你了，我慢慢跟你说。', '问得好。你等我一下，我想想该从哪里说起。'],
        's': ['我听着呢。你这么一说，我倒是突然想起一件事来。', '真的吗？那我可得好好跟你说说，你先别挂。', '你刚才这句话啊，我大概会记很久很久。', '哈，你总是这样，让我一下子都接不上话了。', '好，那既然这样，我也跟你说一句实话吧。', '等等，你刚才那句话，让我先缓一缓。']},
 'en': {'q': ["You're asking me that… okay. I'll be honest with you, just don't laugh.", "That's a good question. I've actually thought about it a lot, so let me tell you.", "Since you asked, I'm not gonna hide it from you. Here's the thing.", "Okay. Give me a second, I'm figuring out where to even start."],
        's': ["I'm listening. And you know, that actually reminds me of something.", "Really? Okay, then I've got something to tell you too. Don't hang up.", "Hm. I think I'm gonna remember you said that for a long time.", "Ha. You always do this — you leave me a little speechless.", "Okay. Then let me be honest with you too, for a second.", "Wait. Hold on. Let me just take that in for a moment."]}}
BRIDGE_URLS = {}  # (series, who, lang) -> {'q': [(text, url)], 's': [...]}
_BRIDGE_MAKING = set()


def bridge_urls(series, who, lang, make=True):
    k = (series, who, lang)
    if k in BRIDGE_URLS: return BRIDGE_URLS[k]
    f = CACHE / 'fillers' / f'bridge2.{series}.{who}.{lang}.json'
    if f.exists():
        BRIDGE_URLS[k] = {g: [tuple(x) for x in v] for g, v in json.load(open(f)).items()}; return BRIDGE_URLS[k]
    if not make or k in _BRIDGE_MAKING: return None
    _BRIDGE_MAKING.add(k)
    try:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(5) as ex:
            d = {g: list(zip(ts, ex.map(lambda t: tts(series, who, t, lang, CALL_TTS), ts))) for g, ts in BRIDGES[lang].items()}
        f.parent.mkdir(parents=True, exist_ok=True); json.dump(d, open(f, 'w'), ensure_ascii=False)
        BRIDGE_URLS[k] = {g: [tuple(x) for x in v] for g, v in d.items()}; return BRIDGE_URLS[k]
    finally: _BRIDGE_MAKING.discard(k)


QWORDS = re.compile(r'[?？]|吗|呢$|什么|怎么|为什么|为啥|哪|谁|几|是不是|有没有|能不能|会不会|要不要|可不可以|多少', re.I)
QEN = re.compile(r'\?|^(what|why|how|where|who|when|which|do|does|did|are|is|can|could|will|would|should|have|has)\b', re.I)
def pick_bridge(c, text):
    b = bridge_urls(c['series'], c['who'], c['lang'], make=False)
    if not b: return None
    g = 'q' if (QWORDS.search(text) if c['lang'] == 'zh' else QEN.search(text.strip())) else 's'
    used = c.setdefault('_bused', [])
    pool = [x for x in b.get(g, []) if x[0] not in used[-3:] and x[1]] or [x for x in b.get(g, []) if x[1]]
    if not pool: return None
    t, u = random.choice(pool); used.append(t)
    return {'who': c['who'], 'text': t, 'url': u}


THINKS = {'zh': ['让我想想。', '你这么问……', '嗯……我在想怎么跟你说。', '……这个问题。'], 'en': ['Let me think.', 'You asking me that…', "Mm… I'm figuring out how to say this.", '…That question.']}


def callers(sid):
    """能打电话的主角（voices.json 里 lead=true 的角色；三真四假有 Wes 和 Jasper 两个）"""
    w = WORLD[sid]; out = []
    for key, v in VOICES[sid].items():
        if key.startswith('_') or not v.get('lead'): continue
        ch = next((c for c in w['characters'] if c['name'].split()[0] == key or c['name'] == key), {})
        av = f'avatars/cast/{sid}.{key.replace(" ", "")}.jpg'  # 11-09：多角色的剧每人一张头像（来电、选人、通话页）
        out.append({'key': key, 'name': key, 'name_zh': ch.get('name_zh') or key, 'role_zh': ch.get('role_zh', ''), 'role_en': ch.get('role_en', ''), 'avatar': av if (APP / av).exists() else None, 'gender': ch.get('gender') or 'male'})
    return out


def greet_url(series, who, lang, make=True):
    """接通那声“喂？”单独缓存（每个角色、每种语言一句），/api/call/start 直接带回去，接通瞬间就能播（11-09）"""
    f = CACHE / 'fillers' / f'greet.{series}.{who}.{lang}.json'
    if f.exists(): return json.load(open(f)).get('url')
    full = CACHE / 'fillers' / f'{series}.{who}.{lang}.json'
    if full.exists():
        d = json.load(open(full))
        if isinstance(d, dict) and d.get('greet'): json.dump({'url': d['greet'][0]}, open(f, 'w')); return d['greet'][0]
    if not make: return None
    f.parent.mkdir(parents=True, exist_ok=True)
    u = tts(series, who, ('[quietly] ' + GREETS[lang][0]) if lang == 'en' else GREETS[lang][0], lang)
    json.dump({'url': u}, open(f, 'w')); return u


def load_reacts(series, who, lang):
    """中转重启后内存里的预配短反应没了（11-09 她打电话每轮第一句都要现配音）：从缓存文件读回来"""
    try:
        d = json.load(open(CACHE / 'fillers' / f'{series}.{who}.{lang}.json'))
        if isinstance(d, dict) and d.get('react'): REACT_URLS[(series, who, lang)] = {react_key(k): v for k, v in d['react'].items()}; return True
    except Exception: pass
    return False


def call_fillers(series, who, lang):
    """垫场声：她说完立刻播一句“嗯，我在听”，盖住他“想”的那几秒（11-05 她说这几句的音色最好）。第一次用时合成，之后缓存。"""
    f = CACHE / 'fillers' / f'{series}.{who}.{lang}.json'
    if f.exists():
        d = json.load(open(f))
        if isinstance(d, dict) and d.get('greet') and d.get('react'):
            REACT_URLS[(series, who, lang)] = {react_key(k): v for k, v in d['react'].items()}
            return d
        if not isinstance(d, dict): d = {'urls': d}  # 旧缓存只有垫场声，补上思考声
    else: d = None
    f.parent.mkdir(parents=True, exist_ok=True)
    import concurrent.futures as cf
    say = lambda t: tts(series, who, ('[quietly] ' + t) if lang == 'en' else t, lang)
    with cf.ThreadPoolExecutor(4) as ex:
        urls = d['urls'] if d else list(ex.map(say, FILLERS[lang]))
        think = (d or {}).get('think') or list(ex.map(say, THINKS[lang]))
        greet = (d or {}).get('greet') or list(ex.map(say, GREETS[lang]))
        react = (d or {}).get('react') or dict(zip(REACTS[lang], ex.map(say, REACTS[lang])))
    d = {'urls': urls, 'think': think, 'greet': greet, 'react': react}
    REACT_URLS[(series, who, lang)] = {react_key(k): v for k, v in react.items()}
    json.dump(d, open(f, 'w')); return d


CALL_RULES = {
 'zh': """这是一通电话，纯语音。你只演 {who}（{role}），对面是她（听众本人），她叫「{name}」。
- 只写 {who} 对着电话说的话，口语、短句，像真人深夜打电话；不要旁白、不要动作描写、不要括号。
- 每轮 5–7 句（第 1 轮开场 6–8 句），多说一点（11-09 她嫌太短、只听到语气词）：讲具体的细节、此刻在做什么、一段回忆或心里话，最后常常抛给她一个好回答的具体问题，引她开口。不要用“嗯/哈/好/行”这种语气词单独成句；第一句就说到点子上（12–30 个字），后面每句 10–40 个字。她沉默就回应沉默。
- 她随时可能打断你（记录里写着“被她打断”）：别把被打断的话原样再说一遍，先接她刚说的。
- 她没出声的时候，你自己把电话撑下去：接着讲一件具体的事、说一句心里话，或者问她一个很好回答的具体问题，引她开口；别反复问“你怎么不说话”，也别催她。
- 严格按人设和说话方式说话；只说他这时候知道的事，世界卡里的真相按节奏透露，不一次说破。
- 记得你们在剧里经历过的事（见“剧里到目前为止”），可以提起具体细节；她有明确想聊的方向就跟着她。
- 每轮往前推一点：问她一个问题、提出一个约定、说出一点心里话或一个小秘密。偶尔叫她的名字，不要每句都叫。
- 她可能说中文也可能说英文（语音识别可能有错字），照样听懂；你一律用中文回（人名保留英文），不要“亲爱的/宝贝”。可以在句首少量用 [softly] [quietly] [sighs] [chuckles softly] [exhales]，每轮最多 1 个。
- 通话到第 18 轮左右自然收尾，给一个让她想再打来的钩子，HANGUP: yes。""",
 'en': """This is a phone call, voice only. You play only {who} ({role}); on the other end is her (the listener), named "{name}".
- Write only what {who} says into the phone: short, natural late-night phone talk; no narration, no actions, no brackets.
- 5–7 lines per turn (6–8 for the opening turn) — say more: concrete details, what you're doing right now, a memory or a feeling, and often end with one easy, specific question that draws her in. Never make a bare interjection ("Mm." / "Ha." / "Okay.") its own line; make the first line get straight to the point (8–20 words), the rest under 25 words each. If she is silent, respond to the silence.
- She can interrupt you at any moment (the log says "cut off by her"): don't repeat what you were cut off saying; answer what she just said.
- When she stays quiet, carry the call yourself: tell her something specific, admit a small feeling, or ask one easy, concrete question that draws her in. Don't keep asking why she's quiet and don't push her.
- Stay strictly in character; only say what he knows now; reveal the world-card truths gradually, never all at once.
- Remember what you've been through in the story (see "story so far") and bring up specifics; if she steers, follow her.
- Each turn moves things a little: ask her something, make a promise, admit a feeling or a small secret. Use her name now and then, not every line.
- She may speak English or Chinese (speech recognition may have typos); understand her either way and always answer in English.
- No "baby/darling". Sparse tags at line start allowed: [softly] [quietly] [sighs] [chuckles softly] [exhales], at most one per turn.
- Around turn 18, wrap up naturally with a hook that makes her want to call again, HANGUP: yes."""}
CALL_FORMAT = """OUTPUT FORMAT — plain lines only, nothing else:
LINE: <his first line: short, straight to the point>
LINE: <what he says next>
LINE: <more>
LINE: <more>
LINE: <optional>
LINE: <optional>
LINE: <optional, often an easy question for her>
HANGUP: no"""


CALL_TTS = tts_engine(os.environ.get('CALL_TTS', 'flash'))  # 11-08 通话要像真打电话：默认 Turbo v2.5（每句约 3.4 秒，v4 约 5.2 秒）
CALL_FAST = tuple(os.environ.get('CALL_FAST_MODEL', 'qwen/qwen3.6-35b-a3b,deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,moonshotai/kimi-k3').split(','))  # 11-09 两个同时写，谁先出第一句用谁  # 11-06 实测第一句 2.7 秒（本机 Opus 19–22 秒）
CALL_FAST_EN = tuple(os.environ.get('CALL_FAST_MODEL_EN', 'deepseek/deepseek-v4.1-flash,moonshotai/kimi-k3,qwen/qwen3-30b-a3b-instruct-2507,qwen/qwen3.8-flash').split(','))  # 11-09 英文实测：deepseek/kimi 第一句约 1.9 秒；qwen3.6 英文常不带 LINE: 前缀


PREP = {}; PREP_TTL = 600  # 预备好的拨出电话第一轮（10 分钟内拨出就直接用）


def prep_key(series, who, lang, sess, name):
    return (series, who, lang, sess['sid'] if sess and sess['series'] == series else '', len(sess['eps']) if sess and sess['series'] == series else 0, name)


def purge_prep():
    for k, v in list(PREP.items()):
        if time.time() - v['t'] > PREP_TTL:
            PREP.pop(k, None); c = CALLS.get(v['cid'])
            if c and c.get('_prep'): CALLS.pop(v['cid'], None)


def warm_call_assets(series, who, lang):
    """这个角色的“喂？”、过渡句、短反应：没配过就后台配好（原来第一次打给新角色时现配，挤得第一句等了 11 秒）"""
    if (series, who, lang) not in REACT_URLS and not load_reacts(series, who, lang):
        threading.Thread(target=call_fillers, args=(series, who, lang), daemon=True).start()
    if not bridge_urls(series, who, lang, make=False): threading.Thread(target=bridge_urls, args=(series, who, lang), daemon=True).start()
    if not greet_url(series, who, lang, make=False): threading.Thread(target=greet_url, args=(series, who, lang), daemon=True).start()
    def precache():  # “喂？”、过渡句、垫话先下到中转：手机取 blob 时不用现拉谷歌存储
        us = [greet_url(series, who, lang, make=False)] + [u for v in (bridge_urls(series, who, lang, make=False) or {}).values() for _, u in v]
        f = CACHE / 'fillers' / f'{series}.{who}.{lang}.json'
        if f.exists():
            d = json.load(open(f)); us += (d.get('urls') or []) + (d.get('think') or []) if isinstance(d, dict) else []
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(6) as ex: list(ex.map(cache_line, [u for u in us if u]))
    threading.Thread(target=precache, daemon=True).start()


def call_system(c, lite=False):
    s, lang, w = c['series'], c['lang'], WORLD[c['series']]
    ch = next((x for x in w['characters'] if x['name'].split()[0] == c['who'] or x['name'] == c['who']), w['characters'][0])
    if lite: w = {k: w[k] for k in ('premise_zh', 'premise_en', 'her', 'truths', 'tone', 'rules') if k in w}  # 快模型用精简版，提示词短一半
    role = ch.get('role_zh' if lang == 'zh' else 'role_en') or ch.get('role_zh', '')
    nt = neutral(s)
    head = (f'你是{"" if nt else "女性向"}互动音频剧的角色演员，现在在电话里演 {c["who"]}。' if lang == 'zh' else f'You are voicing {c["who"]} live on a phone call in a{"n" if nt else " women-focused"} interactive audio drama.')
    return '\n\n'.join([head, '世界卡（内部资料）：\n' + json.dumps(w, ensure_ascii=False),
                        '这个角色：\n' + json.dumps(ch, ensure_ascii=False),
                        CALL_RULES[lang].format(who=c['who'], role=role, name=c['name']) + ('\n- ' + POV_NOTE[lang] if nt else ''), me_block(c.get('me'), lang), CALL_FORMAT])


def call_context(c):
    sess = get_sess(c.get('sid'))
    story = story_so_far(sess) if sess else ('（她还没听这部剧，就当你们刚认识不久，按第 1 集的处境打电话）' if c['lang'] == 'zh' else "(She hasn't started the series; call as if you've only just met, in Episode 1's situation.)")
    cut = '（说到这里被她打断）' if c['lang'] == 'zh' else ' (cut off by her)'
    turns = '\n'.join((f'她：{t["her"]}\n{c["who"]}：' + ' / '.join(t['lines']) + (cut if t.get('cut') else '')) for t in c['turns'])
    return story, turns


def run_call(job, c, her, spec=None, bridge=None):
    """一轮通话。spec={'base': 轮数}：预先生成（她还没选）——只合成第一句，不记进通话；她点了这条快捷回复（commit_spec）才补合成其余句并记进通话。"""
    t0 = time.time(); lang = c['lang']; n = len(c['turns']) + 1
    if (c['series'], c['who'], lang) not in REACT_URLS: load_reacts(c['series'], c['who'], lang)
    out = {'lines': [], 'choices': [], 'hangup': False}; job['call'] = out; job['t'] = {}; ths = []; raws = []
    job['_raws'] = raws; job['_her'] = her; job['_n'] = n; job['_ths'] = ths; job['_started'] = set()
    if bridge:  # 他已经先说了这句（预先配好），正文从它后面接
        out['lines'].append(dict(bridge)); raws.append(bridge['text']); job['_started'].add(0)
        job['status'] = 'voicing'; job['t'] = {'l0': 0, 'bridge': True}

    def synth(i, text):
        if job.get('_canceled'): out['lines'][i]['url'] = ''; return  # 她已经打断了这一轮，后面的句子不再配音
        k = i - (1 if bridge else 0)  # 第一句正文三路、第二句两路并发（Waku 每句 4–9 秒且波动大，取最快的）
        hn = 1 if c.get('_prep') else (CALL_HEDGE[k] if 0 <= k < len(CALL_HEDGE) else 1)  # 预备通话不赶时间，一路就够
        try:
            u = tts_hedged(c['series'], c['who'], text, lang, hn, c.get('tts', 'flash'), CALL_POOL)
            cache_line(u)  # 11-10 先下到中转（手机经 /api/a 取 blob 时不再现拉谷歌存储，接通原来卡到 6.5 秒）
            out['lines'][i]['url'] = u
        except Exception: out['lines'][i]['url'] = ''
        job['t'][f'l{i}'] = round(time.time() - t0, 2)
    job['_synth'] = synth

    def on_line(k, v):
        if k == 'LINE' and v and len(out['lines']) < (8 if n == 1 else 7):
            if bridge and len(out['lines']) == 1 and difflib.SequenceMatcher(None, react_key(v), react_key(bridge['text'])).ratio() >= 0.5: return  # 有的模型会把过渡句再写一遍
            if bridge and len(out['lines']) == 1 and react_key(re.sub(r'\[[^\]]*\]\s*', '', v)) in {react_key(x) for x in REACTS[lang]}: return  # 过渡句后面不再接单个语气词
            if n == 1 and not out['lines']:  # 接通时已经播过预先配好的“喂？/Hey.”，第一句别再打招呼
                v = re.sub(r'^\s*(\[[^\]]*\]\s*)?(喂+|嗨|(?:hey|hi|hello)\b)[\s,，。.!！?？—–-]*', lambda m: m.group(1) or '', v, flags=re.I).strip()
                v = re.sub(r'^((?:\[[^\]]*\]\s*)?)([a-z])', lambda m: m.group(1) + m.group(2).upper(), v)
                if not v: return
                if react_key(re.sub(r'\[[^\]]*\]\s*', '', v)) in {react_key(x) for x in REACTS[lang]}: return  # 第 1 轮“喂？”之后不要再接“嗯？”，直接说正事
            i = len(out['lines']); out['lines'].append({'who': c['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', v), 'url': None}); raws.append(v)
            pre = (REACT_URLS.get((c['series'], c['who'], lang)) or {}).get(react_key(re.sub(r'\[[^\]]*\]\s*', '', v))) if i == 0 else None
            if pre:  # 预先配好的短反应：不用等配音
                out['lines'][0]['url'] = pre; job['_started'].add(0); job['status'] = 'voicing'; job['t'].setdefault('first_line', round(time.time() - t0, 2)); job['t']['l0'] = job['t']['first_line']; job['t']['react'] = True
                return
            job['status'] = 'voicing'; job['t'].setdefault('first_line', round(time.time() - t0, 2))
            if spec and i > 1 and not job.get('_committed'): return  # 预先生成先配前两句（沉默续说最常用，11-09），其余等真用到再配
            job['_started'].add(i)
            th = threading.Thread(target=synth, args=(i, v), daemon=True); th.start(); ths.append(th)
        elif k in ('C1', 'C2') and v: out['choices'].append(v)
        elif k == 'HANGUP': out['hangup'] = v.lower().startswith('y')
    story, turns = call_context(c)
    g = GREETS[lang][0]
    if c['direction'] == 'incoming' and n == 1:
        ask = f'他主动打给她。电话刚接通，他已经说了一声“{g}”，接着往下说（别再说“喂”）。' if lang == 'zh' else f'He is calling her. The call just connected; he has already said "{g}" — continue from there (don\'t greet again).'
    elif n == 1:
        ask = f'她主动打给他。他接起电话，已经说了一声“{g}”，接着往下说（别再说“喂”）。' if lang == 'zh' else f'She is calling him. He picked up and already said "{g}" — continue from there (don\'t greet again).'
    else:
        ask = her
    if bridge:
        ask += (f'\n他已经先回了一句：“{bridge["text"]}”——从这句话后面直接接着说（别重复它，也别再用“嗯/哈/好”这种语气词开头），第一句就说到点子上。' if lang == 'zh'
                else f'\nHe has already answered with: "{bridge["text"]}" — continue straight on from it (don\'t repeat it, don\'t open with "Mm/Ha/Okay"); get to the point in the first line.')
    pace = ''
    if n >= MAX_CALL_TURNS - 2: pace = '（该收尾了，1–2 轮内挂断。）' if lang == 'zh' else '(Time to wrap up within 1–2 turns.)'
    if n >= MAX_CALL_TURNS: pace = '（这是最后一轮，说再见，HANGUP: yes。）' if lang == 'zh' else '(Last turn: say goodbye, HANGUP: yes.)'
    msg = (f'剧里到目前为止：\n{story}\n\n这通电话到目前为止：\n{turns or "（刚接通）"}\n\n第 {n} 轮。{ask}{pace}' if lang == 'zh' else
           f'Story so far:\n{story}\n\nThis call so far:\n{turns or "(just connected)"}\n\nTurn {n}. {ask}{pace}')
    try:
        c['_got_lines'] = False
        # 11-08：第 1 轮也用快模型（原来 Opus 要 19–22 秒才接通）；第 1 轮用完整世界卡，之后精简
        write_episode(c, msg, on_line, sysm=call_system(c, lite=n > 1), fast_model=CALL_FAST_EN if lang == 'en' else CALL_FAST)
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
    with c.setdefault('_tlock', threading.Lock()):
        if not job.get('_appended'):
            job['_appended'] = True
            c['turns'].append({'her': her if n > 1 else '（接通）', 'lines': [l['text'] for l in out['lines']]})
    job['status'] = 'done'
    if job.get('_canceled'): return
    log('call-' + c['cid'], {'turn': n, 'her': her, 'writer': job.get('writer'), 'spec': bool(job.get('_committed')), 't': job['t'], 'out': out, 'at': time.strftime('%F %T')})
    if not out['hangup'] and c['cid'] in CALLS: start_specs(c, out['choices'])


def asr_local(data, ctype, lang, hint='', fast=True, choice=False):
    """本机识别（unscripted_asr.py 8917）。hint：人名/他刚说的话/选项，帮识别认对专有名词（11-09 她说识别不准）"""
    from urllib.parse import quote
    req = U.Request('http://127.0.0.1:8917/asr', data=data, headers={'Content-Type': ctype or 'audio/wav', 'X-Lang': lang, 'X-Hint': quote((hint or '')[:300]), 'X-Fast': '1' if fast else '0', 'X-Choice': '1' if choice else '0'})
    return (json.loads(op.open(req, timeout=30).read()).get('text') or '').strip()


def call_hint(c):
    names = [c['who'], c.get('name') or '']
    last = (c['turns'][-1]['lines'] if c['turns'] else [])[-2:]
    return '，'.join(x for x in names if x) + ('。' + ' '.join(last) if last else '')


import difflib
def echo_of_him(c, text, extra=None):
    """锁屏外放时他的声音会被录进去：识别结果和他最近说的话很像就当回声丢掉"""
    t = re.sub(r'[\s\W_]+', '', text.lower())
    if len(t) < 2: return True
    recent = [l for tt in c['turns'][-2:] for l in tt['lines']] + list(extra or [])
    for l in recent:
        ll = re.sub(r'[\s\W_]+', '', l.lower())
        if ll and (t in ll or difflib.SequenceMatcher(None, t, ll).ratio() >= 0.55): return True
    return False


def ear_feed(c, data, ctype, end=False):
    """锁屏通话：手机每 ~2 秒传一段录音（锁屏后网页没法测音量），这里解码拼起来，用能量检测找“她说完的一句”
    （说了 ≥0.3 秒、之后静 ≥1 秒）。返回说完的那段 16k 单声道 PCM，没有就 None。"""
    import array, tempfile
    with tempfile.NamedTemporaryFile(suffix='.mp4' if 'mp4' in (ctype or '') else '.webm', delete=False) as f: f.write(data); src = f.name
    try:
        pcm = subprocess.run([FF, '-v', 'error', '-i', src, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, timeout=20).stdout
    finally: os.unlink(src)
    E = c.setdefault('_ear', {'buf': bytearray(), 'start': None, 'voiced': 0, 'quiet': 0, 'floor': 300.0})
    E['buf'] += pcm
    a = array.array('h'); a.frombytes(bytes(E['buf'][len(E['buf']) - len(pcm):]) if pcm else b'')
    fr = 480  # 30 ms
    base = (len(E['buf']) - len(pcm)) // 2
    done = None
    for i in range(0, len(a) - fr + 1, fr):
        x = a[i:i + fr]; rms = (sum(v * v for v in x) / fr) ** 0.5
        th = max(700.0, E['floor'] * 3)
        if rms > th:
            if E['start'] is None: E['start'] = max(0, base + i - 8000)  # 0.5 秒前开始，别吃掉第一个字
            E['voiced'] += 0.03; E['quiet'] = 0
        else:
            if E['start'] is None: E['floor'] = E['floor'] * 0.97 + rms * 0.03
            else: E['quiet'] += 0.03
        # 锁屏时她句中停顿常有 0.8 秒，等 1 秒再算说完；已经说了 2 秒以上（长回答、边想边说）就等 1.6 秒，别把一段话切断（11-09）
        if E['start'] is not None and E['quiet'] >= (1.0 if E['voiced'] < 2 else 1.6):
            if E['voiced'] >= 0.3: done = bytes(E['buf'][E['start'] * 2:(base + i + fr) * 2])
            E['start'] = None; E['voiced'] = 0; E['quiet'] = 0
    if end and not done and E['start'] is not None and E['voiced'] >= 0.3:  # 最后一段（说到上限了）：说到哪算哪
        done = bytes(E['buf'][E['start'] * 2:]); E['start'] = None; E['voiced'] = 0; E['quiet'] = 0
    if E['start'] is None and len(E['buf']) > 16000 * 2 * 6: del E['buf'][:len(E['buf']) - 16000 * 2 * 2]  # 不在说话时只留最后 2 秒
    if done:
        import io, wave
        bio = io.BytesIO(); w = wave.open(bio, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(done); w.close()
        return bio.getvalue()
    return None


BC_ZH = set('嗯 嗯嗯 嗯哼 哦 噢 啊 嗨 喂 好 好的 对 对啊 对对 是 是啊 哈 哈哈 嘿 嗯呢 行 唔 呃'.split())
BC_EN = set('hi hey hello mm mhm mmhmm hmm yeah yep yes ok okay uh um huh oh ah right sure aha'.split())
def backchannel(text, lang):
    """他说着话时她随口应的一声（嗯/对/嗨/Hi/Yeah）：不算插话"""
    t = re.sub(r'[\s\W_]+', ' ', (text or '').lower()).strip()
    if not t: return True
    words = t.split()
    if all(w in BC_EN for w in words) and len(words) <= 3: return True
    z = t.replace(' ', '')
    if len(z) <= 1 or z in BC_ZH: return True
    if re.fullmatch(r'[嗯哦啊嗨喂好对是哈嘿呃唔]{1,3}', z): return True
    return False


def call_start_turn(c, text, prev, played, cut):
    """返回 (job id, 他马上说的过渡句 {text,url} 或 None)"""
    if cut or prev: cut_turn(c, prev, played)
    c['spec'] = {}
    b = pick_bridge(c, text)
    return start_job(run_call, c, her_said(text, 'voice', c['lang']), None, b), b


def cut_turn(c, job_id, played):
    """她插话打断：他这一轮只算她听到的前 played 句，记进通话（标“被她打断”），其余句子不再配音"""
    job = JOBS.get(job_id or '')
    with c.setdefault('_tlock', threading.Lock()):
        if job and job.get('call') is not None and not job.get('_appended') and job.get('_n') == len(c['turns']) + 1:
            job['_canceled'] = True; job['_appended'] = True
            n = job['_n']; her = job.get('_her') or ''
            c['turns'].append({'her': her if n > 1 else '（接通）', 'lines': [l['text'] for l in job['call']['lines'][:max(0, played)]], 'cut': True})
        elif c['turns'] and played >= 0:
            t = c['turns'][-1]; t['lines'] = t['lines'][:max(1, played)]; t['cut'] = True


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
    for ch in ['__silence__']:  # 11-08 通话改成纯语音（没有快捷回复了），只预先写“她没出声”这一种
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
    pl, ra = STATS.get(sid) or tuple(b.get('stats') or ('100K', 4.7))
    return {'id': sid, 'title': b['title'][lang], 'lead': (b.get('lead') or {}).get(lang, ''), 'hook': b['hook'][lang],
            'tags': [t[lang] for t in b.get('tags', [])], 'genres': b['genres'], 'accent': b['accent'], 'cover': b['cover'], 'avatar': b['avatar'], 'motion': MOTION.get(sid), 'visuals': vis_card(sid),
            'callers': [{'key': x['key'], 'name': x['name'] if lang == 'en' else x['name_zh'], 'role': x['role_en'] if lang == 'en' else x['role_zh'], 'avatar': x.get('avatar'), 'gender': x.get('gender')} for x in callers(sid)],
            'stats': {'plays': pl, 'rating': ra}, 'ep1': {'title': w[f'ep1_title_{lang}'], 'dur': c['dur'] if c else None, 'ready': bool(c), 'audio': c.get('audio') if c else None,
                    'visuals': (ep1_with_visuals(c, sid, lang) or {}).get('visuals') if c else None},  # audio：前端点播放先直接放，不等 /api/play 走隧道
            **series_about(sid, lang)}


def cast_of(sid, lang):
    """介绍页演员表：有配音的角色 + 旁白，每人带头像（build_cast_avatars.py）"""
    w = WORLD[sid]; cast = []
    for ch in w['characters']:
        v = VOICES[sid].get(ch['name'].split()[0]) or VOICES[sid].get(ch['name'])
        if not v: continue
        key = ch['name'].split()[0] if ch['name'].split()[0] in VOICES[sid] else ch['name']
        av = f'avatars/cast/{sid}.{key.replace(" ", "")}.jpg'   # 11-11 介绍页演员表每人一张头像
        cast.append({'name': ch['name'] if lang == 'en' else (ch.get('name_zh') or ch['name']), 'role': ch.get(f'role_{lang}') or ch.get('role_zh', ''),
                     'voice': v.get('zh_name') if lang == 'zh' else v.get('en'),
                     'avatar': f'{av}?v={int((APP / av).stat().st_mtime) % 1000000}' if (APP / av).exists() else None})   # ?v=：同名文件换了图（11-11 换成角色包主图），手机不拿旧缓存
    cast.append({'name': 'Narrator' if lang == 'en' else '旁白', 'role': 'Narrator' if lang == 'en' else '旁白', 'voice': VOICES['NARR']['zh_name'] if lang == 'zh' else VOICES['NARR']['en'], 'narr': True})
    return cast


def series_about(sid, lang):
    """简介 + 演员表。11-11 她截图：介绍页 About 一直是灰条——原来只在进详情页时单独请求一次，那一次失败（中转重启 / 换隧道）就再也不出。
    现在随剧集列表一起带回（手机还会缓存），详情接口只是兜底。"""
    w = WORLD[sid]
    return {'synopsis': w.get(f'synopsis_{lang}') or w.get(f'premise_{lang}'), 'cast': cast_of(sid, lang)}


def series_detail(sid, lang):
    return series_card(sid, lang)


# ---------------- 实时语音输入（11-11 她要求：输入框里边说边出字，像豆包输入法） ----------------
# 原来每 0.7 秒把整段录音重新 POST 一次，过隧道一个来回就要 0.8–2 秒，字出得又慢又一顿一顿。
# 改成一条 WebSocket：手机把麦克风的 16k PCM 每 ~85 毫秒发一小块，中转不停地把“到目前为止的全部声音”送本机识别（一次约 0.2–0.3 秒），
# 认出来就推回去；她说完手机发 end，中转做最后一遍（带选项提示 + 字母复认）并马上开写下一集。没有逐次请求的往返。
import struct, io, wave
WS_MAGIC = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def ws_read(rf):
    """读一帧：返回 (opcode, payload)；连接断了返回 None"""
    h = rf.read(2)
    if len(h) < 2: return None
    op_, ln = h[0] & 0x0f, h[1] & 0x7f
    if ln == 126: ln = struct.unpack('>H', rf.read(2))[0]
    elif ln == 127: ln = struct.unpack('>Q', rf.read(8))[0]
    if ln > 2_000_000: return None
    mask = rf.read(4) if h[1] & 0x80 else b''
    data = rf.read(ln) if ln else b''
    if len(data) < ln: return None
    if mask: data = bytes(b ^ mask[i & 3] for i, b in enumerate(data)) if ln < 64 else (int.from_bytes(data, 'big') ^ int.from_bytes((mask * (ln // 4 + 1))[:ln], 'big')).to_bytes(ln, 'big')
    return op_, data


def ws_send(wf, lock, text, op_=1):
    b = text.encode() if isinstance(text, str) else text
    n = len(b); head = bytes([0x80 | op_]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536 else bytes([127]) + struct.pack('>Q', n))
    with lock:
        wf.write(head + b); wf.flush()


def asr_stream(h, q):
    """h: 请求处理器（已确认是 WebSocket 升级）。q: 查询参数"""
    g = lambda k, d='': q.get(k, [d])[0]
    key = h.headers.get('Sec-WebSocket-Key') or ''
    acc = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode()).digest()).decode()
    h.wfile.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + acc + '\r\n\r\n').encode()); h.wfile.flush()
    h.close_connection = True
    try: h.connection.settimeout(25)
    except Exception: pass
    sess = get_sess(g('sid')); lang = g('lang') or (sess or {}).get('lang', '')
    hint = ''
    if sess:
        ch = (sess['eps'][-1].get('choices') or [])[:2]
        hint = '，'.join([k for k in VOICES[sess['series']] if not k.startswith('_')][:4] + [sess.get('name') or '']) + '。' + ' '.join(ch)
    from urllib.parse import quote
    buf = bytearray(); lock = threading.Lock(); st = {'end': False, 'closed': False, 'done': 0}
    t0 = time.time()

    def recog(pcm, final):
        b = io.BytesIO()
        with wave.open(b, 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
        req = U.Request('http://127.0.0.1:8917/asr', data=b.getvalue(), headers={'Content-Type': 'audio/wav', 'X-Lang': lang, 'X-Hint': quote(hint[:300]),
                                                                              'X-Choice': '1' if final and sess else '0', 'X-Partial': '0' if final else '1'})
        return json.loads(op.open(req, timeout=20).read())

    def quiet_cut(seg):
        """一长段里找个停顿切开（6–12 秒之间最长的一段安静，≥0.2 秒）；找不到就在 12 秒处切。返回字节偏移"""
        import array
        a = array.array('h'); a.frombytes(seg[6 * 32000:12 * 32000]); hop = 320
        e = [sum(x * x for x in a[i:i + hop]) / hop for i in range(0, len(a) - hop + 1, hop)]
        if not e: return 12 * 32000
        thr = max(sorted(e)[len(e) // 5] * 3, 90000.0)   # 比最安静的 20% 稍高（至少约 -40 dBFS）
        best, run, at = 0, 0, None
        for i, v in enumerate(e + [1e18]):
            if v < thr: run += 1
            else:
                if run > best: best, at = run, i - run // 2
                run = 0
        return (6 * 32000 + at * hop * 2) if best >= 10 and at is not None else 12 * 32000

    def tail_quiet(n):
        """到第 n 字节为止，结尾已经安静了多少秒（和这段话里最响的 0.1 秒比，低 20 dB 以上算安静；最多回看 2 秒）"""
        import array
        a = array.array('h'); a.frombytes(bytes(buf[max(0, n - 2 * 32000):n])); hop = 1600
        if len(a) < hop: return 0.0
        e = [sum(x * x for x in a[i:i + hop]) / hop for i in range(0, len(a) - hop + 1, hop)]
        st['peak'] = max(st.get('peak', 0), max(e))
        thr = max(st['peak'] * 0.01, 40000.0)   # -20 dB（至少约 -44 dBFS）
        k = 0
        for v in reversed(e):
            if v < thr: k += 1
            else: break
        return k * 0.1

    def join(head, t):
        if not head: return t
        return head + ('' if re.search(r'[一-鿿，。！？]$', head) or not t else ' ') + t

    def worker():
        last = ''; cut = 0; head = ''; same = 0; judged = set(); chs = ((sess['eps'][-1].get('choices') or [])[:2]) if sess else []
        # 11-12 提速（她说：语音输入完往下生成还是慢，要接近流式）：文字停住、读着不像半句话时就先按它理解 + 开写（spec_pre，配音先拦着）；
        # 她说完、最终识别就是这句 → 直接认领，已经写好的句子马上从这条连接推给手机（不等 /api/next 和 /api/job 的往返）。
        can_spec = bool(sess) and g('go') == '1' and not sess['eps'][-1].get('ending') and (sess.get('_pre') or {}).get('n') != len(sess['eps']) + 1
        sp = {'pre': None, 'n': 0}
        # 她可以一口气说到 60 秒：说过的前半段按停顿切开、认一次就定下来，每一遍只重认最近十来秒，出字速度不随时长变慢
        while not st['closed']:
            n = len(buf) // 2 * 2; final = st['end']
            if not final and (n < 9600 or n - st['done'] < 3200): time.sleep(0.03); continue   # 至少 0.3 秒声音；有 0.1 秒新声音才再认一遍
            st['done'] = n
            try:
                while n - cut > 14 * 32000:
                    k = quiet_cut(bytes(buf[cut:cut + 12 * 32000 + 640]))
                    head = join(head, (recog(bytes(buf[cut:cut + k]), False).get('text') or '').strip()); cut += k
                if final and last and len(_norm_said(last)) >= 6 and st.get('last_n', 0) and tail_quiet(n) >= (n - st['last_n']) / 32000 - 0.1:
                    r = {'text': None, 'reuse': True}   # 上一遍之后只有安静：那一遍的文字就是最终结果（短回答 / 字母仍然重认，带选项提示）
                else:
                    r = recog(bytes(buf[cut:n]), final and not head) if n - cut >= 3200 else {'text': ''}
            except Exception as e: r = {'text': '', 'error': repr(e)[:80]}
            text = last if r.get('reuse') else join(head, (r.get('text') or '').strip())
            try:
                if final:
                    pre = None; hit = False
                    if can_spec and text:   # 选择点上的回答：马上开写下一集（预写的那集正好是这句话就直接认领）
                        if sp['pre'] and _norm_said(sp['pre']['text']) == _norm_said(text): pre = sp['pre']; pre['text'] = text[:400]; hit = True
                        else:
                            if sp['pre']: spec_kill(sp['pre'])
                            pre = spec_pre(sess, text[:400], live=True)
                        sp['pre'] = None
                        pre['gate']['tts'].set(); pre['gate']['ok'].set(); sess['_pre'] = pre
                    elif sp['pre']: spec_kill(sp['pre']); sp['pre'] = None
                    ws_send(h.wfile, lock, json.dumps({'final': text, 'lang': r.get('lang'), 'ms': r.get('ms'), 'keep': bool(pre)}, ensure_ascii=False))
                    log('asr-stream', {'sid': g('sid'), 'final': text, 'sec': round(n / 32000, 1), 'asr_ms': r.get('ms'), 'spec': hit, 'head': round(time.time() - pre['t0'], 2) if hit else 0, 'at': time.strftime('%F %T')})
                    if pre:   # 写出一句推一句（最多 10 秒，或手机那边关了连接）：手机上文字跟着出来，不用等配音
                        t_end = time.time() + 10; sent = -1
                        try:
                            pre['ev'].wait(4); res = pre.get('res') or {}
                            if res.get('matched') is not None: ws_send(h.wfile, lock, json.dumps({'pre': {'n': pre['n'], 'matched': res['matched']}}, ensure_ascii=False))
                            job = JOBS.get(res.get('free') or '')
                            while job and time.time() < t_end and not st['closed']:
                                ls = ((job.get('ep') or {}).get('lines') or [])
                                if len(ls) > sent:
                                    sent = len(ls)
                                    ws_send(h.wfile, lock, json.dumps({'pre': {'n': pre['n'], 'job': job['id'], 'lines': [{'who': l['who'], 'text': l['text']} for l in ls]}}, ensure_ascii=False))
                                if job.get('status') in ('done', 'error', 'cancelled') or any(l.get('url') for l in ls): break   # 第一句配好了：之后走 /api/job
                                time.sleep(0.1)
                        except Exception: pass
                    break
                told = False
                if lang != 'zh' and n < 2 * 32000 and re.search(r'[\u4e00-\u9fff]', text): pass   # 英文版：开头两秒里冒出来的中文多半是误认（“嗯”“一”），不显示
                elif text and text != last and not re.fullmatch(r'[嗯啊呃哦唔额一。，,.!?！？\s]+', text):   # 刚开口那零点几秒常被认成“嗯”“一”：不推，等下一遍
                    last = text; same = 0; told = True
                    if sp['pre'] and _norm_said(sp['pre']['text']) != _norm_said(text): spec_kill(sp['pre']); sp['pre'] = None   # 她接着说了：预写的作废
                    ws_send(h.wfile, lock, json.dumps({'t': text, 'at': round(n / 32000, 2), 'eou': eou_heur(text, lang, chs)}, ensure_ascii=False))   # eou：这句话像不像说完了（手机据此决定安静多久算说完）
                elif text and text == last:
                    same += 1
                    e_now = eou_heur(text, lang, chs); q_now = tail_quiet(n)
                    if can_spec and e_now != 'open' and len(_norm_said(text)) >= 2:
                        # 文字没再变、声音也停了 0.3 秒：先按这句理解 + 开写（只花快模型，不配音）
                        if not sp['pre'] and sp['n'] < 4 and q_now >= 0.3: sp['pre'] = spec_pre(sess, text); sp['n'] += 1; print('spec start', repr(text[-20:]), 'quiet', q_now, flush=True)
                        if sp['pre'] and q_now >= (0.6 if e_now == 'done' else 0.9): sp['pre']['gate']['tts'].set()   # 安静够久，她多半说完了：放行配音
                    if same == 1 and text not in judged and eou_heur(text, lang, chs) == 'unk':   # 文字停住了（她停顿了）而规则拿不准：问一次快模型
                        judged.add(text)
                        def judge(tx=text):
                            tj = time.time(); v = eou_llm(sess, tx, lang)
                            print('eou', v, round(time.time() - tj, 2), repr(tx[-24:]), flush=True)
                            if v and not st['closed'] and not st['end']:
                                try: ws_send(h.wfile, lock, json.dumps({'eou': v, 'for': tx}, ensure_ascii=False))
                                except Exception: pass
                        threading.Thread(target=judge, daemon=True).start()
                if text and text == last: st['last_n'] = n   # 这一遍认到第 n 字节，文字就是 last
                if not told: ws_send(h.wfile, lock, json.dumps({'at': round(n / 32000, 2)}))   # 没有新字也报一声“听到第几秒了”：手机知道这边已经跟上她最后说的话（过隧道时中间结果会晚 1–2 秒，没跟上就判停会把半句话截断）
            except Exception: break
        st['closed'] = True
        if sp['pre']: spec_kill(sp['pre']); sp['pre'] = None   # 没等到她说完就断了：预写的作废
    th = threading.Thread(target=worker, daemon=True); th.start()
    try:
        while not st['closed'] and time.time() - t0 < 120:
            fr = ws_read(h.rfile)
            if fr is None: break
            op_, data = fr
            if op_ == 8: break
            if op_ == 9: ws_send(h.wfile, lock, data, 10); continue
            if op_ in (2, 0): buf.extend(data)
            elif op_ == 1 and data[:3] == b'end': st['end'] = True
    except Exception: pass
    if st['end']: th.join(16)   # 最后一遍还在认 / 还在推写好的句子：等它发完
    st['closed'] = True
    try: ws_send(h.wfile, lock, b'', 8)
    except Exception: pass


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a): pass

    def _send(self, code, body, ctype='application/json', cache='no-store'):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        # 11-11 公网隧道今天一个来回 3–10 秒：JSON 回包压一下（剧目列表 67 KB → 约 10 KB），慢的那一段少传
        gz = ctype == 'application/json' and len(b) > 1200 and 'gzip' in (self.headers.get('Accept-Encoding') or '')
        if gz:
            import gzip; b = gzip.compress(b, 5)
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        if gz: self.send_header('Content-Encoding', 'gzip'); self.send_header('Vary', 'Accept-Encoding')
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
            if u.path == '/api/asr/ws' and (self.headers.get('Upgrade') or '').lower() == 'websocket': return asr_stream(self, q)
            if u.path == '/api/series': return self._send(200, [series_card(s, lang) for s in BASE])
            if u.path == '/api/ep1pack':  # 11-11 所有剧第 1 集的文字稿 + 画面时间轴，一次给完（不建会话）：手机存好，点播放直接有字有画面，不用等 /api/play 过隧道
                out = {}
                for sid in BASE:
                    c = ep1_cached(sid, lang)
                    if c: out[sid] = ep1_with_visuals(c, sid, lang)
                return self._send(200, out)
            if u.path.startswith('/api/series/'):
                sid = u.path.split('/')[-1]
                return self._send(200, series_detail(sid, lang)) if sid in BASE else self._send(404, {'error': 'no series'})
            if u.path == '/api/call/fillers':
                sid, who = g('series'), g('who')
                if sid not in BASE or who not in VOICES[sid]: return self._send(404, {'error': 'no caller'})
                try: return self._send(200, call_fillers(sid, who, lang))
                except Exception as e: return self._send(500, {'error': str(e)[:200]})
            if u.path == '/api/cue':  # 闭眼听模式：集尾旁白把选择点念给她听（第一次约 5–8 秒，前端提前 45 秒取）
                sess = get_sess(g('sid'))
                if not sess: return self._send(404, {'error': 'session expired'})
                try: d = make_cue(sess, int(g('n') or len(sess['eps'])))
                except Exception as e: return self._send(500, {'error': str(e)[:200]})
                return self._send(200 if d else 404, d or {'error': 'no episode'})
            if u.path == '/api/specs':  # 她还在听这一集时，前端先取两个选项预先写好的下一集（前两句已配音），点选项就本地直接播，省掉公网往返
                sess = get_sess(g('sid'))
                out = {}
                for ch, sp in ((sess or {}).get('spec') or {}).items():
                    j = JOBS.get(sp['job'])
                    if not j or sp['base'] != len(sess['eps']) or j.get('status') == 'error' or not j.get('ep'): continue
                    L = j['ep']['lines']
                    if not (L and L[0].get('url')): continue
                    out[ch] = {'job': sp['job'], 'n': j['ep']['n'], 'ep': dict(j['ep'], lines=[dict(x) for x in L])}
                return self._send(200, {'n': len(sess['eps']) + 1 if sess else 0, 'specs': out, 'bridge': sel_bridge(sess, len(sess['eps']), False) if sess else None, 'beats': beat_card(sess) if sess else None})
            if u.path == '/api/a':  # 一句配音（本机缓存，带跨域头），手机取成 blob 提前放在本地
                f = cache_line(g('u'))
                return self._send(200, f.read_bytes(), 'audio/mpeg', 'public, max-age=604800, immutable') if f else self._send(404, {'error': 'no audio'})
            if u.path == '/api/ep':  # 任务丢了（中转重启）但这一集其实写完了：按会话日志把整集（含配音地址）还给前端
                sess = get_sess(g('sid'))
                if not sess: return self._send(404, {'error': 'session expired'})
                ep = (sess.get('_full') or {}).get(int(g('n') or 0))
                return self._send(200, {'ep': ep}) if ep else self._send(404, {'error': 'no episode'})
            if u.path == '/api/job':
                j = JOBS.get(g('id'))
                if j and g('wait') and g('have'):  # 长轮询：等到多一句有了配音、或写完/出错（最多 8 秒），省掉公网反复问
                    have = int(g('have') or 0); dl = time.time() + min(8, float(g('wait') or 8))
                    voiced = lambda: sum(1 for l in ((j.get('call') or j.get('ep') or {}).get('lines') or []) if l.get('url') is not None)
                    nl = int(g('nl')) if g('nl') else None; wrote = lambda: len(((j.get('call') or j.get('ep') or {}).get('lines') or []))
                    while time.time() < dl and j.get('status') not in ('done', 'error', 'ready') and voiced() <= have and (nl is None or wrote() <= nl): time.sleep(0.15)   # nl：手机已有几句文字——多写出一句也马上回（文字先显示）
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
        if u.path == '/api/call/say':  # 通话里她说的一段话（wav/webm 原始音频）：本机识别 + 打断处理 + 开始他下一轮，一次往返
            q = parse_qs(u.query); gq = lambda k, d='': q.get(k, [d])[0]
            if gq('k') != TOKEN: return self._send(403, {'error': 'bad key'})
            c = CALLS.get(gq('cid'))
            if not c: return self._send(404, {'error': 'call ended'})
            n = int(self.headers.get('Content-Length') or 0)
            data = self.rfile.read(n) if 0 < n <= 8_000_000 else b''
            t0 = time.time(); text = ''
            if data:
                try: text = asr_local(data, self.headers.get('Content-Type') or 'audio/wav', c['lang'], call_hint(c))
                except Exception as e: print('call/say asr', repr(e)[:120], flush=True)
            asr_ms = int((time.time() - t0) * 1000)
            if not text: return self._send(200, {'text': '', 'asr_ms': asr_ms})
            prev_job = JOBS.get(gq('prev') or '') or {}
            his_now = [l['text'] for l in ((prev_job.get('call') or {}).get('lines') or [])]
            # 11-09 她说“嗨/嗯/对”或者他自己的声音漏进麦克风，都不该打断他、让他重开一轮（原来每句都重开，他一直没声）
            if gq('cut') == '1' and (backchannel(text, c['lang']) or echo_of_him(c, text, his_now)):
                log('call-' + c['cid'], {'say_drop': text, 'asr_ms': asr_ms, 'at': time.strftime('%F %T')})
                return self._send(200, {'text': '', 'bc': text, 'asr_ms': asr_ms})
            jid, first = call_start_turn(c, text, gq('prev'), int(gq('played') or 0), gq('cut') == '1')
            log('call-' + c['cid'], {'say': text, 'asr_ms': asr_ms, 'cut': gq('cut') == '1', 'played': gq('played'), 'bridge': (first or {}).get('text'), 'at': time.strftime('%F %T')})
            return self._send(200, {'text': text, 'job': jid, 'asr_ms': asr_ms, 'first': first})
        if u.path == '/api/call/chunk':  # 锁屏通话：一小段录音；服务器拼起来断句，她说完一句就识别 + 开始他下一轮
            q = parse_qs(u.query); gq = lambda k, d='': q.get(k, [d])[0]
            if gq('k') != TOKEN: return self._send(403, {'error': 'bad key'})
            c = CALLS.get(gq('cid'))
            if not c: return self._send(404, {'error': 'call ended'})
            n = int(self.headers.get('Content-Length') or 0)
            data = self.rfile.read(n) if 0 < n <= 4_000_000 else b''
            if not data: return self._send(200, {'text': ''})
            with c.setdefault('_earlock', threading.Lock()):
                try: wav = ear_feed(c, data, self.headers.get('Content-Type') or '')
                except Exception as e: print('call/chunk', repr(e)[:160], flush=True); wav = None
                speaking = (c.get('_ear') or {}).get('start') is not None
            if not wav: return self._send(200, {'text': '', 'speaking': speaking})
            t0 = time.time()
            try: text = asr_local(wav, 'audio/wav', c['lang'], call_hint(c))
            except Exception as e: text = ''; print('call/chunk asr', repr(e)[:120], flush=True)
            prev_job = JOBS.get(gq('prev') or '') or {}
            his_now = [l['text'] for l in ((prev_job.get('call') or {}).get('lines') or [])]
            if not text or echo_of_him(c, text, his_now) or (gq('cut') == '1' and backchannel(text, c['lang'])):
                log('call-' + c['cid'], {'chunk_drop': text, 'at': time.strftime('%F %T')}); return self._send(200, {'text': ''})
            jid, first = call_start_turn(c, text, gq('prev'), int(gq('played') or 0), gq('cut') == '1')
            log('call-' + c['cid'], {'say': text, 'locked': True, 'asr_ms': int((time.time() - t0) * 1000), 'bridge': (first or {}).get('text'), 'at': time.strftime('%F %T')})
            return self._send(200, {'text': text, 'job': jid, 'first': first})
        if u.path == '/api/asr/chunk':  # 锁屏时的选择点：一小段录音，中转拼起来断句，她一说完就识别（不用等满 5 秒）
            q = parse_qs(u.query); gq = lambda k, d='': q.get(k, [d])[0]
            if gq('k') != TOKEN: return self._send(403, {'error': 'bad key'})
            sess = get_sess(gq('sid'))
            if not sess: return self._send(404, {'error': 'session expired'})
            n = int(self.headers.get('Content-Length') or 0)
            data = self.rfile.read(n) if 0 < n <= 4_000_000 else b''
            with sess.setdefault('_earlock', threading.Lock()):
                if gq('first') == '1': sess.pop('_ear', None)
                try: wav = ear_feed(sess, data, self.headers.get('Content-Type') or '', end=gq('end') == '1') if data else None
                except Exception as e: print('asr/chunk', repr(e)[:160], flush=True); wav = None
                E = sess.get('_ear') or {}
                speaking = E.get('start') is not None
            if not wav: return self._send(200, {'text': '', 'speaking': speaking, 'heard': speaking or bool(E.get('voiced'))})
            ch = (sess['eps'][-1].get('choices') or [])[:2]
            hint = '，'.join([k for k in VOICES[sess['series']] if not k.startswith('_')][:4] + [sess.get('name') or '']) + '。' + ' '.join(ch)
            try: text = asr_local(wav, 'audio/wav', sess['lang'], hint, choice=True)  # 选择点：短回答再用字母提示认一遍（A/B）
            except Exception as e: text = ''; print('asr/chunk asr', repr(e)[:120], flush=True)
            sess.pop('_ear', None)
            if text: threading.Thread(target=pre_next, args=(sess, text), daemon=True).start()  # 不等手机再发 /api/next，马上开写
            return self._send(200, {'text': text, 'done': True})
        if u.path == '/api/asr':  # 手机录的几秒语音 → 本机 faster-whisper（unscripted_asr.py，8917），中英文自动判断
            q = parse_qs(u.query)
            if q.get('k', [''])[0] != TOKEN: return self._send(403, {'error': 'bad key'})
            n = int(self.headers.get('Content-Length') or 0)
            data = self.rfile.read(n) if 0 < n <= 8_000_000 else b''
            if not data: return self._send(400, {'error': 'empty'})
            try:
                from urllib.parse import quote
                sess = get_sess(q.get('sid', [''])[0]); hint = ''
                part = q.get('partial', [''])[0] == '1'  # 她还在说：把已录到的先认出来显示在输入框里（11-11），不触发写下一集、不做字母复认
                if sess:  # 选项原文 + 角色名当提示，识别更准（11-09）
                    ch = (sess['eps'][-1].get('choices') or [])[:2]
                    hint = '，'.join([k for k in VOICES[sess['series']] if not k.startswith('_')][:4] + [sess.get('name') or '']) + '。' + ' '.join(ch)
                req = U.Request('http://127.0.0.1:8917/asr', data=data, headers={'Content-Type': self.headers.get('Content-Type') or 'audio/webm', 'X-Lang': q.get('lang', [''])[0] or (sess or {}).get('lang', ''), 'X-Hint': quote(hint[:300]), 'X-Choice': '1' if sess and not part else '0', 'X-Partial': '1' if part else '0'})
                r = json.loads(op.open(req, timeout=30).read())
                if sess and not part and q.get('go', [''])[0] == '1' and (r.get('text') or '').strip():  # 选择点上的回答：马上开写下一集
                    threading.Thread(target=pre_next, args=(sess, r['text'].strip()[:400]), daemon=True).start()
                return self._send(200, r)
            except Exception as e:
                return self._send(200, {'text': '', 'error': 'asr unavailable: ' + repr(e)[:120]})
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
            sess = SESS[sid] = {'sid': sid, 'series': series, 'lang': lang, 'name': name, 'me': (body.get('me') or '').strip()[:400], 'tts': tts_engine(body.get('tts')),
                                'eps': [{'n': 1, 'title': sc['title'], 'lines': [{'who': l['who'], 'text': re.sub(r'\[[^\]]*\]\s*', '', l['text'])} for l in sc['lines']], 'prompt': sc['prompt'], 'choices': sc['choices']}]}
            log(sid, {'start': True, 'series': series, 'lang': lang, 'name': name, 'me': sess['me'], 'tts': sess['tts'], 'at': time.strftime('%F %T')})
            c = ep1_cached(series, lang)
            if not body.get('prewarm'): threading.Thread(target=start_ep_specs, args=(sess,), daemon=True).start()  # 她听第 1 集的 3 分钟里，第 2 集已经按两个选项写好（批量预热第 1 集时不做）
            return self._send(200, {'sid': sid, 'ep': ep1_with_visuals(c, series, lang)} if c else {'sid': sid, 'job': start_job(ep1_job, series, lang)})
        if u.path == '/api/call/prepare':  # 11-10 她在剧详情/选人页时：先把他开口第一轮写好、前两句配好（拨出后约 1 秒就接通，原来 6–17 秒）
            series = body.get('series')
            if series not in BASE: return self._send(404, {'error': 'no series'})
            cs = callers(series); who = body.get('who') if body.get('who') in [x['key'] for x in cs] else cs[0]['key']
            warm_call_assets(series, who, lang)
            if body.get('warm_only'): return self._send(200, {'ok': True})
            name = (body.get('name') or ('你' if lang == 'zh' else 'you')).strip()[:24]
            sess = get_sess(body.get('sid'))
            key = prep_key(series, who, lang, sess, name)
            purge_prep()
            if key in PREP and PREP[key]['cid'] in CALLS: return self._send(200, {'ok': True, 'cached': True})
            cid = 'c' + time.strftime('%m%d%H%M') + rid(4)
            c = CALLS[cid] = {'cid': cid, 'series': series, 'lang': lang, 'name': name, 'who': who, 'me': (body.get('me') or (sess or {}).get('me') or '').strip()[:400], 'sid': sess['sid'] if sess and sess['series'] == series else None,
                              'direction': 'outgoing', 'turns': [], 'tts': body.get('tts') if body.get('tts') in ('turbo', 'flash') else CALL_TTS, '_prep': True}
            jid = rid(); JOBS[jid] = {'id': jid, 'status': 'writing', 'error': None, '_spec': True}
            threading.Thread(target=run_call, args=(JOBS[jid], c, '', {'base': 0}), daemon=True).start()
            PREP[key] = {'cid': cid, 'job': jid, 't': time.time()}
            return self._send(200, {'ok': True})
        if u.path == '/api/call/start':
            series = body.get('series')
            if series not in BASE: return self._send(404, {'error': 'no series'})
            ck = (body.get('ckey') or '')[:40]
            if ck and ck in CALL_KEYS and CALL_KEYS[ck][0] in CALLS:  # 同一通电话的重试（公网隧道丢了回包）：还给同一个
                return self._send(200, {'cid': CALL_KEYS[ck][0], 'who': CALLS[CALL_KEYS[ck][0]]['who'], 'job': CALL_KEYS[ck][1]})
            cs = callers(series); who = body.get('who') if body.get('who') in [x['key'] for x in cs] else cs[0]['key']
            name = (body.get('name') or ('你' if lang == 'zh' else 'you')).strip()[:24]
            sess = get_sess(body.get('sid'))
            pk = prep_key(series, who, lang, sess, name)
            pr = PREP.pop(pk, None) if body.get('direction') != 'incoming' else None
            if pr and time.time() - pr['t'] < PREP_TTL and pr['cid'] in CALLS and JOBS.get(pr['job'], {}).get('status') != 'error':  # 预备好的第一轮：直接接上
                c = CALLS[pr['cid']]; c.pop('_prep', None); job = JOBS[pr['job']]
                with c.setdefault('_lock', threading.Lock()):
                    job['_committed'] = True; ready = job['status'] == 'ready'
                if ready: threading.Thread(target=finish_spec, args=(job, c), daemon=True).start()
                log('call-' + c['cid'], {'start': True, 'series': series, 'who': who, 'lang': lang, 'name': name, 'sid': c['sid'], 'direction': 'outgoing', 'prepared': round(time.time() - pr['t'], 1), 'at': time.strftime('%F %T')})
                if ck: CALL_KEYS[ck] = (c['cid'], pr['job'])
                g = greet_url(series, who, lang, make=False); bu = bridge_urls(series, who, lang, make=False) or {}
                ls = (job.get('call') or {}).get('lines') or []
                return self._send(200, {'cid': c['cid'], 'who': who, 'job': pr['job'], 'greet': g, 'bridges': [u for v in bu.values() for _, u in v if u], 'prepared': True,
                                        'lines': [{'who': l['who'], 'text': l['text'], 'url': l['url']} for l in ls[:2] if l.get('url')]})
            cid = 'c' + time.strftime('%m%d%H%M') + rid(4)
            c = CALLS[cid] = {'cid': cid, 'series': series, 'lang': lang, 'name': name, 'who': who, 'me': (body.get('me') or (sess or {}).get('me') or '').strip()[:400], 'sid': sess['sid'] if sess and sess['series'] == series else None,
                              'direction': 'incoming' if body.get('direction') == 'incoming' else 'outgoing', 'turns': [],
                              'tts': body.get('tts') if body.get('tts') in ('turbo', 'flash') else CALL_TTS}
            log('call-' + cid, {'start': True, 'series': series, 'who': who, 'lang': lang, 'name': name, 'sid': c['sid'], 'direction': c['direction'], 'at': time.strftime('%F %T')})
            if (series, who, lang) not in REACT_URLS and not load_reacts(series, who, lang):
                threading.Thread(target=call_fillers, args=(series, who, lang), daemon=True).start()  # 第一次打给这个角色：后台配好短反应
            if not bridge_urls(series, who, lang, make=False): threading.Thread(target=bridge_urls, args=(series, who, lang), daemon=True).start()
            jid = start_job(run_call, c, '')
            if ck: CALL_KEYS[ck] = (cid, jid)
            g = greet_url(series, who, lang, make=False)
            if not g: threading.Thread(target=greet_url, args=(series, who, lang), daemon=True).start()
            bu = bridge_urls(series, who, lang, make=False) or {}
            return self._send(200, {'cid': cid, 'who': who, 'job': jid, 'greet': g, 'bridges': [u for v in bu.values() for _, u in v if u]})
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
            sess = get_sess(body.get('sid'))
            if not sess: return self._send(404, {'error': 'session expired'})
            text = (body.get('text') or '').strip()[:400]; via = body.get('via') or 'free'
            n = len(sess['eps']) + 1; matched = None; free = None; her_u = None
            pre = sess.get('_pre') if (sess.get('_pre') or {}).get('n') == n else None
            sess.pop('_pre', None)
            if pre:  # 识别时中转已经动手了（pre_next）：等它判断完（通常已经好了）
                pre['ev'].wait(8); r = pre['res'] or {}
                if text and (text == pre['text'] or text == r.get('matched')) and via in ('voice', 'free', 'option'):
                    matched = r.get('matched'); free = r.get('free'); her_u = r.get('her')
                    if via == 'option' and not matched: matched = text
                elif r.get('free'): cancel_job(r['free'])
            if not pre or (free is None and matched is None):
                if via in ('voice', 'free') and text:
                    r = prepare_next(sess, text, via)  # 先按原话开写，同时理解她的话（改错字、判断选项、按意图重写）
                    matched, free, her_u = r['matched'], r['free'], r.get('her')
            if via == 'auto':  # 闭眼听/被动收听：她没回应，故事自己往下走；有预先写好的就用第一个（默认走向），马上开播
                ch = (sess['eps'][-1].get('choices') or [])
                matched = ch[0] if ch and sess.get('spec') else None
            pick = matched if matched else (text if via == 'option' else None)
            jid = commit_ep_spec(sess, pick) if pick else None
            if jid and free: cancel_job(free); free = None
            if not jid: sess['spec'] = {}
            her = her_said(matched, 'option', sess['lang']) if matched and via != 'auto' else her_said(text, via, sess['lang'])  # 说中了选项：现写也按“她选择：选项”写，和点选项一样
            br = sel_bridge(sess, n - 1) if not jid and via != 'auto' else None
            if her_u and not matched: her = her_u
            log(sess['sid'], {'her': text, 'understood': her_u, 'via': via, 'matched': matched, 'next': n, 'spec': bool(jid), 'early': bool(free), 'wishes': sess.get('wishes'), 'at': time.strftime('%F %T')})
            out = jid or free or start_job(run_episode, sess, next_msg(sess, her, br and br['text']), None, her)
            sess['wishes'] = []
            return self._send(200, {'job': out, 'matched': matched, 'via': via, 'spec': bool(jid), 'bridge': br})
        if u.path == '/api/wish':  # 听的过程中对故事说的话：记下，按它重写两个选项的下一集（仍然秒开）
            sess = get_sess(body.get('sid'))
            if not sess: return self._send(404, {'error': 'session expired'})
            text = (body.get('text') or '').strip()[:300]
            if text:
                sess.setdefault('wishes', []).append(text); sess['wishes'] = sess['wishes'][-3:]
                log(sess['sid'], {'wish': text, 'after_ep': len(sess['eps']), 'at': time.strftime('%F %T')})
                if not sess['eps'][-1].get('ending'): threading.Thread(target=start_ep_specs, args=(sess,), daemon=True).start()
            return self._send(200, {'ok': True, 'wishes': sess.get('wishes', [])})
        self._send(404, {'error': 'not found'})


if __name__ == '__main__':
    print(f'unscripted audio on {PORT}', flush=True)
    for _l in ('zh', 'en'): threading.Thread(target=generic_bridges, args=(_l,), daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
