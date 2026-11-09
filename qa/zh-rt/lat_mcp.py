import json, sys, time, threading, concurrent.futures as cf
sys.path.insert(0, '../..')
from wakumcp import WakuMCP
from lat_zh import J
POOL = [WakuMCP() for _ in range(6)]
def run(i, k):
    m, p = J[k]; t = time.monotonic()
    try:
        r = POOL[i % 6].tool('multimodal_run_model', {'capability': 'multimodal.generate.audio', 'model_id': m, 'parameters': p}, timeout=120)
        return k, round(time.monotonic() - t, 2), (r.get('asset_url') or str(r)[:150])
    except Exception as e:
        return k, round(time.monotonic() - t, 2), 'ERR ' + repr(e)[:150]
res = {}
for rnd in range(3):
    with cf.ThreadPoolExecutor(6) as ex:
        for k, s, u in ex.map(lambda a: run(*a), enumerate(J)):
            res.setdefault(k, []).append(s); print(rnd, k, s, u[-60:], flush=True)
print(json.dumps(res))
