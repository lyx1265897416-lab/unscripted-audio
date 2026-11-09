import json, sys, time, urllib.request as U, concurrent.futures as cf
B = 'http://127.0.0.1:8913'; K = '3Vl2au8QUir9'
op = U.build_opener(U.ProxyHandler({}))
def post(p, b): return json.loads(op.open(U.Request(B + p, json.dumps(dict(b, k=K)).encode(), {'Content-Type': 'application/json'}), timeout=60).read())
def get(p): return json.loads(op.open(B + p, timeout=30).read())
def run(tts, text):
    r = post('/api/play', {'series': 'magnus', 'lang': 'zh', 'name': 'Vicky', 'tts': tts, 'prewarm': True}); sid = r['sid']
    t0 = time.time(); j = post('/api/next', {'sid': sid, 'text': text, 'via': 'free'})['job']
    first = None
    while time.time() - t0 < 120:
        d = get(f'/api/job?k={K}&id={j}')
        L = (d.get('ep') or {}).get('lines') or []
        if first is None and L and L[0].get('url'): first = round(time.time() - t0, 1)
        if d['status'] in ('done', 'error'): break
        time.sleep(0.5)
    return tts, sid, first, round(time.time() - t0, 1), d['status'], (d.get('t') or {})
with cf.ThreadPoolExecutor(2) as ex:
    for x in ex.map(lambda a: run(*a), [('flash', '我先不上车。你的眼睛到底怎么了？说实话。'), ('v4', '我先不上车。你的眼睛到底怎么了？说实话。')]): print(json.dumps(x, ensure_ascii=False))
