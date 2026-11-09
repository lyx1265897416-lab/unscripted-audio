"""Unscripted Audio 的中转地址同步和隧道守护（launchd：com.vicky.realtime.unscripted-audio-sync）。
Pages 上的前端读 docs/relay.json 找当前隧道地址，所以链接长期不变：每分钟探一次隧道，地址变了就更新 relay.json 并推到 GitHub。
relay.json 只有地址，口令不进仓库。Cloudflare 临时隧道可能域名失效而进程还活着：连续 3 次连不上、这台 Mac 本身有网，就重启隧道（至少隔 10 分钟）。
照 tools/realtime-relays/app_relay_sync.py 的做法。"""
import json, os, re, subprocess, time
from pathlib import Path
from urllib import request as U, error as E

ROOT = Path(__file__).resolve().parent
F = ROOT / 'docs' / 'relay.json'
# 11-09：两条独立的临时隧道（单条偶尔掉线十几秒，手机就卡住）；relay.json 给出两个地址，前端一条连不上就切另一条
TUNNELS = [(ROOT / 'logs' / 'tunnel-public.log', 'com.vicky.realtime.unscripted-audio-tunnel'),
           (ROOT / 'logs' / 'tunnel2-public.log', 'com.vicky.realtime.unscripted-audio-tunnel2')]
REPO = 'https://github.com/lyx1265897416-lab/unscripted-audio.git'
PAGES = 'https://lyx1265897416-lab.github.io/unscripted-audio/relay.json'
op = U.build_opener(U.ProxyHandler({}))
fails, kicked = [0, 0], [0, 0]


def log(*a): print(time.strftime('%m-%d %H:%M:%S'), *a, flush=True)


def git(*a): return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, timeout=300)


def up(u):
    try:
        with op.open(u, timeout=20) as r: return r.status < 500
    except E.HTTPError as e: return e.code < 500 and e.code not in (404, 530)
    except Exception: return False


def latest(path):
    try: urls = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', path.read_text(errors='ignore'))
    except OSError: return None
    return urls[-1] if urls else None


def published():
    try:
        with op.open(PAGES + '?t=%d' % time.time(), timeout=15) as r: return r.read().decode()
    except Exception: return ''


while True:
    try:
        old = json.loads(F.read_text()) if F.exists() else {}
        online = up('https://github.com'); good = []
        for i, (path, label) in enumerate(TUNNELS):
            u = latest(path)
            if u and up(u + '/health'): fails[i] = 0; good.append(u)
            elif online:
                fails[i] += 1
                if fails[i] >= 3 and time.time() - kicked[i] > 600:
                    kicked[i] = time.time(); fails[i] = 0
                    r = subprocess.run(['launchctl', 'kickstart', '-k', f'gui/{os.getuid()}/{label}'], capture_output=True, text=True)
                    log('kick tunnel', label, u, r.returncode, r.stderr.strip()[-120:])
        if good and (old.get('bases') or [old.get('base')]) != good:
            F.parent.mkdir(exist_ok=True)
            F.write_text(json.dumps({'base': good[0], 'bases': good, 'updated': time.strftime('%Y-%m-%dT%H:%M:%S%z')}, indent=1) + '\n')
            git('add', 'docs/relay.json')
            c = git('commit', '-m', '更新中转地址\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>', '--', 'docs/relay.json')
            log('relay.json', good, c.returncode, c.stderr.strip()[-160:])
        cur = json.loads(F.read_text()) if F.exists() else {}
        pub = published() if online and cur else ''
        if online and cur and any(b not in pub for b in (cur.get('bases') or [cur.get('base')])):
            r = git('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', REPO, 'main')
            log('push', r.returncode, r.stderr.strip()[-160:])
    except Exception as e:
        log('fail', repr(e)[:200])
    time.sleep(60)
