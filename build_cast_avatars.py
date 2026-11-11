"""介绍页演员表的头像（11-11 她要求：介绍页的角色头像 / 形象全部补齐）。
原来只有主角和能来电的角色有头像，其他角色显示名字首字母。这里给每个有台词的角色出一张 app/avatars/cast/<剧>.<角色键>.jpg（320×320）：
- 有现成定装图 / 脸部参考的：直接按脸裁（各剧的角色库、perhaps-worlds 的 ref、Prota 原卡角色图）。
- 没有任何形象的（7 个 realtime 配角 + 10 个 Prota 配角）：用这部剧主角的图做画风参考，按世界卡里的身份设定生成一张半身像
  （Waku google/nano-banana-2.1/edit），原图留在 data/cast_gen/（只留本机），再按脸裁。
旁白不出人像，介绍页用一个话筒徽标（app.js）。
用法：python3 build_cast_avatars.py copy       现成图 → 头像（要 OPENROUTER_API_KEY 找脸；结果缓存在 data/faces.json）
     python3 build_cast_avatars.py gen [--only=剧.角色,…]   生成缺的
     加 --force 重做。"""
import json, os, re, subprocess, sys, concurrent.futures as cf
from pathlib import Path
from PIL import Image, ImageOps
import framing as FR

ROOT = Path(__file__).resolve().parent
R = ROOT.parents[1]
PW = R / 'external' / 'perhaps-worlds'
OUT = ROOT / 'app' / 'avatars' / 'cast'
GEN = ROOT / 'data' / 'cast_gen'; GEN.mkdir(parents=True, exist_ok=True)
FORCE = '--force' in sys.argv
V = json.load(open(ROOT / 'data' / 'voices.json'))
PROTA = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']

# 现成的定装图 / 脸部参考（realtime 13 部的配角；主角用剧的头像）
SRC = {
    'magnus': {'Luca': R / 'outputs/magnus-character-map-20261016/images/luca-portrait.png', 'Harland': R / 'outputs/magnus-character-map-20261016/images/harland-portrait.png',
               'Selene': R / 'output/magnus-third-live-v1/masters/selene.png'},
    'rafael': {n: R / f'external/nlh-worlds/rafael/ref/{n.lower()}_face.png' for n in ('Maya', 'Cole', 'Ryan', 'Evan')},
    'rowan': {'Nora': R / 'external/nlh-worlds/rowan/ref/nora_face.jpg'},
    'rian': {'Vessa': R / 'output/rian-third-live-v1/docs/media/cast/vessa.jpg', 'Mila': R / 'output/rian-third-live-v1/docs/media/cast/mila.jpg'},
    'island': {n: R / f'external/nlh-worlds/liars/ref/{n.lower()}_face.jpg' for n in ('Mei', 'Sloane', 'Kian')},
    'mii': {'Store Clerk': R / 'projects/realtime-drama-test-log/v/mii-pack/clerk.jpg'},
    'kael': {'Selene': PW / 'worlds/kael/ref/selene_face.jpg', 'Elder': PW / 'worlds/kael/ref/elder_face.jpg'},
    'villa': {'Sloane': PW / 'worlds/villa/ref/head_sloane_gpt.jpg'},
    'mask': {'Victor': PW / 'assets/mask/cast/victor.jpg'},
}
# 没有形象的：画风参考图 + 人物描述（按世界卡的身份、年龄、性格写；和主角长相明显不同）
STYLE = {'dorian': PW / 'worlds/dorian/ref/dorian_face.jpg', 'hear': PW / 'worlds/hear/ref/head_ray.jpg', 'milo': PW / 'worlds/milo/ref/head_milo.png',
         'rian': R / 'output/rian-third-live-v1/docs/media/cast/rian.jpg'}
REAL = 'photorealistic cinematic film still, the same camera look, color grade, lighting quality and realism as the reference photo'
NEW = {
    ('dorian', 'Sebastian'): (REAL, 'a handsome man in his mid twenties, son of a rival crime family at a wedding: dark brown hair slicked back with one loose strand, brown eyes, sharp jaw, a charcoal three-piece suit with the tie loosened, an insolent half-smile, staring straight at the camera; candle-lit dining hall behind him'),
    ('dorian', 'Guard'): (REAL, "a man in his mid thirties, one of a crime family's guards: close-cropped black hair, clean-shaven, broad shoulders, plain black suit and black tie, a discreet earpiece, tense and respectful expression, eyes on the camera; dim corridor of a mansion behind him"),
    ('hear', 'His Assistant'): (REAL, "a man in his early thirties, an executive assistant: neat short dark-blond hair, thin wire glasses, composed and discreet expression, fitted navy suit with a white shirt, a phone in his hand at chest height; bright glass-walled office with a city skyline behind him"),
    ('milo', 'Sacha'): (REAL, 'a 22-year-old man riding shotgun in a car at night: styled wavy dark hair, a cocky teasing grin, an expensive varsity-style jacket over a white tee, a thin gold chain, turned around in the front seat looking at the camera; pink and amber neon light through the car windows'),
    ('milo', 'Evren'): (REAL, 'a 22-year-old man driving a car at night: short black curly hair, olive skin, calm unsmiling face, sharp observant dark eyes looking at the camera, a plain dark green overshirt over a black tee; one hand on the steering wheel, pink and amber neon light through the car windows'),
    ('milo', 'Sienna'): (REAL, 'a 22-year-old woman in the back seat of a car at night: long straight black hair, dry knowing half-smile, one eyebrow slightly raised, a grey hoodie under a denim jacket, her face lit by the phone in her hand, looking up at the camera; pink and amber neon light through the car windows'),
    ('rian', 'Sera'): ('the same semi-realistic fantasy illustration style, rendering, color palette and lighting as the reference image', "a merfolk noblewoman, heir to the Tidal City's fleet: sharp bright teal eyes, long dark teal hair in a high braid with small shell clasps, a fitted pearl-white naval-style coat with mother-of-pearl shoulder plates and a coral-red sash, confident and businesslike expression, looking at the camera; an undersea palace hall with blue light behind her"),
}
ANIME = 'exactly the same anime-style digital illustration as the reference image: the same line quality, shading, color palette and lighting'
NEW.update({
    ('reborn', 'Thalrex'): (ANIME, 'the head and neck of a colossal ancient serpentine dragon emperor: deep indigo scales, a pale silver underbelly, four curved ivory horns sweeping back, glowing amber eyes looking at the viewer, storm clouds and lightning behind; no people'),
    ('hellqueen', 'Malachar'): (ANIME, "a tall high-ranking demon, Hell's chancellor: slicked-back black hair, two small curved dark horns, pale skin, narrow crimson eyes behind a monocle, a severe expression, an immaculate black and crimson formal coat with a high collar; a dark gothic office with red candlelight behind him"),
    ('hellqueen', 'Seraphiel'): (ANIME, "a female angel, Heaven's liaison: long pale-gold hair, soft sky-blue eyes, a calm polite smile, a thin golden halo, white feathered wings partly visible, a white and gold office-style uniform, holding a slim clipboard; soft morning light behind her"),
    ('hellqueen', 'Holloway'): (ANIME, 'a woman of about fifty, a government caseworker: grey-streaked brown hair in a tidy bun, rectangular glasses, a stern but fair expression, a beige blazer over a blouse, a lanyard badge and a folder under her arm; a suburban front porch behind her'),
    ('heroacad', 'Liora'): (ANIME, 'a 17-year-old hero-academy student: warm chestnut hair in a low ponytail with bangs, soft violet eyes, dimples, a gentle smile, a navy and white academy uniform; faint prismatic light refracting around her hands, a bright training hall behind her'),
    ('starmate', 'Marisol'): (ANIME, "a 38-year-old woman, a celebrity's manager: sleek shoulder-length black bob, sharp dark eyes, a composed knowing expression, a tailored cream blazer over a black top, a phone in her hand; a modern apartment hallway behind her"),
    ('starmate', 'Theo'): (ANIME, 'a 25-year-old man, a friendly coworker and big fan: messy light-brown hair, round glasses, a wide excited grin, a casual hoodie with an office lanyard; a cozy office break room behind him'),
    ('starmate', 'Rex'): (ANIME, 'a 44-year-old man, a veteran paparazzo: stubble, tired sharp eyes, a baseball cap, a worn olive field jacket, a camera with a long lens hanging from his neck, a sly look; a city street at dusk behind him'),
    ('starmate', 'Julian'): (ANIME, 'a 27-year-old male film star: swept-back dark blond hair, a charming practiced smile, green eyes, an open-collar white shirt under a dark blazer; a film-premiere backdrop with soft lights behind him'),
    ('onestat', 'System'): (ANIME, 'no people: a floating translucent blue holographic panel with a glowing crystal core at its center, thin light rings orbiting it, tiny sparkles, pale pillars and blue light of an otherworldly rebirth space behind; absolutely no letters or numbers on the panel, only abstract glowing shapes'),
})


# dorian 的 Father / Mom：现成参考图是侧脸、背光，当头像看不清脸；让模型“照同一个人转正脸”出来的脸又太像现实里的演员，
# 所以不用参考图认人，按世界卡的身份重新设计一张原创的脸（写明不像任何真人）
ORIG = 'an original fictional face that does not resemble any real actor, celebrity or public figure'
NEW[('dorian', 'Father')] = (REAL, f"a man in his late sixties, an old mafia don at his own wedding: thick silver-white hair combed back, a broad lined face with heavy eyebrows and a short grey moustache, kind tired dark eyes, a black tuxedo with a bow tie and a white boutonniere; {ORIG}; candle-lit dining hall behind him")
NEW[('dorian', 'Mom')] = (REAL, f"a woman in her early fifties, the bride tonight: dark blonde hair in a low chignon, a narrow face with high cheekbones, grey-green eyes, a composed warm smile, a champagne satin gown with thin straps and small pearl earrings; {ORIG}; candle-lit dining hall behind her")


def keyfile(sid, key): return OUT / f'{sid}.{key.replace(" ", "")}.jpg'


def face_square(path, out, size=320):
    """按脸裁成方形头像：最大的那张脸放中间略偏上，四周留出头发和肩；没找到脸就取上半部居中"""
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB'); W, H = im.size
    fs = FR.faces(im, 'av:' + FR.img_key(str(path)))
    if fs:
        x0, y0, x1, y1 = max(fs, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
        x0, x1, y0, y1 = x0 * W, x1 * W, y0 * H, y1 * H
        side = min(max(x1 - x0, y1 - y0) * 1.7, W, H); cx = (x0 + x1) / 2; cy = (y0 + y1) / 2 + (y1 - y0) * 0.08
    else:
        side = min(W, H); cx = W / 2; cy = side / 2 if H > W else H / 2
    left = min(max(0, cx - side / 2), W - side); top = min(max(0, cy - side / 2), H - side)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.crop((round(left), round(top), round(left + side), round(top + side))).resize((size, size), Image.LANCZOS).save(out, quality=88)
    return bool(fs)


def copy():
    import build_prota_app as PA
    jobs = [(sid, k, p) for sid, m in SRC.items() for k, p in m.items()]
    for sid in PROTA:
        for k in V[sid]:
            if k.startswith('_') or (sid, k) in NEW: continue
            p = PA.portrait(sid, k)
            if p and os.path.exists(p): jobs.append((sid, k, Path(p)))

    def one(j):
        sid, k, p = j; out = keyfile(sid, k)
        if out.exists() and not FORCE: return sid, k, 'exists'
        if not Path(p).exists(): return sid, k, 'MISSING ' + str(p)[-60:]
        try: return sid, k, 'ok' if face_square(p, out) else 'ok (no face found: centered)'
        except Exception as e: return sid, k, 'FAIL ' + repr(e)[:100]
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(one, jobs):
            if r[2] != 'exists': print(r, flush=True)
    print('copy done', len(jobs))


def _json(s):
    m = re.search(r'\{.*\}', s or '', re.S)
    return json.loads(m.group(0)) if m else {}


def gen_one(item):
    (sid, k), (style, desc) = item
    raw = GEN / f'{sid}.{k.replace(" ", "")}.jpg'; out = keyfile(sid, k)
    if out.exists() and raw.exists() and not FORCE: return sid, k, 'exists'
    if not raw.exists() or FORCE:
        if sid in PROTA:
            import build_prota_app as PA
            lead = next(n for n in V[sid] if not n.startswith('_')); ref = PA.portrait(sid, lead)
        else: ref = STYLE[sid]
        up = subprocess.run(['waku', 'persist', str(ref)], capture_output=True, text=True, timeout=180)
        m = re.search(r'"url":\s*"([^"]+)"', up.stdout)
        if not m: return sid, k, 'upload failed'
        prompt = (f'Use the reference image ONLY as a style guide: {style}. Do NOT copy the person in the reference — create a completely different character. '
                  f'Subject: a head-and-shoulders portrait of {desc}. Centered, face clearly visible and well lit, eyes open. '
                  'No text, letters, numbers, logos, captions or watermarks anywhere; no border or frame. Correct anatomy. Tasteful.')
        params = {'prompt': prompt, 'images': [m.group(1)], 'aspect_ratio': '1:1', 'resolution': '1k', 'output_format': 'jpeg'}
        for attempt in range(3):
            r = subprocess.run(['waku', 'gen', 'run', 'google/nano-banana-2.1/edit', '--capability', 'multimodal.generate.image', '--params', json.dumps(params), '--wait', '--timeout', '300', '--out', str(raw)],
                               capture_output=True, text=True, timeout=360)
            if raw.exists() and raw.stat().st_size > 20000: break
            j = _json(r.stdout + r.stderr)
            if j.get('job_id'): subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '240', '--out', str(raw)], capture_output=True, text=True, timeout=300)
            if raw.exists() and raw.stat().st_size > 20000: break
        else:
            return sid, k, 'gen failed ' + (r.stdout + r.stderr)[-160:].replace('\n', ' ')
    try: face_square(raw, out)
    except Exception as e: return sid, k, 'crop FAIL ' + repr(e)[:80]
    return sid, k, 'ok'


def gen():
    only = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--only=')), None)
    items = [(key, v) for key, v in NEW.items() if not only or f'{key[0]}.{key[1]}' in only]
    with cf.ThreadPoolExecutor(3) as ex:
        for r in ex.map(gen_one, items): print(r, flush=True)


if __name__ == '__main__':
    {'copy': copy, 'gen': gen}[sys.argv[1]]()
    have = {f.stem for f in OUT.glob('*.jpg')}
    miss = [f'{sid}.{k}' for sid in V if isinstance(V[sid], dict) for k in V[sid] if not k.startswith('_') and isinstance(V[sid][k], dict) and not V[sid][k].get('lead') and f'{sid}.{k.replace(" ", "")}' not in have]
    print('still without an avatar:', miss)
