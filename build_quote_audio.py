"""把每个角色的那句台词预先配好、做成静态文件（11-13 她要求：点一下立刻播，不能转半天）。
  python3 build_quote_audio.py [id…]
对 data/quotes.json 里每部剧 / 每个角色 / 中英文：向本机中转要这一句（/api/quote：没配过就配一次，配过的直接给，和剧里同一个声音、已拉到统一响度），
转成 64 kbps 单声道 → app/quote/<剧>.<角色>.<语言>.mp3，并拷到 docs/quote/。已有的跳过（--force 重做）。一次 4 路，不多发。"""
import json, sys, subprocess, shutil, urllib.request as U, urllib.parse as P, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parent; APP = ROOT / 'app' / 'quote'; DOCS = ROOT / 'docs' / 'quote'
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
Q = json.load(open(ROOT / 'data' / 'quotes.json')); K = open(ROOT / 'token.txt').read().strip()
op = U.build_opener(U.ProxyHandler({})); FORCE = '--force' in sys.argv
def one(job):
    sid, key, lang = job; out = APP / f'{sid}.{key.replace(" ", "")}.{lang}.mp3'
    if out.exists() and out.stat().st_size > 2000 and not FORCE: return job, 'kept'
    h = json.loads(op.open('http://127.0.0.1:8913/health', timeout=10).read()).get('tts', {})
    if h.get('degraded'): return job, 'SKIPPED (voice service is timing out)'
    try:
        b = op.open('http://127.0.0.1:8913/api/quote?' + P.urlencode({'k': K, 'series': sid, 'who': key, 'lang': lang}), timeout=150).read()
    except Exception as e: return job, 'FAILED ' + repr(e)[:80]
    r = subprocess.run([FF, '-v', 'error', '-y', '-i', '-', '-ac', '1', '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '64k', str(out)], input=b, capture_output=True)
    if r.returncode or not out.exists(): return job, 'FAILED encode'
    return job, f'ok {out.stat().st_size // 1024} KB'
if __name__ == '__main__':
    APP.mkdir(exist_ok=True); DOCS.mkdir(exist_ok=True)
    ids = [a for a in sys.argv[1:] if a in Q] or list(Q)
    jobs = [(sid, key, lang) for sid in ids for key in Q[sid] for lang in ('en', 'zh') if Q[sid][key].get(lang)]
    bad = 0
    with cf.ThreadPoolExecutor(4) as ex:
        for job, res in ex.map(one, jobs):
            if not res.startswith(('ok', 'kept')): bad += 1; print(job, res, flush=True)
    for f in APP.glob('*.mp3'): shutil.copy(f, DOCS / f.name)
    n = len(list(APP.glob('*.mp3'))); print('clips', n, 'of', len(jobs), '| failed', bad, '| total', sum(f.stat().st_size for f in APP.glob('*.mp3')) // 1024, 'KB')
