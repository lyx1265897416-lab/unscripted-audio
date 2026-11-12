"""narra 静态背景高清重绘（11-11 她看了 v62 的反馈：视频截帧放大后还是不清晰——“诸如此类的图片重新生成高清图替换，不要直接截屏 / 截帧，
确保每一部剧画质画风风格统一”）。

realtime 13 部里从视频截出来的背景（片段编号 o / c / p / i 开头；s 开头的是原始剧照，本来就是高清图，不动）：
  选好的那一帧（build_stills_v2 选帧 + 取景的结果）只当“构图稿”，连同这部剧的角色定装图一起交给图像模型重画一张 2k 的高清图——
  同一个镜头、同样的人、姿势、服装、道具、场景和光线，人物的脸和画风照定装图；每部剧用同一段画风描述、同一批定装图，所以整部剧画质和画风是一套。
  大特写（额头 / 下巴被裁掉的）顺便把镜头拉开一点，整个头和肩都在画面里。
原来的截帧图备份在 cache/still_frames/<剧>/；重绘的 2k 原图在 data/stills_hd/<剧>/（只留本机），缩成 1080×1620 覆盖 app/v/<剧>/still/<片段>.jpg。
Prota 8 部的背景是原卡图 / 专门生成的图，不是截帧，不处理。

用法：python3 build_stills_hd.py [剧 id…] [--only=剧.片段,…] [--force] [--dry]     重绘
     python3 build_stills_hd.py pack [剧 id…]     出慢网用的小图、更新 index.json（w / lo / v）
模型：Waku google/nano-banana-2.1/edit，2k，2:3。"""
import json, re, shutil, subprocess, sys, time, concurrent.futures as cf
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
R = ROOT.parents[1]
PW = R / 'external' / 'perhaps-worlds'
PACK = ROOT / 'data' / 'cast_pack'
RAW = ROOT / 'data' / 'stills_hd'; RAW.mkdir(parents=True, exist_ok=True)
BAK = ROOT / 'cache' / 'still_frames'
URLS = RAW / 'urls.json'
FORCE, DRY = '--force' in sys.argv, '--dry' in sys.argv
REDO = next((set(a.split('=', 1)[1].split(',')) for a in sys.argv if a.startswith('--redo=')), set())   # 指定重做的 剧.片段
W, H = 1080, 1620

# 画风不另起一套：照构图稿和定装图本身的画风，只是更干净更清楚——每部剧用同一句话、同一批定装图，整部剧是一套
STYLE = ('exactly the art style, rendering and color grading of image 1 and of the character reference sheets — do not change the art style, do not make it more or less realistic; '
         'only cleaner and far sharper: clean detailed skin, finely resolved individual hair strands, crisp fabric texture, clear eyes with catchlights')
PWR = PW / 'worlds'
# 每部剧的定装图（文件, 这个人是谁——写清楚性别 / 发色 / 身份，模型靠这句话把构图稿里的人对上定装图）
CFG = {
    'magnus': [(PACK / 'magnus.Magnus', 'Magnus, the man with black hair, light stubble and amber eyes, usually in a black suit'),
               (PACK / 'magnus._wolf', 'Magnus in his werewolf form (the same man with black wolf ears) — only if he has wolf ears in image 1'),
               (PACK / 'magnus._her', 'the heroine, the young woman with long hair'),
               (PACK / 'magnus.Luca', 'Luca, the man with brown hair and glasses'), (PACK / 'magnus.Selene', 'Selene, the woman with dark brown pinned-up hair and emerald earrings'),
               (PACK / 'magnus.Harland', 'Harland, the older man with grey hair and a grey beard')],
    'rafael': [(PACK / 'rafael.Rafael', 'Rafael, the man with messy black hair and a tattoo on his neck'), (PACK / 'rafael._her', 'the heroine, the young woman with long light-flaxen wavy hair'),
               (PACK / 'rafael.Maya', 'Maya, the woman with a wavy red-auburn bob and freckles'), (PACK / 'rafael.Cole', 'Cole, the man with light-brown hair and a short beard'),
               (PACK / 'rafael.Ryan', 'Ryan, the young man with reddish-brown hair'), (PACK / 'rafael.Evan', 'Evan, the man with ash-blond hair')],
    'rowan': [(PACK / 'rowan.Rowan', 'Rowan, the young man with fluffy brown hair, cream knit sweater and brown suede jacket'),
              (PACK / 'rowan._her', 'the heroine, the young woman with long wavy auburn hair, a small gold leaf hair clip, cream blouse and olive-green laced bodice'),
              (PACK / 'rowan.Nora', 'Nora, the woman with short brown hair and a green apron')],
    'rian': [(PACK / 'rian.Rian', 'Rian in court attire: the man with long silver-lavender hair, blue fin-shaped ears and a pearl-draped white robe'),
             (PACK / 'rian._shore', 'Rian in shore clothes (the same man in a plain white high-collar top) — use the outfit he wears in image 1'),
             (PACK / 'rian._mer', 'Rian in merman form — only if he is in the water with a tail in image 1'),
             (PACK / 'rian._her', 'the heroine Skye, the young woman with curly red hair and a silver moon hair clip'),
             (PACK / 'rian.Vessa', 'Vessa, the woman with a braided purple updo with pearls and an ornate purple gown'),
             (PACK / 'rian.Mila', 'Mila, the young woman with curly blonde hair and freckles'), (PACK / 'rian.Sera', 'Sera, the woman with dark braids, a silver circlet and blue fin-shaped ears')],
    'lena': [(PACK / 'lena.Lena', 'Lena, the young woman with long dark-brown wavy hair'), (PACK / 'lena.Voss', 'Voss, the man with short dark-brown curly hair and a black turtleneck'),
             (PACK / 'lena.Hollis', 'Hollis, the bearded man in a dark work uniform')],
    'mii': [(PACK / 'mii.Mii', 'Mii, the small orange-and-white kitten: the same face, markings, body proportions and exactly the same bib / apron as on this sheet'),
            (PACK / 'mii.StoreClerk', 'the store clerk, a woman in a cream shirt and a sage-green apron')],
    'island': [(PACK / 'island.Wes', 'Wes, the man with tousled light-brown hair'), (PACK / 'island.Jasper', 'Jasper, the man with dark curly hair and green eyes'),
               (PACK / 'island._her', 'the heroine Sofia, the young woman with long brown hair'), (PACK / 'island.Mei', 'Mei, the host, a woman in her forties with a black bob'),
               (PACK / 'island.Sloane', 'Sloane, the woman with wavy blonde hair and bangs'), (PACK / 'island.Kian', 'Kian, the man with wavy black hair'),
               (PACK / 'island.Ethan', 'Ethan, the man with curly brown hair and blue eyes'), (PACK / 'island.Brody', 'Brody, the man with light-brown curly hair'),
               (PACK / 'island.Jude', 'Jude, the man with short light-brown hair'), (PACK / 'island.Ravi', 'Ravi, the man in a navy blazer')],
    'kael': [(PWR / 'kael/ref/kael_head.jpg', 'Kael, the man with black hair and pale grey eyes'), (PWR / 'kael/ref/selene_face.jpg', 'Selene, the woman with long silver-blonde hair'),
             (PWR / 'kael/ref/elder_face.jpg', 'the Elder, the older man with silver hair and beard')],
    'dorian': [(PWR / 'dorian/ref/dorian_face.jpg', 'Dorian, the young man with ash-blond hair'), (PWR / 'dorian/ref/father_head.jpg', 'the father, the old man with silver hair in a tuxedo'),
               (PWR / 'dorian/ref/mother_head.jpg', 'the mother, the woman with auburn pinned-up hair')],
    'hear': [(PWR / 'hear/ref/head_ray.jpg', 'Ray, the young man with brown hair in a black suit'), (PWR / 'hear/ref/dana.jpg', 'Dana, the young woman with long auburn hair')],
    'milo': [(PWR / 'milo/ref/head_milo.png', 'Milo, the young man with messy brown hair')],
    'villa': [(PW / 'assets/villa/cast/jace.jpg', 'Jace, the man with curly blond hair'), (PW / 'assets/villa/cast/theo.jpg', 'Theo, the man with black hair and glasses'),
              (PW / 'assets/villa/cast/kai.jpg', 'Kai, the man with short black hair'), (PW / 'assets/villa/cast/sloane.jpg', 'Sloane, the woman with a long blonde braid')],
    'mask': [(PW / 'assets/mask/cast/adrian.jpg', 'Adrian, the man with wavy brown hair in a cream suit'), (PW / 'assets/mask/cast/nightraven.jpg', 'Night Raven, the man in a black feathered mask and feathered collar'),
             (PW / 'assets/mask/cast/eve.jpg', 'the heroine Eve, the woman with dark pinned-up hair in a beaded strapless gown'), (PW / 'assets/mask/cast/victor.jpg', 'Victor, the older man with grey hair in a navy tuxedo')],
}


def urls():
    return json.load(open(URLS)) if URLS.exists() else {}


def upload(path):
    u = urls(); k = str(path)
    if k in u: return u[k]
    src = Path(path)
    if src.suffix.lower() not in ('.jpg', '.jpeg', '.png') or src.stat().st_size > 1_500_000:   # 飞书下载的主图没有扩展名（上传会被拒），大 PNG 也先缩成 JPEG
        t = RAW / '_ref' / (re.sub(r'[^A-Za-z0-9._-]', '_', src.name) + '.jpg'); t.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(src).convert('RGB'); im.thumbnail((1600, 1600)); im.save(t, quality=92); src = t
    r = subprocess.run(['waku', 'persist', str(src)], capture_output=True, text=True, timeout=240)
    m = re.search(r'"url":\s*"([^"]+)"', r.stdout)
    if not m: raise RuntimeError('upload failed ' + (r.stdout + r.stderr)[-200:])
    u = urls(); u[k] = m.group(1); json.dump(u, open(URLS, 'w'), indent=1)
    return m.group(1)


# 全身定装图（主角 / 女主）：特写改成中景时，画面里多出来的身体和衣服照这些画
FULL = {
    'magnus': [(PACK / 'magnus.Magnus.full', 'Magnus'), (PACK / 'magnus._her.full', 'the heroine')],
    'rafael': [(PACK / 'rafael.Rafael.full', 'Rafael'), (PACK / 'rafael._her.full', 'the heroine')],
    'rowan': [(PACK / 'rowan.Rowan.full', 'Rowan'), (PACK / 'rowan._her.full', 'the heroine')],
    'rian': [(PACK / 'rian.Rian.full', 'Rian in court attire'), (PACK / 'rian._shore.full', 'Rian in shore clothes'), (PACK / 'rian._her.full', 'the heroine Skye')],
    'lena': [(PACK / 'lena.Lena.full', 'Lena')],
    'island': [(PACK / 'island.Wes.full', 'Wes'), (PACK / 'island.Jasper.full', 'Jasper'), (PACK / 'island._her.full', 'the heroine Sofia')],
    'kael': [(PWR / 'kael/ref/kael_full.jpg', 'Kael'), (PWR / 'kael/ref/you_costume.jpg', "the heroine's outfit")],
    'dorian': [(PWR / 'dorian/ref/dorian_body.jpg', 'Dorian'), (PWR / 'dorian/ref/you_costume.jpg', "the heroine's outfit")],
    'hear': [(PWR / 'hear/ref/ray_body.jpg', 'Ray'), (PWR / 'hear/ref/you_costume.jpg', "the heroine's outfit")],
    'milo': [(PWR / 'milo/ref/milo_body.png', 'Milo'), (PWR / 'milo/ref/you_costume.jpg', "the heroine's outfit")],
    'villa': [(PWR / 'villa/ref/jace_body.png', 'Jace'), (PWR / 'villa/ref/theo_body.png', 'Theo'), (PWR / 'villa/ref/kai_body.png', 'Kai'), (PWR / 'villa/ref/you_costume.jpg', "the heroine's outfit")],
    'mask': [(PWR / 'mask/ref/adrian-linen-front-4k.png', 'Adrian'), (PWR / 'mask/ref/night-raven-fullbody-front-v3.png', 'Night Raven'), (PWR / 'mask/ref/eve-fullbody.png', 'the heroine Eve')],
}
PROTA = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']
CLOSE = 0.30   # 最大的头占画面高 ≥ 这个比例算大脸特写（11-11 她要求：背景尽量不要大人脸特写，多用中景、全景、远景、场景）


def refs_of(sid):
    """这部剧的定装图。Prota 的剧没有单独配置：用原卡里每个有声音角色的立绘"""
    if sid in CFG: return CFG[sid]
    import build_prota_app as PA
    V = json.load(open(ROOT / 'data' / 'voices.json'))[sid]; out = []
    for k in V:
        if k.startswith('_') or not isinstance(V[k], dict): continue
        pth = PA.portrait(sid, k)
        if pth and Path(pth).exists(): out.append((Path(pth), f'{k} (a character of this story)'))
    return out[:8]


def prompt(sid, kind, mode, n=0, refs=None, full=None, scene=False, facts=''):
    """refs / full：这张图实际用到的定装图（只给原图里出现的角色，没出现的不给——给多了模型会照搬定装图）；scene：最后一张是不是同场景参考"""
    refs = refs_of(sid) if refs is None else refs; full = (FULL.get(sid, []) if mode == 'wide' else []) if full is None else full
    who = '; '.join(f'image {i + 2} = {d}' for i, (_, d) in enumerate(refs))
    if sid == 'mii' and kind == 'scene': kind = 'face'   # 咪的图没有人脸，选帧时标成了空镜；主角是猫，一样要照定装
    if mode == 'wide':
        # 大脸特写 → 同一时刻的中景：镜头拉远，人只占画面一部分，场景露出来
        p = ('Image 1 is a tight face close-up taken from a scene. Re-stage the very same moment as a MEDIUM-WIDE SHOT of that scene: move the camera well back, so that each person in image 1 is seen from about the knees up, '
             'their head no taller than one sixth of the picture height and placed in the upper third of the frame, and the location fills the rest of the picture. '
             'Keep exactly the same individuals as image 1 (same gender, age, hair color and hairstyle, glasses, mask) and no one else, with the same expression, head angle, gaze direction, gesture and action, the same props, time of day, lighting direction and color palette. '
             'Never replace a person in image 1 with a different character. '
             'Stay in the same place: build the wider surroundings by continuing the location that is visible behind them in image 1 (same kind of place, materials and light). If they are inside a car or a room in image 1, the new shot is still inside that same car or room, seen from farther back — do not move them outdoors or anywhere else. '
             'Clothing: every person wears exactly the garments visible on them in image 1 (same shirt, collar, tie, necklace; a jacket only if they wear one in image 1), continued naturally down the body. ')
        if full:
            p += ('Full-body sheets: ' + '; '.join(f'image {len(refs) + 2 + i} = {d}' for i, (_, d) in enumerate(full)) +
                  '. Use them only for body proportions and for the lower-body clothing that image 1 does not show; where a sheet shows a different outfit from image 1, image 1 wins. ')
        if scene:
            p += (f'Image {len(refs) + len(full) + 2} is another shot from the same sequence of the story. If it shows the same place as image 1, take the layout and set dressing of the location and each person\'s complete outfit from it; '
                  'if it clearly shows a different place, ignore it. Do not copy its composition or add people from it. ')
        if n: p += (f'Image 1 shows exactly {n} {"person" if n == 1 else "people"} with a visible face: the new picture must show exactly {"that one person" if n == 1 else f"those {n} people"} '
                    '(plus, at most, the edge of someone who is already partly in image 1). Never add a second or third character just because a reference sheet for them was provided. ')
        if facts: p += ('Facts read from image 1 that the new picture must match exactly, whatever the sheets show — ' + facts + ' ')
        p += ('The reference sheets have plain studio backgrounds and neutral standing poses: the new picture must never have a plain white or grey studio background and must never look like a character sheet or fashion catalogue pose. '
              'This must not be a close-up: no face may fill the frame. ')
    else:
        p = ('Image 1 is the picture to redraw: a soft, low-resolution frame from a video. Redraw exactly this shot as a pristine, tack-sharp, high-resolution still image. '
             'Keep everything that is in image 1: the same people, animals, pose, expression, gaze direction, clothing, props, setting, time of day, lighting direction, color palette, camera angle and framing. '
             'Do not add or remove any person, animal or object, and do not change who is in the shot. '
             'The result must have the same composition as image 1 — it is never a copy or a variation of any other image supplied here. ')
    if kind != 'scene' and refs:
        p += (f'Character reference sheets: {who}. Each character who appears in image 1 and has a reference sheet must look exactly like that sheet (face, hairstyle, hair color, markings; and the outfit when it is the same outfit as in image 1). '
              'Anyone in image 1 without a reference sheet stays exactly as in image 1. '
              'Use the reference sheets only for identity: the pose, action, place and framing always come from image 1, a character who is not in image 1 must not appear, and the backgrounds of the reference sheets must not be used. Eyes open and in focus unless they are clearly closed in image 1. ')
    elif refs:
        p += 'If there are no people in image 1, keep the shot empty of people. The remaining images are only a guide to the look of this series; nobody from them may appear. '
    else:
        p += 'Everyone and everything in image 1 stays exactly as in image 1. '
    p += (f'Rendering: {STYLE if refs else STYLE.replace(" and of the character reference sheets", "")}. The whole series must look like one consistent set of images. '
          'Absolutely no blur, motion smear, double image, compression artifacts or heavy film grain; correct anatomy and hands. No text, letters, logos, captions, watermark, border or frame.')
    return p


# ---- 自动校验（11-11 首轮质检：约四分之一的图模型没照原图画，直接照搬了定装图 / 换了人 / 换了地方）----
PRESENT = RAW / 'present.json'; QC = RAW / 'qc.json'
_jlock = __import__('threading').Lock()


def _jget(path): return json.load(open(path)) if path.exists() else {}


def _jput(path, k, v):
    with _jlock:
        d = _jget(path); d[k] = v; json.dump(d, open(path, 'w'), indent=0)


def vlm(paths, txt, max_tokens=300):
    """几张图 + 一个问题 → 视觉模型回的 JSON（和量景别同一个模型，走 OpenRouter）"""
    import framing as FR, base64, io, os, urllib.request as U
    content = []
    for q in paths:
        im = Image.open(q).convert('RGB'); im.thumbnail((768, 768)); b = io.BytesIO(); im.save(b, 'JPEG', quality=82)
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()}})
    content.append({'type': 'text', 'text': txt})
    body = {'model': FR.MODEL, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': max_tokens, 'temperature': 0}
    err = None
    for _ in range(3):
        try:
            req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                            headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
            c = json.loads(FR._op.open(req, timeout=120).read())['choices'][0]['message']['content']
            return json.loads(re.search(r'\{.*\}', c, re.S).group(0))
        except Exception as e: err = e; time.sleep(2)
    raise RuntimeError('vlm ' + repr(err)[:120])


def present(sid, cid, bak):
    """原图里出现了哪几张定装图上的角色（下标列表）。只把这些人的定装图交给图像模型"""
    k = f'{sid}.{cid}'; d = _jget(PRESENT)
    if k in d: return d[k]
    refs = refs_of(sid)
    if not refs: return []
    txt = ('Image 1 is a frame from a story. The other images are character reference sheets: ' + '; '.join(f'image {i + 2} = {dsc}' for i, (_, dsc) in enumerate(refs)) +
           '. Which of these characters are actually visible in image 1 (even partly or from behind)? Decide by hair color and hairstyle, face, age, gender, species and clothing. '
           'A person in image 1 who does not match any sheet is not in the list. Return JSON only: {"present":[image numbers]} — an empty list if none of them is in image 1.')
    try: r = vlm([bak] + [p for p, _ in refs], txt)
    except Exception as e:
        print('present fail', k, repr(e)[:80], flush=True); return list(range(len(refs)))
    out = sorted({int(x) - 2 for x in r.get('present', []) if str(x).isdigit() and 2 <= int(x) < len(refs) + 2})
    _jput(PRESENT, k, out); return out


FACTS = RAW / 'facts.json'


def describe(sid, cid, bak, sc=None):
    """视觉模型从原图读出地点、每个人穿什么、在做什么 → 一段文字写进提示词（光靠图，模型会照定装图换衣服、换地方）"""
    k = f'{sid}.{cid}'; d = _jget(FACTS)
    if k in d: return d[k]
    txt = ('Image 1 is a close-up from a film scene.' + (' Image 2 is another shot from the same sequence; use it only if it clearly shows the same place, to see more of the location.' if sc else '') +
           ' Describe for a storyboard artist, in English, only what is visible. Return JSON only: {"place": "the location of image 1 in at most 25 words: indoors or outdoors, kind of place, key set pieces, time of day, light and color mood", '
           '"people": [{"who": "gender, age, hair color and style, glasses / mask / animal ears if any", "wearing": "upper-body clothing exactly as visible in image 1: each garment and its color, whether a jacket is worn or not, tie, jewelry", '
           '"doing": "expression, gaze, gesture, what they hold or touch"}]}')
    try: r = vlm([bak] + ([sc] if sc else []), txt, 500)
    except Exception as e:
        print('describe fail', k, repr(e)[:80], flush=True); return ''
    out = 'Location: ' + str(r.get('place', '')).strip().rstrip('.') + '. ' + ' '.join(
        f"Person {i + 1}: {str(x.get('who', '')).strip().rstrip('.')}; wearing {str(x.get('wearing', '')).strip().rstrip('.')}; {str(x.get('doing', '')).strip().rstrip('.')}." for i, x in enumerate(r.get('people') or []) if isinstance(x, dict))
    _jput(FACTS, k, out); return out


def _hist(path):
    import numpy as np
    a = np.asarray(Image.open(path).convert('RGB').resize((48, 72))) // 64
    h = np.bincount((a[..., 0].astype(int) * 16 + a[..., 1] * 4 + a[..., 2]).ravel(), minlength=64).astype(float); return h / h.sum()


def scene_ref(sid, cid):
    """特写改中景时的同场景参考：前后 5 张里不是特写、色调最接近的一张原图（看得到环境和整身衣服）"""
    import numpy as np
    d = ROOT / 'app' / 'v' / sid / 'still'; ix = json.load(open(d / 'index.json')); ids = ix['still']; q = ix.get('q') or {}
    shot = (_jget(SHOT).get('orig') or {}).get(sid, {})
    if cid not in ids: return None
    i = ids.index(cid); me = BAK / sid / f'{cid}.jpg'; h0 = _hist(me); best = (0.8, None)
    for j in range(max(0, i - 5), min(len(ids), i + 6)):
        c = ids[j]
        if c == cid or q.get(c) in ('bad', 'part') or shot.get(c, 0) >= CLOSE: continue
        src = BAK / sid / f'{c}.jpg'
        if not src.exists(): src = d / f'{c}.jpg'
        if not src.exists(): continue
        s = float(np.minimum(h0, _hist(src)).sum()) - abs(i - j) * 0.005
        if s > best[0]: best = (s, src)
    return best[1]


def corr(a, b):
    import numpy as np
    def th(pth):
        x = np.asarray(Image.open(pth).convert('L').resize((24, 36))).astype(float).ravel(); return (x - x.mean()) / (x.std() + 1e-6)
    return float((th(a) * th(b)).mean())


def qc(sid, cid, mode, bak, raw):
    """这张重画合不合格 → (分数 0–1, 说明)。same：缩略图和原图的相关度（构图没变）；wide：视觉模型比对是不是同一批人、同一个地方、同一身衣服、不是白底定装照"""
    if mode != 'wide':
        c = corr(bak, raw); return (1.0 if c >= 0.45 else max(0.0, c), f'corr {c:.2f}')
    txt = ('Image 1 is a close-up from a film scene. Image 2 is meant to be a wider shot of the very same moment. Compare them and return JSON only: '
           '{"same_people": true/false (every main person in image 2 is the same individual as in image 1: same gender, age, hair color and hairstyle, glasses or mask — and nobody from image 1 was swapped for someone else), '
           '"same_place": true/false (image 2 is plausibly the same location as the background of image 1: same kind of place, indoors/outdoors, day/night, same light and color mood), '
           '"same_outfit": true/false (the upper-body clothing of each person matches image 1: jacket or no jacket, shirt color, tie, necklace), '
           '"studio": true/false (image 2 has a plain blank studio backdrop, like a character sheet), '
           '"extra_people": number of clearly visible foreground people in image 2 who are not in image 1}')
    try: r = vlm([bak, raw], txt)
    except Exception as e: return 1.0, 'judge fail ' + repr(e)[:60]
    bad = [k for k in ('same_people', 'same_place', 'same_outfit') if r.get(k) is False] + (['studio'] if r.get('studio') is True else []) + (['extra'] if (r.get('extra_people') or 0) >= 2 else [])
    return 1.0 - len(bad) / 5, ('ok' if not bad else 'bad: ' + ','.join(bad))


MODES = RAW / 'modes.json'


def jobs(sid):
    """[(剧, 片段, 标签, 做法)]：wide = 大脸特写改中景重画（所有来源的图）；same = 截帧照原构图重画成高清；其余（本来就是高清的中景 / 空镜剧照）不动"""
    d = ROOT / 'app' / 'v' / sid / 'still'
    q = (json.load(open(d / 'index.json')).get('q') or {})
    shot = (json.load(open(SHOT)).get('orig') or {}).get(sid, {}) if SHOT.exists() else {}
    modes = json.load(open(MODES)) if MODES.exists() else {}
    out = []
    for f in sorted(d.glob('*.jpg')):
        c = f.stem
        if q.get(c) == 'bad': continue
        if (shot.get(c, 0) >= CLOSE and q.get(c, 'face') in ('face', 'close')) or modes.get(f'{sid}.{c}') == 'wide': out.append((sid, c, 'face', 'wide'))   # 改过中景的保持中景
        elif c[0] in 'ocpi' and sid not in PROTA: out.append((sid, c, q.get(c, 'face'), 'same'))
    return out


_mlock = __import__('threading').Lock()


def one(job):
    sid, cid, kind, mode = job
    cur = ROOT / 'app' / 'v' / sid / 'still' / f'{cid}.jpg'; bak = BAK / sid / f'{cid}.jpg'; raw = RAW / sid / f'{cid}.jpg'
    bak.parent.mkdir(parents=True, exist_ok=True); raw.parent.mkdir(parents=True, exist_ok=True)
    if not bak.exists(): shutil.copy2(cur, bak)   # 构图稿永远用原来的图，不拿重绘过的再重绘
    modes = json.load(open(MODES)) if MODES.exists() else {}
    key = f'{sid}.{cid}'; done = raw.exists() and raw.stat().st_size > 100000 and modes.get(key, 'same') == mode
    note = ''
    if not done or FORCE or key in REDO:
        allrefs = refs_of(sid); pres = present(sid, cid, bak); refs = [allrefs[i] for i in pres if i < len(allrefs)]
        names = ' '.join(d.lower() for _, d in refs); has_her = any('heroine' in d for _, d in allrefs)
        full = [(p, d) for p, d in (FULL.get(sid, []) if mode == 'wide' else [])
                if re.sub(r"^the |'s.*$| .*$", '', d).lower() in names or ('heroine' in d and (('heroine' in names) if has_her else True))]
        sc = scene_ref(sid, cid) if mode == 'wide' else None
        n = 0
        if mode == 'wide':   # 原图里有几张脸（量景别时找过，读缓存）：中景里只许有这几个人
            import framing as FR
            n = len(FR._cache.get('shot:' + FR.img_key(str(bak)), []))
        facts = describe(sid, cid, bak, sc) if mode == 'wide' else ''
        best = (-1, None, ''); tmp = raw.with_suffix('.tmp.jpg'); msg = ''
        for attempt in range(3):
            r_use = refs if not (mode == 'same' and attempt == 2) else []   # 照原构图重画连错两次：最后一次不给定装图，只照原图画
            try: imgs = [upload(bak)] + [upload(p) for p, _ in r_use] + [upload(p) for p, _ in full] + ([upload(sc)] if sc else [])
            except Exception as e: return sid, cid, 'FAIL ' + repr(e)[:120]
            params = {'prompt': prompt(sid, kind, mode, n, r_use, full, bool(sc), facts), 'images': imgs[:14], 'aspect_ratio': '2:3', 'resolution': '2k', 'output_format': 'jpeg'}
            tmp.unlink(missing_ok=True)
            r = subprocess.run(['waku', 'gen', 'run', 'google/nano-banana-2.1/edit', '--capability', 'multimodal.generate.image', '--params', json.dumps(params), '--wait', '--timeout', '420', '--out', str(tmp)],
                               capture_output=True, text=True, timeout=480)
            msg = (r.stdout + r.stderr)[-200:].replace('\n', ' ')
            if not (tmp.exists() and tmp.stat().st_size > 100000):
                m = re.search(r'"job_id":\s*"([^"]+)"', r.stdout + r.stderr)
                if m: subprocess.run(['waku', 'gen', 'result', m.group(1), '--wait', '--timeout', '300', '--out', str(tmp)], capture_output=True, text=True, timeout=360)
            if not (tmp.exists() and tmp.stat().st_size > 100000): time.sleep(5 + attempt * 10); continue
            sc_, why = qc(sid, cid, mode, bak, tmp)
            if sc_ > best[0]:
                keep = raw.with_suffix('.best.jpg'); shutil.copy2(tmp, keep); best = (sc_, keep, f'{why} (try {attempt + 1})')
            if sc_ >= 1: break
        tmp.unlink(missing_ok=True)
        if best[1] is None: return sid, cid, 'gen failed ' + msg
        best[1].replace(raw); note = ' ' + best[2]
        _jput(QC, key, [best[0], best[2]])
        with _mlock:
            modes = json.load(open(MODES)) if MODES.exists() else {}; modes[key] = mode; json.dump(modes, open(MODES, 'w'), indent=0)
    im = Image.open(raw).convert('RGB'); iw, ih = im.size
    cw = min(iw, ih / 1.5); ch = cw * 1.5; x0 = (iw - cw) / 2; y0 = (ih - ch) * 0.3   # 模型给的基本就是 2:3，差一点时略偏上裁
    im = im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch)))
    im.resize((W, H), Image.LANCZOS).save(cur, quality=84, optimize=True, progressive=True)   # 1080 的 JPEG：还开着旧版页面的手机继续用这个名字
    im.save(cur.with_suffix('.webp'), 'WEBP', quality=80, method=5)   # 2k 原尺寸 WebP（≈240 KB，比 1080 的 JPEG 还小）：新版页面用这张，大屏手机铺满也不用放大
    return sid, cid, f'ok {mode} {iw}x{ih}{note}'


SHOT = ROOT / 'data' / 'stills' / 'shot.json'


def head_ratio(path):
    """这张图里最大的头占画面高的比例（0 = 没有人脸）。视觉模型找头框，结果按图片内容缓存（framing.py 的 data/faces.json）"""
    import framing as FR
    fs = FR.faces(Image.open(path).convert('RGB'), 'shot:' + FR.img_key(str(path)))
    return round(max((f[3] - f[1] for f in fs), default=0), 3)


def measure(ids, final=False):
    """量每张背景的景别：final=False 量原图（截帧备份 / 原始剧照），决定哪些要改成中景重画；final=True 量现在线上用的图，给播放器打 close 标签"""
    out = json.load(open(SHOT)) if SHOT.exists() else {}
    todo = []
    for sid in ids:
        d = ROOT / 'app' / 'v' / sid / 'still'
        for c in json.load(open(d / 'index.json'))['still']:
            src = d / f'{c}.jpg'; bak = BAK / sid / f'{c}.jpg'
            todo.append((sid, c, src if final or not bak.exists() else bak))
    with cf.ThreadPoolExecutor(8) as ex: res = list(ex.map(lambda j: head_ratio(j[2]), todo))
    for (sid, c, _), r in zip(todo, res): out.setdefault('final' if final else 'orig', {}).setdefault(sid, {})[c] = r
    json.dump(out, open(SHOT, 'w'), indent=0)
    return out['final' if final else 'orig']


def pack(ids):
    """每部剧：所有背景出一张 360×540 的小图 still/lo/<片段>.jpg（慢网先垫的就是同一张图，不再是另一帧）；
    index.json 记下哪些片段有 2k WebP（w）、有小图（lo）和版本号（v，换了图手机不拿旧缓存）"""
    for sid in ids:
        d = ROOT / 'app' / 'v' / sid / 'still'; ix = json.load(open(d / 'index.json')); (d / 'lo').mkdir(exist_ok=True)
        for cid in ix['still']:
            src = d / f'{cid}.jpg'; lo = d / 'lo' / f'{cid}.jpg'
            if not lo.exists() or lo.stat().st_mtime < src.stat().st_mtime:
                Image.open(src).convert('RGB').resize((360, 540), Image.LANCZOS).save(lo, quality=62, optimize=True, progressive=True)
        # 11-12 中等图 still/md/<片段>.webp（720×1080，≈48 KB）：换背景时先上这张（手机上已经清楚），2k 的等音频缓冲够了再补——慢网不再卡在上一张
        (d / 'md').mkdir(exist_ok=True)
        for cid in ix['still']:
            src = d / f'{cid}.webp' if (d / f'{cid}.webp').exists() else d / f'{cid}.jpg'; md = d / 'md' / f'{cid}.webp'
            if not md.exists() or md.stat().st_mtime < src.stat().st_mtime:
                Image.open(src).convert('RGB').resize((720, 1080), Image.LANCZOS).save(md, 'WEBP', quality=70, method=5)
        ix['md'] = 1
        fin = (json.load(open(SHOT)).get('final') or {}).get(sid, {}) if SHOT.exists() else {}   # measure --final 量过的景别
        q = ix.setdefault('q', {})
        for c in ix['still']:
            if c in fin and q.get(c, 'face') in ('face', 'close'): q[c] = 'close' if fin[c] >= CLOSE else 'face'   # 还是大脸特写的：播放器只在台词提到脸 / 眼神时用
        ix['w'] = sorted(c for c in ix['still'] if (d / f'{c}.webp').exists()); ix['lo'] = 1
        ix['v'] = int(max((d / f'{c}.jpg').stat().st_mtime for c in ix['still'])) % 10000000
        json.dump(ix, open(d / 'index.json', 'w'))
        print(sid, len(ix['still']), 'stills,', sum(1 for c in ix['still'] if q.get(c) == 'close'), 'close,', len(ix['w']), 'webp, lo', sum(f.stat().st_size for f in (d / 'lo').glob('*.jpg')) // 1024, 'KB', flush=True)


if __name__ == '__main__':
    ALL = sorted(p.parent.name for p in (ROOT / 'app' / 'v').glob('*/still'))
    if sys.argv[1:2] == ['check']:   # 把现有的重画全部校验一遍，列出不合格的（--redo= 用）
        modes = json.load(open(MODES)) if MODES.exists() else {}; todo = []
        for key, mode in modes.items():
            sid, cid = key.split('.', 1); raw = RAW / sid / f'{cid}.jpg'; bak = BAK / sid / f'{cid}.jpg'
            if raw.exists() and bak.exists() and (not sys.argv[2:] or sid in sys.argv[2:]): todo.append((sid, cid, mode, bak, raw))
        with cf.ThreadPoolExecutor(8) as ex: res = list(ex.map(lambda j: qc(*j), todo))
        bad = []
        for (sid, cid, mode, _, _), (sc_, why) in zip(todo, res):
            _jput(QC, f'{sid}.{cid}', [sc_, why])
            if sc_ < 1: bad.append(f'{sid}.{cid}'); print(sid, cid, mode, why, flush=True)
        print(len(todo), 'checked,', len(bad), 'bad'); print('REDO=' + ','.join(bad)); sys.exit()
    if sys.argv[1:2] == ['measure']:
        m = measure([a for a in sys.argv[2:] if not a.startswith('--')] or ALL, '--final' in sys.argv)
        for sid, v in m.items():
            r = list(v.values()); print(f'{sid:10} n={len(r):3} none={sum(1 for x in r if x == 0):3} <.22={sum(1 for x in r if 0 < x < .22):3} .22-.3={sum(1 for x in r if .22 <= x < .3):3} .3-.4={sum(1 for x in r if .3 <= x < .4):3} >=.4={sum(1 for x in r if x >= .4):3}')
        sys.exit()
    if sys.argv[1:2] == ['pack']:
        pack([a for a in sys.argv[2:] if not a.startswith('--')] or sorted(p.parent.name for p in (ROOT / 'app' / 'v').glob('*/still')))
        sys.exit()
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or list(CFG) + PROTA
    only = next((set(a.split('=', 1)[1].split(',')) for a in sys.argv if a.startswith('--only=')), None)
    todo = [j for sid in ids for j in jobs(sid) if not only or f'{j[0]}.{j[1]}' in only]
    print(len(todo), 'stills', {sid: f"{sum(1 for j in todo if j[0] == sid and j[3] == 'wide')} wide + {sum(1 for j in todo if j[0] == sid and j[3] == 'same')} same" for sid in ids}, flush=True)
    if DRY: sys.exit()
    with cf.ThreadPoolExecutor(int(next((a.split('=')[1] for a in sys.argv if a.startswith('--par=')), 5))) as ex:
        for r in ex.map(one, todo): print(r, flush=True)
