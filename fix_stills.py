"""剧照返修（11-10 她要求：肢体崩坏/扭曲、手指错、名牌字这类问题全局重出正确的图替换）。
- 审图结果（Claude 逐张看图）：data/still_qa.json {id: {verdict, anatomy[], text[], people, src}}，id = <剧>_sNN（画面库剧照编号）。
- 返修：原图上传（waku persist）→ Waku google/nano-banana-2.1/edit 按原图重画（同角色、同画风、同构图，只把写明的错处画对，去掉文字和描边）。
- 输出 data/fixed_stills/<id>.jpg（只留本机，.gitignore），映射 data/fixed_stills.json {原图路径: 新图路径}；build_prota_visuals / build_visuals 取图时自动换成新图。
用法：python3 fix_stills.py <id…> | --all（全部 verdict=regenerate 的）[--force]"""
import json, re, subprocess, sys, concurrent.futures as cf
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'fixed_stills'; OUT.mkdir(parents=True, exist_ok=True)
MAP = ROOT / 'data' / 'fixed_stills.json'
QA = ROOT / 'data' / (sys.argv[sys.argv.index('--qa') + 1] if '--qa' in sys.argv else 'still_qa.json')
MODEL = 'google/nano-banana-2.1/edit'


def fixed(path):
    """取图时用：有返修图就换成返修图"""
    m = json.loads(MAP.read_text()) if MAP.exists() else {}
    f = m.get(str(path))
    return f if f and Path(f).exists() else path


def _json(s):
    return json.loads(re.search(r'\{.*\}', s, re.S).group(0))


def persist(path):
    for _ in range(4):  # waku 上传偶尔 500
        r = subprocess.run(['waku', 'persist', str(path)], capture_output=True, text=True, timeout=120)
        m = re.search(r'"url":\s*"([^"]+)"', r.stdout)
        if m: return m.group(1)
    raise RuntimeError('persist failed ' + r.stdout[-200:] + r.stderr[-200:])


def ratio(w, h):
    r = w / h
    return min(['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9'], key=lambda a: abs(r - eval(a.replace(':', '/'))))


def prompt_for(q):
    probs = '; '.join(q.get('anatomy') or [])
    txt = q.get('text') or []
    cover = q.get('cover')
    return (
        'Redraw this exact illustration as a clean, corrected version. Keep the SAME character(s) (same face, hair color and style, eye color, outfit, accessories), '
        'the SAME art style and rendering (a photo stays a photo, anime stays anime), the same scene, lighting, colors, camera angle and composition, and the same body pose wherever it is anatomically correct. '
        + (f'Fix these errors: {probs}. ' if probs else '')
        + (f'NEW HAND/ARM POSE (do NOT copy the original hand shape, it is broken — redraw it from scratch exactly like this): {q["repose"]}. ' if q.get('repose') else '')
        + 'Every visible hand must have exactly five fingers (four fingers and one thumb on the correct side) with natural joints and bends; arms attach naturally to the shoulders with correct length and one elbow; '
        'clothing sleeves wrap the arms correctly; animal-eared characters have only their animal ears (no human ears); no limbs merging with objects or other people; held objects are gripped naturally. '
        + ('Keep the title/logo text exactly as it is (same letters, font, color and position). ' if cover else
           ('Remove all text, name plates, captions and logos (' + ', '.join(txt) + ') and fill those areas with the matching background. ' if txt else 'No text, no name plates, no logos, no watermark. ')
           + 'Remove any decorative border frame so the image fills edge to edge. ')
        + 'Adult characters stay adults, children stay children, tasteful, no added nudity.')


def fix(cid, q, force=False):
    out = OUT / f'{cid}.jpg'  # 封面（cover_<剧>）也先出到这里，确认后再换 app/covers
    if out.exists() and not force: return cid, 'exists', str(out)
    src = q['src']
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB'); W, H = im.size
    tmp = OUT / f'_{cid}.src.jpg'; im.save(tmp, quality=92)
    url = persist(tmp); tmp.unlink(missing_ok=True)
    params = {'prompt': prompt_for(q), 'images': [url], 'aspect_ratio': ratio(W, H), 'resolution': '2k', 'output_format': 'jpeg'}
    r = subprocess.run(['waku', 'gen', 'run', MODEL, '--capability', 'multimodal.generate.image', '--params', json.dumps(params)], capture_output=True, text=True, timeout=300)
    j = _json(r.stdout)
    for _ in range(4):
        if j.get('asset_url') or not j.get('job_id'): break
        r = subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '240'], capture_output=True, text=True, timeout=300)
        j = dict(_json(r.stdout), job_id=j['job_id'])
    if not j.get('asset_url'): raise RuntimeError(f'{cid} no asset ' + r.stdout[-300:] + r.stderr[-200:])
    subprocess.run(['curl', '-s', '--noproxy', '*', '-o', str(out), j['asset_url']], check=True)
    m = json.loads(MAP.read_text()) if MAP.exists() else {}
    m[str(src)] = str(out); MAP.write_text(json.dumps(m, ensure_ascii=False, indent=1))
    return cid, j.get('credits') or j.get('cost'), str(out)


if __name__ == '__main__':
    qa = json.loads(QA.read_text())
    ids = [k for k, v in qa.items() if v.get('verdict') == 'regenerate'] if '--all' in sys.argv else [a for a in sys.argv[1:] if not a.startswith('--') and not a.endswith('.json')]
    force = '--force' in sys.argv
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(fix, i, qa[i], force): i for i in ids}
        for f in cf.as_completed(futs):
            try: print(f.result(), flush=True)
            except Exception as e: print('FAIL', futs[f], str(e)[:300], flush=True)


def fix_region(cid, box, instruction, k=2.6, base=None):
    """整张重画改不动的（模型照搬原手）：只把出错的那块裁出来放大重画，再羽化贴回原图。box = 原图像素 (x0,y0,x1,y1)"""
    q = json.loads(QA.read_text())[cid]
    src = base or q['src']
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB'); W, H = im.size
    x0, y0, x1, y1 = box; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = int(min(min(W, H), max(max(x1 - x0, y1 - y0) * k, min(W, H) * 0.35)))
    L = int(min(max(0, cx - side / 2), W - side)); T = int(min(max(0, cy - side / 2), H - side))
    crop = im.crop((L, T, L + side, T + side)).resize((1024, 1024), Image.LANCZOS)
    tmp = OUT / f'_{cid}.crop.jpg'; crop.save(tmp, quality=93); url = persist(tmp); tmp.unlink(missing_ok=True)
    style = 'a real photograph (keep it photorealistic: real skin, real lighting)' if q.get('photo') else 'an illustration (keep the exact same art style)'
    prompt = (f'This is a close-up crop of {style}. Redraw this crop identically — same colors, lighting, textures, clothing and everything near the edges unchanged so it blends back seamlessly — '
              f'except fix this: {instruction}. Every visible hand has exactly four fingers and one thumb with natural joints. No text.')
    params = {'prompt': prompt, 'images': [url], 'aspect_ratio': '1:1', 'resolution': '1k', 'output_format': 'png'}
    r = subprocess.run(['waku', 'gen', 'run', MODEL, '--capability', 'multimodal.generate.image', '--params', json.dumps(params)], capture_output=True, text=True, timeout=300)
    j = _json(r.stdout)
    for _ in range(4):
        if j.get('asset_url') or not j.get('job_id'): break
        r = subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '240'], capture_output=True, text=True, timeout=300)
        j = dict(_json(r.stdout), job_id=j['job_id'])
    if not j.get('asset_url'): raise RuntimeError(f'{cid} no asset')
    patch_f = OUT / f'_{cid}.patch.png'
    subprocess.run(['curl', '-s', '--noproxy', '*', '-o', str(patch_f), j['asset_url']], check=True)
    patch = Image.open(patch_f).convert('RGB').resize((side, side), Image.LANCZOS)
    from PIL import ImageDraw, ImageFilter
    f = int(side * 0.14); mask = Image.new('L', (side, side), 0)
    ImageDraw.Draw(mask).rectangle([f, f, side - f, side - f], fill=255); mask = mask.filter(ImageFilter.GaussianBlur(f / 2.2))
    # 贴着原图边缘的那一侧不用羽化（裁块碰到画面边时）
    if L == 0 or T == 0 or L + side == W or T + side == H:
        m2 = Image.new('L', (side, side), 0); d = ImageDraw.Draw(m2)
        d.rectangle([0 if L == 0 else f, 0 if T == 0 else f, side if L + side == W else side - f, side if T + side == H else side - f], fill=255)
        mask = m2.filter(ImageFilter.GaussianBlur(f / 2.2))
    out_im = im.copy(); out_im.paste(patch, (L, T), mask)
    out = OUT / f'{cid}.jpg'; out_im.save(out, quality=94)
    m = json.loads(MAP.read_text()) if MAP.exists() else {}
    if not q.get('cover'): m[str(q['src'])] = str(out); MAP.write_text(json.dumps(m, ensure_ascii=False, indent=1))
    return cid, (L, T, side), str(out)


def fix_mask(cid, box, instruction, model='openai/gpt-image-2.6-flare/edit', base=None, up=1):
    """遮罩局部重画（GPT Image 2.6 edit 的 mask_image）：只改 box 里的手/手臂，结果只把这块羽化贴回原图——脸、标题字一个像素不动"""
    from PIL import ImageDraw, ImageFilter
    q = json.loads(QA.read_text())[cid]
    im = ImageOps.exif_transpose(Image.open(base or q['src'])).convert('RGB'); W, H = im.size
    big = im.resize((W * up, H * up), Image.LANCZOS) if up > 1 else im
    x0, y0, x1, y1 = [v * up for v in box]
    mask = Image.new('RGBA', big.size, (0, 0, 0, 255)); ImageDraw.Draw(mask).rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 0))
    fi = OUT / f'_{cid}.in.png'; fm = OUT / f'_{cid}.mask.png'; big.save(fi); mask.save(fm)
    u_img, u_mask = persist(fi), persist(fm); fi.unlink(missing_ok=True); fm.unlink(missing_ok=True)
    style = 'Photorealistic photograph, keep it a real photo.' if q.get('photo') else 'Keep the exact same illustration art style.'
    prompt = (f'Edit only the masked (transparent) area. {instruction}. {style} Every visible hand has exactly four fingers and one thumb with natural joints. '
              'Match the surrounding colors, lighting and clothing exactly so it blends seamlessly. No text.')
    params = {'prompt': prompt, 'images': [u_img], 'mask_image': u_mask, 'aspect_ratio': ratio(W, H), 'quality': 'high', 'resolution': '2k', 'output_format': 'png'}
    r = subprocess.run(['waku', 'gen', 'run', model, '--capability', 'multimodal.generate.image', '--params', json.dumps(params)], capture_output=True, text=True, timeout=400)
    j = _json(r.stdout)
    for _ in range(5):
        if j.get('asset_url') or not j.get('job_id'): break
        r = subprocess.run(['waku', 'gen', 'result', j['job_id'], '--wait', '--timeout', '280'], capture_output=True, text=True, timeout=320)
        j = dict(_json(r.stdout), job_id=j['job_id'])
    if not j.get('asset_url'): raise RuntimeError(f'{cid} no asset ' + r.stdout[-300:])
    fo = OUT / f'_{cid}.gpt.png'
    subprocess.run(['curl', '-s', '--noproxy', '*', '-o', str(fo), j['asset_url']], check=True)
    gen = Image.open(fo).convert('RGB').resize((W, H), Image.LANCZOS)
    pad = int(min(W, H) * 0.03)
    m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).rectangle([box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(pad / 1.5))
    out_im = im.copy(); out_im.paste(gen, (0, 0), m)
    out = OUT / f'{cid}.jpg'; out_im.save(out, quality=94)
    mp = json.loads(MAP.read_text()) if MAP.exists() else {}
    if not q.get('cover'): mp[str(q['src'])] = str(out); MAP.write_text(json.dumps(mp, ensure_ascii=False, indent=1))
    return cid, str(out)
