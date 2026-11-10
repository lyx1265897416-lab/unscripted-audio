"""Prota Top10 故事包（彭宏博 11-10 整理，~/Downloads/Prota_Top10_完整故事包_2026-11-10）→ data/prota/<id>.json：
改编音频版要用的文字（系统词、开场、简介、角色设定）和图片本地路径。#04、#07 基于现成动漫/游戏 IP，不收。只留本机。"""
import json, os, unicodedata, glob
SRC = os.path.expanduser('~/Downloads/Prota_Top10_完整故事包_2026-11-10')
IDS = {'01': 'reborn', '02': 'hellqueen', '03': 'crackhigh', '05': 'onestat', '06': 'mythborne', '08': 'heroacad', '09': 'starmate', '10': 'academia'}
os.makedirs('data/prota', exist_ok=True)
norm = lambda s: ' '.join(unicodedata.normalize('NFKC', s or '').split())


def build(dirn, sid):
    d = json.load(open(f'{dirn}/item.json')); R = d['records']
    media = {m['source_key']: f'{dirn}/{m["local_path"]}' for m in d['media'] if m.get('source_key') and m.get('local_path')}
    files = lambda v: [media[x['file_token']] for x in (v or []) if isinstance(x, dict) and x.get('file_token') in media]
    st = R['stories'][0]['fields']; sp = R['split_text'][0]
    sysp = (sp.get('joined_text_fields') or {}).get('自定义系统词') or sp['fields'].get('自定义系统词') or ''
    sys_zh = st.get('自定义系统词｜中文（含续文）') or ''
    routes = [r['fields'] for r in R['routes']]
    r0 = routes[0] if routes else {}
    chars = []
    for r in R.get('preset_mapping') or []:
        f = r['fields']
        if f.get('角色类别') != '已设定角色': continue
        chars.append({'name': norm(f.get('角色名（英文）')), 'name_zh': f.get('角色名（中文）') or '', 'persona_en': (f.get('人物设定（英文）') or '')[:1800],
                      'look_en': (f.get('外貌与服装（英文）') or '')[:600], 'base': files(f.get('新版人物基准图')), 'presets': files(f.get('新版预设图'))[:6]})
    scenes = []
    for r in R.get('images') or []:
        f = r['fields']; p = files(f.get('图片预览'))
        if p: scenes.append({'name': f.get('图名') or f.get('线路 / 封面'), 'route': f.get('线路 / 封面'), 'path': p[0]})
    out = {'id': sid, 'rank': d['ranking']['rank'], 'plays': d['ranking']['play_count_in_table'], 'name_en': norm(d['name']), 'name_zh': d.get('chinese_name'),
           'tags': st.get('标签'), 'genre': st.get('题材'),
           'tagline_en': st.get('一句话修改'), 'tagline_zh': st.get('一句话修改｜中文'), 'synopsis_en': st.get('简介修改'), 'synopsis_zh': st.get('简介修改｜中文'),
           'opening_en': st.get('开场白修改') or r0.get('开场场景') or r0.get('序章（开场白）'), 'opening_zh': st.get('开场白修改｜中文') or r0.get('开场场景｜中文') or r0.get('序章（开场白）｜中文'),
           'replies_en': st.get('回复建议修改') or r0.get('回复建议'), 'replies_zh': st.get('回复建议修改｜中文') or r0.get('回复建议｜中文'),
           'routes': [{'name': r.get('线路'), 'name_zh': r.get('线路｜中文'), 'player_en': r.get('玩家身份'), 'player_zh': r.get('玩家身份｜中文'), 'opening_en': (r.get('开场场景') or r.get('序章（开场白）') or '')[:5000]} for r in routes],
           'system_en': sysp, 'system_zh': sys_zh, 'characters': chars,
           'cover': files(st.get('封面修改')) or files(st.get('prota线上封面')), 'cover_pool': files(st.get('封面候选池')), 'scenes': scenes}
    json.dump(out, open(f'data/prota/{sid}.json', 'w'), ensure_ascii=False, indent=1)
    return sid, out['name_en'], len(sysp), len(out['opening_en'] or ''), [c['name'] for c in chars], len(scenes), bool(out['cover'])


if __name__ == '__main__':
    for dirn in sorted(glob.glob(f'{SRC}/[01]*')):
        k = os.path.basename(dirn)[:2]
        if k in IDS: print(build(dirn, IDS[k]))
