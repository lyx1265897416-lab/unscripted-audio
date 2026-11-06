"""从角色资料包提炼每部剧的“音频版世界卡”（Opus 5.5，经本机 Claude Code）。
输出 data/world/<id>.json：前提、她的身份、角色（含说话方式、声音类型）、真相/悬念、故事地图、氛围声、第 1 集标题。"""
import json, re, sys, glob, os, concurrent.futures as cf
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
import claude_cli as CC
P = '/Users/vicky/Interactive storyline/projects/realtime-character-packs/'
SRC = {'magnus': ('magnus/pack.md', 'magnus/open/pack/magnus_pack.json'), 'rafael': ('rafael/pack.md', 'rafael/third/pack/rafael_pack.json'),
       'rowan': ('rowan/pack.md', 'rowan/third/pack/meet_pack.json'), 'rian': ('rian/pack.md', 'rian/third/pack/rian_pack.json'),
       'island': ('island-liars/pack.md', 'island-liars/wes/pack/ila_pack.json'), 'lena': ('lena/pack.md', 'lena/live/pack/dont_trust_pack.json'),
       'mii': ('mii/pack.md', 'mii/open/pack/mii_pack.json')}
BASE = {s['id']: s for s in json.load(open('data/series_base.json'))}
os.makedirs('data/world', exist_ok=True)

def text_of(path, n):
    try: s = open(P + path, encoding='utf-8').read()
    except FileNotFoundError: return ''
    s = re.sub(r'<img[^>]*>', '', s); s = re.sub(r'data:[^"\')\s]{200,}', '', s); s = re.sub(r'<[^>]+>', ' ', s); s = re.sub(r'[ \t]+', ' ', s)
    return s[:n]

SYS = '''你是女性向有声连载剧（Pocket FM 那一类）的总编剧。要把一部原本是视频的实时互动剧，改编成纯音频的互动连载剧：旁白用第二人称“你”指女主（听众就是她），男主和配角有台词，每集结尾停在一个选择点，下一集按她的选择实时写。
只输出一个 JSON 对象，不要任何解释。'''

def ask(sid):
    if os.path.exists(f'data/world/{sid}.json') and '--force' not in sys.argv: return sid, 'skip'
    md, pk = SRC[sid]; b = BASE[sid]
    user = f'''剧：{b["title"]["zh"]} / {b["title"]["en"]}
现有简介：{b["hook"]["zh"]}
主角：{b["lead"]["zh"]}

【资料包文档（节选）】
{text_of(md, 26000)}

【线上资料包 JSON（节选）】
{text_of(pk, 14000)}

按资料包的设定提炼音频版世界卡，输出 JSON：
{{"premise_zh":"三四句，音频版的故事前提，用“你”","premise_en":"same in English, use you",
"synopsis_zh":"详情页长简介 120-180 字，用“你”，有钩子不剧透真相","synopsis_en":"same in English 90-130 words",
"her":"她（听众）在故事里的身份、处境（中文）",
"characters":[{{"name":"英文名，和资料包一致","name_zh":"中文写法（没有就同英文）","gender":"male|female|cat|other","age":"","role_zh":"一句话身份","role_en":"","personality":"性格、对她的态度（中文）","speech":"说话方式：句子长短、口头习惯、禁忌（中文）","voice":"声音类型（中文，如：成熟低沉温柔的男中音）","is_lead":true}}],
"truths":"只有编剧知道的真相/悬念，以及揭晓节奏（中文，可长）",
"story_map":["按集推进的大纲，6-10 条，每条一句：第 1 集……第 2 集……直到结局；每条都要有冲突或钩子"],
"endings":"可能的结局方向（中文）",
"places":["主要场景"],"ambience":["每个场景的环境声，英文短语，例如 rain on a car roof"],
"tone":"整体语气基调（中文）",
"ep1_title_zh":"第 1 集标题，6-10 字","ep1_title_en":"Episode 1 title",
"rules":"写这部剧时必须遵守的硬规则（中文，来自资料包：不能剧透的、人设不能崩的、不能出现的）"}}
characters 里主角排第一，最多 5 个有台词的角色（不含她）。'''
    txt, meta = CC.call_text(SYS, user, timeout=420, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    json.dump(j, open(f'data/world/{sid}.json', 'w'), ensure_ascii=False, indent=1)
    return sid, meta

if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or list(SRC)
    with cf.ThreadPoolExecutor(7) as ex:
        for r in ex.map(lambda s: (lambda: ask(s))() , ids): print(r, flush=True)
