"""第 1 集有声剧本（Opus 5.5 经本机 Claude Code）：data/ep1/<id>.<lang>.json
格式：{"title","amb","lines":[{"who":"NARR|角色英文名","text":"…"}],"prompt","choices":[2 条]}"""
import json, sys, os, concurrent.futures as cf
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
import claude_cli as CC
BASE = {s['id']: s for s in json.load(open('data/series_base.json'))}
V = json.load(open('data/voices.json'))
CAT = {d['id']: d for d in json.load(open('../realtime-drama-app/catalog.json'))['dramas']}
CID = {'magnus': 'magnus-open', 'rafael': 'rafael-third', 'rowan': 'meet-third', 'rian': 'rian-third', 'island': 'island-liars', 'lena': 'dont-trust', 'mii': 'mii-open'}
os.makedirs('data/ep1', exist_ok=True)

RULES = {
 'zh': '''写法（中文有声剧）：
- 这是纯音频，听众就是女主“你”。旁白（NARR）用第二人称“你”，现在时，短句，像贴着耳朵讲；写声音、气味、触感、距离，少写画面细节；不要“镜头”“画面”这类词。
- 女主不配音：她说的话由旁白转述（“你说，你只是路过。”），最多偶尔一句很短的引语。
- 所有旁白和台词一律用中文说（角色在故事里也说中文），只有人名保留英文（Magnus、Luca……）；不要英文句子，不要中英对照或括号翻译。
- 角色台词口语化、符合人设和说话方式；不要“亲爱的/宝贝”。
- 第 1 集不能出现女主的名字（每个听众名字不同），角色叫她时用“你”或不叫。
- 不要舞台说明、括号动作；可以在台词或旁白句首用少量 Eleven 音频标签：[softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering]，每 4 句最多 1 个。
- 节奏像 Pocket FM 的第 1 集：开头 15 秒内进事件，中间有一次升级，结尾停在钩子上。总长 2.5–3.5 分钟（中文约 650–900 字，28–40 句）。''',
 'en': '''Writing rules (English audio drama):
- Pure audio; the listener IS the heroine "you". Narrator (NARR) in second person, present tense, short sentences, close to the ear; write sound, smell, touch, distance; no "camera/shot/frame" words.
- The heroine is not voiced: the narrator reports what she says ("You tell him you were just passing through."), at most a very short quote now and then.
- Character lines conversational and in character; no "baby/darling".
- Episode 1 must not use the heroine's name (every listener's name differs); characters say "you" or no name.
- No stage directions or bracketed actions, except sparse ElevenLabs audio tags at the start of a line: [softly] [quietly] [low] [sighs] [exhales] [chuckles softly] [tense] [urgent] [whispering] — at most 1 per 4 lines.
- Pace like a Pocket FM episode 1: into the event within 15 seconds, one escalation in the middle, end on a hook. Total 2.5–3.5 minutes (about 420–560 words, 28–40 lines).'''}

PROTA = {'reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia'}  # 11-10 Prota Top10：听众性别不限
NEUTRAL = {'zh': [('听众就是女主“你”', '听众就是故事主角“你”（性别不限）'), ('女主不配音：她说的话由旁白转述（“你说，你只是路过。”）', '主角（听众）不配音：你说的话由旁白转述（“你说，你只是路过。”）'),
                  ('第 1 集不能出现女主的名字（每个听众名字不同），角色叫她时', '第 1 集不能出现听众的名字（每个听众名字不同），角色叫你时')],
           'en': [('the listener IS the heroine "you"', 'the listener IS the protagonist "you" (gender unspecified)'), ('The heroine is not voiced: the narrator reports what she says', 'The protagonist is not voiced: the narrator reports what you say'),
                  ("must not use the heroine's name", "must not use the listener's name")]}
POV = {'zh': '\n- 听众性别不限：别给“你”加性别（不用“他/她”“先生/小姐”“男孩/女孩”指代你，旁人提到你时用名字以外的身份说法，如“新生”“新室友”）。其他角色保持原作性别。',
       'en': '\n- The listener\'s gender is unspecified: never gender "you" (no he/she, sir/miss, boy/girl for the listener; others refer to you by role, e.g. "the new student"). Other characters keep their original genders.'}


def rules_for(sid, lang):
    if sid not in PROTA: return RULES[lang]
    t = RULES[lang]
    for a, b in NEUTRAL[lang]: t = t.replace(a, b)
    return t + POV[lang]


def ask(sid, lang):
    out = f'data/ep1/{sid}.{lang}.json'
    if os.path.exists(out) and '--force' not in sys.argv: return sid, lang, 'skip'
    w = json.load(open(f'data/world/{sid}.json')); b = BASE[sid]
    cast = [k for k in V[sid] if not k.startswith('_')]
    if sid in PROTA:  # Prota 原卡的开场白（文字聊天版）
        pr = json.load(open(f'data/prota/{sid}.json'))
        cues = [{'who': '', 'en': pr.get('opening_en') or '', 'zh': pr.get('opening_zh') or pr.get('opening_en') or ''}]
    elif sid in CID: cues = CAT[CID[sid]].get('live', {}).get('open_cues') or []
    else:  # perhaps-worlds 的世界：开场台词在原世界卡 intro.captions
        pw = json.load(open(f'data/pw/{sid}.world.json'))
        cues = [{'who': (c.get('who') or '').title(), 'en': c.get('text'), 'zh': c.get('zh') or c.get('text')} for c in (pw.get('intro') or {}).get('captions') or []]
    cue_txt = '\n'.join(f'{c.get("who","")}: {c.get(lang) or c.get("en")}' for c in cues)[:4500]
    sysm = '你是女性向有声连载剧的王牌编剧（Pocket FM 那一类：狼人、霸总、恋爱、悬疑）。只输出一个 JSON 对象。' if lang == 'zh' else 'You are the head writer of a women-focused serialized audio drama app (Pocket FM style). Output one JSON object only.'
    if sid in PROTA: sysm = '你是有声连载剧的王牌编剧（Pocket FM 那一类：奇幻冒险、学院、恋爱、喜剧）。只输出一个 JSON 对象。' if lang == 'zh' else 'You are the head writer of a serialized audio drama app (Pocket FM style: fantasy adventure, academy, romance, comedy). Output one JSON object only.'
    user = f'''剧名：{b["title"][lang]}
世界卡（编剧内部资料，真相不能剧透）：
{json.dumps(w, ensure_ascii=False)}

{"原卡（文字聊天版）的开场白" if sid in PROTA else "原视频版开场的台词"}（第 1 集要覆盖这段剧情，可以改写成适合耳朵听的样子；面板、状态栏、表情符号改成旁白念或台词）：
{cue_txt or "（无）"}

能配音的角色（who 只能用这些英文名，或 NARR）：{", ".join(cast)}

{rules_for(sid, lang)}

写第 1 集「{w["ep1_title_" + lang]}」，按世界卡 story_map 第 1 集推进，结尾停在选择点。输出：
{{"title":"{w["ep1_title_" + lang]}","amb":"这一集的环境声（英文短语）","lines":[{{"who":"NARR","text":"…"}}],"prompt":"选择点上方的一句局面说明，用“你”/you，提示她要回应什么","choices":["她的回应 A（她第一人称说的话或动作，10-20 字）","她的回应 B"]}}'''
    txt, meta = CC.call_text(sysm, user, timeout=420, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    bad = [l['who'] for l in j['lines'] if l['who'] != 'NARR' and l['who'] not in cast]
    if bad: raise ValueError(f'{sid} {lang} unknown who {bad}')
    import re
    if lang == 'zh':
        names = {n for c in w['characters'] for n in c['name'].split()} | {'Alpha', 'Beta', 'Mate', 'Vicky'}  # 人名和称呼不算英文句子
        eng = [l['text'] for l in j['lines'] if len([x for x in re.findall(r'[A-Za-z]{3,}', re.sub(r'\[[^\]]*\]', '', l['text'])) if x not in names]) >= 3]
        if eng: raise ValueError(f'{sid} zh 有英文句子 {eng[:2]}')
    json.dump(j, open(out, 'w'), ensure_ascii=False, indent=1)
    return sid, lang, len(j['lines']), sum(len(l['text']) for l in j['lines']), meta.get('sec')

if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or list(BASE)
    jobs = [(s, l) for s in ids for l in ('zh', 'en')]
    with cf.ThreadPoolExecutor(7) as ex:
        futs = {ex.submit(ask, s, l): (s, l) for s, l in jobs}
        for f in cf.as_completed(futs):
            try: print(f.result(), flush=True)
            except Exception as e: print('FAIL', futs[f], str(e)[:200], flush=True)
