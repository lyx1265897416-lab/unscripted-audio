"""把 perhaps-worlds（balabalabalaja/perhaps-worlds，私有）的视频世界卡改编成音频版世界卡，格式同 build_world.py：data/world/<id>.json。
另外补：title_zh（中文剧名）、series 门面字段。源世界卡在 data/pw/<id>.world.json（只留在本机，不进公开仓库）。"""
import json, re, sys, os, concurrent.futures as cf
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
import claude_cli as CC
import build_world as BW
IDS = ['kael', 'villa', 'dorian', 'hear', 'mask', 'milo']
DROP = ('look_blocks', 'body_fix_zh', 'hero_face', 'hero_face_note_zh', 'feed', 'cover', 'cover_note_zh', 'location_refs_with_people', 'location_refs_note_zh', 'w1', 'theme', 'bed', 'hero', 'hero_pos', 'page_hero', 'look_ref')


def src_text(w):
    w = {k: v for k, v in w.items() if k not in DROP}
    s = json.dumps(w, ensure_ascii=False)
    s = re.sub(r'"[^"]*\.(?:jpg|png|mp4|m4a|mp3|json)"', '""', s)
    return s[:42000]


def ask(sid):
    if os.path.exists(f'data/world/{sid}.json') and '--force' not in sys.argv: return sid, 'skip'
    w = json.load(open(f'data/pw/{sid}.world.json'))
    user = f'''剧：{w.get("title")}（{w.get("genre")} / {w.get("genre_zh")}）
一句话：{w.get("tagline")}
设定：{w.get("hook_zh")}

【原视频版世界卡（JSON 节选；spine 是主线拍点，canon 是正典，truths_zh 是只在被问到时才说的真相，never 是禁区，intro.captions 是开场台词）】
{src_text(w)}

按这张世界卡提炼音频版世界卡。注意：
- 原版是第一人称视频（镜头就是她），音频版里她就是听众“你”，旁白用第二人称。
- story_map 按 spine 的拍点顺序改写成按集推进（第 1 集对应开场 + 第一拍）。
- characters 里 pick=true 的是男主（可以和她打电话的人），排在最前；name 用原卡的英文名（首字母大写，如 Kael、Night Raven）。
- 多加两个字段："title_zh"：给中国女性听众的中文剧名（4–10 字，有钩子，不直译也可以），"title_en"：英文剧名（用原卡 title 的自然大小写写法）。
输出 JSON，字段同下（外加 title_zh、title_en）：
{BW.ask.__code__.co_consts and ''}'''
    # 复用 build_world 的字段说明
    tmpl = open('build_world.py').read()
    schema = tmpl[tmpl.index('按资料包的设定提炼音频版世界卡，输出 JSON：') + len('按资料包的设定提炼音频版世界卡，输出 JSON：'):tmpl.index("characters 里主角排第一")]
    user += schema.replace('{{', '{').replace('}}', '}') + '\ncharacters 里男主排前，最多 5 个有台词的角色（不含她）。'
    txt, meta = CC.call_text(BW.SYS, user, timeout=480, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    json.dump(j, open(f'data/world/{sid}.json', 'w'), ensure_ascii=False, indent=1)
    return sid, j.get('title_zh'), j.get('title_en'), [c['name'] for c in j['characters']], meta.get('sec')


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or IDS
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(ask, s): s for s in ids}
        for f in cf.as_completed(futs):
            try: print(f.result(), flush=True)
            except Exception as e: print('FAIL', futs[f], str(e)[:200], flush=True)
