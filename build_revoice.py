"""给第 1 集里某个角色换配音（11-13：咪换成她剧集里定好的音色）。
  python3 build_revoice.py <剧 id> <角色 key> [en] [zh]
只重配这个角色的句子（data/voices.json 里该角色的 seed 配置：seed-speech-tts-2.0），其他句子的配音不动；
各句时长变了，所以重排字幕时间轴（规则和 produce_ep1 一样：开头 0.8 秒，同一人连续停 0.3 秒、换人 0.45 秒，结尾 1.2 秒），
再用 build_audio.mix 重混（统一响度 + 环境声 + BGM + 音效），上传一份到云存储（备用地址），拷到 app/ep1 和 docs/ep1。
旧的句子备份在 parts/old-<角色>/，旧的 json 备份成 .bak-<角色>.json。"""
import json, shutil, subprocess, sys, re, concurrent.futures as cf
from pathlib import Path
import build_audio as BA
ROOT = Path(__file__).resolve().parent; CACHE = ROOT / 'cache' / 'ep1'
VOICES = json.load(open(ROOT / 'data' / 'voices.json'))

def say(sd, text, lang, out):
    params = dict(text=re.sub(r'\[[^\]]*\]\s*', '', text).strip(), voice=sd['voice'], pitch=sd.get(f'pitch_{lang}', sd.get('pitch', 0)), speed=sd.get('speed', 1.0), language=lang,
                  sample_rate=48000, output_format='mp3', voice_instruction=sd.get(f'instr_{lang}') or sd.get('instr_en') or '')
    for k in range(3):
        r = subprocess.run(['waku', 'gen', 'run', 'bytedance/seed-speech-tts-2.0', '--capability', 'multimodal.generate.audio', '--params', json.dumps(params, ensure_ascii=False), '--wait', '--out', str(out)], capture_output=True, text=True, timeout=180)
        if out.exists() and out.stat().st_size > 3000: return True
    print('FAILED', text, r.stderr[-200:]); return False

TAKES = int(sys.argv[sys.argv.index('--takes') + 1]) if '--takes' in sys.argv else 1
def clarity(path, text, lang):
    """这一遍配音有多少词能被本机识别按顺序认出来（0–1）；角色名 Mii 认成 me 也算对"""
    import urllib.request as U
    try:
        r = json.loads(U.build_opener(U.ProxyHandler({})).open(U.Request('http://127.0.0.1:8917/asr', data=open(path, 'rb').read(), headers={'Content-Type': 'audio/mpeg', 'X-Lang': lang, 'X-Partial': '1'}), timeout=30).read())
    except Exception: return 0.5
    if lang == 'zh':
        z = lambda t: re.sub(r'[^\u4e00-\u9fffA-Za-z]', '', t or '').replace('绵', '咪').replace('米', '咪').replace('眯', '咪')
        ref, hyp = z(text), z(r.get('text')); j = 0; hit = 0
        for ch in ref:
            k = hyp.find(ch, j)
            if k >= 0: j = k + 1; hit += 1
        return hit / max(1, len(ref))
    n = lambda t: re.sub(r"[^a-z' ]", ' ', (t or '').lower().replace('mii', 'me').replace('mee', 'me')).split()
    ref, hyp = n(text), n(r.get('text')); j = 0; hit = 0
    for w in ref:
        if w in hyp[j:]: j = hyp.index(w, j) + 1; hit += 1
    return hit / max(1, len(ref))

def run(sid, who, lang):
    sd = VOICES[sid][who]['seed']; ej = CACHE / f'{sid}.{lang}.json'; parts = CACHE / f'{sid}.{lang}.parts'
    ep = json.load(open(ej)); cues = ep['cues']
    bak = CACHE / f'{sid}.{lang}.bak-{who}.json'
    if not bak.exists(): shutil.copy(ej, bak)
    old = parts / f'old-{who}'; old.mkdir(exist_ok=True)
    idx = [i for i, c in enumerate(cues) if c['who'] == who]
    def one(i):
        p = parts / f'{i:03d}.mp3'; new = parts / f'{i:03d}.new.mp3'
        if not (old / p.name).exists(): shutil.copy(p, old / p.name)
        # --takes N：每句配 N 遍，用本机识别挑咬字最清楚的一遍（幼童声偶尔吞掉句首的词）
        best = None
        for k in range(TAKES):
            t = parts / f'{i:03d}.take{k}.mp3'
            if not say(sd, cues[i]['text'], lang, t): continue
            sc = clarity(t, cues[i]['text'], lang) if TAKES > 1 else 1.0
            if best is None or sc > best[0]: best = (sc, t)
            if sc >= 0.99: break
        if not best: return None
        best[1].replace(p)
        for t in parts.glob(f'{i:03d}.take*.mp3'): t.unlink()
        print('  line', i, 'clarity', round(best[0], 2), cues[i]['text'][:40], flush=True)
        return i
    with cf.ThreadPoolExecutor(4) as ex: done = [x for x in ex.map(one, idx)]
    if None in done: raise SystemExit('some lines failed')
    t = 0.8
    for i, c in enumerate(cues):
        d = len(BA.load(parts / f'{i:03d}.mp3')) / BA.SR
        gap = 0.3 if i + 1 < len(cues) and cues[i + 1]['who'] == c['who'] else 0.45
        c['s'], c['e'] = round(t, 2), round(t + d, 2); t += d + gap
    ep['total'] = round(t + 1.2, 2); ep['dur'] = round(ep['total'], 1)
    json.dump(ep, open(ej, 'w'), ensure_ascii=False)
    print(BA.mix(sid, lang), flush=True)
    mp3 = CACHE / f'{sid}.{lang}.mp3'
    r = subprocess.run(['waku', 'persist', str(mp3)], capture_output=True, text=True, timeout=300)
    m = re.search(r'https://\S+?\.mp3', r.stdout + r.stderr)
    if m: ep['audio'] = m.group(0); json.dump(ep, open(ej, 'w'), ensure_ascii=False)
    else: print('upload failed', (r.stdout + r.stderr)[-200:])
    (ROOT / 'docs' / 'ep1').mkdir(exist_ok=True); shutil.copy(ROOT / 'app' / 'ep1' / mp3.name, ROOT / 'docs' / 'ep1' / mp3.name)
    print(sid, lang, who, 'lines', len(idx), 'dur', ep['dur'], 'audio', ep.get('audio', '')[-40:], flush=True)

if __name__ == '__main__':
    sid, who = sys.argv[1], sys.argv[2]
    for lang in ([a for a in sys.argv[3:] if a in ('en', 'zh')] or ['en', 'zh']): run(sid, who, lang)
