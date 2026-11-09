"""Unscripted Audio 的本机语音识别（launchd：com.vicky.realtime.unscripted-audio-asr，127.0.0.1:8917）。
中英文都能说：faster-whisper 多语种模型自动判断语言（中文版里说英文、英文版里说中文都行），输出原话；编剧再用本集语言接着演。
不花额度（waku transcribe 每次 252 credits）。中转 /api/asr 把手机录的 5 秒左右音频（webm/opus 或 mp4/aac）转到这里。
用 asr-env 的 Python 跑：~/Documents/waku内容/off-script/tools/asr-env/bin/python unscripted_asr.py
"""
import glob, json, os, re, sys, tempfile, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from faster_whisper import WhisperModel

PORT = int(os.environ.get('ASR_PORT', '8917'))
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
    r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=prompt, condition_on_previous_text=False, temperature=0.0)
    lang = r.get('language') or ''
    if lang not in ('zh', 'en'):
        lang = hint if hint in ('zh', 'en') else 'zh'
        r = MLX.transcribe(path, path_or_hf_repo=MLX_REPO, initial_prompt=prompt, condition_on_previous_text=False, temperature=0.0, language=lang)
    segs = [x for x in (r.get('segments') or []) if x.get('no_speech_prob', 0) < 0.7]
    text = ''.join(x.get('text', '') for x in segs).strip()
    if ctx and text and text.strip('。，, ') and text.strip('。，, ') in ctx: text = ''   # the model just echoed the hint back
    return text, lang


def transcribe(path, hint, ctx=''):
    with LOCK:
        t = time.time()
        if MLX:
            try:
                text, lang = transcribe_mlx(path, hint, ctx)
                if JUNK.search(text): text = ''
                return {'text': text, 'lang': lang, 'prob': 1.0, 'ms': int((time.time() - t) * 1000), 'engine': 'mlx'}
            except Exception as e:
                print('mlx failed', repr(e)[:160], flush=True)
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


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(200, {'ok': True, 'model': ('mlx:' + MLX_REPO) if MLX else os.path.basename(os.path.dirname(os.path.dirname(MODEL_PATH)))})

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
        try:
            r = transcribe(p, hint, ctx)
        except Exception as e:
            r = {'text': '', 'error': repr(e)[:200]}
        finally:
            os.unlink(p)
        print(time.strftime('%m-%d %H:%M:%S'), len(data), r, flush=True)
        self._send(200, r)


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
