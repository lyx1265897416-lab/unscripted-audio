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

def ask(sid, lang):
    out = f'data/ep1/{sid}.{lang}.json'
    if os.path.exists(out) and '--force' not in sys.argv: return sid, lang, 'skip'
    w = json.load(open(f'data/world/{sid}.json')); b = BASE[sid]
    cast = [k for k in V[sid] if not k.startswith('_')]
    cues = CAT[CID[sid]].get('live', {}).get('open_cues') or []
    cue_txt = '\n'.join(f'{c.get("who","")}: {c.get(lang) or c.get("en")}' for c in cues)[:3000]
    sysm = '你是女性向有声连载剧的王牌编剧（Pocket FM 那一类：狼人、霸总、恋爱、悬疑）。只输出一个 JSON 对象。' if lang == 'zh' else 'You are the head writer of a women-focused serialized audio drama app (Pocket FM style). Output one JSON object only.'
    user = f'''剧名：{b["title"][lang]}
世界卡（编剧内部资料，真相不能剧透）：
{json.dumps(w, ensure_ascii=False)}

原视频版开场的台词（第 1 集要覆盖这段剧情，可以改写成适合耳朵听的样子）：
{cue_txt or "（无）"}

能配音的角色（who 只能用这些英文名，或 NARR）：{", ".join(cast)}

{RULES[lang]}

写第 1 集「{w["ep1_title_" + lang]}」，按世界卡 story_map 第 1 集推进，结尾停在选择点。输出：
{{"title":"{w["ep1_title_" + lang]}","amb":"这一集的环境声（英文短语）","lines":[{{"who":"NARR","text":"…"}}],"prompt":"选择点上方的一句局面说明，用“你”/you，提示她要回应什么","choices":["她的回应 A（她第一人称说的话或动作，10-20 字）","她的回应 B"]}}'''
    txt, meta = CC.call_text(sysm, user, timeout=420, effort='medium')
    j = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    bad = [l['who'] for l in j['lines'] if l['who'] != 'NARR' and l['who'] not in cast]
    if bad: raise ValueError(f'{sid} {lang} unknown who {bad}')
    import re
    if lang == 'zh':
        eng = [l['text'] for l in j['lines'] if len(re.findall(r'[A-Za-z]{3,}', re.sub(r'\[[^\]]*\]', '', l['text']))) >= 3]
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
