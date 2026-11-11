"""narra 的 live 背景（11-11 她要求：背景放动态视频（live），不要频繁切换；清晰度不够，整体超分）。
每部 realtime 剧选 K 段动态片段（第 1 集按时间均分 K 个窗口，每个窗口取出现最久、时长够、有人脸的视频片段），
从源片切竖版高质量片段 → Waku FlashVSR 超分到 1080p → 首尾交叉淡化做成无缝循环 → app/v/<id>/live/<clip>.mp4（1080×1620）
+ 同名 .jpg 海报 + live.json（{"live": [按窗口顺序的片段编号]}）。播放器按进度停在对应窗口的那一段上，一集只换 K 次。
用法：python3 build_live.py --pick            只看选了哪些，不花额度
     python3 build_live.py [剧 id…] [--force]  超分并出片（约 50 credits/段）
需要中转在跑（取第 1 集画面时间轴 /api/ep1pack）。"""
import json, re, subprocess, sys, time, urllib.request as U, concurrent.futures as cf
from pathlib import Path
import build_visuals as BV
import build_hd as HD
import framing as FR

ROOT = Path(__file__).resolve().parent
FF, FP = BV.FF, BV.FP
K, MINSEC, MAXSEC, XF = 5, 3.2, 6.0, 0.6
TOKEN = ''
op = U.build_opener(U.ProxyHandler({}))
TMP = ROOT / 'cache' / 'live_sr'; TMP.mkdir(parents=True, exist_ok=True)
FIX = {'magnus': {'p013': 'p042'}, 'mii': {'o00': 'c16'}, 'hear': {'idle': 'o02'}, 'mask': {'o09': 'c03'}, 'milo': {'o03': None}, 'kael': {'idle': None}}


def pack(lang, k):
    return json.loads(op.open(f'http://127.0.0.1:8913/api/ep1pack?lang={lang}&k={k}', timeout=30).read())


def has_face(src, a, b):
    import hashlib, os
    for t in (a + (b - a) * q for q in (0.15, 0.5, 0.85)):
        key = f'v:{hashlib.sha1(str(src).encode()).hexdigest()[:12]}:{os.path.getsize(src)}:{t:.2f}'
        if FR._cache.get(key): return True
    return False


def pick(sid, packs):
    jobs = {cid: (src, a, b, y) for cid, kind, src, a, b, y in HD.jobs(sid) if kind == 'v'}
    hdv = set(json.load(open(ROOT / 'app' / 'v' / sid / 'hd' / 'index.json'))['video'])
    score = [dict() for _ in range(K)]
    for p in packs:
        ep = p.get(sid) or {}; d = ep.get('dur') or 1
        for x in ep.get('visuals') or []:
            c = x['clip']
            if c not in jobs or c not in hdv: continue
            src, a, b, y = jobs[c]
            if b - a < MINSEC: continue
            for w in range(K):
                lo, hi = d * w / K, d * (w + 1) / K
                ov = max(0, min(x['e'], hi) - max(x['s'], lo))
                if ov > 0: score[w][c] = score[w].get(c, 0) + ov * (1.4 if has_face(src, a, b) else 1.0) * (1.0 if b - a >= 4.5 else 0.8)
    live = []
    for w in range(K):
        best = [c for c, _ in sorted(score[w].items(), key=lambda kv: -kv[1]) if c not in live]
        if best: live.append(best[0]); continue
        # 这个窗口没有合格的视频片段：从整集里补一个还没用过的、最长的
        rest = sorted([c for c in jobs if c in hdv and c not in live and jobs[c][2] - jobs[c][1] >= MINSEC], key=lambda c: -(jobs[c][2] - jobs[c][1]) - (2 if has_face(*jobs[c][:3]) else 0))
        if rest: live.append(rest[0])
    # 人工看过缩略图后的替换：手部/耳朵特写、和别的片段重复的待机、分屏新闻画面换成有人物的；None = 去掉
    for a, b in (FIX.get(sid) or {}).items():
        if a in live:
            i = live.index(a)
            if b and b in jobs and b not in live: live[i] = b
            else: live.pop(i)
    return live, jobs


def run_json(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    m = re.search(r'\{.*\}', r.stdout, re.S)
    return json.loads(m.group(0)) if m else {'error': (r.stdout + r.stderr)[-300:]}


def make(sid, cid, job):
    src, a, b, y = job
    od = ROOT / 'app' / 'v' / sid / 'live'; od.mkdir(parents=True, exist_ok=True)
    out = od / f'{cid}.mp4'
    if out.exists() and out.stat().st_size > 20000 and '--force' not in sys.argv: return cid, 'exists', 0
    w, h = BV.dims(src)
    ch = min(h, int(w * 1.5) // 2 * 2); cw = int(ch / 1.5) // 2 * 2
    yy = HD.face_y(src, a, b, w, h, ch) if y is None else int(min(max(0, y), h - ch))
    d = min(MAXSEC, b - a)
    raw = TMP / f'{sid}.{cid}.in.mp4'; sr = TMP / f'{sid}.{cid}.sr.mp4'
    # 1) 源片的竖版高质量片段（不缩放，尽量不损失）
    subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{a:.2f}', '-t', f'{d:.2f}', '-i', str(src), '-an', '-vf', f'crop={cw}:{ch}:{(w - cw) // 2}:{yy},fps=24,setsar=1,format=yuv420p',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-movflags', '+faststart', str(raw)], check=True)
    # 2) 超分（Waku FlashVSR → 1080p）
    if not (sr.exists() and sr.stat().st_size > 50000):
        up = subprocess.run(['waku', 'persist', str(raw)], capture_output=True, text=True, timeout=180)
        m = re.search(r'"url":\s*"([^"]+)"', up.stdout)
        if not m: return cid, 'upload failed ' + (up.stdout + up.stderr)[-120:], 0
        j = run_json(['waku', 'gen', 'run', 'wavespeed-ai/flashvsr', '--capability', 'multimodal.generate.video', '--params', json.dumps({'video': m.group(1), 'target_resolution': '1080p'}),
                      '--wait', '--timeout', '420', '--out', str(sr)], 480)
        for _ in range(3):
            if sr.exists() and sr.stat().st_size > 50000: break
            if j.get('job_id'): j = dict(run_json(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '300', '--out', str(sr)], 360), job_id=j['job_id'])
            else: break
        if not (sr.exists() and sr.stat().st_size > 50000): return cid, 'sr failed ' + str(j)[:160], 0
    # 3) 无缝循环（尾巴淡到开头）+ 1080×1620
    dd = BV.dur(sr)
    fc = (f'[0:v]fps=24,scale=1080:1620:flags=lanczos,setsar=1,format=yuv420p,split=3[m][h][t];'
          f'[m]trim={XF}:{dd - XF:.3f},setpts=PTS-STARTPTS[body];[t]trim={dd - XF:.3f}:{dd:.3f},setpts=PTS-STARTPTS,settb=AVTB,fps=24[tail];[h]trim=0:{XF},setpts=PTS-STARTPTS,settb=AVTB,fps=24[head];'
          f'[tail][head]xfade=transition=fade:duration={XF - 0.05:.2f}:offset=0,format=yuv420p[x];[body][x]concat=n=2:v=1:a=0[o]')
    r = subprocess.run([FF, '-v', 'error', '-y', '-i', str(sr), '-filter_complex', fc, '-map', '[o]', '-an', '-c:v', 'libx264', '-crf', '27', '-maxrate', '1500k', '-bufsize', '3000k', '-preset', 'slow', '-movflags', '+faststart', str(out)], capture_output=True, text=True)   # 码率封顶：细节多的全景一段原来 3 MB
    if r.returncode or not out.exists() or out.stat().st_size < 20000:
        out.unlink(missing_ok=True); return cid, 'loop failed ' + r.stderr[-160:], 0
    subprocess.run([FF, '-v', 'error', '-y', '-i', str(out), '-frames:v', '1', '-vf', 'scale=720:1080:flags=lanczos', '-q:v', '4', str(out.with_suffix('.jpg'))], check=False)
    return cid, 'ok', out.stat().st_size


if __name__ == '__main__':
    k = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--k=')), None)
    if not k: raise SystemExit('pass --k=<relay token>')
    packs = [pack('en', k), pack('zh', k)]
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or HD.RT
    plan = {sid: pick(sid, packs) for sid in ids}
    for sid, (live, jobs) in plan.items():
        print(sid, [(c, round(jobs[c][2] - jobs[c][1], 1), 'face' if has_face(*jobs[c][:3]) else '-') for c in live], flush=True)
    if '--pick' in sys.argv: raise SystemExit
    todo = [(sid, c, jobs[c]) for sid, (live, jobs) in plan.items() for c in live]
    with cf.ThreadPoolExecutor(4) as ex:
        for sid, c, r in zip([t[0] for t in todo], [t[1] for t in todo], ex.map(lambda t: make(*t), todo)):
            print(sid, r, flush=True)
    for sid, (live, jobs) in plan.items():
        od = ROOT / 'app' / 'v' / sid / 'live'
        ok = [c for c in live if (od / f'{c}.mp4').exists()]
        json.dump({'live': ok}, open(od / 'live.json', 'w'))
        print(sid, 'live', ok, f'{sum((od / f"{c}.mp4").stat().st_size for c in ok) / 1e6:.1f} MB', flush=True)
