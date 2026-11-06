"""Unscripted Audio 的中转地址同步和隧道守护（launchd：com.vicky.realtime.unscripted-audio-sync）。
Pages 上的前端读 docs/relay.json 找当前隧道地址，所以链接长期不变：每分钟探一次隧道，地址变了就更新 relay.json 并推到 GitHub。
relay.json 只有地址，口令不进仓库。Cloudflare 临时隧道可能域名失效而进程还活着：连续 3 次连不上、这台 Mac 本身有网，就重启隧道（至少隔 10 分钟）。
照 tools/realtime-relays/app_relay_sync.py 的做法。"""
import json, os, re, subprocess, time
from pathlib import Path
from urllib import request as U, error as E

ROOT = Path(__file__).resolve().parent
F = ROOT / 'docs' / 'relay.json'
TUNNEL_LOG = ROOT / 'logs' / 'tunnel-public.log'
REPO = 'https://github.com/lyx1265897416-lab/unscripted-audio.git'
PAGES = 'https://lyx1265897416-lab.github.io/unscripted-audio/relay.json'
op = U.build_opener(U.ProxyHandler({}))
fails, kicked = 0, 0


def log(*a): print(time.strftime('%m-%d %H:%M:%S'), *a, flush=True)


def git(*a): return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, timeout=300)


def up(u):
    try:
        with op.open(u, timeout=20) as r: return r.status < 500
    except E.HTTPError as e: return e.code < 500 and e.code not in (404, 530)
    except Exception: return False


def latest():
    try: urls = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', TUNNEL_LOG.read_text(errors='ignore'))
    except OSError: return None
    return urls[-1] if urls else None


def published():
    try:
        with op.open(PAGES + '?t=%d' % time.time(), timeout=15) as r: return r.read().decode()
    except Exception: return ''


while True:
    try:
        old = json.loads(F.read_text()) if F.exists() else {}
        u = latest(); online = up('https://github.com')
        if u and up(u + '/health'):
            fails = 0
            if old.get('base') != u:
                F.parent.mkdir(exist_ok=True)
                F.write_text(json.dumps({'base': u, 'updated': time.strftime('%Y-%m-%dT%H:%M:%S%z')}, indent=1) + '\n')
                git('add', 'docs/relay.json')
                c = git('commit', '-m', '更新中转地址\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>', '--', 'docs/relay.json')
                log('relay.json', u, c.returncode, c.stderr.strip()[-160:])
        elif online:
            fails += 1
            if fails >= 3 and time.time() - kicked > 600:
                kicked = time.time(); fails = 0
                r = subprocess.run(['launchctl', 'kickstart', '-k', f'gui/{os.getuid()}/com.vicky.realtime.unscripted-audio-tunnel'], capture_output=True, text=True)
                log('kick tunnel', u, r.returncode, r.stderr.strip()[-120:])
        if online and F.exists() and json.loads(F.read_text()).get('base') not in published():
            r = git('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', REPO, 'main')
            log('push', r.returncode, r.stderr.strip()[-160:])
    except Exception as e:
        log('fail', repr(e)[:200])
    time.sleep(60)
