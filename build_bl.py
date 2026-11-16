"""BL 三部（evander 头纱下面不是她 / cade 全 A 选秀，只有我是 O / caius 带着狼王的孩子逃了五年）的定装图和封面（11-16）。
她要的画风：写实 / 乙女游戏 2.5D、3D 渲染。每部先出角色定装半身像（文生图，同一段画风描述），再拿定装图当参考出封面，
人物的脸、发型、服装跟定装图走。原图只留本机 data/bl/（.gitignore）。Waku google/nano-banana-2.1，约 4 credits/张。

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
STYLE = ('Art style: a semi-realistic 3D-rendered key visual in the style of a high-end otome romance game (2.5D): lifelike skin with fine texture, real fabric and metal materials, '
         'physically based cinematic lighting with soft rim light, shallow depth of field, slightly idealized handsome adult faces with natural proportions, clean and clear colours (not muddy, not oily, not over-dark). '
         'Not a flat anime drawing, not a cartoon, not a photograph of a real celebrity. ')
RULES = ('Rules: absolutely no text, letters, numbers, logos, watermarks, borders or frames anywhere. Correct anatomy: every visible hand has four fingers and a thumb with natural joints; keep hands simple and relaxed or out of frame. '
         'All characters are adults unless stated otherwise. Tasteful, fully clothed, no nudity.')
SERIES = {
 'evander': {
  'world': 'A Regency-like fantasy kingdom in deep winter: stone castles, candlelight, snow.',
  'cast': {
   'Evander': 'Duke Evander Thorne, 31, very tall and broad-shouldered, short black hair swept back, grey eyes, composed stern face with a faint tired warmth, clean-shaven. A black high-collared formal coat with silver embroidery, a white cravat, black leather gloves, a heavy signet ring. Firelight behind him.',
   'Jules': 'Julian Marlowe, 23, a slim young man with fine androgynous features, chestnut-brown hair to the jaw, hazel eyes, a quick stubborn mouth. He wears an open-collared white linen shirt and a dark riding waistcoat, a little wind-blown, stable lantern light. Clearly a young man.',
   'Juliana': 'Lady Juliana Marlowe, 23, the twin sister of a slim chestnut-haired young man: the same fine features and hazel eyes, long chestnut hair half pinned up, a travelling cloak over a plain blue dress, anxious and determined.',
   'Father': 'The Earl of Marlowe, late fifties, thin, greying brown hair, worried deep-set eyes, a slightly worn dark formal coat that was once expensive, standing in a cold chapel side room.',
   'Cordelia': 'Lady Cordelia Aldous, a 34-year-old woman with a smooth youthful face (clearly in her early thirties, no wrinkles, not elderly), elegant and sharp, rich golden-blonde hair (not white, not grey) in an elaborate updo, a knowing little smile, a rich plum silk gown with pearls, holding a porcelain teacup in a drawing room.',
   'Hobb': 'Hobb, the old steward of a ducal castle, late sixties, white hair neatly combed, lined calm face, a plain black tailcoat and grey waistcoat, hands folded, standing by a heavy wooden door.'},
  'cover': ('Movie-poster composition, vertical. A candlelit winter chapel. In the foreground, Jules (the slim chestnut-haired young man from the reference) stands in a white bridal gown with a long lace veil being lifted: '
            'the veil is half raised so we see his jaw, mouth and one hazel eye looking up, clearly a young man in a bride\'s dress. Behind and above him stands Evander (the tall black-haired duke from the reference), '
            'one black-gloved hand holding the edge of the veil, looking down at him with quiet intensity, not surprised. Snow falls past a tall window behind them, warm candle glow against cold blue light. '
            'Leave calm darker space in the lower third of the picture for a title.'),
  'cover_refs': ['Jules', 'Evander']},
 'cade': {
  'world': 'A modern city: an idol survival show, dormitories, practice rooms, a huge live stage.',
  'cast': {
   'Cade': 'Cade Winter, 24, an idol trainee and main dancer, tall and lean, black undercut hair falling over one eye, cool dark eyes, an unsmiling handsome face, a small silver ear stud. A black sleeveless practice top and a thin silver chain, practice-room mirrors and cold white light behind him.',
   'Kit': 'Kit Lennox, a 22-year-old adult man (clearly in his early twenties, not a teenager: a defined jawline and adult facial structure), an idol trainee, slim and quick, soft ash-blond hair, bright green eyes, a cheeky half-smile hiding nerves, a small matte black cuff clipped on the upper edge of his left ear. A plain white oversized sweatshirt with nothing printed or pinned on it (no badge, no tag), dormitory window light.',
   'Jax': 'Jax Halloran, a 23-year-old idol trainee and rapper with a smooth youthful handsome face in the same K-pop idol look as the other trainees (clearly in his early twenties, no stubble, no wrinkles), bleached silver hair with dark roots, sharp amused eyes, a lazy smirk, one eyebrow slit, a red varsity jacket over a black tee, layered chains, leaning on a corridor wall.',
   'Ezra': 'Ezra Quill, 23, an idol trainee and producer, dark brown curly hair, thin round glasses, calm unreadable face, large headphones around his neck, a grey hoodie, the glow of studio monitors on his face.',
   'Noel': 'Noel Park, 22, an idol trainee and main vocalist, warm brown hair, gentle brown eyes, a soft shy smile, a cream knit sweater, warm backstage bulb lights behind him.',
   'Victor': 'Victor Sable, 33, a wealthy heir, immaculate, dark blond hair combed back, pale cold blue eyes, a patient thin smile, a charcoal three-piece suit with a white boutonniere, standing in a church aisle with white flowers.',
   'Host': 'The host of a talent show, about forty, polished and charismatic, dark hair with a touch of grey, a midnight-blue stage suit, holding a cue card with no readable text and a slim microphone, stage lights behind.'},
  'cover': ('Movie-poster composition, vertical. A huge live stage seen from the stage side, strong blue-white backlight and haze. In the centre foreground Kit (the ash-blond young man from the reference) '
            'wears a fitted black-and-white stage jacket with silver details, turned three-quarters toward the viewer from the chest up, the black cuff on his left ear catching the light, lips closed in a small defiant half-smile, eyes bright. Behind him, spaced across the stage in the backlight, stand four tall young men all watching him: '
            'Cade (black undercut, nearest, arms at his sides, intense), Jax (silver hair, red jacket), Ezra (curly hair, glasses) and Noel (warm brown hair, cream sweater). A sea of small audience lights far below. '
            'The bottom third of the picture fades into deep dark blue stage shadow (dark, not white) for a title.'),
  'cover_refs': ['Kit', 'Cade', 'Jax', 'Ezra', 'Noel']},
 'caius': {
  'world': 'A northern fantasy kingdom of wolf shifters in deep winter: a stone capital, snow, moonlight, firelit halls.',
  'cast': {
   'Caius': 'Caius Vael, the Lycan King, a strikingly handsome man of 33 with a smooth youthful face (clearly in his early thirties: no wrinkles, no gaunt cheeks, clean-shaven), very tall and powerful, long black hair partly tied back with loose strands at his temples, gold eyes that glow faintly, a short scar through one eyebrow, a severe, tired but beautiful face, the romantic male lead of an otome game. A black fur-collared royal coat over dark leather, a plain iron circlet, moonlight from a high window in a dark hall.',
   'Eli': 'Eli Marrow, 26, a slender young man, a white wolf shifter in human form: white hair to the shoulders, pale silver-blue eyes, a quiet guarded gentle face. A worn grey travelling cloak with the hood half up, a healer\'s satchel strap across his chest, a cloth strip wound round his left wrist, snow falling.',
   'Tobin': 'Tobin, a five-year-old boy, small for his age, tousled black hair, big golden-brown eyes, round cheeks flushed with fever, wrapped in an oversized grey wool cloak, sleepy and brave. A child, clearly five years old.',
   'Maren': 'Lady Maren, a beautiful 28-year-old woman with a smooth youthful face (clearly in her twenties, no wrinkles), composed, long pale ash-blonde hair with a silvery sheen in an intricate braid, cool grey eyes, a sweet smile that does not reach them, a silver-white fur-trimmed court gown, a small bone clasp tied at her wrist, standing beside a throne.',
   'Isolde': 'Queen Mother Isolde, about sixty, regal and severe, black hair streaked with silver in a high coil, dark gold eyes, a deep red and black high-collared gown with a heavy gold chain, seated in a high-backed chair behind a thin curtain of incense smoke.',
   'Bram': 'Captain Bram of the royal guard, about forty, broad and weathered, short brown hair, a thick beard, a broken nose, dark steel-and-leather armour with a wolf-fur mantle, standing guard before great wooden doors.'},
  'cover': ('Movie-poster composition, vertical. A snowy night under a full moon outside a stone city wall. In the foreground Eli (the white-haired young man from the reference) in his grey cloak holds his sleeping five-year-old son Tobin '
            '(tousled black hair, from the reference) against his shoulder, looking past the viewer, guarded and tired. Behind him in the dark, tall and half in shadow, stands Caius (the black-haired king from the reference), '
            'his gold eyes glowing, looking at the two of them. Clear luminous blue moonlight with the faces well lit and readable (not murky, not too dark), a little warm torchlight on the faces, snow in the air. Leave calm darker space in the lower third of the picture for a title.'),
  'cover_refs': ['Eli', 'Tobin', 'Caius']},
}


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
    S = SERIES[sid]
    prompt = (STYLE + f'World: {S["world"]} A character portrait for the cast sheet of a romance drama: one person only, waist-up, facing the viewer at a slight three-quarter angle, eyes open and looking toward the viewer, '
              f'the whole head and both shoulders inside the picture with some space above the hair. Character: {S["cast"][name]} ' + RULES)
    err = None
    for _ in range(3):
        try: fetch(run(T2I, {'prompt': prompt, 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}), out); return sid, name, 'ok'
        except Exception as e: err = e; out.unlink(missing_ok=True)
    return sid, name, 'FAILED ' + str(err)[:160]


def cover_one(sid, force=False):
    out = D / sid / 'cover.jpg'
    if out.exists() and not force: return sid, 'cover', 'exists'
    S = SERIES[sid]; refs = [D / sid / f'cast_{n}.jpg' for n in S['cover_refs']]
    miss = [str(r) for r in refs if not r.exists()]
    if miss: return sid, 'cover', 'missing refs ' + ','.join(miss)
    desc = ' | '.join(f'{n} — {S["cast"][n]}' for n in S['cover_refs'])
    prompt = (STYLE + 'Create a NEW picture in exactly the same rendering style as the reference portraits. The characters must match their reference images exactly: same face, hair colour and hairstyle, eye colour and build '
              f'(reference images are given in this order: {", ".join(S["cover_refs"])}). Characters: {desc}. Scene: {S["cover"]} ' + RULES)
    err = None
    for _ in range(3):
        try: fetch(run(EDIT, {'prompt': prompt, 'images': [up(r) for r in refs], 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}), out); return sid, 'cover', 'ok'
        except Exception as e: err = e; out.unlink(missing_ok=True)
    return sid, 'cover', 'FAILED ' + str(err)[:160]


def sheet():
    from PIL import Image, ImageDraw
    W = 300; H = 450; pad = 10; rows = []
    for sid, S in SERIES.items():
        ims = [('cover', D / sid / 'cover.jpg')] + [(n, D / sid / f'cast_{n}.jpg') for n in S['cast']]
        ims = [(n, p) for n, p in ims if p.exists()]
        row = Image.new('RGB', (pad + len(ims) * (W + pad), H + 34 + pad), (18, 18, 22)); d = ImageDraw.Draw(row)
        for i, (n, p) in enumerate(ims):
            im = Image.open(p).convert('RGB').resize((W, H)); row.paste(im, (pad + i * (W + pad), 30)); d.text((pad + i * (W + pad) + 4, 8), f'{sid} · {n}', fill=(230, 230, 230))
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
