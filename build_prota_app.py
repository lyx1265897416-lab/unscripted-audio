"""Prota Top10 的 8 部接进 App：声线（data/voices.json）、剧目卡（data/series_base.json）、封面/头像（app/covers、app/avatars、app/avatars/cast）。
世界卡先由 build_prota_world.py 生成；这里顺手把不好当声线键的名字改短（Ms. Holloway → Holloway，The System → System）。"""
import json, os, sys
import prota_face as F
from PIL import Image, ImageOps

IDS = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']
RENAME = {'Ms. Holloway': 'Holloway', 'The System': 'System'}
ZH = {  # 中文声线库（voices.json 里已经在用的 Eleven 声线）
    'Guan Tang Bao': 'MQkiCZS3mnl44caDtxkJ', 'Jason Chen': 'DowyQ68vDpgFYdWVGjc3', 'James Gao': '4VZIsMPtgggwNg7OXbPY', 'Devon': 'qV41hPnIn6kbvO8hMtPG',
    'Ian': 'tSv4yoTPFFmCMaJpNf0A', 'Evan Zhao': 'MI36FIkp9wRP7cpWKPTl', 'Zicai': 'DVE92KG0Yd4X7RoMqy8J', 'Yi Min': 'ZQ45Xiky4ENZqOdRnyjs', 'James': 'UwT0JPexcCbH107hq7i5',
    'Xin': 'D9bZgM9Er0PhIxuW9Jqa', 'Hardy': 'FS8UtxyDrvYcNCxVaziq', 'Danyu Zhao': 'BWN0mOtkGHghA3CYFzFK', 'Lucky Chan': 'cHDwXsKG0qHMNLIjOusN', 'Chen': '4aW8bNY2tSD8eaHmuXZ0',
    'Kevin Tu': 'BrbEfHMQu0fyclQR7lfh', 'Tung Wong': 'OjkyUe8dIihIFvOisuvM', 'Vincent': 'WkcRFJo38X9XEP8kGExm', 'Wilson': 'z1etx2H6NQWq1LH6oqJA', 'Neil Chuang': 'auoHciLZJwKTwYUoRTYz',
    'Adam Li': 'hZTuv9Zqrq4yHYrEmF1r', 'Martin Li': 'WuLq5z7nEcrhppO0ZQJw', 'Steven Gor': 'M0TrFmFeBJS9H4xzdk8Z',
    'Stella Gu': 'BqljjWyTnrioXPCNkCd4', 'Coco Li': 'Ca5bKgudqKJzq8YRFoAz', 'Karo Yang': '5mZxJZhSmJTjL7GoYfYI', 'Helen Sun': 'Iqi0ix5WGtiSXX9VDZB4', 'Anna Su': 'r6qgCCGI7RWKXCagm158',
    'Yun': 'YxbjaPemDJV2xlfvkiIG', 'Jane': '0Aj540a9UWvQPWdx9Zq4', 'Xiaoxi': '9DMBSOAnMDPiFAsz1ZGK', 'Stacy': 'hkfHEbBvdQFNX4uWHqRF', 'Julia': 'tOuLUAIdXShmWH7PEUrU'}
# 角色 → (中文声线, 英文声线)；按世界卡里的声音描述挑，同一部剧里不重复
VMAP = {
 'reborn': {'Fielle': ('Coco Li', 'Jessica'), 'Gareth': ('Evan Zhao', 'Charlie'), 'Lenne': ('Xiaoxi', 'Lily'), 'Sable': ('Stella Gu', 'Aria'), 'Thalrex': ('Steven Gor', 'Bill')},
 'hellqueen': {'Celine': ('Stella Gu', 'Charlotte'), 'Nora': ('Stacy', 'Jessica'), 'Malachar': ('Martin Li', 'Brian'), 'Seraphiel': ('Anna Su', 'Sarah'), 'Holloway': ('Helen Sun', 'Matilda')},
 'crackhigh': {'Declan': ('Zicai', 'Liam'), 'Lena': ('Coco Li', 'Laura'), 'Tessa': ('Karo Yang', 'Aria'), 'Asher': ('Xin', 'Callum'), 'Vivienne': ('Xiaoxi', 'Sarah')},
 'onestat': {'Renn': ('Chen', 'Harry'), 'Fawn': ('Coco Li', 'Jessica'), 'Seren': ('Helen Sun', 'Alice'), 'Hilde': ('Stella Gu', 'Aria'), 'System': ('Julia', 'River')},
 'mythborne': {'Sora': ('Karo Yang', 'Laura'), 'Rena': ('Stella Gu', 'Alice'), 'Claire': ('Yun', 'Lily'), 'Hinata': ('Helen Sun', 'Charlotte'), 'Mio': ('Stacy', 'Sarah')},
 'starmate': {'Sienna': ('Anna Su', 'Aria'), 'Marisol': ('Helen Sun', 'Matilda'), 'Theo': ('Chen', 'Will'), 'Rex': ('Martin Li', 'Bill'), 'Julian': ('James Gao', 'Eric')},
 'heroacad': {'Ashton': ('Ian', 'Chris'), 'Ember': ('Karo Yang', 'Aria'), 'Liora': ('Xiaoxi', 'Lily'), 'Prism': ('Coco Li', 'Alice'), 'Gareth': ('James Gao', 'Daniel')},
 'academia': {'Dahlia': ('Karo Yang', 'Jessica'), 'Raven': ('Xin', 'Callum'), 'Hinako': ('Coco Li', 'Laura'), 'Maren': ('Yun', 'Sarah'), 'Serena': ('Stella Gu', 'Charlotte')},
}
LOOK = {  # 剧目卡展示：主题色、题材、标签、展示用播放量/评分
 'reborn': ('#C9A24A', ['Fantasy', 'Adventure', 'Isekai'], [('转生', 'Reincarnation'), ('超强技能', 'OP skill'), ('冒险小队', 'Adventuring party')], ('1.8M', 4.8)),
 'hellqueen': ('#B5483A', ['Romance', 'Fantasy', 'Slice of life'], [('地狱女王', 'Queen of Hell'), ('合租养娃', 'Co-parenting'), ('日久生情', 'Slow burn')], ('1.3M', 4.9)),
 'crackhigh': ('#C0392B', ['Action', 'Academy', 'Romance'], [('格斗学院', 'Fight school'), ('校园排名', 'Rankings'), ('热血', 'Action')], ('960K', 4.7)),
 'onestat': ('#D96BA0', ['Fantasy', 'Adventure', 'Comedy'], [('9999 属性', 'Stat 9999'), ('冒险小队', 'Adventuring party'), ('亚人', 'Demihumans')], ('920K', 4.8)),
 'mythborne': ('#7A9A4A', ['Fantasy', 'Academy', 'Romance'], [('魔法学院', 'Magic academy'), ('神裔与怪物', 'Gods & monsters'), ('分院', 'Houses')], ('640K', 4.8)),
 'heroacad': ('#E07A2E', ['Action', 'Academy', 'Superpowers'], [('英雄学院', 'Hero academy'), ('能力觉醒', 'Powers'), ('A 班 B 班', 'Class rivalry')], ('590K', 4.7)),
 'starmate': ('#C77D8E', ['Romance', 'Slice of life', 'Celebrity'], [('大明星室友', 'Celebrity roommate'), ('秘密同居', 'Secret'), ('狗仔', 'Paparazzi')], ('560K', 4.8)),
 'academia': ('#E8C930', ['Action', 'Academy', 'Superpowers'], [('英雄学院', 'Hero academy'), ('等级排名', 'Rankings'), ('四大阵营', 'Four factions')], ('540K', 4.7)),
}
key = lambda name: RENAME.get(name, name).split()[0]


def fix_world(sid):
    p = f'data/world/{sid}.json'; w = json.load(open(p))
    for c in w['characters']: c['name'] = RENAME.get(c['name'], c['name'])
    json.dump(w, open(p, 'w'), ensure_ascii=False, indent=1); return w


def portrait(sid, name):
    pr = json.load(open(f'data/prota/{sid}.json'))
    c = next((x for x in pr['characters'] if x['name'].split()[0] == name or x['name'] == name), None)
    return c and (c['base'] or c['presets'])[0] if c and (c['base'] or c['presets']) else None


def main(ids):
    V = json.load(open('data/voices.json')); B = json.load(open('data/series_base.json'))
    for sid in ids:
        if sid not in VMAP: print('no voice map yet', sid); continue
        w = fix_world(sid); vm = VMAP[sid]
        names = [key(c['name']) for c in w['characters']]
        miss = [n for n in names if n not in vm]
        if miss: raise SystemExit(f'{sid}: no voice for {miss}')
        lead = [key(c['name']) for c in w['characters'] if c.get('is_lead')] or names[:1]
        V[sid] = {n: {'zh': ZH[vm[n][0]], 'zh_name': vm[n][0], 'en': vm[n][1], **({'lead': True} if n in lead else {})} for n in names}
        L = next(c for c in w['characters'] if key(c['name']) == lead[0])
        acc, genres, tags, stats = LOOK[sid]
        b = {'id': sid, 'pack': f'prota:{sid}', 'source': 'prota-top10', 'title': {'zh': w['title_zh'], 'en': w['title_en']},
             'lead': {'zh': f'{L.get("name_zh") or L["name"]} · {L.get("role_zh", "")}', 'en': f'{L["name"]} · {L.get("role_en", "")}'},
             'hook': {'zh': w['premise_zh'], 'en': w['premise_en']}, 'tags': [{'zh': a, 'en': e} for a, e in tags], 'genres': genres, 'accent': acc,
             'cover': f'covers/{sid}.jpg', 'avatar': f'avatars/{sid}.jpg', 'name': lead[0], 'stats': list(stats), 'pov': 'neutral'}
        B = [x for x in B if x['id'] != sid] + [b]
        # 封面（Prota 当前封面）、主角头像、可来电角色头像
        pr = json.load(open(f'data/prota/{sid}.json'))
        im = ImageOps.exif_transpose(Image.open(pr['cover'][0])).convert('RGB'); im.thumbnail((720, 1080)); im.save(f'app/covers/{sid}.jpg', quality=82)
        for n in lead:
            src = portrait(sid, n)
            if not src: print('no portrait', sid, n); continue
            F.avatar(src, f'app/avatars/cast/{sid}.{n}.jpg', 320)
            if n == lead[0]: F.avatar(src, f'app/avatars/{sid}.jpg', 192)
        print(sid, b['title'], lead, {n: vm[n] for n in names})
    json.dump(V, open('data/voices.json', 'w'), ensure_ascii=False, indent=1)
    json.dump(B, open('data/series_base.json', 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main([a for a in sys.argv[1:]] or IDS)
