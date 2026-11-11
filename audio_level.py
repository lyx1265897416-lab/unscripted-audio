"""音量拉齐（11-11 她要求：角色音和旁白音的分贝要一致，不要突然一大一小）。
量法照阿炫《多角色语音故事》第 6 节：只算高于 -40 dBFS 的 20 毫秒帧的平均响度（停顿和尾音衰减不算）。
每一句配音都拉到同一个目标（TARGET），第 1 集（build_audio.py mix）和实时写的每一句（中转 cache_line）用同一个数，
所以旁白 / 各角色 / 第 1 集和后面几集之间都不会忽大忽小。只用标准库 + ffmpeg（中转也在用，不依赖 numpy）。"""
import array, math, os, subprocess

FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
TARGET = -19.0      # 每句配音的有声帧响度（dBFS）
MAX_GAIN = 16.0     # 单句最多提 / 压这么多（中文主角句带 [quietly]，有的比旁白小 12–17 分贝）
SR = 16000


def pcm16(path):
    raw = subprocess.run([FF, '-v', 'quiet', '-i', str(path), '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'], capture_output=True, timeout=60).stdout
    a = array.array('h'); a.frombytes(raw[:len(raw) // 2 * 2])
    return a


def voiced_db(a, gate=-40.0):
    """a: 16 kHz s16 采样。返回 (有声帧平均响度 dBFS, 峰值 dBFS)；没有有声帧返回 (None, 峰值)"""
    hop = SR // 50; thr = (10 ** (gate / 10)) * 32768.0 ** 2; tot = 0.0; n = 0; peak = 1
    for i in range(0, len(a) - hop + 1, hop):
        fr = a[i:i + hop]; ms = sum(x * x for x in fr) / hop
        if ms > thr: tot += ms; n += 1
        m = max(max(fr), -min(fr))
        if m > peak: peak = m
    pk = 20 * math.log10(peak / 32768.0)
    return (10 * math.log10(tot / n / 32768.0 ** 2) if n else None), pk


def gain_for(path, target=TARGET, max_gain=MAX_GAIN):
    v, pk = voiced_db(pcm16(path))
    if v is None: return 0.0, v, pk
    return max(-max_gain, min(max_gain, target - v)), v, pk


def level_file(path, target=TARGET, max_gain=MAX_GAIN, bitrate='128k'):
    """把一句配音就地拉到目标响度（差不到 0.75 dB 就不动）。返回加的增益（dB）。峰值顶到 -1 dBFS 以上时过一道限幅，不削波。"""
    path = str(path)
    g, v, pk = gain_for(path, target, max_gain)
    if abs(g) < 0.75: return 0.0
    af = f'volume={g:.2f}dB' + (',alimiter=limit=0.89:attack=2:release=40:level=disabled' if pk + g > -1.0 else '')
    tmp = path + '.lv'
    r = subprocess.run([FF, '-v', 'error', '-y', '-i', path, '-af', af, '-c:a', 'libmp3lame', '-b:a', bitrate, '-f', 'mp3', tmp], capture_output=True, timeout=60)
    if r.returncode or not os.path.exists(tmp) or os.path.getsize(tmp) < 500:
        try: os.unlink(tmp)
        except OSError: pass
        return 0.0
    os.replace(tmp, path)
    return g
