"""Prota 8 部的“第 1 集专属画面”（11-10 她要求：动态展示框的画面和关键音频对不上、单调——按同画风再生成一批人像、道具、场景，给音频适配）。
1. plan：Opus 5.5（本机 Claude Code）读世界卡、角色外貌、第 1 集逐句台词，写 ~12 个镜头的分镜（人物表情特写/两人同框/关键道具/场景），每个镜头标对应台词。
2. gen：每个镜头用原卡同角色的插图做参考（脸、发型、服装、画风一致），Waku google/nano-banana-2.1/edit 出图；听众“你”不入画，不出现文字。
3. clips：按脸取景做 8 秒呼吸式慢推短片 app/v/<id>/gNN.mp4，描述写进 data/visuals/<id>.json（kind=gen），pool 也加进去。
分镜和新图（含原卡角色改画）只留本机：data/shots/（.gitignore）；公开仓库只有短片。
用法：python3 build_prota_shots.py plan|gen|clips [id…] [--force]"""
import json, os, re, sys, hashlib, subprocess, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
ROOT = Path(__file__).resolve().parent
D = ROOT / 'data' / 'shots'; (D / 'img').mkdir(parents=True, exist_ok=True)
IDS = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']
MODEL = 'google/nano-banana-2.1/edit'
# 原卡定装图和人设文字/场景图对不上的角色：用场景图做参考（Sienna 人设是深红棕短发，定装图却是金色长发）
SCENE_REF = {'starmate': {'Sienna'}}
# 原卡参考图本身画了“四只耳朵”（兽耳 + 人耳）的角色：改用已修好的剧照做参考（fix_stills 去掉了人耳）
FIXED_REF = {('onestat', 'Renn'): ['data/fixed_stills/onestat_s06.jpg', 'data/fixed_stills/onestat_s08.jpg'],
             ('onestat', 'Hilde'): ['data/fixed_stills/onestat_s16.jpg', 'data/fixed_stills/onestat_s17.jpg']}

SYS = '你是有声剧的分镜师兼美术指导。只输出 JSON，不要解释。'


def chars_of(sid):
    p = json.load(open(ROOT / 'data/prota' / f'{sid}.json')); w = json.load(open(ROOT / 'data/world' / f'{sid}.json'))
    caps = json.load(open(ROOT / 'data/prota' / f'{sid}.captions.json'))
    pc = {c['name'].split()[0]: c for c in p['characters']}
    out = {}
    for c in w['characters']:
        k = c['name'].split()[0]; x = pc.get(k) or {}
        scenes = [s['path'] for s in p['scenes'] if s['route'] != '封面' and k in caps.get(hashlib.sha1(s['path'].encode()).hexdigest()[:12], '')]
        if k in SCENE_REF.get(sid, set()): refs = scenes[:2]
        else: refs = (x.get('base') or [])[:1] + (x.get('presets') or [])[:1] or scenes[:2]
        if (sid, k) in FIXED_REF: refs = [str(ROOT / x) for x in FIXED_REF[(sid, k)]]
        out[k] = {'name': c['name'], 'look': x.get('look_en') or '', 'role': c.get('role_en', ''), 'gender': c.get('gender'), 'refs': refs}
    style = next((s['path'] for s in p['scenes'] if s['route'] != '封面'), None)
    return out, style


def plan(sid):
    f = D / f'{sid}.json'
    if f.exists() and '--force' not in sys.argv: return sid, 'skip'
    import claude_cli as CC
    w = json.load(open(ROOT / 'data/world' / f'{sid}.json')); sc = json.load(open(ROOT / 'data/ep1' / f'{sid}.zh.json'))
    ch, _ = chars_of(sid)
    v = json.load(open(ROOT / 'data/visuals' / f'{sid}.json'))
    clean = lambda t: re.sub(r'\[[^\]]*\]\s*', '', t)
    lines = '\n'.join(f"{i}. {l['who']}: {clean(l['text'])}" for i, l in enumerate(sc['lines']))
    cast = '\n'.join(f"- {k}（{c['gender']}，{'有参考图' if c['refs'] else '没有参考图'}）：{c['role']}｜外貌：{c['look'][:500]}" for k, c in ch.items())
    have = '\n'.join(f"- {c['cap'][:80]}" for c in v['clips'][:20])
    user = f'''剧：{w['title_zh']}（{w['title_en']}）。基调：{w.get('tone', '')}
场景：{'、'.join(w.get('places') or [])}

角色：
{cast}

第 1 集逐句台词（旁白用“你”指听众，听众性别不限）：
{lines}

现有画面（原卡插图，大多和第 1 集情节对不上）：
{have}

给第 1 集画 12 个新画面，让播放器在关键台词处显示对应的画。要求：
- 覆盖整集的关键时刻，按台词顺序；每个镜头写清对应哪几句（lines，台词编号）。
- 类型搭配：人物表情/半身特写 5–6 个（跟着台词情绪变）、两人同框 1–2 个、关键道具特写 2–3 个（台词里提到的具体物件）、场景/空镜 2 个。
- 听众“你”绝不入画（画面就是“你”的视线），不画“你”的手。
- 没有参考图的角色最多出现在 1 个镜头里；有参考图的角色写名字（chars 里填角色名的第一个词，如 Sienna）。
- 画面里不能出现任何文字（手机屏幕、招牌、账单只画光和模糊的界面，不画字）。
- 手尽量简单：自然垂着、握住一个东西、插兜，或在画面外；不要复杂手势。
- 15+：可以暧昧，不裸露、不血腥。
- prompt_en 用英文写，一段具体的画面描述：谁、表情、动作、穿着（和设定一致）、地点、光线、景别（close-up / medium shot / wide shot / object close-up）。
- cap_zh：一句中文画面描述（25–45 字，写清人物名字/道具/地点/情绪），用来给后面实时生成的集按台词匹配画面。
输出 JSON：{{"shots":[{{"id":"g00","lines":[0,1],"kind":"portrait|two|prop|scene","chars":["Sienna"],"prompt_en":"...","cap_zh":"..."}}]}}'''
    txt, meta = CC.call_text(SYS, user, timeout=600, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    for i, s in enumerate(j['shots']): s['id'] = f'g{i:02d}'
    json.dump(j, open(f, 'w'), ensure_ascii=False, indent=1)
    return sid, len(j['shots']), meta.get('sec')


URLS = D / '_urls.json'
_U = json.loads(URLS.read_text()) if URLS.exists() else {}


def up(path):
    k = hashlib.sha1(str(path).encode()).hexdigest()
    if k in _U: return _U[k]
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB'); im.thumbnail((1280, 1280))
    tmp = D / f'_up_{k[:10]}.jpg'; im.save(tmp, quality=90)
    for _ in range(4):
        r = subprocess.run(['waku', 'persist', str(tmp)], capture_output=True, text=True, timeout=120)
        m = re.search(r'"url":\s*"([^"]+)"', r.stdout)
        if m: break
    tmp.unlink(missing_ok=True)
    if not m: raise RuntimeError('persist failed')
    _U[k] = m.group(1); URLS.write_text(json.dumps(_U, indent=0)); return _U[k]


def _json(s):
    m = re.search(r'\{.*\}', s or '', re.S)
    if not m: raise RuntimeError('no json in waku output: ' + (s or '')[-160:])
    return json.loads(m.group(0))


def _run_edit(params):
    """提交一次 Waku 出图并等结果；没 JSON / 没出图 / 下载失败都抛错，由上层重试"""
    r = subprocess.run(['waku', 'gen', 'run', MODEL, '--capability', 'multimodal.generate.image', '--params', json.dumps(params)], capture_output=True, text=True, timeout=300)
    j = _json(r.stdout + '\n' + r.stderr)
    for _ in range(4):
        if j.get('asset_url') or not j.get('job_id'): break
        r = subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '240'], capture_output=True, text=True, timeout=300)
        try: j = dict(_json(r.stdout), job_id=j['job_id'])
        except RuntimeError: continue
    if not j.get('asset_url'): raise RuntimeError('no asset ' + json.dumps(j)[:160])
    return j['asset_url']


def gen_one(sid, s, ch, style, force=False, extra=''):
    out = D / 'img' / f'{sid}_{s["id"]}.jpg'
    if out.exists() and not force: return s['id'], 'exists'
    refs, desc = [], []
    for k in s.get('chars') or []:
        c = ch.get(k) or next((v for kk, v in ch.items() if kk.lower() == str(k).split()[0].lower()), None)
        if not c: continue
        refs += c['refs'][:2]; desc.append(f"{c['name']} — {c['look'][:420]}" + ('' if c['refs'] else ' (no reference image: design from this description)'))
    if style and len(refs) < 5: refs.append(style)
    urls = [up(r) for r in refs[:6]]
    prompt = ('Create a NEW illustration in exactly the same art style as the reference images: the same anime-style digital painting, line quality, shading, color palette and lighting quality. '
              + (('Characters (must match their reference images exactly — same face, hair color and hairstyle, eye color, body type, outfit design): ' + ' | '.join(desc) + '. ') if desc else 'No people in this image. ')
              + f'Scene: {s["prompt_en"]} '
              + 'Rules: absolutely no text, letters, numbers, captions, name plates, logos or watermarks anywhere (screens show only light and blurred shapes); no border or frame. '
              'Anatomy must be correct: every visible hand has exactly four fingers and one thumb with natural joints (keep hands simple and relaxed, or out of frame); arms attach properly to shoulders; '
              'animal-eared characters have only their animal ears (no human ears). The viewer/protagonist is NOT in the picture (the image is their point of view). Adults look adult, children look like children. Tasteful, no nudity.'
              + (' ' + extra if extra else ''))
    params = {'prompt': prompt, 'images': urls, 'aspect_ratio': '1:1', 'resolution': '2k', 'output_format': 'jpeg'}
    err = None
    for attempt in range(3):
        try:
            url = _run_edit(params)
            for _ in range(3):
                r = subprocess.run(['curl', '-s', '-f', '--retry', '2', '--noproxy', '*', '-o', str(out), url])
                if r.returncode == 0 and out.exists() and out.stat().st_size > 10000: break
            else: raise RuntimeError('download failed')
            break
        except Exception as e:
            err = e; out.unlink(missing_ok=True)
    else:
        raise RuntimeError(f'{sid} {s["id"]} ' + str(err)[:160])
    return s['id'], 'ok'


def gen(sid, only=None, force=False):
    sh = json.load(open(D / f'{sid}.json'))['shots']; ch, style = chars_of(sid)
    todo = [s for s in sh if not only or s['id'] in only]
    res = []
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(gen_one, sid, s, ch, style, force): s['id'] for s in todo}
        for f in cf.as_completed(futs):
            try: res.append(f.result())
            except Exception as e: res.append((futs[f], 'FAIL ' + str(e)[:120]))
    return sid, sorted(res)


def clips(sid):
    import build_visuals as BV
    sh = json.load(open(D / f'{sid}.json'))['shots']
    od = ROOT / 'app' / 'v' / sid; V = json.load(open(ROOT / 'data/visuals' / f'{sid}.json'))
    V['clips'] = [c for c in V['clips'] if c.get('kind') != 'gen']
    new = []
    def one(s):
        img = D / 'img' / f'{sid}_{s["id"]}.jpg'
        if not img.exists(): return None
        out = od / f'{s["id"]}.mp4'
        if not out.exists() or '--force' in sys.argv or out.stat().st_mtime < img.stat().st_mtime: BV.kenburns(str(img), out)
        return {'id': s['id'], 'kind': 'gen', 'cap': '剧照：' + s['cap_zh'], 'src': f'v/{sid}/{s["id"]}.mp4', 'dur': round(BV.dur(out), 2), 'lines': s.get('lines') or []}
    with cf.ThreadPoolExecutor(6) as ex: new = [x for x in ex.map(one, sh) if x]
    V['clips'] = new + V['clips']
    V['pool'] = [c['id'] for c in new] + [x for x in V['pool'] if not x.startswith('g')]
    json.dump(V, open(ROOT / 'data/visuals' / f'{sid}.json', 'w'), ensure_ascii=False, indent=1)
    return sid, len(new)


if __name__ == '__main__':
    what = sys.argv[1]; ids = [a for a in sys.argv[2:] if not a.startswith('--') and a in IDS] or IDS
    only = [a for a in sys.argv[2:] if re.match(r'^g\d\d$', a)]
    if what == 'plan':
        with cf.ThreadPoolExecutor(4) as ex:
            for r in ex.map(plan, ids): print(r, flush=True)
    elif what == 'gen':
        for sid in ids: print(gen(sid, only, '--force' in sys.argv), flush=True)
    elif what == 'clips':
        for sid in ids: print(clips(sid), flush=True)
