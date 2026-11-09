import json, time, urllib.request as U, sys
B = 'http://127.0.0.1:8913'; K = '3Vl2au8QUir9'; op = U.build_opener(U.ProxyHandler({}))
def post(p, b): return json.loads(op.open(U.Request(B + p, json.dumps(dict(b, k=K)).encode(), {'Content-Type': 'application/json'}), timeout=60).read())
def get(p): return json.loads(op.open(B + p, timeout=30).read())
audio = open(sys.argv[1], 'rb').read()
r = post('/api/call/start', {'series': 'rafael', 'lang': 'zh', 'name': 'Vicky', 'direction': 'outgoing'}); cid, j = r['cid'], r['job']
# wait until his first line is voiced (he is "talking"), then she cuts in
t = time.time(); have = 0
while True:
    d = get(f'/api/job?k={K}&id={j}&wait=8&have={have}'); L = d['call']['lines']; have = sum(1 for l in L if l.get('url') is not None)
    if have >= 1 or d['status'] == 'done': break
print('his first line voiced', round(time.time() - t, 1), [l['text'] for l in L][:2])
t = time.time()
req = U.Request(f'{B}/api/call/say?k={K}&cid={cid}&prev={j}&played=1&cut=1', data=audio, headers={'Content-Type': 'audio/mpeg'})
s = json.loads(op.open(req, timeout=60).read()); t_say = round(time.time() - t, 2)
print('say ->', s, 'roundtrip', t_say)
j2 = s['job']; have = 0; first = None
while True:
    d = get(f'/api/job?k={K}&id={j2}&wait=8&have={have}'); L = d['call']['lines']; have = sum(1 for l in L if l.get('url') is not None)
    if first is None and any(l.get('url') for l in L): first = round(time.time() - t, 2)
    if d['status'] in ('done', 'error'): break
print('after she stopped: first reply audio', first, 's; done', round(time.time() - t, 1), [l['text'] for l in L], d.get('t'))
post('/api/call/end', {'cid': cid, 'seconds': 20})
