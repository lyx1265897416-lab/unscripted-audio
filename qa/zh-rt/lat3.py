import json, sys, time, statistics as st, concurrent.futures as cf
sys.path.insert(0, '../..')
from wakumcp import WakuMCP
V = 'MQkiCZS3mnl44caDtxkJ'
TX = ['你倒是会挑时候。上车，路上我把一切都告诉你。', '别回头看，他们的人还在楼上。', '我数到三，你要是还不走，我就抱你上去。', '你的手在抖。冷吗，还是怕我？', '今晚过后，你可以恨我，但现在先听我的。', '车库的门要关了。Vicky，过来。']
E = {'v4': ('elevenlabs/eleven-v4', lambda t: dict(text='[quietly] ' + t, voice_id=V, stability=0.4, similarity=0.8)),
     'v4-turbo': ('elevenlabs/eleven-v4-turbo', lambda t: dict(text=t, voice_id=V, stability=0.4, similarity=0.8)),
     'turbo-v2.5': ('elevenlabs/turbo-v2.5', lambda t: dict(text=t, voice_id=V))}
P = [WakuMCP() for _ in range(3)]
def one(i, k, t):
    m, f = E[k]; s = time.monotonic()
    try: r = P[i].tool('multimodal_run_model', {'capability': 'multimodal.generate.audio', 'model_id': m, 'parameters': f(t)}, timeout=120); ok = bool(r.get('asset_url'))
    except Exception: ok = False
    return k, round(time.monotonic() - s, 2), ok
R = {k: [] for k in E}
for t in TX:
    with cf.ThreadPoolExecutor(3) as ex:
        for k, s, ok in ex.map(lambda a: one(*a), [(i, k, t) for i, k in enumerate(E)]):
            if ok: R[k].append(s)
    print({k: v[-1] for k, v in R.items() if v}, flush=True)
print(json.dumps({k: {'median': st.median(v), 'min': min(v), 'max': max(v), 'n': len(v)} for k, v in R.items() if v}))
