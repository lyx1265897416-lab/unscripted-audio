"""播放器画面取景（11-10 她要求：画面要露出角色面部、镜头别抖）。
- faces(img)：Qwen3-VL 看图找人脸框（0–1 归一化），结果缓存在 data/faces.json（按图片内容 sha1）。
- still_clip(img, out)：剧照 → 方形“呼吸式”慢推短片。按脸取景（脸在画面上方 40% 处，头到腰），
  逐帧用 PIL 亚像素缩放（不走 ffmpeg zoompan 的整数取整，所以不抖），缩放以脸为锚点、首尾相接无缝循环。
- video_box(src, a, b)：视频切方形时按脸定裁切位置（取 3 帧，脸的并集放进画面）。
需要 OPENROUTER_API_KEY（中转进程里的那把）；没有 key 或识别失败时退回原来的居中偏上取景。"""
import json, os, io, re, base64, hashlib, math, subprocess, threading, urllib.request as U
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
FP = FF.replace('ffmpeg', 'ffprobe')
CACHE = ROOT / 'data' / 'faces.json'
MODEL = 'qwen/qwen3-vl-235b-a22b-instruct'
SIZE, FPS, LOOP, ZOOM = 480, 24, 8.0, 0.06  # 8 秒一个呼吸周期，最大推近 6%
_lock = threading.Lock()
_op = U.build_opener(U.ProxyHandler({}))
_cache = json.load(open(CACHE)) if CACHE.exists() else {}


def _save():
    with _lock: json.dump(_cache, open(CACHE, 'w'), indent=0)


def detect(im):
    """PIL 图 → [(x0,y0,x1,y1)]，0–1 归一化"""
    im = im.convert('RGB').copy(); im.thumbnail((896, 896))
    b = io.BytesIO(); im.save(b, 'JPEG', quality=85)
    txt = ('Find every human (or humanoid) face in this illustration or film frame. Return JSON only: {"faces":[{"box":[x0,y0,x1,y1]}]} '
           'with coordinates normalized 0-1000 relative to image width/height, box tight around the head (hair top to chin). Empty list if no face.')
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()}}, {'type': 'text', 'text': txt}]}],
        'max_tokens': 400, 'temperature': 0}
    req = U.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(),
                    headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY'], 'Content-Type': 'application/json'})
    c = json.loads(_op.open(req, timeout=90).read())['choices'][0]['message']['content']
    out = []
    for bx in re.findall(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', c):
        x0, y0, x1, y1 = (min(1000, int(v)) / 1000 for v in bx)
        if x1 - x0 > 0.01 and y1 - y0 > 0.01: out.append((x0, y0, x1, y1))
    return out


def faces(im, key):
    if key in _cache: return [tuple(f) for f in _cache[key]]
    for _ in range(3):
        try: f = detect(im); break
        except Exception as e: err = e
    else:
        print('face detect fail', key[:10], repr(err)[:80], flush=True); return []
    with _lock: _cache[key] = f
    _save(); return f


def img_key(path): return hashlib.sha1(open(path, 'rb').read()).hexdigest()[:16]


def main_faces(fs):
    """最大的脸，加上和它差不多大的（≥45% 面积）——合照时一起框进来"""
    if not fs: return []
    area = lambda f: (f[2] - f[0]) * (f[3] - f[1])
    big = max(area(f) for f in fs)
    return [f for f in fs if area(f) >= big * 0.45]


def frame_box(W, H, fs, head=3.4, at=0.40):
    """像素坐标的方形取景 (x0, y0, side) + 推近锚点 (ax, ay)。fs 是像素框"""
    m = min(W, H)
    if not fs:
        side = m; x0 = (W - side) / 2; y0 = (H - side) * 0.3
        return x0, y0, side, (x0 + side / 2, y0 + side * 0.4)
    ux0 = min(f[0] for f in fs); uy0 = min(f[1] for f in fs); ux1 = max(f[2] for f in fs); uy1 = max(f[3] for f in fs)
    fh = max(f[3] - f[1] for f in fs)
    side = min(m, max(fh * head, (ux1 - ux0) * 1.25, (uy1 - uy0) * 1.6, m * 0.42))
    cx, cy = (ux0 + ux1) / 2, (uy0 + uy1) / 2
    x0 = min(max(0, cx - side / 2), W - side); y0 = min(max(0, cy - side * at), H - side)
    return x0, y0, side, (cx, cy)


def load(path, inset=0.012):
    """读图并切掉 Prota 场景图四周的细描边"""
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB'); W, H = im.size
    d = int(min(W, H) * inset)
    return im.crop((d, d, W - d, H - d))


def plain_pad(im, fs, frac=0.22):
    """纯色背景的定装图：头贴着顶边时，四周补一圈同色背景，给头顶留空间（场景图不补）"""
    W, H = im.size
    if not fs: return im, fs
    sm = im.resize((64, max(1, round(64 * H / W)))); w, h = sm.size; px = sm.load()
    edge = [px[x, 0] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    mean = [sum(c[i] for c in edge) / len(edge) for i in range(3)]
    if max(max(abs(c[i] - mean[i]) for i in range(3)) for c in edge) > 28: return im, fs
    d = int(min(W, H) * frac)
    can = Image.new('RGB', (W + 2 * d, H + d), tuple(int(v) for v in mean)); can.paste(im, (d, d))
    return can, [(a + d, b + d, c + d, e + d) for a, b, c, e in fs]


def still_clip(path, out, secs=LOOP, size=SIZE):
    im = load(path); W, H = im.size
    fs = [(a * W, b * H, c * W, d * H) for a, b, c, d in main_faces(faces(im, img_key(path)))]
    if fs and min(f[1] for f in fs) < max(f[3] - f[1] for f in fs) * 0.9:  # 头顶离边不到一张脸高
        im, fs = plain_pad(im, fs); W, H = im.size
    x0, y0, side, (ax, ay) = frame_box(W, H, fs)
    s = min(1.0, size * 2.2 / side)  # 先缩到取景约 2.2 倍输出大小，逐帧缩放又快又不糊
    if s < 1: im = im.resize((round(W * s), round(H * s)), Image.LANCZOS); x0, y0, side, ax, ay = x0 * s, y0 * s, side * s, ax * s, ay * s
    W2, H2 = im.size  # 缩放取整后可能小零点几像素：取景框收进图内
    side = min(side, W2, H2); x0 = min(max(0, x0), W2 - side); y0 = min(max(0, y0), H2 - side)
    ax = min(max(ax, x0), x0 + side); ay = min(max(ay, y0), y0 + side)
    n = int(secs * FPS)
    p = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size}x{size}', '-r', str(FPS), '-i', '-',
                          '-c:v', 'libx264', '-crf', '29', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)], stdin=subprocess.PIPE)
    for i in range(n):
        z = 1 + ZOOM * (1 - math.cos(2 * math.pi * i / n)) / 2  # 0→最大→0，首尾相接
        k = 1 / z  # 以锚点（脸）为中心缩放：锚点在画面里的位置不动，窗口永远在取景框内
        bx0 = ax - (ax - x0) * k; by0 = ay - (ay - y0) * k
        fr = im.resize((size, size), Image.BICUBIC, box=(bx0, by0, bx0 + side * k, by0 + side * k))
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError(f'ffmpeg {p.returncode} {out}')
    return dict(faces=len(fs), side=round(side / s), at=(round(x0 / s), round(y0 / s)))


def grab(src, t):
    r = subprocess.run([FF, '-v', 'error', '-ss', f'{t:.2f}', '-i', str(src), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert('RGB') if r.stdout else None


def video_box(src, a, b, w, h):
    """视频裁方形的位置 (x, y, side)：取 3 帧找脸，脸的并集放进画面上部"""
    side = min(w, h)
    b = b or a + 6
    fs = []
    for t in (a + (b - a) * q for q in (0.15, 0.5, 0.85)):
        key = f'v:{hashlib.sha1(str(src).encode()).hexdigest()[:12]}:{os.path.getsize(src)}:{t:.2f}'
        im = None if key in _cache else grab(src, t)
        if key not in _cache and im is None: continue
        fs += [(x0 * w, y0 * h, x1 * w, y1 * h) for x0, y0, x1, y1 in main_faces(faces(im, key))]
    if not fs: return (w - side) // 2, int(max(0, (h - side) * 0.42)), side
    ux0 = min(f[0] for f in fs); uy0 = min(f[1] for f in fs); ux1 = max(f[2] for f in fs); uy1 = max(f[3] for f in fs)
    cx, cy = (ux0 + ux1) / 2, (uy0 + uy1) / 2
    if uy1 - uy0 > side * 0.8: cy = uy0 + side * 0.4  # 脸动得太多放不下：优先保住最上面的
    x = int(min(max(0, cx - side / 2), w - side)); y = int(min(max(0, cy - side * 0.40), h - side))
    return x, y, side
