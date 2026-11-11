"""画面库露脸检查：每段短片取中间一帧，Qwen3-VL 找脸；有人但脸被画面边切掉、或整段没脸的标出来，并出每部剧的缩略图总览。
用法：python3 check_framing.py [sid…] --sheet <目录>（需要 OPENROUTER_API_KEY）"""
import json, sys, glob, hashlib, concurrent.futures as cf
from pathlib import Path
from PIL import Image, ImageDraw
import framing as FR

ROOT = Path(__file__).resolve().parent


def check(sid):
    V = json.load(open(ROOT / 'data/visuals' / f'{sid}.json'))
    rows = []

    def one(c):
        f = ROOT / 'app' / c['src']
        if not f.exists(): return c['id'], c.get('kind'), None, [], 'missing'
        t = min(max(0.1, (c.get('dur') or 6) / 2), 30)
        im = FR.grab(f, t)
        key = f'chk:{hashlib.sha1(f.read_bytes()).hexdigest()[:16]}'
        fs = FR.faces(im, key)
        cut = [x for x in fs if (x[0] < 0.01 or x[2] > 0.99 or x[3] > 0.985) and (x[2] - x[0]) > 0.08]
        return c['id'], c.get('kind'), im, fs, ('cut' if cut else 'ok' if fs else 'noface')
    with cf.ThreadPoolExecutor(8) as ex: rows = list(ex.map(one, V['clips']))
    return rows


def sheet(sid, rows, out, tw=150, cols=8):
    rows = [r for r in rows if r[2] is not None]
    S = Image.new('RGB', (tw * cols, (tw + 14) * ((len(rows) + cols - 1) // cols)), (40, 40, 40)); d = ImageDraw.Draw(S)
    for i, (cid, kind, im, fs, st) in enumerate(rows):
        t = im.copy(); t.thumbnail((tw, tw)); x, y = (i % cols) * tw, (i // cols) * (tw + 14)
        S.paste(t, (x, y + 14))
        dd = ImageDraw.Draw(S)
        for a, b, c, e in fs: dd.rectangle([x + a * tw, y + 14 + b * tw, x + c * tw, y + 14 + e * tw], outline=(255, 60, 60) if st == 'cut' else (60, 220, 90))
        d.text((x + 3, y + 1), f'{cid} {st}', fill=(255, 220, 120) if st != 'ok' else (200, 200, 200))
    S.save(out, quality=82)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    od = Path(sys.argv[sys.argv.index('--sheet') + 1]) if '--sheet' in sys.argv else None
    ids = [a for a in args if not od or a != str(od)] or sorted(Path(p).stem for p in glob.glob(str(ROOT / 'data/visuals/*.json')))
    allr = {}
    for sid in ids:
        r = check(sid); allr[sid] = [(a, b, s) for a, b, _, _, s in r]
        from collections import Counter
        print(sid, dict(Counter(x[4] for x in r)), 'cut:', [x[0] for x in r if x[4] == 'cut'], flush=True)
        if od: od.mkdir(parents=True, exist_ok=True); sheet(sid, r, od / f'{sid}.jpg')
    if od: json.dump(allr, open(od / 'result.json', 'w'), indent=0)
