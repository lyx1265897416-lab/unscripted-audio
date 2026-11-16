"""BL 三部（evander 头纱下面不是她 / cade 全 A 选秀，只有我是 O / caius 带着狼王的孩子逃了五年）的定装图和封面（11-16）。
她要的画风：写实 / 乙女游戏 2.5D、3D 渲染，角色从 Vicky 角色库里选（库里没有的按库的画风生成）。每部先出角色定装半身像
（库里的正面图 + 头部多角度当身份参考，只换服装和背景），再拿定装图当参考出封面。原图只留本机 data/bl/（.gitignore）。Waku google/nano-banana-2.1，约 4 credits/张。

  python3 build_bl.py cast [id…] [--only=剧.角色,…]    角色定装半身像 → data/bl/<剧>/cast_<角色>.jpg
  python3 build_bl.py cover [id…]                     封面（2:3）→ data/bl/<剧>/cover.jpg
  python3 build_bl.py sheet                            三部的定装图 + 封面拼一张对照图 → qa/bl/sheet.jpg
  加 --force 重做。
"""
import json, os, re, subprocess, sys, hashlib, pathlib
from concurrent.futures import ThreadPoolExecutor
ROOT = pathlib.Path(__file__).parent
D = ROOT / 'data' / 'bl'
T2I, EDIT = 'google/nano-banana-2.1/text-to-image', 'google/nano-banana-2.1/edit'
LIB = pathlib.Path('/Users/vicky/Documents/waku内容/vicky-character-library')
# 11-16 她否了第一版（文生图自己编的脸）：角色从 Vicky 角色库里选，库里没有的按库的画风生成。
# 画风 = 角色库的 otome_2d5d_3d 一族（白底 3D 乙游角色）。每个角色用库里的正面图 + 头部多角度当身份参考，只换剧里的服装和背景。
STYLE = ('Render in exactly the same art style as the reference images: a polished semi-realistic 3D otome-game character render (2.5D), refined delicate facial features, luminous clean skin, '
         'finely detailed hair strands, soft clear light, clean bright colours (not muddy, not oily, not over-dark). ')
RULES = ('Rules: absolutely no text, letters, numbers, logos, watermarks, borders or frames anywhere. Correct anatomy: every visible hand has four fingers and a thumb with natural joints; keep hands simple and relaxed or out of frame. '
         'All characters are adults unless stated otherwise. Tasteful, fully clothed, no nudity.')
P = lambda proj, n: f'human.{proj}-{n:02d}'
W34, O28, F17 = '3d-white-34-20260923', '3d-original-28-selected-20260924', '3d-front-17-20260923'
SERIES = {
 'evander': {
  'world': 'A Regency-like fantasy kingdom in deep winter: stone castles, candlelight, snow.',
  'cast': {
   'Evander': {'lib': P(O28, 8), 'num': 1474, 'look': 'Duke Evander Thorne, 31. Costume: a black high-collared Regency-style formal coat with silver embroidery, a white cravat, black leather gloves, a heavy signet ring. Background: a firelit stone bedchamber, softly blurred.'},
   'Jules': {'lib': P(W34, 23), 'num': 866, 'look': 'Julian Marlowe, 23, a slim young man. Costume: an open-collared white linen shirt and a dark riding waistcoat, a little wind-blown. Background: a stable at night with one warm lantern, softly blurred.'},
   'Juliana': {'lib': P(W34, 3), 'num': 717, 'look': 'Lady Juliana Marlowe, 23. Her hair is worn long and half pinned up. Costume: a travelling cloak over a plain blue Regency dress; anxious and determined. Background: a snowy castle courtyard at night, softly blurred.'},
   'Cordelia': {'lib': P(W34, 9), 'num': 759, 'look': 'Lady Cordelia Aldous, mid-thirties, a knowing little smile. Costume: a rich plum silk Regency gown with pearls; she holds a porcelain teacup. Background: a candlelit drawing room, softly blurred.'},
   'Father': {'style': [P(O28, 8), P(O28, 13)], 'look': 'A NEW character (do not copy the faces in the reference images, use them only for the rendering style): the Earl of Marlowe, a man in his late fifties, thin, greying brown hair, worried deep-set eyes, lined face, a slightly worn dark Regency formal coat that was once expensive. Background: a cold chapel side room, softly blurred.'},
   'Hobb': {'style': [P(O28, 8), P(O28, 13)], 'look': 'A NEW character (do not copy the faces in the reference images, use them only for the rendering style): Hobb, the old steward of a ducal castle, late sixties, neatly combed white hair, lined calm face, a plain black tailcoat and grey waistcoat. Background: a heavy wooden door in a stone corridor, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A candlelit winter chapel. In the foreground Jules stands in a white bridal gown with a long lace veil being lifted: the veil is half raised so we see his jaw, mouth and eyes looking up, '
            'clearly a young man in a bride\'s dress. Close behind and above him stands Evander in his black embroidered coat, one black-gloved hand holding the edge of the veil, looking down at him with quiet intensity, not surprised. '
            'Snow falls past a tall window behind them, warm candle glow against cool blue light. The lower third of the picture is calm and darker, for a title.'),
  'cover_refs': ['Jules', 'Evander']},
 'cade': {
  'world': 'A modern city: an idol survival show, dormitories, practice rooms, a huge live stage.',
  'cast': {
   'Cade': {'lib': P(W34, 19), 'num': 838, 'look': 'Cade Winter, 24, idol trainee and main dancer, unsmiling. Costume: a black sleeveless practice top and a thin silver chain. Background: a practice room with mirrors and cool white light, softly blurred.'},
   'Kit': {'lib': P(W34, 33), 'num': 936, 'look': 'Kit Lennox, 22, idol trainee, a cheeky half-smile hiding nerves. One small matte black cuff is clipped on the upper edge of his left ear (no other earrings). Costume: a plain white oversized sweatshirt with nothing printed on it. Background: a dormitory room with window light, softly blurred.'},
   'Jax': {'lib': P(W34, 31), 'num': 922, 'look': 'Jax Halloran, 23, idol trainee and rapper, a lazy smirk. Costume: a red varsity jacket over a black tee, layered thin chains. Background: a backstage corridor, softly blurred.'},
   'Ezra': {'lib': P(O28, 9), 'num': 1480, 'look': 'Ezra Quill, 23, idol trainee and producer, calm and unreadable, wearing his thin gold-rimmed glasses. Costume: a grey hoodie with large headphones around his neck. Background: a dim studio with glowing monitors, softly blurred.'},
   'Noel': {'lib': P(O28, 7), 'num': 1468, 'look': 'Noel Park, 22, idol trainee and main vocalist, a soft warm smile. Costume: a cream cable-knit sweater. Background: backstage dressing-room bulb lights, softly blurred.'},
   'Victor': {'lib': P(O28, 13), 'num': 1498, 'look': 'Victor Sable, 34, a wealthy heir, a patient thin smile. Costume: a charcoal three-piece suit with a white boutonniere. Background: a church aisle with white flowers, softly blurred.'},
   'Host': {'lib': P(F17, 11), 'num': 1376, 'look': 'The host of a talent show, polished and charismatic. Costume: a midnight-blue stage suit; he holds a slim microphone. Background: colourful stage lights, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A huge live stage seen from the stage side, strong blue-white backlight and haze. In the centre foreground Kit wears a fitted black-and-white stage jacket with silver details, '
            'turned three-quarters toward the viewer from the chest up, the black cuff on his left ear catching the light, lips closed in a small defiant half-smile. Behind him, spaced across the stage in the backlight, stand exactly FOUR tall young men (count them: four, two on each side of him), all watching him: '
            'on the left Cade (black hair, black sleeveless top, nearest, intense) and Noel (brown hair, cream cable-knit sweater, gentle); on the right Jax (silver hair, red varsity jacket) and Ezra (black hair, gold-rimmed glasses, grey hoodie). A sea of small audience lights far below. The bottom third of the picture fades into deep dark blue stage shadow for a title.'),
  'cover_refs': ['Kit', 'Cade', 'Jax', 'Ezra', 'Noel']},
 'caius': {
  'world': 'A northern fantasy kingdom of wolf shifters in deep winter: a stone capital, snow, moonlight, firelit halls.',
  'cast': {
   'Caius': {'lib': P(W34, 21), 'num': 852, 'look': 'Caius Vael, the Lycan King, 33, severe and tired; his amber eyes glow faintly gold. Costume: a black fur-collared royal coat over dark leather, a plain iron circlet on his brow. Background: a dark stone hall with moonlight from a high window, softly blurred, the face clearly lit.'},
   'Eli': {'lib': P(F17, 2), 'num': 1332, 'look': 'Eli Marrow, 26, a quiet guarded gentle young man (human ears, no pointed ears). Costume: a worn grey travelling cloak with the hood down over his light grey coat, a healer\'s satchel strap across his chest, a cloth strip wound round his left wrist. Background: falling snow outside a stone city wall, softly blurred.'},
   'Maren': {'lib': P(W34, 7), 'num': 745, 'look': 'Lady Maren, 28, a sweet smile that does not reach her eyes. Costume: a silver-white fur-trimmed court gown, a small bone clasp tied at her wrist. Background: a firelit throne hall, softly blurred.'},
   'Bram': {'lib': P(O28, 2), 'num': 1433, 'look': 'Captain Bram of the royal guard, about forty, weathered, with short stubble. Costume: dark steel-and-leather armour with a wolf-fur mantle. Background: great wooden doors in a torchlit corridor, softly blurred.'},
   'Tobin': {'style': [P(W34, 21)], 'look': 'A NEW character: Tobin, a five-year-old boy who is clearly the small son of the man in the reference image (the same black wavy hair and amber-gold eyes, a child\'s round face). Small for his age, cheeks flushed with fever, wrapped in an oversized grey wool cloak, sleepy and brave. A child, clearly five years old. Background: falling snow at night, softly blurred.'},
   'Isolde': {'style': [P(W34, 21), P(W34, 7)], 'look': 'A NEW character (do not copy the faces in the reference images, use them only for the rendering style): Queen Mother Isolde, about sixty, regal and severe, black hair streaked with silver in a high coil, dark gold eyes, fine lines on her face, a deep red and black high-collared gown with a heavy gold chain, seated in a high-backed chair. Background: an inner chamber with a thin veil of incense smoke, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A snowy night under a full moon outside a stone city wall. In the foreground Eli in his grey cloak holds his sleeping five-year-old son Tobin against his shoulder, looking past the viewer, guarded and tired. '
            'Several steps behind him and apart from them, half in shadow under a torch, stands Caius in his black fur-collared coat, his amber eyes glowing gold, watching the two of them; he does not touch them. '
            'Clear luminous blue moonlight with the faces well lit and readable, a little warm torchlight, snow in the air. The lower third of the picture is calm and darker, for a title.'),
  'cover_refs': ['Eli', 'Tobin', 'Caius']},
}
_MAN = None


def lib_refs(cid, n=2):
    """库里这个角色的身份参考：正面图 + 头部多角度"""
    global _MAN
    if _MAN is None: _MAN = {g['id']: g for g in json.load(open(LIB / 'gallery-manifest.json'))['characters']}
    sl = {s['key']: s['paths'] for s in _MAN[cid]['asset_slots']}
    out = []
    for k in ('front', 'head_angles', 'identity', 'full_body'):
        for p in sl.get(k) or []:
            if str(LIB / p) not in out and (LIB / p).exists(): out.append(str(LIB / p))
    return out[:n]


def _json(s):
    m = re.search(r'\{.*\}', s or '', re.S)
    if not m: raise RuntimeError('no json in waku output: ' + (s or '')[-200:])
    return json.loads(m.group(0))


def run(model, params):
    r = subprocess.run(['waku', 'gen', 'run', model, '--capability', 'multimodal.generate.image', '--params', json.dumps(params)], capture_output=True, text=True, timeout=300)
    j = _json(r.stdout + '\n' + r.stderr)
    for _ in range(4):
        if j.get('asset_url') or not j.get('job_id'): break
        r = subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '240'], capture_output=True, text=True, timeout=300)
        try: j = dict(_json(r.stdout), job_id=j['job_id'])
        except RuntimeError: continue
    if not j.get('asset_url'): raise RuntimeError('no asset ' + json.dumps(j)[:200])
    return j['asset_url']


def fetch(url, out):
    for _ in range(3):
        r = subprocess.run(['curl', '-s', '-f', '--retry', '2', '--noproxy', '*', '-o', str(out), url])
        if r.returncode == 0 and out.exists() and out.stat().st_size > 10000: return True
    raise RuntimeError('download failed ' + url[:80])


URLS = D / '_urls.json'


def up(path):
    U = json.loads(URLS.read_text()) if URLS.exists() else {}
    k = hashlib.sha1((str(path) + str(os.path.getmtime(path))).encode()).hexdigest()
    if k in U: return U[k]
    from PIL import Image
    im = Image.open(path).convert('RGB'); im.thumbnail((1280, 1280)); tmp = D / f'_up_{k[:10]}.jpg'; im.save(tmp, quality=90)
    m = None
    for _ in range(4):
        r = subprocess.run(['waku', 'persist', str(tmp)], capture_output=True, text=True, timeout=120)
        m = re.search(r'"url":\s*"([^"]+)"', r.stdout)
        if m: break
    url = m.group(1) if m else None
    if not url:   # `waku persist` 被限流（429 asset_upload_quota_exceeded）时改走 MCP 的内联上传
        import base64, wakumcp
        global _MCP
        _MCP = globals().get('_MCP') or wakumcp.WakuMCP()
        r = _MCP.tool('polyverse_upload_local_asset', {'filename': tmp.name, 'content_type': 'image/jpeg', 'asset_kind': 'image', 'data_base64': base64.b64encode(tmp.read_bytes()).decode()}, timeout=180)
        url = r.get('public_url') or r.get('url') or (r.get('asset') or {}).get('public_url')
        if not url: tmp.unlink(missing_ok=True); raise RuntimeError('upload failed ' + json.dumps(r)[:200])
    tmp.unlink(missing_ok=True)
    U = json.loads(URLS.read_text()) if URLS.exists() else {}; U[k] = url; URLS.write_text(json.dumps(U, indent=0)); return url


def cast_one(sid, name, force=False):
    out = D / sid / f'cast_{name}.jpg'; out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force: return sid, name, 'exists'
    S = SERIES[sid]; c = S['cast'][name]
    if c.get('lib'):
        refs = lib_refs(c['lib'])
        prompt = (STYLE + 'The reference images show ONE character from a character library (front view and head angles). Create a NEW waist-up portrait of this exact same person: the same face, facial structure, eye colour, '
                  'hair colour and hairstyle, skin tone and apparent age as in the references. Only the costume and the background change. '
                  f'World: {S["world"]} One person only, facing the viewer at a slight three-quarter angle, eyes open, the whole head and both shoulders inside the picture with some space above the hair. Character: {c["look"]} ' + RULES)
    else:
        refs = [r for cid in c['style'] for r in lib_refs(cid, 1)]
        prompt = (STYLE + f'World: {S["world"]} A waist-up cast portrait, one person only, facing the viewer at a slight three-quarter angle, eyes open, the whole head and both shoulders inside the picture with some space above the hair. '
                  f'Character: {c["look"]} ' + RULES)
    err = None
    for _ in range(3):
        try: fetch(run(EDIT, {'prompt': prompt, 'images': [up(r) for r in refs], 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}), out); return sid, name, 'ok'
        except Exception as e: err = e; out.unlink(missing_ok=True)
    return sid, name, 'FAILED ' + str(err)[:160]


def cover_one(sid, force=False):
    out = D / sid / 'cover.jpg'
    if out.exists() and not force: return sid, 'cover', 'exists'
    S = SERIES[sid]; refs = [D / sid / f'cast_{n}.jpg' for n in S['cover_refs']]
    miss = [str(r) for r in refs if not r.exists()]
    if miss: return sid, 'cover', 'missing refs ' + ','.join(miss)
    extra = [r for n in S['cover_refs'][:2] if S['cast'][n].get('lib') for r in lib_refs(S['cast'][n]['lib'], 1)]   # 两位主角再加库里的正面图，脸不走样
    desc = ' | '.join(f'{n} — {S["cast"][n]["look"]}' for n in S['cover_refs'])
    prompt = (STYLE + 'Create a NEW picture. The characters must match their reference portraits exactly: same face, hair colour and hairstyle, eye colour, build and costume '
              f'(the first {len(refs)} reference images are costume portraits in this order: {", ".join(S["cover_refs"])}; the remaining images are the library identity sheets of the first two). Characters: {desc}. Scene: {S["cover"]} ' + RULES)
    err = None
    for _ in range(3):
        try: fetch(run(EDIT, {'prompt': prompt, 'images': [up(r) for r in refs] + [up(r) for r in extra], 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}), out); return sid, 'cover', 'ok'
        except Exception as e: err = e; out.unlink(missing_ok=True)
    return sid, 'cover', 'FAILED ' + str(err)[:160]


def sheet():
    from PIL import Image, ImageDraw, ImageFont
    try: font = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', 17)
    except Exception: font = ImageFont.load_default()
    W = 300; H = 450; pad = 10; rows = []
    for sid, S in SERIES.items():
        ims = [('封面', D / sid / 'cover.jpg', None)] + [(n, D / sid / f'cast_{n}.jpg', c) for n, c in S['cast'].items()]
        ims = [x for x in ims if x[1].exists()]
        row = Image.new('RGB', (pad + len(ims) * (W + pad), 34 + H + 6 + 150 + pad), (18, 18, 22)); d = ImageDraw.Draw(row)
        for i, (n, p, c) in enumerate(ims):
            x = pad + i * (W + pad)
            row.paste(Image.open(p).convert('RGB').resize((W, H)), (x, 32))
            d.text((x + 2, 6), f'{n}' + (f' · 角色库 #{c["num"]}' if c and c.get('num') else ' · 按库画风生成' if c else ''), fill=(235, 235, 235), font=font)
            if c and c.get('lib'):   # 库里的原图（正面）放在下面对照
                r = lib_refs(c['lib'], 1)
                if r:
                    im = Image.open(r[0]).convert('RGB'); w, h = im.size; im = im.crop((0, 0, w, min(h, int(w * 1.0)))); im.thumbnail((150, 150)); row.paste(im, (x, 32 + H + 6))
                    d.text((x + 158, 32 + H + 60), '← 库里的原图', fill=(160, 160, 170), font=font)
        rows.append(row)
    out = Image.new('RGB', (max(r.width for r in rows), sum(r.height for r in rows)), (18, 18, 22)); y = 0
    for r in rows: out.paste(r, (0, y)); y += r.height
    (ROOT / 'qa' / 'bl').mkdir(parents=True, exist_ok=True); out.save(ROOT / 'qa' / 'bl' / 'sheet.jpg', quality=88); print('sheet', out.size)


if __name__ == '__main__':
    a = sys.argv[1:]; cmd = a[0] if a else ''; force = '--force' in a
    only = next((x.split('=', 1)[1].split(',') for x in a if x.startswith('--only=')), None)
    ids = [x for x in a[1:] if x in SERIES] or list(SERIES)
    if cmd == 'cast':
        jobs = [(s, n) for s in ids for n in SERIES[s]['cast'] if not only or f'{s}.{n}' in only]
        with ThreadPoolExecutor(4) as ex:
            for r in ex.map(lambda j: cast_one(*j, force=force), jobs): print(*r, flush=True)
    elif cmd == 'cover':
        for s_ in ids: print(*cover_one(s_, force=force), flush=True)
    elif cmd == 'sheet': sheet()
    else: print(__doc__)
