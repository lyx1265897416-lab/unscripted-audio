"""静态背景第二版选帧（11-11 她看了 v60 的反馈：视频截帧不要带虚影、闭眼、动作不明确的；不要只露下巴这种局部；
优先完整的角色面部，其次空镜 / 道具；肢体特写只在音频提到时才用）。

第一版（build_stills.py）每个片段取“最清晰的一帧”再套片段级的固定裁切：清晰度会偏向重影帧，裁切对不上这一帧里头的位置。
这一版对每个视频片段：
  1. 抽 8 fps 的小图算每一帧的“稳不稳”（和前后帧的差）和清晰度，挑 4 个互相隔开的候选时刻——动得最少的时刻，避开首尾转场；
  2. 候选帧整帧给视觉模型（OpenRouter kimi）看：人脸框、眼睛睁 / 闭 / 看不见、有没有重影、是角色 / 空镜 / 道具 / 局部肢体；
     第一张“脸完整 + 睁眼 + 无重影”（或干净的空镜、道具）就用；都不合格时留最好的一张并标 bad / part；
  3. 按这一帧里的脸重新取 2:3 竖裁：整个头在画面里、眼睛在上三分之一附近（大特写贴着脸上沿裁，不会只剩下巴）；
  4. 竖裁宽 < 1000 的送 Waku image-upscaler（4 credits/张），存成 app/v/<id>/still/<clip>.jpg。
index.json 里加 "q"：{片段: face | scene | part | bad}，播放器排图时优先 face / scene，part 只在台词提到肢体时用，bad 不用。
选帧结果缓存在 data/stills/<id>.json（只留本机）。需要 OPENROUTER_API_KEY（~/.config/vicky-realtime/env）。

用法：python3 build_stills_v2.py select [id…]     选帧 + 模型质检（不花 Waku 额度）
     python3 build_stills_v2.py render [id…]     出图（超分）并写 index.json
     python3 build_stills_v2.py tag              给剧照 / Prota 图补 q 标签（按已有的人脸缓存，不调模型）
     加 --force 重做。"""
import base64, io, json, os, re, subprocess, sys, time, urllib.request as U, concurrent.futures as cf
from pathlib import Path
import numpy as np
from PIL import Image
import build_visuals as BV
import build_hd as HD
import build_stills as BS
import framing as FR
import fix_stills

ROOT = Path(__file__).resolve().parent
FF = BV.FF
QA = ROOT / 'data' / 'stills'; QA.mkdir(parents=True, exist_ok=True)
TMP = ROOT / 'cache' / 'still_v2'; TMP.mkdir(parents=True, exist_ok=True)
MODEL = os.environ.get('STILL_QA_MODEL', 'moonshotai/kimi-k3.1-pro')
FORCE = '--force' in sys.argv
_op = U.build_opener(U.ProxyHandler({}))
TXT = ('Look at this film frame. Return JSON only: {"faces":[{"box":[x0,y0,x1,y1],"eyes":"open|closed|hidden"}],"ghost":true|false,"kind":"character|scene|prop|bodypart"}. '
       'faces: every human face whose features are visible; box = tight box around the whole head (hair top to chin), coordinates 0-1000 relative to image width/height; '
       'eyes = "closed" if the eyes are shut, mid-blink or nearly shut, "hidden" if covered or turned away, else "open". '
       'ghost = true if the frame shows a double image, motion smear, transparent overlap of two moments, or melted/duplicated facial features. '
       'kind: "character" (a person with a visible face), "bodypart" (hands, torso, back of head — no visible face), "prop" (an object is the subject), "scene" (environment / empty shot).')


def look(im):
    im = im.copy(); im.thumbnail((896, 896)); b = io.BytesIO(); im.save(b, 'JPEG', quality=85)
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()}}, {'type': 'text', 'text': TXT}]}],
            'max_tokens': 3000, 'temperature': 0}
    err = None
    for k in range(3):
        try:
            if k == 2: body['model'] = 'qwen/qwen3-vl-235b-a22b-instruct'; body['max_tokens'] = 500   # kimi 两次没给出 JSON（偶尔思考用光了字数）：换 Qwen 看这一帧
            r = json.loads(_op.open(U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                                              headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'}), timeout=120).read())
            c = r['choices'][0]['message']['content'] or ''
            j = json.loads(c[c.index('{'):c.rindex('}') + 1])
            faces = []
            for f in j.get('faces') or []:
                bx = f.get('box') or []
                if len(bx) == 4 and bx[2] - bx[0] > 10 and bx[3] - bx[1] > 10: faces.append({'box': [min(1000, max(0, float(v))) / 1000 for v in bx], 'eyes': f.get('eyes') or 'open'})
            return {'faces': faces, 'ghost': bool(j.get('ghost')), 'kind': j.get('kind') or ('character' if faces else 'scene')}
        except Exception as e:
            err = e; time.sleep(2 + 3 * k)
    raise RuntimeError('vlm ' + repr(err)[:120])


def candidates(src, a, d, n=4):
    """动得最少、又清楚的 n 个时刻（秒，相对源片），互相至少隔 0.4 秒"""
    w, h = BV.dims(src); sw = 160; sh = int(h * sw / w) // 2 * 2
    raw = subprocess.run([FF, '-v', 'error', '-ss', f'{a:.2f}', '-t', f'{d:.2f}', '-i', str(src), '-vf', f'fps=8,scale={sw}:{sh},format=gray', '-f', 'rawvideo', '-'], capture_output=True, timeout=120).stdout
    k = len(raw) // (sw * sh)
    if k < 3: return [a + d * 0.5]
    f = np.frombuffer(raw[:k * sw * sh], dtype=np.uint8).reshape(k, sh, sw).astype(np.float32)
    df = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))                      # 相邻帧的差
    mot = np.empty(k); mot[0] = df[0] * 2; mot[-1] = df[-1] * 2; mot[1:-1] = df[:-1] + df[1:]
    lap = np.abs(f[:, 1:-1, 1:-1] * 4 - f[:, :-2, 1:-1] - f[:, 2:, 1:-1] - f[:, 1:-1, :-2] - f[:, 1:-1, 2:]).mean(axis=(1, 2))
    score = lap / (np.median(lap) + 1e-6) - 1.5 * mot / (np.median(mot) + 1e-6)
    lo, hi = int(np.ceil(k * 0.08)), int(np.floor(k * 0.92))
    order = sorted(range(max(1, lo), min(k - 1, max(hi, lo + 1))), key=lambda i: -score[i]) or [k // 2]
    out = []
    for i in order:
        t = a + i / 8
        if all(abs(t - u) >= 0.4 for u in out): out.append(t)
        if len(out) >= n: break
    return out


def crop_box(w, h, faces):
    """这一帧的 2:3 竖裁（像素）：有脸就把最大的脸（连同差不多大的）整个放进来，眼睛在上三分之一附近"""
    ch = min(h, int(w * 1.5) // 2 * 2); cw = int(ch / 1.5) // 2 * 2
    fs = FR.main_faces([tuple(f['box']) for f in faces]) if faces else []
    if not fs: return (w - cw) // 2, int((h - ch) * 0.22), cw, ch
    x0, y0, x1, y1 = min(f[0] for f in fs) * w, min(f[1] for f in fs) * h, max(f[2] for f in fs) * w, max(f[3] for f in fs) * h
    if x1 - x0 > cw: m = max(fs, key=lambda f: (f[2] - f[0]) * (f[3] - f[1])); x0, y0, x1, y1 = m[0] * w, m[1] * h, m[2] * w, m[3] * h   # 两张脸放不下：只取最大的
    cx = int(min(max(0, (x0 + x1) / 2 - cw / 2), w - cw))
    fh = y1 - y0
    cy = (y0 + y1) / 2 - ch * 0.36                 # 脸的中心放在上 36%
    cy = min(cy, y0 - ch * 0.04)                    # 头顶留一点空，不切头
    if fh > ch * 0.9: cy = y0                       # 大特写：贴着头顶裁（眼睛一定在画面里）
    return cx, int(min(max(0, cy), h - ch)), cw, ch


def verdict(v):
    """→ (q, 合格吗)"""
    if v['ghost']: return 'bad', False
    fs = v['faces']
    if fs:
        main = max(fs, key=lambda f: (f['box'][2] - f['box'][0]) * (f['box'][3] - f['box'][1]))
        if main['eyes'] == 'open': return 'face', True
        if main['eyes'] == 'closed': return 'bad', False
        return 'part', False                         # 脸被挡住 / 背过去
    if v['kind'] in ('scene', 'prop'): return 'scene', True
    return 'part', False


def select(sid):
    f = QA / f'{sid}.json'; db = json.load(open(f)) if f.exists() else {}
    have = set(json.load(open(ROOT / 'app' / 'v' / sid / 'hd' / 'index.json'))['poster'])
    jobs = [(cid, src, a, b) for cid, kind, src, a, b, y in HD.jobs(sid) if kind == 'v' and cid in have and (FORCE or cid not in db)]

    def one(j):
        cid, src, a, b = j
        try:
            d = min(HD.MAXSEC, b - a); w, h = BV.dims(src); best = None; tried = 0
            for t in candidates(src, a, d):
                im = BS.grab(src, t)
                if im is None: continue
                v = look(im); tried += 1; q, ok = verdict(v)
                rec = {'t': round(t, 2), 'q': q, 'ghost': v['ghost'], 'kind': v['kind'], 'faces': v['faces'], 'box': list(crop_box(w, h, v['faces'] if q in ('face', 'bad') else [])), 'tried': tried}
                rank = {'face': 0, 'scene': 1, 'part': 2, 'bad': 3}[q]
                if best is None or rank < best[0]: best = (rank, rec, im)
                if ok and (q == 'face' or tried >= 2): break      # 空镜先再看一帧：后面可能有人脸出现
            if best is None: return cid, 'no frame'
            _, rec, im = best; x, y, cw, ch = rec['box']
            im.crop((x, y, x + cw, y + ch)).save(TMP / f'{sid}.{cid}.jpg', quality=95)
            return cid, rec
        except Exception as e:
            return cid, 'FAIL ' + repr(e)[:100]
    with cf.ThreadPoolExecutor(8) as ex:
        for cid, r in ex.map(one, jobs):
            if isinstance(r, dict): db[cid] = r
            else: print(sid, cid, r, flush=True)
    json.dump(db, open(f, 'w'), indent=0)
    c = {}
    for r in db.values(): c[r['q']] = c.get(r['q'], 0) + 1
    return sid, len(jobs), 'new', c, 'calls', sum(r.get('tried', 1) for r in db.values())


# 人工看过缩略图后的更正：模型把只露下半张脸 / 半张脸的大特写也算成了“脸”；咪的主角是猫，模型按“没有人脸”标成局部
FIXQ = {'magnus': {'p056': 'part', 'p077': 'part'}}
CAT = {'mii'}


def write_index(sid, extra=None):
    od = ROOT / 'app' / 'v' / sid / 'still'; f = od / 'index.json'
    old = json.load(open(f)) if f.exists() else {}
    q = dict(old.get('q') or {}); q.update(extra or {}); q.update(FIXQ.get(sid) or {})
    if sid in CAT: q = {k: ('scene' if v == 'part' else v) for k, v in q.items()}
    ok = sorted(p.stem for p in od.glob('*.jpg'))
    json.dump({'still': ok, 'q': {k: v for k, v in sorted(q.items()) if k in ok}}, open(f, 'w'), separators=(',', ':'))


def render(sid):
    f = QA / f'{sid}.json'
    if not f.exists(): return sid, 'no selection'
    db = json.load(open(f)); od = ROOT / 'app' / 'v' / sid / 'still'; od.mkdir(parents=True, exist_ok=True)

    def one(item):
        cid, rec = item
        src = TMP / f'{sid}.{cid}.jpg'; out = od / f'{cid}.jpg'
        if not src.exists(): return cid, 'no crop'
        if rec.get('done') and out.exists() and not FORCE: return cid, 'exists'
        im = Image.open(src).convert('RGB')
        if im.size[0] < 1000:
            im = BS.upscale(im, f'{sid}.{cid}.v2')
            if im is None: return cid, 'sr failed'
        BS.save(im, out); rec['done'] = True
        return cid, 'ok'
    with cf.ThreadPoolExecutor(6) as ex: res = list(ex.map(one, list(db.items())))
    json.dump(db, open(f, 'w'), indent=0)
    write_index(sid, {cid: rec['q'] for cid, rec in db.items()})
    bad = [r for r in res if r[1] not in ('ok', 'exists')]
    return sid, {k: sum(1 for r in res if r[1] == k) for k in ('ok', 'exists')}, bad[:8]


def tag(sid):
    """剧照 / Prota 图：有脸 = face，没脸 = scene（它们是画好的图，没有闭眼重影的问题）；已有 q 的不动"""
    od = ROOT / 'app' / 'v' / sid / 'still'; old = (json.load(open(od / 'index.json')).get('q') or {}) if (od / 'index.json').exists() else {}
    extra = {}
    if sid in BS.PROTA:
        import build_prota_visuals as PV
        V = json.load(open(ROOT / 'data' / 'visuals' / f'{sid}.json')); imgs = PV.pick(json.load(open(ROOT / 'data' / 'prota' / f'{sid}.json')))
        src = {c['id']: (ROOT / 'data' / 'shots' / 'img' / f'{sid}_{c["id"]}.jpg') if c.get('kind') == 'gen' else (Path(imgs[int(c['id'][1:])]) if re.match(r'^s\d\d$', c['id']) and int(c['id'][1:]) < len(imgs) else None) for c in V['clips']}
    else:
        src = {cid: s for cid, kind, s, a, b, y in HD.jobs(sid) if kind == 's'}
    for cid, p in src.items():
        if cid in old or not p or not Path(p).exists(): continue
        p = fix_stills.fixed(str(p))
        extra[cid] = 'face' if FR.main_faces([tuple(x) for x in FR._cache.get(FR.img_key(p), [])]) else 'scene'
    write_index(sid, extra)
    return sid, {k: sum(1 for v in extra.values() if v == k) for k in ('face', 'scene')}


if __name__ == '__main__':
    what = sys.argv[1]; ids = [a for a in sys.argv[2:] if not a.startswith('--')]
    if what == 'select':
        for sid in ids or HD.RT: print(select(sid), flush=True)
    elif what == 'render':
        for sid in ids or HD.RT: print(render(sid), flush=True)
    elif what == 'tag':
        for sid in ids or HD.RT + BS.PROTA: print(tag(sid), flush=True)
