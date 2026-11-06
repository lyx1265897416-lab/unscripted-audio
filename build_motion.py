"""播放器动态封面（Pocket FM 式）：各剧开场/待机片段剪成方形、静音、正放+倒放首尾相接的循环短片，传 CDN，写进 data/motion.json"""
import json, os, subprocess, base64, sys
sys.path.insert(0, '.')
from wakumcp import WakuMCP
FF = '/Users/vicky/Interactive storyline/.media-runtime/vivix-bin/ffmpeg'
D = '/Users/vicky/Interactive storyline/projects/realtime-drama-app/docs/'
SRC = {  # 源片, 起, 止, 方形裁切的 y（源片 540 宽）
 'magnus': ('live/magnus-open-idle.mp4', 0, None, 0),
 'rafael': ('live/rafael-third-idle.mp4', 0, None, 40),
 'rowan': ('live/meet-third-idle.mp4', 0, None, 20),
 # 'rian'：开场没有 Rian 正脸镜头 → 11-06 改用 data/motion_src/rian-kling-v4.mp4（nano-banana-pro 按定装图出海下长廊关键帧 rian-key.jpg，Kling v4 首尾同帧做 5 秒无缝循环），不再从这里剪
 'island': ('openings/island-liars.mp4', 7.7, 10.3, 200), # 七位男嘉宾合影
 'lena': ('live/dont-trust-idle.mp4', 0, None, 180),
 'mii': ('live/mii-open-idle.mp4', 0, None, 110),
}
m = WakuMCP(); out = json.load(open('data/motion.json')) if os.path.exists('data/motion.json') else {}  # 保留不在 SRC 里的（rian 用 Kling 生成）
for sid, (src, a, b, y) in SRC.items():
    if len(sys.argv) > 1 and sid not in sys.argv[1:]: continue
    f = f'cache/motion/{sid}.mp4'
    trim = ['-ss', str(a)] + (['-to', str(b)] if b else [])
    subprocess.run([FF, '-v', 'error', '-y', *trim, '-i', D + src, '-an', '-filter_complex',
                    f'[0:v]crop=540:540:0:{y},scale=480:480,fps=24,setsar=1,split[f][r0];[r0]reverse[r];[f][r]concat=n=2:v=1:a=0,format=yuv420p[o]',
                    '-map', '[o]', '-c:v', 'libx264', '-crf', '27', '-preset', 'slow', '-movflags', '+faststart', f], check=True)
    r = m.tool('polyverse_upload_local_asset', {'filename': f'motion-{sid}.mp4', 'content_type': 'video/mp4', 'data_base64': base64.b64encode(open(f, 'rb').read()).decode(), 'asset_kind': 'video'}, timeout=180)
    out[sid] = r.get('public_url') or r.get('asset_url'); print(sid, out[sid], flush=True)
json.dump(out, open('data/motion.json', 'w'), indent=1)
