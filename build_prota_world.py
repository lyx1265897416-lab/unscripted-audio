"""Prota Top10（data/prota/<id>.json，build_prota_src.py 生成）→ 音频版世界卡 data/world/<id>.json（Opus 5.5 经本机 Claude Code）。
和 build_world.py 字段相同，另加：title_zh / title_en（沿用 Prota 原名）、listener（听众本人的身份，性别不限）、pov="neutral"。
11-10 她定的：保持原作性别（女主角色就是女性，例如 Celine、Sienna），听众“你”不指定性别。"""
import json, re, sys, os, concurrent.futures as cf
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
import claude_cli as CC
IDS = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia']

SYS = '''你是 Pocket FM 那一类有声连载剧的总编剧。要把一张 AI 文字角色扮演故事卡（Prota 平台，玩家和 AI 聊天推进剧情）改编成纯音频的互动连载剧：
旁白用第二人称“你”指听众（听众就是故事里的玩家角色），其他角色有台词，每集结尾停在一个选择点，下一集按听众的选择实时写。
听众的性别不指定：保持原作里其他角色的性别和关系，不要把听众写成男或女。只输出一个 JSON 对象，不要任何解释。'''

SCHEMA = '''{"title_zh":"中文剧名（就用原卡的中文名，去掉多余符号）","title_en":"英文剧名（原卡英文名的正常写法）",
"premise_zh":"三四句，音频版的故事前提，用“你”","premise_en":"same in English, use you",
"synopsis_zh":"详情页长简介 120-180 字，用“你”，有钩子不剧透","synopsis_en":"same in English 90-130 words",
"her":"听众（你）在故事里的身份、处境、能力（中文；不写性别）",
"listener":"一句话：听众性别不限；角色提到听众时怎么称呼（中文）",
"characters":[{"name":"英文名，和原卡一致（只写名，或名+姓）","name_zh":"中文写法","gender":"male|female|other","age":"","role_zh":"一句话身份","role_en":"","personality":"性格、对你的态度（中文）","speech":"说话方式：句子长短、口头习惯、禁忌（中文）","voice":"声音类型（中文，如：清亮少年音、慵懒御姐音）","is_lead":true}],
"truths":"只有编剧知道的真相/悬念/世界规则（含原卡的数值、等级、技能系统怎么在音频里体现），以及揭晓节奏（中文，可长）",
"story_map":["按集推进的大纲，8-10 条，每条一句：第 1 集……第 2 集……直到一个阶段性结局；每条都要有冲突或钩子"],
"endings":"可能的结局方向（中文）",
"places":["主要场景"],"ambience":["每个场景的环境声，英文短语"],
"tone":"整体语气基调（中文）",
"ep1_title_zh":"第 1 集标题，6-10 字","ep1_title_en":"Episode 1 title",
"rules":"写这部剧必须遵守的硬规则（中文，来自原卡：世界规则、人设不能崩的、不能出现的；原卡给 AI 的格式要求如状态栏、表情包、图片指令一律不要）"}'''


def clip(s, n): return (s or '')[:n]


def ask(sid):
    if os.path.exists(f'data/world/{sid}.json') and '--force' not in sys.argv: return sid, 'skip'
    p = json.load(open(f'data/prota/{sid}.json'))
    chars = '\n\n'.join(f'## {c["name"]}（{c["name_zh"]}）\n{clip(c["persona_en"], 1200)}' for c in p['characters'][:16])
    user = f'''原卡：{p["name_en"]} / {p["name_zh"]}（Prota 游玩数第 {p["rank"]}）
标签：{p["tags"]}
一句话：{p["tagline_zh"]} / {p["tagline_en"]}
简介（中文）：{clip(p["synopsis_zh"], 1500)}

【开场白（中文）】
{clip(p["opening_zh"], 3500)}

【线路】{json.dumps([{k: v for k, v in r.items() if k != "opening_en" and v} for r in p["routes"]], ensure_ascii=False)}

【给 AI 的系统词（英文原文，节选）】
{clip(p["system_en"], 16000)}

【角色设定（节选）】
{chars}

按这张卡提炼音频版世界卡。要求：
- 原卡是文字聊天、可能有数值/等级/技能面板、状态栏、图片指令；音频版只保留故事和世界规则，数值用旁白和台词自然带出（例如“系统提示音：力量 9999”可以由旁白念）。
- characters 最多 5 个有台词的角色（不含听众），按戏份排；is_lead=true 的是听众身边最重要、可以和听众打电话的那一位（一般一个，最多两个），排最前。角色很多的学院类故事，挑开场就会出场、最有戏的。
- 第 1 集要覆盖原开场白的剧情（原卡开场常常是选技能/选身份：把最有戏的两个选项留给第 1 集结尾，其余在旁白里交代，听众也能自由说）。
- 原卡如果有成人/暴力尺度，音频版控制在 15+：可以暧昧、可以打斗，不写露骨性内容和血腥细节。
输出 JSON，字段如下：
{SCHEMA}'''
    txt, meta = CC.call_text(SYS, user, timeout=600, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    j['pov'] = 'neutral'
    json.dump(j, open(f'data/world/{sid}.json', 'w'), ensure_ascii=False, indent=1)
    return sid, j.get('title_zh'), j.get('title_en'), [(c['name'], c.get('gender'), c.get('is_lead')) for c in j['characters']], meta.get('sec')


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or IDS
    with cf.ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(ask, s): s for s in ids}
        for f in cf.as_completed(futs):
            try: print(f.result(), flush=True)
            except Exception as e: print('FAIL', futs[f], str(e)[:300], flush=True)
