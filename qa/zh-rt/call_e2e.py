import json, time, urllib.request as U, concurrent.futures as cf
B = 'http://127.0.0.1:8913'; K = '3Vl2au8QUir9'; op = U.build_opener(U.ProxyHandler({}))
def post(p, b): return json.loads(op.open(U.Request(B + p, json.dumps(dict(b, k=K)).encode(), {'Content-Type': 'application/json'}), timeout=60).read())
def get(p): return json.loads(op.open(B + p, timeout=120).read())
def fillers(lang):
    t = time.time(); d = get(f'/api/call/fillers?k={K}&series=rafael&who=Rafael&lang={lang}'); return lang, 'fillers', round(time.time() - t, 1), len(d.get('greet') or [])
def call(lang, text=None):
    t0 = time.time(); r = post('/api/call/start', {'series': 'rafael', 'lang': lang, 'name': 'Vicky', 'direction': 'outgoing'}); cid, j = r['cid'], r['job']
    out = []
    for turn in range(2):
        t = time.time(); first = None
        while time.time() - t < 90:
            d = get(f'/api/job?k={K}&id={j}'); L = (d.get('call') or {}).get('lines') or []
            if first is None and L and L[0].get('url'): first = round(time.time() - t, 1)
            if d['status'] in ('done', 'error'): break
            time.sleep(0.4)
        out.append({'turn': turn + 1, 'first_audio_s': first, 'done_s': round(time.time() - t, 1), 'lines': [l['text'] for l in L][:2], 't': d.get('t')})
        if turn == 0:
            j = post('/api/call/turn', {'cid': cid, 'text': text, 'via': 'voice'})['job']
    post('/api/call/end', {'cid': cid, 'seconds': 30})
    return lang, out
with cf.ThreadPoolExecutor(4) as ex:
    fs = [ex.submit(fillers, 'zh'), ex.submit(fillers, 'en'), ex.submit(call, 'zh', '你昨晚那个吻，是认真的吗？'), ex.submit(call, 'en', 'Was that kiss last night real?')]
    for f in fs: print(json.dumps(f.result(), ensure_ascii=False))
