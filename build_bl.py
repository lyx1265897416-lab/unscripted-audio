"""BL 三部（evander 头纱下面不是她 / cade 全 A 选秀，只有我是 O / caius 带着狼王的孩子逃了五年）的定装图和封面。

11-16 她定的三条：
1. 角色从 Vicky 角色库里选（库里没有的年龄段按库的画风生成），不要文生图自己编脸；
2. 画风用写实（角色库的 realistic_live_action 一族），不用 3D 乙游那一族；
3. 服装造型优先从 Vicky 服装造型库里选，实在没有和设定匹配的才重新生成。
做法：每个角色用库里的正面图 + 头部多角度当身份参考，库里的「完整造型」图当服装参考，只新画背景。
原图只留本机 data/bl/（.gitignore）。Waku google/nano-banana-2.1/edit，约 4 credits/张。

  python3 build_bl.py cast [id…] [--only=剧.角色,…]    角色定装半身像 → data/bl/<剧>/cast_<角色>.jpg
  python3 build_bl.py cover [id…]                     封面（2:3）→ data/bl/<剧>/cover.jpg
  python3 build_bl.py sheet                            三部的定装图 + 封面拼一张对照图（标角色和服装的库编号）→ qa/bl/sheet.jpg
  加 --force 重做。
"""
import json, os, re, subprocess, sys, hashlib, pathlib
from concurrent.futures import ThreadPoolExecutor
ROOT = pathlib.Path(__file__).parent
D = ROOT / 'data' / 'bl'
LIB = pathlib.Path('/Users/vicky/Documents/waku内容/vicky-character-library')
EDIT = 'google/nano-banana-2.1/edit'
STYLE = ('Photorealistic live-action drama still, exactly the look of the reference portraits: a real person photographed with a 50mm lens at shallow depth of field, natural skin with fine texture and pores, '
         'soft clear light on the face, clean natural colours (not muddy, not oily, not over-dark, no heavy teal grading). Not a 3D render, not an illustration, no plastic skin, no heavy makeup. ')
RULES = ('Rules: absolutely no text, letters, numbers, logos, watermarks, borders or frames anywhere. Correct anatomy: every visible hand has four fingers and a thumb with natural joints; keep hands simple and relaxed or out of frame. '
         'All characters are adults unless stated otherwise. Tasteful, fully clothed, no nudity.')
WM, M31, M23, F32 = 'western-male-white-28-v3-20260923', 'male-white-portraits-31-v2-20260923', 'male-white-portraits-23-v2-20260923', 'front-id-32-20260923'
P = lambda proj, n: f'human.{proj}-{n:02d}'
# lib = 角色库里的人；outfit = 服装造型库编号（完整造型）；wear = 库里没有匹配服装时才写，按文字生成；style = 库里没有这个年龄段时用来定画风的参考
SERIES = {
 'evander': {
  'world': 'An old-world ducal castle in deep winter: stone halls, candlelight, snow outside tall windows.',
  'cast': {
   'Evander': {'lib': P(WM, 18), 'outfit': 364, 'look': 'Duke Evander Thorne, 31, composed and stern. He wears the black leather gloves from the outfit reference. No glasses. Background: a firelit stone bedchamber, softly blurred.'},
   'Jules': {'lib': P(WM, 4), 'outfit': 814, 'look': 'Julian Marlowe, 23, a slim young man, a little wind-blown, wary. No backpack, no wristwatch, bare wrists. Background: a stable at night with one warm lantern, softly blurred.'},
   'Juliana': {'lib': P(F32, 22), 'outfit': 329, 'look': 'Lady Juliana Marlowe, 23, anxious and determined, the black lace shawl from the outfit reference around her shoulders, no hat. Background: a snowy castle courtyard at dusk, softly blurred.'},
   'Cordelia': {'lib': P(F32, 29), 'outfit': 303, 'look': 'Lady Cordelia Aldous, mid-thirties, a knowing little smile, holding a porcelain teacup. Background: a candlelit drawing room, softly blurred.'},
   'Father': {'style': [P(WM, 18), P(WM, 12)], 'outfit': 23, 'look': 'A NEW person (do not copy the faces in the reference portraits, they only set the photographic style): the Earl of Marlowe, a man in his late fifties, thin, greying brown hair, worried deep-set eyes, a lined face. No cap, no gloves. Background: a cold chapel side room, softly blurred.'},
   'Hobb': {'style': [P(WM, 18), P(WM, 12)], 'outfit': 363, 'look': 'A NEW person (do not copy the faces in the reference portraits, they only set the photographic style): Hobb, the old steward of a ducal castle, late sixties, neatly combed white hair, a lined calm face, hands folded. Background: a heavy wooden door in a stone corridor, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A candlelit winter chapel. In the foreground Jules stands dressed as a bride: he wears the white high-necked long-sleeved blouse and long tiered ruffled white skirt from the bridal outfit reference, '
            'and a long white lace veil that is being lifted, half raised so we see his jaw, mouth and eyes looking up; clearly a young man in a bride\'s dress. Close behind and above him stands Evander in his black suit, '
            'one black-gloved hand holding the edge of the veil, looking down at him with quiet intensity, not surprised. Snow falls past a tall window behind them, warm candle glow against cool daylight. The lower third of the picture is calm and darker, for a title.'),
  'cover_refs': ['Jules', 'Evander'], 'cover_outfits': [1194]},
 'cade': {
  'world': 'A modern city: an idol survival show, dormitories, practice rooms, a huge live stage.',
  'cast': {
   'Cade': {'lib': P(M31, 20), 'outfit': 808, 'look': 'Cade Winter, 24, idol trainee and main dancer, unsmiling. No watch. Background: a practice room with mirrors and cool daylight, softly blurred.'},
   'Kit': {'lib': P(M31, 11), 'outfit': 828, 'look': 'Kit Lennox, 22, idol trainee, a cheeky half-smile hiding nerves. One small matte black cuff is clipped on the upper edge of his left ear. Background: a dormitory room with window light, softly blurred.'},
   'Jax': {'lib': P(M31, 21), 'outfit': 68, 'look': 'Jax Halloran, 23, idol trainee and rapper, a lazy smirk. Background: a backstage corridor, softly blurred.'},
   'Ezra': {'lib': P(WM, 10), 'outfit': 65, 'look': 'Ezra Quill, 23, idol trainee and producer, calm and unreadable, wearing his thin round glasses, large headphones around his neck. No shoulder bag. Background: a dim studio with glowing monitors, softly blurred.'},
   'Noel': {'lib': P(M31, 6), 'outfit': 762, 'look': 'Noel Park, 22, idol trainee and main vocalist, a soft warm smile. No bag. Background: backstage dressing-room bulb lights, softly blurred.'},
   'Victor': {'lib': P(WM, 12), 'outfit': 1, 'look': 'Victor Sable, 33, a wealthy heir on his wedding day, a patient thin smile. Background: a church aisle with white flowers, softly blurred.'},
   'Host': {'lib': P(M23, 15), 'outfit': 361, 'look': 'The host of a talent show, about forty, polished and charismatic, holding a slim microphone. No glasses. Background: colourful stage lights, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A huge live stage seen from the stage side, strong blue-white backlight and haze. In the centre foreground Kit wears the black shirt, white tie and black trousers from the stage outfit reference, '
            'turned three-quarters toward the viewer from the chest up, the black cuff on his left ear catching the light, lips closed in a small defiant half-smile. Behind him stand exactly FOUR tall young men (count them: two on each side of him), all watching him: '
            'on the left Cade (sleeveless dark top, nearest, intense) and Noel (oatmeal knit, gentle); on the right Jax (platinum hair, black leather jacket) and Ezra (dark curls, round glasses, grey knit hoodie). '
            'A sea of small audience lights far below. The bottom third of the picture fades into deep dark blue stage shadow for a title.'),
  'cover_refs': ['Kit', 'Cade', 'Jax', 'Ezra', 'Noel'], 'cover_outfits': [70]},
 'caius': {
  'world': 'A northern kingdom of wolf shifters in deep winter: a stone capital, snow, moonlight, firelit halls.',
  'cast': {
   'Caius': {'lib': P(M31, 23), 'wear': 'a long black wool royal coat with a heavy black fur collar over dark leather, a plain iron circlet on his brow', 'look': 'Caius Vael, the Lycan King, 33, severe and tired; his eyes are a striking amber-gold. Background: a dark stone hall with moonlight from a high window, softly blurred, the face clearly lit.'},
   'Eli': {'lib': P(WM, 6), 'wear': 'a worn grey wool travelling cloak with the hood down over a plain pale linen shirt, a leather healer\'s satchel strap across his chest, a cloth strip wound round his left wrist', 'look': 'Eli Marrow, 26, a quiet guarded gentle young man. Background: falling snow outside a stone city wall, softly blurred.'},
   'Maren': {'lib': P(F32, 23), 'outfit': 312, 'look': 'Lady Maren, 28, a sweet smile that does not reach her eyes, a small bone clasp tied at her wrist. Background: a firelit throne hall, softly blurred.'},
   'Bram': {'lib': P(M31, 22), 'wear': 'dark steel-and-leather armour with a wolf-fur mantle', 'look': 'Captain Bram of the royal guard, about forty, weathered. Background: great wooden doors in a torchlit corridor, softly blurred.'},
   'Tobin': {'style': [P(M31, 23)], 'wear': 'an oversized grey wool cloak wrapped around him', 'look': 'A NEW person: Tobin, a five-year-old boy who is clearly the small son of the man in the reference portrait (the same dark wavy hair and amber-gold eyes, a child\'s round face). He is a very young child of five: a small body, a large head for his body, a soft round baby-ish face, chubby cheeks flushed with fever, small hands, kindergarten age (not eight or nine), sleepy and brave. Background: falling snow at dusk, softly blurred.'},
   'Isolde': {'style': [P(M31, 23), P(F32, 23)], 'outfit': 1235, 'look': 'A NEW person (do not copy the faces in the reference portraits, they only set the photographic style): Queen Mother Isolde, about sixty, regal and severe, black hair streaked with silver in a high coil, dark amber eyes, fine lines on her face, seated in a high-backed chair. No handbag. Background: an inner chamber with a thin veil of incense smoke, softly blurred.'}},
  'cover': ('Movie-poster composition, vertical. A snowy night under a full moon outside a stone city wall. In the foreground Eli in his grey cloak holds his sleeping five-year-old son Tobin against his shoulder, looking past the viewer, guarded and tired. '
            'Several steps behind him and apart from them, half in shadow under a torch, stands Caius in his black fur-collared coat, his amber-gold eyes catching the light, watching the two of them; he does not touch them. '
            'Clear luminous blue moonlight with the faces well lit and readable, a little warm torchlight, snow in the air. The lower third of the picture is calm and darker, for a title.'),
  'cover_refs': ['Eli', 'Tobin', 'Caius'], 'cover_outfits': []},
}
_MAN = _NUM = _OUT = None


def _load():
    global _MAN, _NUM, _OUT
    if _MAN is None:
        m = json.load(open(LIB / 'gallery-manifest.json'))
        _MAN = {g['id']: g for g in m['characters']}
        _NUM = {a['path']: a.get('library_number') for a in m['assets']}
        _OUT = {}
        for a in m['assets']:
            if a.get('wardrobe_batch') and a['category'] == 'outfit': _OUT.setdefault(a['library_number'], a)


def lib_refs(cid, n=2):
    """库里这个角色的身份参考：正面图 + 头部多角度"""
    _load(); sl = {s['key']: s['paths'] for s in _MAN[cid]['asset_slots']}; out = []
    for k in ('front', 'head_angles', 'identity', 'full_body'):
        for p in sl.get(k) or []:
            if str(LIB / p) not in out and (LIB / p).exists(): out.append(str(LIB / p))
    return out[:n]


def lib_num(cid):
    _load(); sl = {s['key']: s['paths'] for s in _MAN[cid]['asset_slots']}
    for k in ('front', 'identity'):
        for p in sl.get(k) or []:
            if _NUM.get(p): return _NUM[p]


def outfit(num):
    _load(); a = _OUT[num]; return str(LIB / a['path']), a.get('outfit_name') or a['title']


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
_MCP = None
import threading
_UPL = threading.Lock()


def up(path):
    """参考图传到 Waku：`waku persist` 被限流（429 asset_upload_quota_exceeded）时改走 MCP 的内联上传。结束时 close_mcp() 关掉自己起的那个进程。"""
    global _MCP
    with _UPL:
        U = json.loads(URLS.read_text()) if URLS.exists() else {}
        k = hashlib.sha1((str(path) + str(os.path.getmtime(path))).encode()).hexdigest()
        if k in U: return U[k]
        from PIL import Image
        im = Image.open(path).convert('RGB'); im.thumbnail((1280, 1280)); tmp = D / f'_up_{k[:10]}.jpg'; im.save(tmp, quality=90)
        url = None
        if _MCP is None:   # 先试一次 persist；限流了这一轮就不再试
            r = subprocess.run(['waku', 'persist', str(tmp)], capture_output=True, text=True, timeout=120)
            m = re.search(r'"url":\s*"([^"]+)"', r.stdout); url = m.group(1) if m else None
        if not url:
            import base64, wakumcp
            _MCP = _MCP or wakumcp.WakuMCP()
            r = _MCP.tool('polyverse_upload_local_asset', {'filename': tmp.name, 'content_type': 'image/jpeg', 'asset_kind': 'image', 'data_base64': base64.b64encode(tmp.read_bytes()).decode()}, timeout=180)
            url = r.get('public_url') or r.get('url') or (r.get('asset') or {}).get('public_url')
            if not url: tmp.unlink(missing_ok=True); raise RuntimeError('upload failed ' + json.dumps(r)[:200])
        tmp.unlink(missing_ok=True)
        U[k] = url; URLS.write_text(json.dumps(U, indent=0)); return url


def close_mcp():
    """只关自己起的这一个（按进程对象；不要按名字 pkill，会杀掉中转的配音通道）"""
    global _MCP
    if _MCP is not None:
        try: _MCP.p.kill()
        except Exception: pass
        _MCP = None


def cast_one(sid, name, force=False):
    out = D / sid / f'cast_{name}.jpg'; out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force: return sid, name, 'exists'
    S = SERIES[sid]; c = S['cast'][name]
    refs = lib_refs(c['lib']) if c.get('lib') else [r for cid in c['style'] for r in lib_refs(cid, 1)]
    who = ('The first reference images show ONE real-looking person from a casting library (front view and head angles). Create a NEW waist-up portrait of this exact same person: the same face, facial structure, eye colour, '
           'hair colour and hairstyle, skin tone and apparent age. ') if c.get('lib') else 'The portrait reference images only set the photographic style. '
    if c.get('outfit'):
        op, on = outfit(c['outfit']); refs = refs + [op]
        wear = (f'The LAST reference image is a flat-lay outfit board. The person wears exactly that outfit ({on}): the same garments, colours, fabrics and cut. Bags, hats, glasses, watches and other loose accessories on the board are left out unless the character note asks for them. ')
    else:
        wear = f'Costume: {c["wear"]}. '
    prompt = (STYLE + who + wear + f'World: {S["world"]} One person only, framed from the waist up (a medium close shot, not a full-body or knee shot: the face is large and clearly readable), facing the viewer at a slight three-quarter angle, eyes open, the whole head and both shoulders inside the picture with some space above the hair. '
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
    outs = [outfit(n) for n in S.get('cover_outfits') or []]
    desc = ' | '.join(f'{n} — {S["cast"][n]["look"]}' for n in S['cover_refs'])
    prompt = (STYLE + 'Create a NEW picture. The characters must match their reference portraits exactly: same face, hair colour and hairstyle, eye colour, build and costume '
              f'(the first {len(refs)} reference images are costume portraits in this order: {", ".join(S["cover_refs"])}; the next {len(extra)} are the casting-library identity sheets of the first two'
              + (f'; the last {len(outs)} image(s) are flat-lay outfit boards named in the scene: {", ".join(o[1] for o in outs)}' if outs else '') +
              f'). Characters: {desc}. Scene: {S["cover"]} ' + RULES)
    err = None
    for _ in range(3):
        try: fetch(run(EDIT, {'prompt': prompt, 'images': [up(r) for r in refs] + [up(r) for r in extra] + [up(o[0]) for o in outs], 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}), out); return sid, 'cover', 'ok'
        except Exception as e: err = e; out.unlink(missing_ok=True)
    return sid, 'cover', 'FAILED ' + str(err)[:160]


def _font(n):
    from PIL import ImageFont
    for f in ('/System/Library/Fonts/Hiragino Sans GB.ttc', '/System/Library/Fonts/STHeiti Medium.ttc'):
        try: return ImageFont.truetype(f, n)
        except Exception: pass
    return ImageFont.load_default()


def sheet():
    """每个角色：定装图 + 下面两张小图（角色库原图、服装库原图），都标库编号"""
    from PIL import Image, ImageDraw
    font, small = _font(17), _font(14)
    W = 300; H = 450; pad = 10; TH = 170; rows = []
    for sid, S in SERIES.items():
        ims = [('封面', D / sid / 'cover.jpg', None)] + [(n, D / sid / f'cast_{n}.jpg', c) for n, c in S['cast'].items()]
        ims = [x for x in ims if x[1].exists()]
        row = Image.new('RGB', (pad + len(ims) * (W + pad), 34 + H + 6 + TH + 22 + pad), (18, 18, 22)); d = ImageDraw.Draw(row)
        for i, (n, p, c) in enumerate(ims):
            x = pad + i * (W + pad)
            row.paste(Image.open(p).convert('RGB').resize((W, H)), (x, 32))
            d.text((x + 2, 6), n, fill=(235, 235, 235), font=font)
            if not c: continue
            y = 32 + H + 6
            if c.get('lib'):
                im = Image.open(lib_refs(c['lib'], 1)[0]).convert('RGB'); w, h = im.size; im = im.crop((0, 0, w, min(h, int(w * 1.15)))); im.thumbnail((146, TH)); row.paste(im, (x, y))
                d.text((x, y + TH + 2), f'角色库 #{lib_num(c["lib"])}', fill=(170, 170, 180), font=small)
            else: d.text((x, y + 60), '库里没有这个\n年龄段，新生成', fill=(170, 170, 180), font=small)
            if c.get('outfit'):
                op, on = outfit(c['outfit']); im = Image.open(op).convert('RGB'); im.thumbnail((146, TH)); row.paste(im, (x + 152, y))
                d.text((x + 152, y + TH + 2), f'服装库 #{c["outfit"]}', fill=(170, 170, 180), font=small)
            else: d.text((x + 152, y + 60), '服装库没有\n匹配的，新生成', fill=(170, 170, 180), font=small)
        rows.append(row)
    out = Image.new('RGB', (max(r.width for r in rows), sum(r.height for r in rows)), (18, 18, 22)); y = 0
    for r in rows: out.paste(r, (0, y)); y += r.height
    (ROOT / 'qa' / 'bl').mkdir(parents=True, exist_ok=True); out.save(ROOT / 'qa' / 'bl' / 'sheet.jpg', quality=88); print('sheet', out.size)


if __name__ == '__main__':
    a = sys.argv[1:]; cmd = a[0] if a else ''; force = '--force' in a
    only = next((x.split('=', 1)[1].split(',') for x in a if x.startswith('--only=')), None)
    ids = [x for x in a[1:] if x in SERIES] or list(SERIES)
    try:
        if cmd == 'cast':
            jobs = [(s, n) for s in ids for n in SERIES[s]['cast'] if not only or f'{s}.{n}' in only]
            with ThreadPoolExecutor(4) as ex:
                for r in ex.map(lambda j: cast_one(*j, force=force), jobs): print(*r, flush=True)
        elif cmd == 'cover':
            for s_ in ids: print(*cover_one(s_, force=force), flush=True)
        elif cmd == 'sheet': sheet()
        else: print(__doc__)
    finally:
        close_mcp()
