"""播放器画面库：每部剧把现成的剧情视频切成方形静音片段，附上画面描述，供“音频台词 ↔ 画面”匹配；再做万能轮播池。
来源（都在本机，不花额度）：
- 开场视频（即兴剧场 APP docs/openings/）：按镜头切开，描述 = 那段时间里的台词（catalog open_cues）。
- 实时测试片段（realtime-drama-test-log 的 cards）：每段 10–15 秒，描述 = 导演层逐镜头 beat + 男主台词 + 她的输入；画面硬错误的不要。
- 剧照：封面和角色包里的场景关键图，做成 6 秒缓推（Ken Burns）短片。
输出 app/v/<id>/*.mp4（随 Pages 发布）和 data/visuals/<id>.json：
{"clips":[{"id","src","dur","kind":"open|card|still|idle","cap"}], "pool":[id…]}（pool = 没有合适画面时轮播的万能 live/剧照）"""
import json, os, subprocess, sys, concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = Path('/Users/vicky/Interactive storyline/projects')
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
FP = FF.replace('ffmpeg', 'ffprobe')
LOG = P / 'realtime-drama-test-log'
APPD = P / 'realtime-drama-app/docs'
CAT = {d['id']: d for d in json.load(open(P / 'realtime-drama-app/catalog.json'))['dramas']}
CP = P / 'realtime-character-packs'
SIZE, CARD_MAX, CARD_SEC = 400, 36, 12
SRC = {
 'magnus': dict(cards=['magnus-open', 'magnus-third'], opening='magnus-open', stills=[APPD / 'covers/magnus-open.jpg', CP / 'magnus/open/masters/open-lock.jpg', CP / 'magnus/open/masters/open-nohand.jpg', CP / 'magnus/open/masters/selene-room.png']),
 'rafael': dict(cards=['rafael-third'], opening='rafael-third', stills=[APPD / 'covers/rafael-third.jpg']),
 'rowan': dict(cards=['meet-third'], opening='meet-third', stills=[APPD / 'covers/meet-third.jpg']),
 'rian': dict(cards=['rian-third'], opening='rian-third', stills=[APPD / 'covers/rian-third.jpg', CP / 'rian/third/masters/open-key.jpg', CP / 'rian/third/masters/open-last.jpg', ROOT / 'data/motion_src/rian-key.jpg', CP / 'rian/third/masters/plate-gallery.jpg']),
 'island': dict(cards=['island-liars'], opening='island-liars', stills=[APPD / 'covers/island-liars.jpg', CP / 'island-liars/wes/masters/open-key.jpg', CP / 'island-liars/jasper/masters/open-key.jpg']),
 'lena': dict(cards=['dont-trust'], opening='dont-trust', stills=[APPD / 'covers/dont-trust.jpg', CP / 'lena/live/masters/direct_key.jpg', CP / 'lena/live/masters/relay_key.jpg', CP / 'lena/live/masters/open-last-v2.jpg', CP / 'lena/live/masters/loc_room.jpg', CP / 'lena/live/masters/loc_stairwell.jpg']),
 'mii': dict(cards=['mii-open', 'mii'], opening='mii-open', stills=[APPD / 'covers/mii-open-clean.jpg', APPD / 'covers/mii.jpg']),
}


PWR = Path('/Users/vicky/Interactive storyline/external/perhaps-worlds')  # perhaps-worlds 克隆（私有仓库，媒体只在本机）
PW = {  # 开场视频、额外片段（待机 / 场景镜头）、剧照（场景图、带人的关键帧、封面）
 'kael': dict(opening='worlds/kael/intro/intro_notag.mp4', extra=['worlds/kael/cast/kael_idle_end.mp4', 'worlds/kael/cast/kael_idle_raw.mp4'],
              stills=['worlds/kael/assets/cover.jpg', 'worlds/kael/assets/hero.jpg', 'worlds/kael/ref/banquet.jpg', 'worlds/kael/ref/place_jetty.jpg', 'worlds/kael/ref/place_corridor.jpg', 'worlds/kael/cast/kael_idle_end_first.png']),
 'villa': dict(opening='worlds/villa/intro/intro_notag.mp4', extra=['worlds/villa/intro/vid/v4v_jace_d1.mp4', 'worlds/villa/intro/vid/v4v_kai_d2.mp4', 'worlds/villa/intro/vid/v4v_theo_d2.mp4', 'samples/villa_w1_jace.mp4'],
               stills=['worlds/villa/assets/cover.jpg', 'worlds/villa/ref/kf_meet_jace.png', 'worlds/villa/ref/kf_bar2_jace.png', 'worlds/villa/ref/kf_kitchen_jace.png', 'worlds/villa/ref/kf_terrace.png', 'worlds/villa/ref/night_fire_a.png', 'worlds/villa/ref/kf_open.png', 'worlds/villa/ref/kf_roof.png']),
 'dorian': dict(opening='worlds/dorian/intro/intro_notag.mp4', extra=['worlds/dorian/cast/dorian_idle.mp4'],
                stills=['worlds/dorian/assets/cover.jpg', 'worlds/dorian/assets/hero.jpg', 'worlds/dorian/ref/kitchen.jpg', 'worlds/dorian/ref/dining.jpg', 'worlds/dorian/ref/v4/study.jpg', 'worlds/dorian/ref/v4/terrace.jpg', 'worlds/dorian/ref/v4/pool.jpg', 'worlds/dorian/ref/v4/corridor.jpg']),
 'hear': dict(opening='worlds/hear/intro/intro.mp4', extra=['worlds/hear/intro/app/ray_idle.mp4'],
              stills=['worlds/hear/assets/cover.jpg', 'assets/hear/hero.jpg', 'assets/hear/look_day.jpg', 'assets/hear/look_night.jpg', 'worlds/hear/ref/loc_hear_car.jpg', 'worlds/hear/ref/loc_hear_terrace.jpg', 'worlds/hear/ref/loc_hear_mediation.jpg']),
 'mask': dict(opening='worlds/mask/intro/intro_notag.mp4', extra=['worlds/mask/intro/vid/x4_called.mp4', 'worlds/mask/intro/vid/r7b_reach.mp4', 'assets/mask/ui/coldopen.mp4', 'samples/mask_w1_gala.mp4'],
              stills=['worlds/mask/assets/cover.jpg', 'assets/mask/look/hero.jpg', 'worlds/mask/ref/sc03-start.png', 'worlds/mask/ref/look-gallery-v1.png', 'worlds/mask/keepsakes/lib/champagne_tower.jpg', 'worlds/mask/keepsakes/lib/rain_window.jpg', 'worlds/mask/keepsakes/lib/service_door.jpg']),
 'milo': dict(opening='worlds/milo/intro/intro_clean.mp4', extra=[],
              stills=['worlds/milo/assets/cover.jpg', 'worlds/milo/assets/hero.jpg', 'worlds/milo/intro/look/milo_cabin.png', 'worlds/milo/intro/cast/locked/milo_grin.png', 'worlds/milo/ref/loc_milo_party_kitchen.jpg', 'worlds/milo/ref/loc_milo_porch.jpg', 'worlds/milo/ref/loc_milo_her_place.jpg']),
}
IDLE_PW = {'kael': 'worlds/kael/cast/kael_idle_end.mp4', 'dorian': 'worlds/dorian/cast/dorian_idle.mp4', 'hear': 'worlds/hear/intro/app/ray_idle.mp4', 'villa': 'worlds/villa/intro/vid/v4v_jace_d1.mp4', 'mask': 'worlds/mask/intro/vid/x4_called.mp4'}


def dur(f):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout.strip() or 0)


def dims(f):
    o = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout.strip().split(',')
    return int(o[0]), int(o[1])


def square(src, out, a=0.0, b=None):
    """竖版裁方形：取上中部（人脸多在这里），缩到 SIZE，静音，快启动"""
    w, h = dims(src); side = min(w, h); y = int(max(0, (h - side) * 0.42))
    trim = ['-ss', f'{a:.2f}'] + (['-to', f'{b:.2f}'] if b else [])
    subprocess.run([FF, '-v', 'error', '-y', *trim, '-i', str(src), '-an', '-vf', f'crop={side}:{side}:{(w - side) // 2}:{y},scale={SIZE}:{SIZE},fps=24,setsar=1,format=yuv420p',
                    '-c:v', 'libx264', '-crf', '30', '-preset', 'veryfast', '-movflags', '+faststart', str(out)], check=True)


def kenburns(img, out, secs=6):
    """剧照缓推：方形取中上部，6 秒从 1.0 缓推到 1.12"""
    n = secs * 24
    subprocess.run([FF, '-v', 'error', '-y', '-i', str(img), '-frames:v', str(n), '-vf',
                    f"scale='if(gt(iw,ih),-2,{SIZE * 2})':'if(gt(iw,ih),{SIZE * 2},-2)',crop={SIZE * 2}:{SIZE * 2}:(iw-{SIZE * 2})/2:(ih-{SIZE * 2})*0.3,"
                    f"zoompan=z='1+0.12*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={SIZE}x{SIZE}:fps=24,format=yuv420p",
                    '-c:v', 'libx264', '-crf', '28', '-preset', 'veryfast', '-movflags', '+faststart', str(out)], check=True)


def opening_shots(cid):
    src = APPD / 'openings' / f'{cid}.mp4'
    if not src.exists(): return []
    t = subprocess.run([FF, '-hide_banner', '-i', str(src), '-vf', "select='gt(scene,0.3)',showinfo", '-f', 'null', '-'], capture_output=True, text=True).stderr
    import re
    cuts = [0.0] + [float(x) for x in re.findall(r'pts_time:([0-9.]+)', t)] + [dur(src)]
    cues = (CAT[cid].get('live') or {}).get('open_cues') or []
    shots = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 1.2: continue
        said = ' / '.join(f"{c.get('who', '')}: {c.get('zh') or c.get('en')}" for c in cues if c['s'] < b and c['e'] > a)
        shots.append((src, a, b, '开场镜头' + (f'（台词：{said}）' if said else '（无台词，环境/动作镜头）')))
    return shots


def cards(ids):
    out, spare = [], []  # spare：标了画面硬错误的（多是没出声、布局不连贯，当静音画面还能用）；好片段不足 12 段时拿来补
    for did in ids:
        d = json.load(open(LOG / 'dramas' / f'{did}.json'))
        for g in d['groups']:
            for c in g.get('cards', []):
                v = LOG / (c.get('video') or '')
                if not c.get('video') or not v.exists(): continue
                marks = c.get('marks') or []
                bad = any(m[1] == '画面硬错误' and m[0] == 0 for m in marks)
                cap = (c.get('beat') or '')[:360] + (f"｜他说：{c.get('he_zh') or c.get('he')}" if c.get('he') or c.get('he_zh') else '') + (f"｜她：{c.get('her')}" if c.get('her') else '')
                (spare if bad else out).append((v, cap))
    if len(out) < 12: out += spare[:12 - len(out)]
    if len(out) > CARD_MAX:  # 均匀抽样，保留不同测试局的不同场景
        step = len(out) / CARD_MAX; out = [out[int(i * step)] for i in range(CARD_MAX)]
    return out


def pw_opening_shots(sid):
    """perhaps 世界的开场：按镜头切开，描述 = 那段时间里原世界卡 intro.captions 的台词"""
    w = json.load(open(ROOT / 'data' / 'pw' / f'{sid}.world.json')); src = PWR / PW[sid]['opening']
    if not src.exists(): return []
    import re
    t = subprocess.run([FF, '-hide_banner', '-i', str(src), '-vf', "select='gt(scene,0.3)',showinfo", '-f', 'null', '-'], capture_output=True, text=True).stderr
    cuts = [0.0] + [float(x) for x in re.findall(r'pts_time:([0-9.]+)', t)] + [dur(src)]
    caps = (w.get('intro') or {}).get('captions') or []
    shots = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 1.2: continue
        said = ' / '.join(f"{(c.get('who') or '').title()}: {c.get('zh') or c.get('text')}" for c in caps if c.get('start', 0) < b and c.get('end', 0) > a)
        shots.append((src, a, min(b, a + 12), '开场镜头' + (f'（台词：{said}）' if said else '（无台词，环境/动作镜头）')))
    return shots


def build(sid):
    if sid in PW: return build_pw(sid)
    cfg = SRC[sid]; od = ROOT / 'app' / 'v' / sid; od.mkdir(parents=True, exist_ok=True)
    clips, jobs = [], []
    for i, (src, a, b, cap) in enumerate(opening_shots(cfg['opening'])):
        cid = f'o{i:02d}'; clips.append({'id': cid, 'kind': 'open', 'cap': cap}); jobs.append(('sq', src, od / f'{cid}.mp4', a, b))
    for i, (v, cap) in enumerate(cards(cfg['cards'])):
        cid = f'c{i:02d}'; clips.append({'id': cid, 'kind': 'card', 'cap': cap}); jobs.append(('sq', v, od / f'{cid}.mp4', 0, min(CARD_SEC, dur(v))))
    for i, img in enumerate([s for s in cfg['stills'] if Path(s).exists()]):
        cid = f's{i:02d}'; clips.append({'id': cid, 'kind': 'still', 'cap': '剧照：' + Path(img).stem}); jobs.append(('kb', img, od / f'{cid}.mp4', 0, 0))
    idle = ROOT / 'cache' / 'motion' / f'{sid}.mp4'
    if idle.exists():
        subprocess.run(['cp', str(idle), str(od / 'idle.mp4')]); clips.append({'id': 'idle', 'kind': 'idle', 'cap': '男主待机动态封面'})

    def run(j):
        kind, src, out, a, b = j
        if out.exists() and out.stat().st_size > 2000 and '--force' not in sys.argv: return
        try: square(src, out, a, b) if kind == 'sq' else kenburns(src, out)
        except Exception:
            out.unlink(missing_ok=True); raise  # 失败别留下空文件（否则下次会被当成已做好跳过）
    with cf.ThreadPoolExecutor(6) as ex: list(ex.map(run, jobs))
    for c in clips:
        f = od / f"{c['id']}.mp4"; c['src'] = f'v/{sid}/{c["id"]}.mp4'; c['dur'] = round(dur(f), 2)
    opens = [c['id'] for c in clips if c['kind'] == 'open']
    pool = ['idle'] * any(c['id'] == 'idle' for c in clips) + [c['id'] for c in clips if c['kind'] == 'still'] + opens[:: max(1, len(opens) // 4)][:4]
    (ROOT / 'data' / 'visuals').mkdir(exist_ok=True)
    json.dump({'clips': clips, 'pool': pool}, open(ROOT / 'data' / 'visuals' / f'{sid}.json', 'w'), ensure_ascii=False, indent=1)
    size = sum(f.stat().st_size for f in od.glob('*.mp4'))
    return sid, len(clips), sum(c['kind'] == 'open' for c in clips), sum(c['kind'] == 'card' for c in clips), len(pool), f'{size / 1e6:.1f}MB'


def build_pw(sid):
    cfg = PW[sid]; od = ROOT / 'app' / 'v' / sid; od.mkdir(parents=True, exist_ok=True)
    clips, jobs = [], []
    for i, (src, a, b, cap) in enumerate(pw_opening_shots(sid)):
        cid = f'o{i:02d}'; clips.append({'id': cid, 'kind': 'open', 'cap': cap}); jobs.append(('sq', src, od / f'{cid}.mp4', a, b))
    for i, rel in enumerate(cfg['extra']):
        v = PWR / rel
        if not v.exists(): continue
        cid = f'c{i:02d}'; clips.append({'id': cid, 'kind': 'card', 'cap': '剧情片段：' + Path(rel).stem.replace('_', ' ')}); jobs.append(('sq', v, od / f'{cid}.mp4', 0, min(CARD_SEC, dur(v))))
    for i, rel in enumerate([s for s in cfg['stills'] if (PWR / s).exists()]):
        cid = f's{i:02d}'; clips.append({'id': cid, 'kind': 'still', 'cap': '剧照：' + Path(rel).stem.replace('_', ' ')}); jobs.append(('kb', PWR / rel, od / f'{cid}.mp4', 0, 0))
    idle = IDLE_PW.get(sid)
    if idle and (PWR / idle).exists(): jobs.append(('sq', PWR / idle, od / 'idle.mp4', 0, min(8, dur(PWR / idle)))); clips.append({'id': 'idle', 'kind': 'idle', 'cap': '男主待机动态'})

    def run(j):
        kind, src, out, a, b = j
        if out.exists() and out.stat().st_size > 2000 and '--force' not in sys.argv: return
        try: square(src, out, a, b) if kind == 'sq' else kenburns(src, out)
        except Exception:
            out.unlink(missing_ok=True); raise
    with cf.ThreadPoolExecutor(6) as ex: list(ex.map(run, jobs))
    for c in clips:
        f = od / f"{c['id']}.mp4"; c['src'] = f'v/{sid}/{c["id"]}.mp4'; c['dur'] = round(dur(f), 2)
    opens = [c['id'] for c in clips if c['kind'] == 'open']
    pool = ['idle'] * any(c['id'] == 'idle' for c in clips) + [c['id'] for c in clips if c['kind'] == 'still'] + opens[:: max(1, len(opens) // 4)][:4]
    (ROOT / 'data' / 'visuals').mkdir(exist_ok=True)
    json.dump({'clips': clips, 'pool': pool}, open(ROOT / 'data' / 'visuals' / f'{sid}.json', 'w'), ensure_ascii=False, indent=1)
    size = sum(f.stat().st_size for f in od.glob('*.mp4'))
    return sid, len(clips), len(opens), sum(c['kind'] == 'card' for c in clips), len(pool), f'{size / 1e6:.1f}MB'


if __name__ == '__main__':
    for sid in [a for a in sys.argv[1:] if not a.startswith('--')] or list(SRC) + list(PW):
        print(build(sid), flush=True)
