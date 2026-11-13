"""音频层（11-11 她要求）：角色音和旁白音量一致；配一条很小声、清亮的 BGM；关键情节加特定音效。
借鉴阿炫《多角色语音故事》：响度只算高于 -40 dBFS 的 20 毫秒帧；换人处后一句不比前一句响 4 分贝以上；不逐段做动态归一。

  python3 build_audio.py bgm [id…]      每部剧一条 60 秒 BGM（Waku elevenlabs/music-v2，15 credits/条）→ 做成无缝循环 → app/bgm/<id>.mp3
  python3 build_audio.py sfxlib         通用音效库（sfx_lib.py，实时写的集用）→ app/sfx/<id>.mp3（约 0.5 credits/秒）
  python3 build_audio.py plan [id…]     Opus（本机 Claude Code）读第 1 集中英文剧本，挑 4–7 处关键音效 → data/sfx/<id>.json
  python3 build_audio.py gen [id…]      按 plan 生成第 1 集专属音效 → cache/sfx_ep1/<id>/<x>.mp3
  python3 build_audio.py mix [id…]      重混第 1 集：每句拉到同一响度（audio_level.TARGET）+ 环境声 + BGM + 音效 → cache/ep1 和 app/ep1 的 mp3
                                        （逐句配音用缓存，不重新配；时长和字幕时间轴不变；旧成片备份成 .bak-v58.mp3）
  加 --force 重做已有的（bgm 只重做循环和均衡；加 --regen 才重新生成）。mix 会打印换人处响度跳变的前后对比。"""
import json, os, re, shutil, subprocess, sys, concurrent.futures as cf
from pathlib import Path
import numpy as np
import audio_level as AL
import sfx_lib as SL

ROOT = Path(__file__).resolve().parent
FF = AL.FF; FP = FF.replace('ffmpeg', 'ffprobe')
SR = 44100
CACHE = ROOT / 'cache'; APP = ROOT / 'app'
BASE = json.load(open(ROOT / 'data' / 'series_base.json'))
IDS = [s['id'] for s in BASE]
FORCE = '--force' in sys.argv
BGM_FILE_DB, SFX_FILE_DB = -24.0, -24.0   # 公开文件自身的响度（手机端再乘增益）
BGM_DB, AMB_DB, SFX_DB = -42.0, -46.0, -25.0   # 混进第 1 集的响度：配音 -19，BGM 低 23 分贝，环境声更低，音效低 6 分贝
TAIL = ('Instrumental only. No drums, no bass, no percussion hits, no vocals. Bright, clear, airy high-register timbre. Very gentle and quiet, '
        'steady mood with no big build-ups or drops, slow tempo, a seamless background loop under spoken narration.')
BGM = {
    'magnus': 'Underscore for a tense, intimate werewolf-billionaire romance: sparse high felt-piano notes over a soft glassy pad, a faint breathy string harmonic.',
    'kael': 'Underscore for a gothic candlelit engagement banquet romance: delicate music-box celesta and high piano over a thin shimmer of strings, mysterious and tender.',
    'rafael': 'Underscore for a warm friends-to-lovers morning: bright fingerpicked nylon guitar with a few soft piano notes, light and tender.',
    'rowan': 'Underscore for a seaside healing love story with a quiet mystery: gentle bright piano arpeggios, soft kalimba, airy pad, nostalgic and hopeful.',
    'rian': 'Underscore for a merman-prince fantasy romance: shimmering harp, glass bells and a soft watery pad, underwater wonder.',
    'island': 'Underscore for an island dating show with a mystery: light marimba and clean electric-guitar plucks, playful with a hint of suspense.',
    'lena': 'Underscore for a countdown thriller watched through a live feed: minimal high piano ostinato, a thin glassy synth, restrained tension.',
    'mii': 'Underscore for a cozy day with a little cat: playful ukulele, glockenspiel and soft pizzicato, cute and warm.',
    'villa': 'Underscore for a sun-soaked villa love-triangle show: breezy clean guitar and soft electric-piano chords, flirty and relaxed.',
    'dorian': 'Underscore for a mafia dark romance in a port city: sparse high piano with soft noir vibraphone, smoky restrained tension.',
    'hear': 'Underscore for a penthouse second-chance romance where he can hear her thoughts: elegant bright piano and soft pizzicato strings, intimate and a little wistful.',
    'mask': 'Underscore for a masquerade gala mystery: delicate waltz-like celesta and solo violin harmonics, elegant and secretive.',
    'milo': 'Underscore for a road-trip friends-to-lovers comedy: light bouncy acoustic guitar and a soft whistling synth, cheerful and gentle.',
    'reborn': 'Underscore for an isekai fantasy adventure with a mysterious System: bright harp, soft bells and a flute-like pad, wonder and adventure.',
    'hellqueen': 'Underscore for a slice-of-life comedy about co-parenting with the Queen of Hell: playful pizzicato strings and light harpsichord plucks, mischievous and cozy.',
    'crackhigh': 'Underscore for a high-school fight-academy drama: clean muted electric-guitar pulse with soft high synth plucks, youthful determination.',
    'onestat': 'Underscore for a fantasy comedy adventure: whimsical glockenspiel and harp with a light woodwind pad, curious and funny.',
    'mythborne': 'Underscore for a magical academy romance: enchanted celesta and a warm shimmer of strings, wonder and first-day nerves.',
    'heroacad': 'Underscore for a superpower hero-academy story: a hopeful bright piano motif over a soft airy synth pulse, heroic but gentle.',
    'starmate': 'Underscore for a cozy roommate romance with a celebrity: soft bright piano and clean guitar, a quiet apartment evening, tender.',
    'academia': 'Underscore for a superhero academy in New York: uplifting bright piano and light string staccato, youthful and gentle.',
}


def load(path, sr=SR):
    raw = subprocess.run([FF, '-v', 'quiet', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', str(sr), '-'], capture_output=True).stdout
    return np.frombuffer(raw, dtype='<f4').astype(np.float64)


def frames_db(x, hop):
    n = len(x) // hop
    return 20 * np.log10(np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-12)


def voiced(x, sr=SR, gate=-40.0):
    f = frames_db(x, sr // 50); f = f[f > gate]
    return float(10 * np.log10(np.mean(10 ** (f / 10)))) if len(f) else None


def rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12))


def limit(x, knee=0.7, top=0.95):
    """软限幅：|x| 超过 knee 的部分压进 knee–top，不削波"""
    a = np.abs(x); over = a > knee
    if over.any(): x = np.where(over, np.sign(x) * (knee + (top - knee) * np.tanh((a - knee) / (top - knee))), x)
    return x


def save_mp3(x, out, br='96k'):
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FF, '-nostdin', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', '-c:a', 'libmp3lame', '-b:a', br, str(out)],
                   input=x.astype('<f4').tobytes(), check=True)


def waku_audio(model, params, out, timeout=300):
    r = subprocess.run(['waku', 'gen', 'run', model, '--capability', 'multimodal.generate.audio', '--params', json.dumps(params), '--wait', '--timeout', str(timeout), '--out', str(out)],
                       capture_output=True, text=True, timeout=timeout + 60)
    ok = Path(out).exists() and Path(out).stat().st_size > 3000
    if not ok: print('waku failed', model, (r.stdout + r.stderr)[-200:].replace('\n', ' '), flush=True)
    return ok


# ---------------- BGM ----------------
def bgm(sid):
    raw = CACHE / 'bgm' / f'{sid}.raw.mp3'; out = APP / 'bgm' / f'{sid}.mp3'
    raw.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not FORCE: return sid, 'exists'
    if not (raw.exists() and raw.stat().st_size > 100000) or '--regen' in sys.argv:   # --force 只重做循环和均衡，--regen 才重新生成（花额度）
        if not waku_audio('elevenlabs/music-v2', {'prompt': BGM[sid] + ' ' + TAIL, 'music_length_ms': 60000, 'force_instrumental': True, 'output_format': 'mp3_44100_128'}, raw):
            return sid, 'gen failed'
    x = load(raw)
    # 去掉开头的渐入和结尾的收尾，首尾交叉淡化 3 秒做成循环
    a, b, xf = int(1.5 * SR), len(x) - int(2.5 * SR), int(3 * SR)
    x = x[a:b]; body = x[xf:len(x) - xf]; w = np.linspace(0, 1, xf)
    loop = np.concatenate([body, x[len(x) - xf:] * np.sqrt(1 - w) + x[:xf] * np.sqrt(w)])
    # 清亮：切掉 280 Hz 以下（轰和闷都在这），人声主体的 480 Hz 一带让开 5 分贝，2 kHz 以上提 7 分贝；再拉到固定响度
    tmp = CACHE / 'bgm' / f'{sid}.loop.wav'
    subprocess.run([FF, '-nostdin', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', '-af', 'highpass=f=280,highpass=f=280,equalizer=f=480:t=q:w=1.2:g=-5,treble=g=7:f=2000,acompressor=threshold=-30dB:ratio=3:attack=40:release=700', str(tmp)], input=loop.astype('<f4').tobytes(), check=True)   # acompressor：压一下起伏，不会突然冒出一段响的
    y = load(tmp); os.unlink(tmp)
    y = limit(y * 10 ** ((BGM_FILE_DB - rms_db(y)) / 20))
    save_mp3(y, out, '96k')
    lo = np.abs(np.fft.rfft(y[:SR * 20])); fr = np.fft.rfftfreq(SR * 20, 1 / SR)
    return sid, f'{len(y) / SR:.1f}s {out.stat().st_size // 1024} KB', f'频谱重心 {int((fr * lo ** 2).sum() / (lo ** 2).sum())} Hz', f'起伏 {float(np.percentile(frames_db(y, SR // 2), 90) - np.percentile(frames_db(y, SR // 2), 10)):.1f} dB'


# ---------------- 音效 ----------------
def shape_sfx(src, target=SFX_FILE_DB):
    x = load(src)
    act = np.flatnonzero(frames_db(x, 441) > -55)
    if not len(act): return None
    x = x[max(0, act[0] * 441 - 441):min(len(x), (act[-1] + 1) * 441 + 4410)]
    v = voiced(x, gate=-50) or rms_db(x)
    x = x * 10 ** ((target - v) / 20)
    pk = np.max(np.abs(x))
    if pk > 0.6: x *= 0.6 / pk   # 突发的一下（摔门、枪声）峰值封顶，不吓人
    fo = min(len(x) // 3, int(0.25 * SR)); x[-fo:] *= np.linspace(1, 0, fo) ** 2; x[:220] *= np.linspace(0, 1, 220)
    return x


def sfxlib():
    (CACHE / 'sfx').mkdir(parents=True, exist_ok=True)

    def one(k):
        raw = CACHE / 'sfx' / f'{k}.raw.mp3'; out = APP / 'sfx' / f'{k}.mp3'
        if out.exists() and not FORCE: return k, 'exists'
        if not raw.exists() or FORCE:
            if not waku_audio('elevenlabs/sound-effects-v2', {'prompt': SL.LIB[k]['p'] + '. No voices, no music.', 'duration': SL.LIB[k]['d'], 'prompt_influence': 0.6}, raw, 200): return k, 'gen failed'
        x = shape_sfx(raw)
        if x is None: return k, 'silent'
        save_mp3(x, out, '96k'); return k, f'{len(x) / SR:.1f}s'
    with cf.ThreadPoolExecutor(4) as ex:
        for r in ex.map(one, list(SL.LIB)): print(r, flush=True)
    json.dump(sorted(p.stem for p in (APP / 'sfx').glob('*.mp3')), open(APP / 'sfx' / 'index.json', 'w'))


PLAN_SYS = '''你是有声剧的音效设计。下面是同一集的英文稿和中文稿（逐句编号）。请挑 4–7 处最值得加音效的关键时刻：只挑剧情里真的有声音发生、而且对气氛或情节重要的地方（门、脚步、玻璃、雷、心跳、手机、火、水、人群反应、魔法 / 系统提示音、打斗的一下……），不要每句都加，不要给情绪加“音乐感”的东西，不要人声、不要音乐。
每处给：
- "prompt"：英文，给 ElevenLabs 音效模型的描述，写清是什么声音、在什么空间、远近，1 句，≤ 200 字符
- "dur"：秒，1–4（一下的声音 1.5–2，持续的 3–4）
- "en"：英文稿里对应那一句的编号；"zh"：中文稿里对应那一句的编号（两份稿子句数、顺序可能不同，各自找写到这个声音的那一句；某个语言的稿子里没有这个声音就写 -1）
- "at"："before"（声音先响、这句话接着说，适合“门砰地关上。”这类）、"start"（和这句同时开始）、"end"（这句话说完时响，适合句尾才发生的事）
只输出 JSON：{"sfx":[{"prompt":"…","dur":2,"en":3,"zh":4,"at":"before"}, …]}'''


def plan(sid):
    for k in range(3):   # 模型偶尔空回：重试
        try: return _plan(sid)
        except Exception as e: err = repr(e)[:120]
    return sid, 'plan failed', err


def _plan(sid):
    out = ROOT / 'data' / 'sfx' / f'{sid}.json'; out.parent.mkdir(exist_ok=True)
    if out.exists() and not FORCE: return sid, 'exists'
    sys.path.insert(0, '/Users/vicky/Interactive storyline/tools')
    import claude_cli as CC
    S = {l: json.load(open(ROOT / 'data' / 'ep1' / f'{sid}.{l}.json')) for l in ('en', 'zh')}
    txt = lambda l: '\n'.join(f'{i}. [{x["who"]}] {x["text"]}' for i, x in enumerate(S[l]['lines']))
    user = f'环境声（已经铺在整集下面，不用重复）：{S["en"].get("amb")}\n\n【英文稿】\n{txt("en")}\n\n【中文稿】\n{txt("zh")}'
    obj, _, _ = CC.call_json([{'role': 'system', 'content': PLAN_SYS}, {'role': 'user', 'content': user}])
    sfx = []
    for i, x in enumerate((obj or {}).get('sfx') or []):
        if not x.get('prompt'): continue
        en, zh = int(x.get('en', -1)), int(x.get('zh', -1))
        if not (-1 <= en < len(S['en']['lines'])) or not (-1 <= zh < len(S['zh']['lines'])): continue
        sfx.append({'id': f'x{i}', 'prompt': str(x['prompt'])[:400], 'dur': float(min(4, max(1, x.get('dur') or 2))), 'en': en, 'zh': zh, 'at': x.get('at') if x.get('at') in ('before', 'start', 'end') else 'before'})
    json.dump({'sfx': sfx[:7]}, open(out, 'w'), ensure_ascii=False, indent=1)
    return sid, len(sfx), [x['prompt'][:40] for x in sfx]


def gen(sid):
    f = ROOT / 'data' / 'sfx' / f'{sid}.json'
    if not f.exists(): return sid, 'no plan'
    od = CACHE / 'sfx_ep1' / sid; od.mkdir(parents=True, exist_ok=True); res = []
    for x in json.load(open(f))['sfx']:
        raw = od / f'{x["id"]}.mp3'
        if raw.exists() and not FORCE: res.append('exists'); continue
        res.append('ok' if waku_audio('elevenlabs/sound-effects-v2', {'prompt': x['prompt'][:420] + ' No voices, no music.', 'duration': x['dur'], 'prompt_influence': 0.6}, raw, 200) else 'failed')
    return sid, res


# ---------------- 第 1 集重混 ----------------
def tile(x, n):
    return np.tile(x, n // len(x) + 1)[:n]


def seams(levels, who):
    j = [abs(levels[i + 1] - levels[i]) for i in range(len(levels) - 1) if who[i] != who[i + 1] and levels[i] is not None and levels[i + 1] is not None]
    return (round(float(np.median(j)), 1), round(max(j), 1), sum(1 for v in j if v > 4), len(j)) if j else (0, 0, 0, 0)


def mix(sid, lang):
    ej = CACHE / 'ep1' / f'{sid}.{lang}.json'; parts = CACHE / 'ep1' / f'{sid}.{lang}.parts'; mp3 = CACHE / 'ep1' / f'{sid}.{lang}.mp3'
    if not ej.exists() or not parts.exists(): return sid, lang, 'no parts'
    ep = json.load(open(ej)); cues = ep['cues']
    bak = CACHE / 'ep1' / f'{sid}.{lang}.bak-v58.mp3'
    if not bak.exists(): shutil.copy(mp3, bak)
    # 11-13 换过角色配音的集（build_revoice.py）：各句时长变了，总长按新的时间轴（ep['total']），不再取旧成片的长度
    total = int(round(ep['total'] * SR)) if ep.get('total') else int(round(float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(bak)], capture_output=True, text=True).stdout.strip()) * SR))
    y = np.zeros(total); before, after, who = [], [], []
    for i, c in enumerate(cues):
        p = parts / f'{i:03d}.mp3'
        if not p.exists(): return sid, lang, f'missing part {i}'
        x = load(p); v = voiced(x)
        g = 0.0 if v is None else max(-AL.MAX_GAIN, min(AL.MAX_GAIN, AL.TARGET - v))
        x = limit(x * 10 ** (g / 20))
        before.append(v); after.append(voiced(x)); who.append(c['who'])
        a = int(c['s'] * SR); x = x[:max(0, total - a)]; y[a:a + len(x)] += x
    fade = lambda z, fi, fo: z * np.minimum(1, np.minimum(np.arange(len(z)) / (fi * SR), (len(z) - np.arange(len(z))) / (fo * SR)))
    amb = CACHE / 'amb' / f'{sid}.mp3'
    if amb.exists():
        a = load(amb); y += fade(tile(a * 10 ** ((AMB_DB - rms_db(a)) / 20), total), 1.5, 2.0)
    bg = APP / 'bgm' / f'{sid}.mp3'
    if bg.exists():
        b = load(bg); y += fade(tile(b * 10 ** ((BGM_DB - rms_db(b)) / 20), total), 2.5, 3.0)
    used = []
    pf = ROOT / 'data' / 'sfx' / f'{sid}.json'
    for x in (json.load(open(pf))['sfx'] if pf.exists() else []):
        i = x.get(lang, -1); src = CACHE / 'sfx_ep1' / sid / f'{x["id"]}.mp3'
        if i < 0 or i >= len(cues) or not src.exists(): continue
        z = shape_sfx(src, SFX_DB)
        if z is None: continue
        c = cues[i]
        t = c['s'] - min(len(z) / SR * 0.6, 0.9) if x['at'] == 'before' else c['s'] if x['at'] == 'start' else c['e'] - 0.25
        a = max(0, int(t * SR)); z = z[:max(0, total - a)]; y[a:a + len(z)] += z; used.append((x['id'], i, x['at'], round(t, 1)))
    y = limit(y, 0.8, 0.97)
    save_mp3(y, mp3, '96k')
    (APP / 'ep1').mkdir(exist_ok=True); shutil.copy(mp3, APP / 'ep1' / mp3.name)
    return sid, lang, f'{total / SR:.1f}s', '换人处跳变 中位/最大/超4dB/总数：', seams(before, who), '→', seams(after, who), f'音效 {len(used)}', used


if __name__ == '__main__':
    what = sys.argv[1]; ids = [a for a in sys.argv[2:] if a in IDS] or IDS
    langs = [a for a in sys.argv[2:] if a in ('en', 'zh')] or ['en', 'zh']
    if what == 'bgm':
        with cf.ThreadPoolExecutor(3) as ex:
            for r in ex.map(bgm, ids): print(r, flush=True)
    elif what == 'sfxlib': sfxlib()
    elif what == 'plan':
        with cf.ThreadPoolExecutor(4) as ex:
            for r in ex.map(plan, ids): print(r, flush=True)
    elif what == 'gen':
        with cf.ThreadPoolExecutor(4) as ex:
            for r in ex.map(gen, ids): print(r, flush=True)
    elif what == 'mix':
        for sid in ids:
            for l in langs: print(mix(sid, l), flush=True)
