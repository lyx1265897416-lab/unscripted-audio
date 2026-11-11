"""Unscripted Audio 的本机语音识别（launchd：com.vicky.realtime.unscripted-audio-asr，127.0.0.1:8917）。
中英文都能说：faster-whisper 多语种模型自动判断语言（中文版里说英文、英文版里说中文都行），输出原话；编剧再用本集语言接着演。
不花额度（waku transcribe 每次 252 credits）。中转 /api/asr 把手机录的 5 秒左右音频（webm/opus 或 mp4/aac）转到这里。
用 asr-env 的 Python 跑：~/Documents/waku内容/off-script/tools/asr-env/bin/python unscripted_asr.py
"""
import glob, json, os, re, sys, tempfile, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from faster_whisper import WhisperModel

PORT = int(os.environ.get('ASR_PORT', '8917'))
# mlx_whisper decodes audio by running `ffmpeg`; launchd's PATH has none → use the project's ffmpeg (11-09)
_FFDIR = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin'
if os.path.exists(os.path.join(_FFDIR, 'ffmpeg')) and _FFDIR not in os.environ.get('PATH', ''):
    os.environ['PATH'] = _FFDIR + os.pathsep + os.environ.get('PATH', '')
HUB = os.path.expanduser('~/.cache/huggingface/hub')


def pick_model():
    """large-v3-turbo 下好了就用它（中文更准），否则 small（多语种）"""
    for name in ('mobiuslabsgmbh--faster-whisper-large-v3-turbo', 'Systran--faster-whisper-small'):
        for snap in glob.glob(f'{HUB}/models--{name}/snapshots/*'):
            if os.path.exists(os.path.join(snap, 'model.bin')):
                return snap
    raise SystemExit('no multilingual faster-whisper model in ' + HUB)


MODEL_PATH = pick_model()
MODEL = WhisperModel(MODEL_PATH, device='cpu', compute_type='int8', cpu_threads=4)
LOCK = threading.Lock()
# 11-09：Apple 芯片上优先用 MLX 版 whisper-large-v3-turbo（GPU，比 small 准得多，也快）；没装好就用 faster-whisper small
MLX_REPO = os.environ.get('MLX_WHISPER', os.path.expanduser('~/.local/mlx-whisper-turbo'))  # config.json + weights.safetensors（curl 断点下载，HF 客户端走代理会卡住）
MLX = None
try:
    import mlx_whisper
    if os.path.exists(os.path.join(MLX_REPO, 'weights.safetensors')) and os.path.getsize(os.path.join(MLX_REPO, 'weights.safetensors')) > 1_000_000_000:
        MLX = mlx_whisper
except Exception as e:
    print('mlx unavailable', repr(e)[:120], flush=True)
print(time.strftime('%m-%d %H:%M:%S'), 'asr ready', 'mlx ' + MLX_REPO if MLX else MODEL_PATH, flush=True)

# whisper 在静音/噪声上常见的幻觉
JUNK = re.compile(r'(谢谢观看|感谢观看|字幕由|请不吝点赞|订阅|明镜|thank(s| you) for watching|subtitles by|please subscribe|^\W*$)', re.I)
PROMPT = '以下是简体中文或英文的句子。'


def transcribe_mlx(path, hint, ctx):
    prompt = PROMPT + (ctx or '')
    if hint == 'en':  # 11-09 已知是英文：跳过语言检测、不带中文提示词（英文从 2.1 秒降下来）
        r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=(ctx or None), condition_on_previous_text=False, temperature=0.0, language='en')
        segs = [x for x in (r.get('segments') or []) if x.get('no_speech_prob', 0) < 0.7]
        return ''.join(x.get('text', '') for x in segs).strip(), 'en'
    r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=prompt, condition_on_previous_text=False, temperature=0.0)
    lang = r.get('language') or ''
    if lang not in ('zh', 'en'):
        lang = hint if hint in ('zh', 'en') else 'zh'
        r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=prompt, condition_on_previous_text=False, temperature=0.0, language=lang)
    segs = [x for x in (r.get('segments') or []) if x.get('no_speech_prob', 0) < 0.7]
    text = ''.join(x.get('text', '') for x in segs).strip()
    if ctx and text and text.strip('。，, ') and text.strip('。，, ') in ctx: text = ''   # the model just echoed the hint back
    return text, lang


# 11-09：SenseVoice（sherpa-onnx int8，CPU 上十分之一秒级，中文明显更准）放最前；没有就 MLX turbo；再没有 faster-whisper small
SV = SVZH = None
try:
    import sherpa_onnx
    _m = sorted(glob.glob(os.path.expanduser('~/.local/sensevoice/sherpa-onnx-sense-voice-*/model.int8.onnx')))
    if _m:
        SV = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=_m[-1], tokens=os.path.join(os.path.dirname(_m[-1]), 'tokens.txt'), num_threads=4, use_itn=True, language='auto')
        # 11-10：自动判语言时普通话常被判成粤语（“先里经嘅试到咗…”），判成粤/日/韩就用固定普通话的再认一遍
        SVZH = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=_m[-1], tokens=os.path.join(os.path.dirname(_m[-1]), 'tokens.txt'), num_threads=4, use_itn=True, language='zh')
        print('sensevoice ready', _m[-1], flush=True)
except Exception as e:
    print('sensevoice unavailable', repr(e)[:160], flush=True)


PK = None  # 11-09 英文：NVIDIA Parakeet-TDT 0.6B v2（sherpa-onnx int8），约 0.2 秒，准确率和 Whisper large-v3-turbo 相当（Whisper 要 2 秒）
try:
    _pd = sorted(glob.glob(os.path.expanduser('~/.local/parakeet/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8')))
    if _pd and os.path.exists(os.path.join(_pd[-1], 'encoder.int8.onnx')):
        _d = _pd[-1]
        PK = sherpa_onnx.OfflineRecognizer.from_transducer(encoder=os.path.join(_d, 'encoder.int8.onnx'), decoder=os.path.join(_d, 'decoder.int8.onnx'),
                                                           joiner=os.path.join(_d, 'joiner.int8.onnx'), tokens=os.path.join(_d, 'tokens.txt'),
                                                           num_threads=4, model_type='nemo_transducer')
        import numpy as _np
        _st = PK.create_stream(); _st.accept_waveform(16000, _np.zeros(16000, dtype=_np.float32)); PK.decode_stream(_st)  # 预热：首句不再 1.2 秒
        print('parakeet ready', _d, flush=True)
except Exception as e:
    print('parakeet unavailable', repr(e)[:160], flush=True)


def _pcm16k(path):
    import numpy as np, subprocess
    pcm = subprocess.run([os.path.join(_FFDIR, 'ffmpeg'), '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, timeout=20).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0



# 11-10 她说：别录进杂音/旁边其他人的声音。Silero 人声检测找出有人声的地方，再按 20 ms 帧的响度只留“离手机最近的那个人”：
# 比她说话最响时（人声帧响度的 95 分位）小 16 dB 以上的帧静音掉（远处别人说话、电视、杂音）；整体最响都低于 -40 dBFS 就当没说话。
GATE_REL, GATE_ABS = float(os.environ.get('GATE_REL', '16')), float(os.environ.get('GATE_ABS', '-40'))
try:
    from faster_whisper.vad import get_speech_timestamps, VadOptions
except Exception as e:
    get_speech_timestamps = None; print('vad unavailable', repr(e)[:120], flush=True)


def foreground(x):
    """x: 16 kHz float32 → (只留前景人声的音频 or None, 说明)"""
    import numpy as np
    if get_speech_timestamps is None or x.size < 3200: return x, 'skip'
    ts = get_speech_timestamps(x, VadOptions(threshold=0.45, min_speech_duration_ms=180, min_silence_duration_ms=250, speech_pad_ms=120))
    if not ts: return None, 'no speech'
    F = 320; n = len(x) // F
    if n < 5: return x, 'short'
    e = 20 * np.log10(np.sqrt((x[: n * F].reshape(n, F) ** 2).mean(axis=1)) + 1e-9)
    voiced = np.zeros(n, bool)
    for t in ts: voiced[t['start'] // F: min(n, t['end'] // F + 1)] = True
    if not voiced.any(): return None, 'no speech'
    loud = float(np.percentile(e[voiced], 95))
    if loud < GATE_ABS: return None, f'too quiet {loud:.0f}dB'
    keep = voiced & (e >= loud - GATE_REL)
    k = np.convolve(keep.astype(float), np.ones(17), 'same') > 0   # 前后各留 160 ms，别把字头字尾切掉
    keep = k & voiced
    if keep.sum() * F < 0.25 * 16000: return None, f'fg too short ({keep.sum() * 20} ms)'
    g = np.repeat(keep.astype(np.float32), F)
    g = np.convolve(g, np.ones(160, dtype=np.float32) / 160, 'same')   # 10 ms 淡入淡出，不出咔哒声
    y = x[: n * F] * g
    return y, f'kept {int(keep.sum()) * 20}/{int(voiced.sum()) * 20} ms voiced, loud {loud:.0f}dB'


def gate_file(path):
    """转成 16k 单声道、只留前景人声，写回一个 wav；没有人声返回 None"""
    import numpy as np, wave
    x = _pcm16k(path)
    y, why = foreground(x)
    if y is None: return None, why
    out = path + '.fg.wav'
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return out, why


import threading as _th
_PKL = _th.Lock()


def transcribe_pk(x):
    with _PKL:
        st = PK.create_stream(); st.accept_waveform(16000, x); PK.decode_stream(st)
    return (st.result.text or '').strip()


def transcribe_sv(path, hint=''):
    import numpy as np, subprocess
    pcm = subprocess.run([os.path.join(_FFDIR, 'ffmpeg'), '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, timeout=20).stdout
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size < 1600: return '', ''
    st = SV.create_stream(); st.accept_waveform(16000, x); SV.decode_stream(st)
    r = st.result
    lang = (getattr(r, 'lang', '') or '').strip('<|>')
    text = (r.text or '').strip()
    if SVZH and lang in ('yue', 'ja', 'ko') and hint != 'en' and len(re.sub(r'\W', '', text)) >= 3:  # 11-11：“嗯”重认成了“不”——两个字以内的语气词不重认
        st = SVZH.create_stream(); st.accept_waveform(16000, x); SVZH.decode_stream(st)
        print('sv relang', lang, repr(text[:30]), '->', repr((st.result.text or '')[:30]), flush=True)
        text, lang = (st.result.text or '').strip(), 'zh'
    return text, ('zh' if lang in ('zh', 'yue') else 'en' if lang == 'en' else lang)


# MLX keeps its GPU state per thread: run every MLX call on ONE worker thread (a new HTTP thread each time cost ~2 s extra)
import queue as _q
MLXQ = _q.Queue()
def _mlx_worker():
    while True:
        fn, box, ev = MLXQ.get()
        try: box['r'] = fn()
        except Exception as e: box['e'] = e
        ev.set()
threading.Thread(target=_mlx_worker, daemon=True).start()
def on_mlx(fn, wait=60):
    box, ev = {}, threading.Event(); MLXQ.put((fn, box, ev))
    if not ev.wait(wait): raise TimeoutError('mlx slow')
    if 'e' in box: raise box['e']
    return box.get('r')


LETTER_PROMPT = {'zh': '选A。选B。第一个，第二个。', 'en': 'A. B. Option A. Option B.'}


def short_answer(text):
    z = re.sub(r'[\s，。！？、,.!?~…"\'：:]+', '', text or '')
    return len(z) <= 6 if re.search(r'[\u4e00-\u9fff]', z) else len((text or '').split()) <= 3


def letter_pass(path, lang):
    """选择点上的短回答（A / 选B / Option A）：SenseVoice、Parakeet 常把单念的字母听成“选地”“Yeah”，MLX 带字母提示约 0.9 秒全对（11-09 实测）"""
    r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=LETTER_PROMPT.get(lang, LETTER_PROMPT['en']), condition_on_previous_text=False,
                       temperature=0.0, language=('zh' if lang == 'zh' else 'en'))
    segs = [x for x in (r.get('segments') or []) if x.get('no_speech_prob', 0) < 0.6]
    return ''.join(x.get('text', '') for x in segs).strip()


LETTERISH = re.compile(r'(^|[^a-z])[ab]([^a-z]|$)|第[一二]|选项|^(我|那)?(就|还是|要)?(选|挑|上|宣|旋|悬|学)(诶|欸|哎|唉|地|比|必|逼|币|笔|臂|壁|毕|闭|鼻|避|碧|彼)[吧八呀啊了。.!！]*$', re.I)


_MLX_SLOW = [0.0]  # 上次 MLX 超时的时间：之后 90 秒内不再等它（11-11 “Okay, your way.” 等 MLX 3 秒超时，识别拖到 5.4 秒）


def tiny_answer(text):
    """真正可能是“单念字母”的回答：中文 ≤3 个字、英文 ≤2 个词（“Okay, your way.” 这种完整短句不用再认）"""
    z = re.sub(r'[\s，。！？、,.!?~…"\'：:]+', '', text or '')
    return len(z) <= 3 if re.search(r'[\u4e00-\u9fff]', z) else len(re.findall(r"[A-Za-z']+", text or '')) <= 2


def transcribe(path, hint, ctx='', fast=False, choice=False):
    r = _transcribe(path, hint, ctx, fast)
    txt0 = (r.get('text') or '').strip()
    # 已经像字母回答（含“选地/选臂/上臂”这类同音字，中转按同音字认）就不再等 MLX（11-09 MLX 偶尔 2–4 秒，锁屏时拖到超时）
    if (choice and MLX and txt0 and tiny_answer(txt0) and not LETTERISH.search(txt0.lower())
            and time.time() - _MLX_SLOW[0] > 90 and MLXQ.qsize() == 0):  # MLX 忙或刚超时过：不等它
        t = time.time()
        try:
            txt = on_mlx(lambda: letter_pass(path, r.get('lang') or hint or 'en'), 1.0)
            if txt and not JUNK.search(txt) and short_answer(txt):
                r = dict(r, text=txt, engine=r.get('engine', '') + '+letter', fast_text=r.get('text'), ms=r.get('ms', 0) + int((time.time() - t) * 1000))
        except Exception as e:
            if isinstance(e, TimeoutError): _MLX_SLOW[0] = time.time()
            print('letter pass failed', repr(e)[:120], flush=True)
    return r


def _transcribe(path, hint, ctx='', fast=False):
    with LOCK:
        t = time.time(); sv = None
        if SV:
            try:
                text, lang = transcribe_sv(path, hint)
                letters = re.sub(r'[^A-Za-z\u4e00-\u9fff]', '', text)
                english = bool(letters) and sum(1 for ch in letters if ch.isascii()) / len(letters) > 0.6
                if not english:   # Chinese (or nothing): SenseVoice is the more accurate one and ~0.15 s
                    if JUNK.search(text): text = ''
                    return {'text': text, 'lang': 'zh' if text else (hint or 'zh'), 'prob': 1.0, 'ms': int((time.time() - t) * 1000), 'engine': 'sensevoice'}
                hint = 'en'   # English: Whisper below is better at English (and keeps normal casing/punctuation)
                sv = text
                if PK:
                    try:
                        text = transcribe_pk(_pcm16k(path))
                        if JUNK.search(text): text = ''
                        return {'text': text, 'lang': 'en', 'prob': 1.0, 'ms': int((time.time() - t) * 1000), 'engine': 'parakeet'}
                    except Exception as e: print('parakeet failed', repr(e)[:160], flush=True)
            except Exception as e:
                print('sensevoice failed', repr(e)[:160], flush=True)
        if MLX:
            try:
                text, lang = on_mlx(lambda: transcribe_mlx(path, hint, ctx), 2.5 if fast and sv else 60)  # 通话里（X-Fast）英文最多等 2.5 秒
                if JUNK.search(text): text = ''
                return {'text': text, 'lang': lang, 'prob': 1.0, 'ms': int((time.time() - t) * 1000), 'engine': 'mlx'}
            except Exception as e:
                print('mlx failed', repr(e)[:160], flush=True)
                if sv: return {'text': sv, 'lang': 'en', 'prob': 1.0, 'ms': int((time.time() - t) * 1000), 'engine': 'sensevoice-en'}
        kw = dict(beam_size=1, vad_filter=True, vad_parameters={'min_silence_duration_ms': 400}, condition_on_previous_text=False, without_timestamps=True)
        segs, info = MODEL.transcribe(path, initial_prompt=PROMPT + (ctx or ''), **kw)  # 一遍：自动判断中/英，提示让中文出简体（11-08 实测约 1.8 秒）
        segs = list(segs)
        lang = info.language
        if lang not in ('zh', 'en'):  # 太短判错语言：按本集语言重来
            lang = hint if hint in ('zh', 'en') else 'zh'
            segs, info = MODEL.transcribe(path, language=lang, initial_prompt=PROMPT + (ctx or ''), **kw)
            segs = list(segs)
        text = ''.join(s.text for s in segs if s.no_speech_prob < 0.7).strip()
        if JUNK.search(text): text = ''
        if ctx and text and text.strip('。，, ') in ctx: text = ''   # silence → the model repeating the hint
        return {'text': text, 'lang': lang, 'prob': round(info.language_probability, 2), 'ms': int((time.time() - t) * 1000)}


SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'asr_samples')  # 最近 80 段录音（只在本机，调识别用）


def keep_sample(path, data, r):
    try:
        os.makedirs(SAMPLES, exist_ok=True)
        k = time.strftime('%m%d-%H%M%S') + '-' + str(int(time.time() * 1000) % 1000)
        open(os.path.join(SAMPLES, k + os.path.splitext(path)[1]), 'wb').write(data)
        json.dump(r, open(os.path.join(SAMPLES, k + '.json'), 'w'), ensure_ascii=False)
        fs = sorted(glob.glob(os.path.join(SAMPLES, '*')))
        for f in fs[:-160]: os.unlink(f)
    except Exception: pass


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(200, {'ok': True, 'model': 'sensevoice' if SV else ('mlx:' + MLX_REPO) if MLX else os.path.basename(os.path.dirname(os.path.dirname(MODEL_PATH)))})

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > 8_000_000: return self._send(400, {'error': 'bad size'})
        data = self.rfile.read(n)
        hint = (self.headers.get('X-Lang') or '').strip()
        from urllib.parse import unquote
        ctx = unquote(self.headers.get('X-Hint') or '').strip()
        ct = self.headers.get('Content-Type') or ''
        ext = '.mp4' if 'mp4' in ct else '.wav' if 'wav' in ct else '.mp3' if 'mpeg' in ct else '.webm'
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(data); p = f.name
        g = None
        try:
            t0 = time.time()
            try: g, why = gate_file(p)
            except Exception as e: g, why = p, 'gate error ' + repr(e)[:80]
            if g is None:
                r = {'text': '', 'lang': hint or 'zh', 'gate': why, 'ms': int((time.time() - t0) * 1000)}
            else:
                r = transcribe(g, hint, ctx, fast=self.headers.get('X-Fast') == '1', choice=self.headers.get('X-Choice') == '1')
                r['gate'] = why; r['ms'] = int((time.time() - t0) * 1000)
            if self.headers.get('X-Partial') != '1': keep_sample(p, data, r)   # 边说边认的中间结果不留样本
        except Exception as e:
            r = {'text': '', 'error': repr(e)[:200]}
        finally:
            os.unlink(p)
            if g and g != p and os.path.exists(g): os.unlink(g)
        print(time.strftime('%m-%d %H:%M:%S'), len(data), r, flush=True)
        self._send(200, r)


if __name__ == '__main__':
    if MLX:
        try:
            import numpy as np
            on_mlx(lambda: MLX.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=MLX_REPO, language='zh'))
            print(time.strftime('%m-%d %H:%M:%S'), 'mlx warmed', flush=True)
        except Exception as e: print('mlx warm-up failed', repr(e)[:120], flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
