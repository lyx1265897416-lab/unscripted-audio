"""封面超分（11-11 她要求展示内容整体超分）：app/covers/<id>.jpg（约 720×1080）→ Waku image-upscaler 2k → 缩到 1080 宽 → app/covers/x/<id>.jpg。
首页主推大图、剧详情、播放器底图在网速正常时用它。用法：python3 build_covers_hd.py [剧 id…] [--force]"""
import json, re, subprocess, sys, concurrent.futures as cf
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'app' / 'covers' / 'x'; OUT.mkdir(parents=True, exist_ok=True)
TMP = ROOT / 'cache' / 'cover_sr'; TMP.mkdir(parents=True, exist_ok=True)


def one(f):
    out = OUT / f.name
    if out.exists() and out.stat().st_size > 30000 and '--force' not in sys.argv: return f.stem, 'exists'
    big = TMP / f.name
    if not (big.exists() and big.stat().st_size > 100000):
        up = subprocess.run(['waku', 'persist', str(f)], capture_output=True, text=True, timeout=180)
        m = re.search(r'"url":\s*"([^"]+)"', up.stdout)
        if not m: return f.stem, 'upload failed'
        subprocess.run(['waku', 'gen', 'run', 'wavespeed-ai/image-upscaler', '--capability', 'multimodal.generate.image', '--params',
                        json.dumps({'image': m.group(1), 'target_resolution': '2k', 'output_format': 'jpeg'}), '--wait', '--timeout', '300', '--out', str(big)], capture_output=True, text=True, timeout=360)
    if not (big.exists() and big.stat().st_size > 100000): return f.stem, 'sr failed'
    im = Image.open(big).convert('RGB'); w, h = im.size
    im.resize((1080, round(h * 1080 / w)), Image.LANCZOS).save(out, quality=84, optimize=True, progressive=True)
    return f.stem, f'{out.stat().st_size // 1024} KB'


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')]
    fs = [f for f in sorted((ROOT / 'app' / 'covers').glob('*.jpg')) if not ids or f.stem in ids]
    with cf.ThreadPoolExecutor(3) as ex:
        for r in ex.map(one, fs): print(r, flush=True)
