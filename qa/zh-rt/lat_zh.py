import json, subprocess, time, sys, concurrent.futures as cf
T = "你倒是会挑时候。上车，路上我把一切都告诉你……别回头看。"
J = {
 'eleven-v4': ('elevenlabs/eleven-v4', dict(text='[quietly] ' + T, voice_id='MQkiCZS3mnl44caDtxkJ', stability=0.4, similarity=0.8)),
 'eleven-v4-turbo': ('elevenlabs/eleven-v4-turbo', dict(text=T, voice_id='MQkiCZS3mnl44caDtxkJ', stability=0.4, similarity=0.8)),
 'eleven-turbo-v2.5': ('elevenlabs/turbo-v2.5', dict(text=T, voice_id='MQkiCZS3mnl44caDtxkJ')),
 'seed-tts-2': ('bytedance/seed-speech-tts-2.0', dict(text=T, voice='magnus_en_zh', language='zh', voice_instruction='低沉克制的成年男声，压低嗓音，靠近说话，带一点疲惫和保护欲')),
 'inworld-rt2': ('inworld/realtime-tts-2', dict(text=T, voice_id='Yichen')),
 'qwen3-flash': ('alibaba/qwen3-tts-flash', dict(text=T, voice='Ethan', language='Chinese')),
}
def run(k, tag):
    m, p = J[k]; t = time.monotonic()
    r = subprocess.run(['waku','gen','run',m,'--capability','multimodal.generate.audio','--params',json.dumps(p, ensure_ascii=False),'--out',f'{k}{tag}.mp3','--timeout','120','--poll-interval','0.3'],capture_output=True,text=True)
    return k + tag, round(time.monotonic()-t,1), r.returncode, (r.stdout+r.stderr)[-300:].replace('\n',' ') if r.returncode else ''
if __name__ == "__main__":
  with cf.ThreadPoolExecutor(12) as ex:
      futs = [ex.submit(run, k, t) for t in ('', '_2') for k in J]
      for f in futs: print(*f.result(), flush=True)
