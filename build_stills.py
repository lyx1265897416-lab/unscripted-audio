"""narra 的静态背景（11-11 她要求：所有内容的动态背景改成静态图片，图要贴合当前音频内容的画面场景）。
每个画面片段出一张竖版 1080×1620 静态图 app/v/<id>/still/<clip>.jpg + index.json（{"still": [片段编号]}），片段编号和画面时间轴一致，
播放器按音频位置换图（app.js 的 stillPlan）。
- realtime 13 部：视频片段在片段范围内取最清晰的一帧；已有超分循环（live/）的直接取它的帧；源图 / 源片竖裁宽 ≥ 1000 的直接缩；
  其余（竖裁只有 480–920 宽）加 --sr 时送 Waku image-upscaler 2k 超分再缩到 1080，只处理第 1 集时间轴和轮播池用到的片段；
  没超分的片段播放器退回 hd/<clip>.jpg（720×1080）。
- Prota 8 部：原卡图 / 第 1 集专属生成图按脸取景直接裁（源图够大，不用超分）。
用法：python3 build_stills.py [剧 id…] [--sr] [--k=<中转 token>] [--dry] [--force]   （--sr 需要 --k 取第 1 集时间轴）"""
import io, json, re, subprocess, sys, time, urllib.request as U, concurrent.futures as cf
from pathlib import Path
from PIL import Image, ImageFilter, ImageStat
import build_visuals as BV
import build_hd as HD
import framing as FR
import fix_stills

ROOT = Path(__file__).resolve().parent
FF = BV.FF
W, H = 1080, 1620
PROTA = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']
TMP = ROOT / 'cache' / 'still_sr'; TMP.mkdir(parents=True, exist_ok=True)
op = U.build_opener(U.ProxyHandler({}))
FORCE, SR, DRY = '--force' in sys.argv, '--sr' in sys.argv, '--dry' in sys.argv


def sharp(im):
    g = im.convert('L'); g.thumbnail((540, 810))
    return ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]


def grab(src, t, crop=''):
    r = subprocess.run([FF, '-v', 'error', '-ss', f'{max(0, t):.2f}', '-i', str(src), '-frames:v', '1'] + (['-vf', crop] if crop else []) + ['-f', 'image2pipe', '-c:v', 'png', '-'], capture_output=True, timeout=60)
    return Image.open(io.BytesIO(r.stdout)).convert('RGB') if r.stdout else None


def best(src, a, d, crop=''):
    """片段里最清晰的一帧（避开首尾的转场和运动模糊）"""
    c = [im for im in (grab(src, a + d * q, crop) for q in (0.2, 0.35, 0.5, 0.65, 0.8)) if im]
    return max(c, key=sharp) if c else None


def face_crop(img):
    """剧照按脸取 2:3（和 build_hd.still 同一套取景），返回原始分辨率的裁切"""
    img = fix_stills.fixed(str(img))
    im = FR.load(img); iw, ih = im.size
    fs = [(a * iw, b * ih, c * iw, d * ih) for a, b, c, d in FR.main_faces([tuple(f) for f in FR._cache.get(FR.img_key(img), [])])]
    cw = min(iw, ih / 1.5); ch = cw * 1.5
    if fs:
        cx = (min(f[0] for f in fs) + max(f[2] for f in fs)) / 2; cy = (min(f[1] for f in fs) + max(f[3] for f in fs)) / 2
        x0 = min(max(0, cx - cw / 2), iw - cw); y0 = min(max(0, cy - ch * 0.33), ih - ch)
    else: x0 = (iw - cw) / 2; y0 = (ih - ch) * 0.2
    return im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).convert('RGB')


def save(im, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    w = min(W, im.size[0]) // 2 * 2
    im.resize((w, round(w * 1.5)), Image.LANCZOS).save(out, quality=80, optimize=True, progressive=True)


def upscale(im, tag):
    """Waku image-upscaler（2k）；返回超分后的图，失败返回 None"""
    src = TMP / f'{tag}.in.jpg'; big = TMP / f'{tag}.sr.jpg'
    if not (big.exists() and big.stat().st_size > 60000):
        im.save(src, quality=95)
        up = subprocess.run(['waku', 'persist', str(src)], capture_output=True, text=True, timeout=180)
        m = re.search(r'"url":\s*"([^"]+)"', up.stdout)
        if not m: return None
        for attempt in range(3):   # 偶发失败（11-11 第一轮跑到一半连续失败，单独重跑又正常）：隔几秒重试
            r = subprocess.run(['waku', 'gen', 'run', 'wavespeed-ai/image-upscaler', '--capability', 'multimodal.generate.image', '--params',
                                json.dumps({'image': m.group(1), 'target_resolution': '2k', 'output_format': 'jpeg'}), '--wait', '--timeout', '300', '--out', str(big)], capture_output=True, text=True, timeout=360)
            if big.exists() and big.stat().st_size > 60000: break
            print('sr retry', tag, (r.stdout + r.stderr)[-200:].replace('\n', ' '), flush=True); time.sleep(6 + attempt * 10)
    if not (big.exists() and big.stat().st_size > 60000): return None
    return Image.open(big).convert('RGB')


def rt_jobs(sid, used):
    """[(clip, how, fn)]：how = live / native / sr / skip"""
    have = set(json.load(open(ROOT / 'app' / 'v' / sid / 'hd' / 'index.json'))['poster'])
    lf = ROOT / 'app' / 'v' / sid / 'live' / 'live.json'
    live = set(json.load(open(lf))['live']) if lf.exists() else set()
    out = []
    for cid, kind, src, a, b, y in HD.jobs(sid):
        if cid not in have: continue   # 素材和编号对不上的（build_hd 跳过的）不出图
        if kind == 's':
            get = lambda src=src: face_crop(src)
            iw, ih = FR.load(fix_stills.fixed(str(src))).size; cw = min(iw, ih / 1.5)
        elif cid in live:
            lv = ROOT / 'app' / 'v' / sid / 'live' / f'{cid}.mp4'
            out.append((cid, 'live', lambda lv=lv: best(lv, 0, BV.dur(lv)))); continue
        else:
            w, h = BV.dims(src); ch = min(h, int(w * 1.5) // 2 * 2); cw = int(ch / 1.5) // 2 * 2
            yy = HD.face_y(src, a, b, w, h, ch) if y is None else int(min(max(0, y), h - ch))
            get = lambda src=src, a=a, d=min(HD.MAXSEC, b - a), c=f'crop={cw}:{ch}:{(w - cw) // 2}:{yy}': best(src, a, d, c)
        if cw >= 1000: out.append((cid, 'native', get))
        elif SR and (used is None or cid in used): out.append((cid, 'sr', get))
        else: out.append((cid, 'skip', None))
    return out


def prota_jobs(sid):
    import build_prota_visuals as PV
    out = []
    V = json.load(open(ROOT / 'data' / 'visuals' / f'{sid}.json'))
    imgs = PV.pick(json.load(open(ROOT / 'data' / 'prota' / f'{sid}.json')))
    for c in V['clips']:
        cid = c['id']
        if c.get('kind') == 'gen': img = ROOT / 'data' / 'shots' / 'img' / f'{sid}_{cid}.jpg'
        elif re.match(r'^s\d\d$', cid) and int(cid[1:]) < len(imgs): img = Path(imgs[int(cid[1:])])
        else: continue
        if img.exists(): out.append((cid, 'native', lambda img=img: face_crop(img)))
    return out


def build(sid, used):
    od = ROOT / 'app' / 'v' / sid / 'still'
    jobs = prota_jobs(sid) if sid in PROTA else rt_jobs(sid, used)
    if DRY:
        return sid, {h: sum(1 for j in jobs if j[1] == h) for h in ('live', 'native', 'sr', 'skip')}

    def run(j):
        cid, how, get = j
        out = od / f'{cid}.jpg'
        if how == 'skip': return cid, how
        if out.exists() and out.stat().st_size > 20000 and not FORCE: return cid, 'exists'
        try:
            im = get()
            if im is None: return cid, 'no frame'
            if how == 'sr':
                im = upscale(im, f'{sid}.{cid}')
                if im is None: return cid, 'sr failed'
            save(im, out); return cid, how
        except Exception as e:
            return cid, 'FAIL ' + repr(e)[:120]
    with cf.ThreadPoolExecutor(3) as ex: res = list(ex.map(run, jobs))
    bad = [r for r in res if r[1] not in ('live', 'native', 'sr', 'exists', 'skip')]
    ok = sorted(f.stem for f in od.glob('*.jpg')) if od.exists() else []
    if ok: json.dump({'still': ok}, open(od / 'index.json', 'w'))
    return sid, f'{len(ok)} stills {sum((od / f"{c}.jpg").stat().st_size for c in ok) / 1e6:.1f} MB', {h: sum(1 for r in res if r[1] == h) for h in ('live', 'native', 'sr', 'exists', 'skip')}, bad[:6]


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or HD.RT + PROTA
    only = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--only=')), None)
    k = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--k=')), None)
    packs = [json.loads(op.open(f'http://127.0.0.1:8913/api/ep1pack?lang={l}&k={k}', timeout=30).read()) for l in ('en', 'zh')] if k else []
    for sid in ids:
        used = None
        if packs:
            used = set((json.load(open(ROOT / 'data' / 'visuals' / f'{sid}.json')).get('pool') or []))
            for p in packs: used |= {x['clip'] for x in ((p.get(sid) or {}).get('visuals') or [])}
        if only: used = set(only)
        print(build(sid, used), flush=True)
