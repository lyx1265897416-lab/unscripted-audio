"""第 1 集逐句配画面（Opus 5.5 经本机 Claude Code）：按台词内容从画面库挑片段，输出 data/ep1_visuals/<id>.<lang>.json = [{"line": i, "clip": id}]。
中转把它按逐句字幕时间换成时间轴 visuals=[{s,e,clip}]，播放器按时间切画面。"""
import json, sys, os, concurrent.futures as cf
sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
import claude_cli as CC
os.makedirs('data/ep1_visuals', exist_ok=True)
PREFER = '\n- 最重要：p 开头是预设完整版成片的镜头，画面质量和人物最统一，优先用它们；只有预设镜头里完全没有对应的场景或人物时，才用 o 开头的开场镜头、剧照或 idle。'
SYS = '你是有声剧的剪辑师，给每句台词配一段循环播放的画面（静音视频）。只输出 JSON 数组。'


def catalog(sid):
    v = json.load(open(f'data/visuals/{sid}.json'))
    cl = [c for c in v['clips'] if not (v.get('prefer') and c['kind'] == 'card')]  # 有预设完整版切片的剧：不再给实时测试片段
    return v, '\n'.join(f"{c['id']}（{c['kind']}，{c['dur']}s）：{c['cap'][:220]}" for c in cl)


def ask(sid, lang):
    out = f'data/ep1_visuals/{sid}.{lang}.json'
    if os.path.exists(out) and '--force' not in sys.argv: return sid, lang, 'skip'
    sc = json.load(open(f'data/ep1/{sid}.{lang}.json')); v, cat = catalog(sid)
    lines = '\n'.join(f"{i}. {l['who']}: {l['text']}" for i, l in enumerate(sc['lines']))
    user = f'''画面库（id：画面描述）：
{cat}

第 1 集台词（逐句）：
{lines}

给每一句挑一个最匹配的画面 id：
- 优先匹配这句在讲的动作、地点、人物和情绪；{'' if v.get('prefer') else '开场镜头（o 开头）和开场剧情一致，前半段优先用；'}
- 同一个情景连续几句可以用同一段，但同一段最多连续 4 句，整集尽量多用不同片段，不要来回只用两三段；
- 实在没有合适的就用剧照（s 开头）或 idle；不能编造不存在的 id。{PREFER if v.get('prefer') else ''}
输出：[{{"line":0,"clip":"o00"}}, …]，每一句都要有。'''
    txt, meta = CC.call_text(SYS, user, timeout=300, effort='low')
    arr = json.loads(txt[txt.find('['):txt.rfind(']') + 1])
    ids = {c['id'] for c in v['clips']}
    m = {int(x['line']): x['clip'] for x in arr if x.get('clip') in ids}
    res = [{'line': i, 'clip': m.get(i) or (v['pool'] or ['idle'])[i % max(1, len(v['pool']))]} for i in range(len(sc['lines']))]
    json.dump(res, open(out, 'w'), ensure_ascii=False, indent=1)
    return sid, lang, len(set(r['clip'] for r in res)), 'clips for', len(res), 'lines', meta.get('sec')


if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or ['magnus', 'rafael', 'rowan', 'rian', 'island', 'lena', 'mii']
    jobs = [(s, l) for s in ids for l in ('zh', 'en')]
    with cf.ThreadPoolExecutor(7) as ex:
        futs = {ex.submit(ask, s, l): (s, l) for s, l in jobs}
        for f in cf.as_completed(futs):
            try: print(f.result(), flush=True)
            except Exception as e: print('FAIL', futs[f], str(e)[:200], flush=True)
