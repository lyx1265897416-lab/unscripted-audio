"""全身定装图（纯色背景）→ 头像方块：找出人物轮廓，取最上面一段的中心作为头部"""
from PIL import Image, ImageOps
import statistics


def head_box(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB'); W, H = im.size
    s = 256 / W; sm = im.resize((256, int(H * s))); w, h = sm.size; px = sm.load()
    border = [px[x, 0] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    bg = tuple(statistics.median(c[i] for c in border) for i in range(3))
    far = lambda c: sum(abs(c[i] - bg[i]) for i in range(3)) > 60
    rows = [[x for x in range(w) if far(px[x, y])] for y in range(h)]
    hit = [y for y in range(h) if len(rows[y]) > 2]
    top, bot = hit[0], hit[-1]; fh = bot - top
    band = [x for y in range(top + int(fh * .02), top + int(fh * .09)) for x in rows[y]]
    cx = statistics.median(band) if band else w / 2
    side = fh * 0.19; cy = top + fh * 0.085
    x0 = max(0, min(w - side, cx - side / 2)); y0 = max(0, cy - side / 2)
    return im, tuple(int(v / s) for v in (x0, y0, x0 + side, y0 + side))


def avatar(path, out, size=320):
    im, box = head_box(path)
    im.crop(box).resize((size, size), Image.LANCZOS).save(out, quality=86)
    return box
