"""每段画面短片出一张海报帧（同名 .jpg，400 px，约 15–25 KB）：narra 播放器在这句开始时先显示海报，短片加载好再盖上去；
慢网络下只用海报（带 CSS 慢推），背景照样按内容换。用法：python3 build_posters.py [剧 id…] [--force]"""
import subprocess, sys, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parent
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
FP = FF.replace('ffmpeg', 'ffprobe')


def one(mp4):
    out = mp4.with_suffix('.jpg')
    if out.exists() and out.stat().st_size > 1500 and '--force' not in sys.argv: return 0
    d = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(mp4)], capture_output=True, text=True).stdout.strip() or 0)
    subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{max(0.1, d * 0.4):.2f}', '-i', str(mp4), '-frames:v', '1', '-vf', 'scale=400:-2', '-q:v', '6', str(out)], check=False)
    return out.stat().st_size if out.exists() else 0


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or sorted(p.name for p in (ROOT / 'app' / 'v').iterdir() if p.is_dir())
    for sid in ids:
        fs = sorted((ROOT / 'app' / 'v' / sid).glob('*.mp4'))
        with cf.ThreadPoolExecutor(6) as ex: sizes = list(ex.map(one, fs))
        tot = sum(f.with_suffix('.jpg').stat().st_size for f in fs if f.with_suffix('.jpg').exists())
        print(sid, len(fs), 'clips', f'{tot / 1e6:.2f} MB posters', flush=True)
