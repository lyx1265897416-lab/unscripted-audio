"""介绍页角色的“一句话”（11-13 她要求：角色下面不写配音员，换成一句有个性的台词，点一下能听这个角色说）。
  python3 build_quotes.py [id…]   让模型给每部剧的每个有声角色 + 旁白各写一句（中英各一句）→ data/quotes.json
已有的不重写（加 --force 重写）；mii 是手写的，不会被覆盖。配音在中转里按需做（/api/quote，存 cache/quote/）。"""
import json, os, re, sys, urllib.request as U
from pathlib import Path
ROOT = Path(__file__).resolve().parent; DATA = ROOT / 'data'
for l in open(os.path.expanduser('~/.config/vicky-realtime/env')):
    m = re.match(r'\s*(?:export\s+)?(\w+)=["\']?([^"\'\n]*)', l)
    if m: os.environ.setdefault(m.group(1), m.group(2))
BASE = [s['id'] for s in json.load(open(DATA / 'series_base.json'))]
VOICES = json.load(open(DATA / 'voices.json'))
OUT = DATA / 'quotes.json'
Q = json.load(open(OUT)) if OUT.exists() else {}
HAND = {'mii': {'Mii': {'zh': '今天不要上班。咪养你。', 'en': 'No work today. Mii will take care of you.'},
                'Store Clerk': {'zh': '哎呀，小猫又自己来买东西啦？', 'en': 'Well, look who came shopping all on its own again.'},
                'NARR': {'zh': '它叫咪，三个月大，今天说要照顾你一整天。', 'en': 'Its name is Mii. Three months old, and in charge of you for the whole day.'}}}
op = U.build_opener(U.ProxyHandler({}))
def chat(prompt, model):
    body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 1400, 'temperature': 0.7, 'reasoning': {'enabled': False}}
    r = op.open(U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'}), timeout=90)
    return json.loads(r.read())['choices'][0]['message']['content']
def cast(sid):
    w = json.load(open(DATA / 'world' / f'{sid}.json')); out = []
    for ch in w['characters']:
        key = ch['name'].split()[0] if ch['name'].split()[0] in VOICES[sid] else ch['name']
        if key not in VOICES[sid]: continue
        out.append((key, ch))
    return w, out
def make(sid):
    w, cs = cast(sid)
    people = '\n'.join(f'- key "{k}": {c.get("name_zh") or c["name"]} / {c["name"]}；身份：{c.get("role_zh", "")}；性格：{(c.get("personality") or "")[:260]}；说话方式：{(c.get("speech") or "")[:200]}' for k, c in cs)
    pr = (f'有声互动剧《{w.get("ep1_title_zh", "")}》。故事：{(w.get("premise_zh") or w.get("synopsis_zh") or "")[:500]}\n听众是女主“你”。\n\n角色：\n{people}\n- key "NARR": 旁白（贴着听众耳朵讲故事的女声）\n\n'
          '给每个角色写一句最能代表他 / 她的话，放在角色介绍下面，点一下可以试听这个角色的声音。要求：\n'
          '1. 是这个角色会亲口说的一句台词（对“你”说，或他的口头禅），一听就知道是谁、是什么性格；旁白那句是一句带画面感的开场白。\n'
          '2. 有个性、有记忆点，不剧透后面的反转和结局，不要解释设定，不要引号，不要舞台说明或方括号标签。\n'
          '3. 中文 8–22 个字；英文 5–16 个词，口语、自然，是英文母语者会说的话，不是中文直译。两种语言意思对应即可。\n'
          '4. 只输出 JSON：{"<key>": {"zh": "…", "en": "…"}, …}，key 用上面给的原样。')
    for model in ('moonshotai/kimi-k3', 'deepseek/deepseek-v4.1-flash', 'z-ai/glm-5.3-prime'):
        try:
            t = chat(pr, model); m = re.search(r'\{[\s\S]*\}', t); d = json.loads(m.group(0))
            ok = {k: {'zh': str(v['zh']).strip().strip('“”"'), 'en': str(v['en']).strip().strip('“”"')} for k, v in d.items() if isinstance(v, dict) and v.get('zh') and v.get('en') and (k == 'NARR' or k in VOICES[sid])}
            if len(ok) >= len(cs): return ok, model
        except Exception as e: print('  ', sid, model, repr(e)[:120], flush=True)
    return None, None
if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if a in BASE] or BASE; force = '--force' in sys.argv
    for sid in ids:
        if sid in HAND: Q[sid] = HAND[sid]; continue
        if sid in Q and not force: continue
        d, model = make(sid)
        if d: Q[sid] = d; print(sid, model, json.dumps(d, ensure_ascii=False), flush=True)
        else: print(sid, 'FAILED', flush=True)
        json.dump(Q, open(OUT, 'w'), ensure_ascii=False, indent=1)
    json.dump(Q, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print('series', len(Q), 'lines', sum(len(v) for v in Q.values()))
