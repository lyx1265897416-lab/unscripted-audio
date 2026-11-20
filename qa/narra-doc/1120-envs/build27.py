#!/usr/bin/env python3
"""飞书 narra_2611「真实界面链路演示」新增的「客户端测试版 / 正式版」HTML 演示（11-20）。

输入：本目录 test/ 和 prod/（shot_tour.py --env 截的英文版截图 + index.json + build.json + *.sem.json）
做的事：截图转 600 宽 jpg → 上传（缓存在 urls27.tsv）→ 语义树出编号框 → 写 viewer.html（单文件 < 500KB）
用法：python3 build27.py [--no-upload]
"""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENVS = [('test', '测试版'), ('prod', '正式版')]
STEPS = ['新人引导', '首页', '搜索', '剧集详情', '播放器', '选择点', '下一集', '我的', '设置', '福利和金币']
W, H = 402, 874
sys.path.insert(0, '/Users/vicky/Interactive storyline/projects/cat-who-inherited/tools')

URLS = HERE / 'urls27.tsv'
cache = {}
if URLS.exists():
    for line in URLS.read_text().splitlines():
        k, v = line.split('\t')
        cache[k] = v


def jpg(png: Path) -> Path:
    out = HERE / 'jpg' / png.parent.name / (png.stem + '.jpg')
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.stat().st_mtime < png.stat().st_mtime:
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '82', '--resampleWidth', '600', str(png), '--out', str(out)],
                       check=True, capture_output=True)
    return out


def url_of(png: Path, upload: bool) -> str:
    j = jpg(png)
    key = f'{png.parent.name}/{j.name}:{int(j.stat().st_mtime)}'
    if key not in cache:
        if not upload:
            return j.as_uri()
        import mcp_upload
        cache[key] = mcp_upload.upload(str(j))
        with URLS.open('a') as f:
            f.write(f'{key}\t{cache[key]}\n')
    return cache[key]


KIND = [('isTextField', '输入框，可以打字'), ('isSlider', '滑块，可以拖动'), ('isToggled', '开关'), ('hasToggledState', '开关'),
        ('isChecked', '勾选项'), ('hasCheckedState', '勾选项'), ('isLink', '链接，点了跳转'), ('isButton', '按钮，可以点'),
        ('isHeader', '标题')]


def marks_of(sem: Path):
    if not sem.exists():
        return []
    try:
        nodes = json.loads(sem.read_text())
    except Exception:
        return []
    out, seen = [], set()
    for n in nodes:
        lab = ' '.join((n.get('label') or n.get('value') or n.get('hint') or '').split())
        for _ in range(2):   # 语义树里按钮文字常被合并成「A A」：去掉整段重复
            ws = lab.split(' ')
            for k in range(len(ws) // 2, 0, -1):   # 末尾整段重复（如「Play Now, The Villa The Villa」）
                if ws[-2 * k:-k] == ws[-k:]:
                    lab = ' '.join(ws[:-k])
                    break
        x, y, w, h = n.get('rect', [0, 0, 0, 0])
        x, y = max(0, x), max(0, y)
        w, h = min(w, W - x), min(h, H - y)
        if not lab or w < 14 or h < 14 or y > H - 8:
            continue
        if w * h > W * H * 0.6:   # 整屏容器
            continue
        flags, acts = set(n.get('flags') or []), set(n.get('actions') or [])
        d = next((t for f, t in KIND if f in flags), None)
        if d is None:
            if 'tap' in acts or 'longPress' in acts:
                d = '可以点'
            elif acts & {'scrollUp', 'scrollDown', 'scrollLeft', 'scrollRight'}:
                d = '可以滑动'
            else:
                continue
        if len(lab) > 46:
            lab = lab[:44] + '…'
        k = (lab, round(x / 8), round(y / 8))
        if k in seen:
            continue
        seen.add(k)
        out.append({'r': [round(x), round(y), round(w), round(h)], 'n': lab, 'd': d})
    out.sort(key=lambda m: (m['r'][1] // 24, m['r'][0]))
    return out[:12]


def load(env, upload):
    d = HERE / env
    idx = json.loads((d / 'index.json').read_text())
    b = json.loads((d / 'build.json').read_text())
    steps = {}
    for it in idx:
        png = d / it['file']
        sid = Path(it['file']).stem
        steps.setdefault(it['step'], []).append({
            'id': sid, 'key': sid.split('_', 1)[1] if '_' in sid else sid, 'name': it['name'], 'note': it.get('note', ''),
            'at': it.get('shot_at', ''), 'img': url_of(png, upload), 'marks': marks_of(d / (sid + '.sem.json'))})
    data = [{'step': s, 'screens': steps[s]} for s in STEPS if s in steps]
    data += [{'step': s, 'screens': v} for s, v in steps.items() if s not in STEPS]
    return {'env': env, 'build': b, 'data': data}


def main():
    upload = '--no-upload' not in sys.argv
    payload = []
    for env, label in ENVS:
        if (HERE / env / 'index.json').exists():
            v = load(env, upload)
            v['label'] = label
            payload.append(v)
    tpl = (HERE / 'viewer.tpl.html').read_text()
    html = tpl.replace('/*DATA*/[]', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    out = HERE / ('viewer.html' if upload else 'viewer.local.html')
    out.write_text(html)
    print(out, f'{len(html.encode()) / 1024:.0f}KB', [(v['env'], sum(len(s['screens']) for s in v['data'])) for v in payload])


if __name__ == '__main__':
    main()
