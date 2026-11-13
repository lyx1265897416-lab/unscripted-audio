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
    params = dict(text=re.sub(r'\[[^\]]*\]\s*', '', text).strip(), voice=sd['voice'], pitch=sd.get('pitch', 0), speed=sd.get('speed', 1.0), language=lang,
                  sample_rate=48000, output_format='mp3', voice_instruction=sd.get(f'instr_{lang}') or sd.get('instr_en') or '')
    for k in range(3):
        r = subprocess.run(['waku', 'gen', 'run', 'bytedance/seed-speech-tts-2.0', '--capability', 'multimodal.generate.audio', '--params', json.dumps(params, ensure_ascii=False), '--wait', '--out', str(out)], capture_output=True, text=True, timeout=180)
        if out.exists() and out.stat().st_size > 3000: return True
    print('FAILED', text, r.stderr[-200:]); return False

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
        if say(sd, cues[i]['text'], lang, new): new.replace(p); return i
        return None
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
