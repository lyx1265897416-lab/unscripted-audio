"""Prota Top10 的播放器画面库：原卡场景图 / 角色图 → 6 秒缓推方形短片（app/v/<id>/sNN.mp4）+ 画面描述（快模型看图写，供台词↔画面匹配）。
输出 data/visuals/<id>.json：{"clips":[{"id","src","dur","kind":"still","cap"}],"pool":[…]}。需要 OPENROUTER_API_KEY（中转进程里的那把）。"""
import json, os, sys, base64, io, hashlib, concurrent.futures as cf, urllib.request as U
from pathlib import Path
from PIL import Image, ImageOps
import build_visuals as BV

ROOT = Path(__file__).resolve().parent
IDS = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']
MAX = 18
op = U.build_opener(U.ProxyHandler({}))


def caption(path, cast, title):
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB'); im.thumbnail((640, 640))
    b = io.BytesIO(); im.save(b, 'JPEG', quality=80)
    names = '\n'.join(f'- {c["name"]}：{(c.get("look_en") or "")[:220]}' for c in cast[:12])
    msg = [{'type': 'text', 'text': f'这是有声剧《{title}》的一张场景图。角色外貌参考：\n{names}\n\n用一句中文（25–45 字）描述画面：谁（能认出就写名字，认不出写外貌）、在哪、在做什么、情绪/氛围。只输出这一句。'},
           {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()}}]
    body = {'model': 'deepseek/deepseek-v4.1-flash', 'messages': [{'role': 'user', 'content': msg}], 'max_tokens': 120, 'temperature': 0.2, 'reasoning': {'enabled': False}}
    req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                    headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
    return json.loads(op.open(req, timeout=60).read())['choices'][0]['message']['content'].strip().strip('"“”')


def pick(p):
    """场景图优先（去掉封面、去重），不够再补角色定装图；最多 MAX 张，均匀取"""
    seen, out = set(), []
    for s in p['scenes']:
        if s['route'] == '封面' or s['path'] in seen: continue
        seen.add(s['path']); out.append(s['path'])
    for c in p['characters']:
        for f in (c['presets'][:2] + c['base'][:1]):
            if f not in seen: seen.add(f); out.append(f)
    if len(out) > MAX: out = [out[round(i * (len(out) - 1) / (MAX - 1))] for i in range(MAX)]
    return out


def build(sid):
    p = json.load(open(ROOT / 'data/prota' / f'{sid}.json')); w = json.load(open(ROOT / 'data/world' / f'{sid}.json'))
    od = ROOT / 'app' / 'v' / sid; od.mkdir(parents=True, exist_ok=True)
    capf = ROOT / 'data/prota' / f'{sid}.captions.json'
    caps = json.load(open(capf)) if capf.exists() else {}
    imgs = pick(p)

    def one(i_f):
        i, f = i_f; cid = f's{i:02d}'; out = od / f'{cid}.mp4'
        if not (out.exists() and out.stat().st_size > 2000): BV.kenburns(f, out)
        k = hashlib.sha1(f.encode()).hexdigest()[:12]
        if k not in caps:
            try: caps[k] = caption(f, p['characters'], w['title_zh'])
            except Exception as e: caps[k] = '剧照：' + Path(f).stem[:40]; print('caption fail', sid, cid, repr(e)[:80], flush=True)
        return {'id': cid, 'kind': 'still', 'cap': '剧照：' + caps[k], 'src': f'v/{sid}/{cid}.mp4', 'dur': round(BV.dur(out), 2)}
    with cf.ThreadPoolExecutor(6) as ex: clips = list(ex.map(one, enumerate(imgs)))
    json.dump(caps, open(capf, 'w'), ensure_ascii=False, indent=1)
    (ROOT / 'data' / 'visuals').mkdir(exist_ok=True)
    json.dump({'clips': clips, 'pool': [c['id'] for c in clips]}, open(ROOT / 'data' / 'visuals' / f'{sid}.json', 'w'), ensure_ascii=False, indent=1)
    size = sum(x.stat().st_size for x in od.glob('*.mp4'))
    return sid, len(clips), f'{size / 1e6:.1f}MB', clips[0]['cap'][:50] if clips else ''


if __name__ == '__main__':
    for sid in [a for a in sys.argv[1:] if not a.startswith('--')] or IDS:
        print(build(sid), flush=True)
