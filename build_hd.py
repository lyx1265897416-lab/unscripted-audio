"""realtime 这批剧（13 部）的竖版高清背景（11-11 她要求：背景可以动态或动静结合，清晰度和封面一致）。
原来的画面短片是 400/480 px 方形，narra 播放器把它放大铺满上半屏，发糊。这里按同一套片段编号重出竖版 2:3：
- 视频片段（开场镜头 o / 实时片段 c / 预设切片 p / perhaps 待机 idle）：app/v/<id>/hd/<clip>.mp4，宽 = min(源宽, 720)，最长 6 秒，
  按人脸定上下位置（framing 的人脸缓存，不重新识别）；同名 .jpg 是海报帧。
- 剧照（s）：只出高清海报 app/v/<id>/hd/<clip>.jpg（720×1080，按脸取景），动效交给播放器的 CSS 慢推（动静结合）。
片段编号和 build_visuals.py / build_preset_visuals.py 一致；时长对不上（素材后来变过）的片段跳过，仍用原来的方形短片。
用法：python3 build_hd.py [剧 id…] [--force]"""
import hashlib, json, os, subprocess, sys, concurrent.futures as cf
from pathlib import Path
from PIL import Image
import build_visuals as BV
import build_preset_visuals as BP
import framing as FR
import fix_stills

ROOT = Path(__file__).resolve().parent
FF, FP = BV.FF, BV.FP
RT = ['magnus', 'rafael', 'rowan', 'rian', 'island', 'lena', 'mii', 'kael', 'villa', 'dorian', 'hear', 'mask', 'milo']
MAXW, MAXSEC = 720, 6.0


def face_y(src, a, b, w, h, ch):
    """竖向裁切的起点：脸的中心放在画面上方约 1/3（只读 framing 的缓存）"""
    cys = []
    for t in (a + (b - a) * q for q in (0.15, 0.5, 0.85)):
        key = f'v:{hashlib.sha1(str(src).encode()).hexdigest()[:12]}:{os.path.getsize(src)}:{t:.2f}'
        for x0, y0, x1, y1 in FR.main_faces([tuple(f) for f in FR._cache.get(key, [])]): cys.append((y0 + y1) / 2 * h)
    if not cys: return int((h - ch) * 0.22)
    return int(min(max(0, sum(cys) / len(cys) - ch * 0.33), h - ch))


def cut(src, out, a, b, y_hint=None):
    w, h = BV.dims(src)
    ch = min(h, int(w * 1.5) // 2 * 2); cw = int(ch / 1.5) // 2 * 2
    y = face_y(src, a, b, w, h, ch) if y_hint is None else int(min(max(0, y_hint), h - ch))
    W = min(cw, MAXW) // 2 * 2; H = int(W * 1.5) // 2 * 2
    vf = f'crop={cw}:{ch}:{(w - cw) // 2}:{y}' + (f',scale={W}:{H}:flags=lanczos' if W != cw else '') + ',fps=24,setsar=1,format=yuv420p'
    subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{a:.2f}', '-t', f'{min(MAXSEC, b - a):.2f}', '-i', str(src), '-an', '-vf', vf,
                    '-c:v', 'libx264', '-crf', '30', '-preset', 'slow', '-movflags', '+faststart', str(out)], check=True)
    d = BV.dur(out)
    subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{max(0.05, d * 0.4):.2f}', '-i', str(out), '-frames:v', '1', '-q:v', '4', str(out.with_suffix('.jpg'))], check=False)


def still(img, out):
    img = fix_stills.fixed(str(img))
    im = FR.load(img); W, H = im.size
    fs = [(a * W, b * H, c * W, d * H) for a, b, c, d in FR.main_faces([tuple(f) for f in FR._cache.get(FR.img_key(img), [])])]
    cw = min(W, H / 1.5); ch = cw * 1.5
    if fs:
        cx = (min(f[0] for f in fs) + max(f[2] for f in fs)) / 2; cy = (min(f[1] for f in fs) + max(f[3] for f in fs)) / 2
        x0 = min(max(0, cx - cw / 2), W - cw); y0 = min(max(0, cy - ch * 0.33), H - ch)
    else: x0 = (W - cw) / 2; y0 = (H - ch) * 0.2
    im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize((MAXW, int(MAXW * 1.5)), Image.LANCZOS).save(out, quality=82, optimize=True, progressive=True)


def jobs(sid):
    """[(clip id, 'v'|'s', src, a, b, y_hint)]，编号规则和 build_visuals / build_preset_visuals 相同"""
    out = []
    if sid in BV.PW:
        cfg = BV.PW[sid]
        for i, (src, a, b, cap) in enumerate(BV.pw_opening_shots(sid)): out.append((f'o{i:02d}', 'v', src, a, b, None))
        for i, rel in enumerate(cfg['extra']):
            v = BV.PWR / rel
            if v.exists(): out.append((f'c{i:02d}', 'v', v, 0, min(BV.CARD_SEC, BV.dur(v)), None))
        for i, rel in enumerate([s for s in cfg['stills'] if (BV.PWR / s).exists()]): out.append((f's{i:02d}', 's', BV.PWR / rel, 0, 0, None))
        idle = BV.IDLE_PW.get(sid)
        if idle and (BV.PWR / idle).exists(): out.append(('idle', 'v', BV.PWR / idle, 0, min(8, BV.dur(BV.PWR / idle)), None))
        return out
    cfg = BV.SRC[sid]
    if sid not in BP.PRESET:   # 有预设完整版的剧（magnus）播放器只用预设切片，原来的 o/c 不出高清
        for i, (src, a, b, cap) in enumerate(BV.opening_shots(cfg['opening'])): out.append((f'o{i:02d}', 'v', src, a, b, None))
        for i, (v, cap) in enumerate(BV.cards(cfg['cards'])): out.append((f'c{i:02d}', 'v', v, 0, min(BV.CARD_SEC, BV.dur(v)), None))
    for i, img in enumerate([s for s in cfg['stills'] if Path(s).exists()]): out.append((f's{i:02d}', 's', img, 0, 0, None))
    if sid in BP.PRESET:
        pc = BP.PRESET[sid]
        for cid, src, a, b, cap, y in pc['clips']: out.append((cid, 'v', Path(pc['media']) / f'{src}.mp4', a, b, y - 50))
    return out


def build(sid):
    V = {c['id']: c for c in json.load(open(ROOT / 'data' / 'visuals' / f'{sid}.json'))['clips']}
    od = ROOT / 'app' / 'v' / sid / 'hd'; od.mkdir(parents=True, exist_ok=True)
    todo, skipped = [], []
    for cid, kind, src, a, b, y in jobs(sid):
        if cid not in V: skipped.append(cid + ':no-id'); continue
        if kind == 'v' and abs((V[cid].get('dur') or 0) - (b - a)) > 0.6: skipped.append(f'{cid}:dur {V[cid].get("dur")} vs {b - a:.1f}'); continue   # 素材变了，别配错画面
        todo.append((cid, kind, src, a, b, y))

    def run(j):
        cid, kind, src, a, b, y = j
        out = od / (f'{cid}.mp4' if kind == 'v' else f'{cid}.jpg')
        if out.exists() and out.stat().st_size > 2000 and '--force' not in sys.argv: return
        try: cut(src, out, a, b, y) if kind == 'v' else still(src, out)
        except Exception as e:
            out.unlink(missing_ok=True); print('FAIL', sid, cid, repr(e)[:120], flush=True)
    with cf.ThreadPoolExecutor(5) as ex: list(ex.map(run, todo))
    mp4 = sorted(od.glob('*.mp4')); jpg = sorted(od.glob('*.jpg'))
    json.dump({'video': [f.stem for f in mp4], 'poster': [f.stem for f in jpg]}, open(od / 'index.json', 'w'))
    return sid, f'{len(mp4)} clips {sum(f.stat().st_size for f in mp4) / 1e6:.1f} MB', f'{len(jpg)} posters {sum(f.stat().st_size for f in jpg) / 1e6:.1f} MB', 'skipped ' + str(skipped[:6]) if skipped else ''


if __name__ == '__main__':
    for sid in [a for a in sys.argv[1:] if not a.startswith('--')] or RT:
        print(build(sid), flush=True)
