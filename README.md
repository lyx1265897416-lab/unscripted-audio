# Unscripted Audio

Pocket FM 式的音频连载 App（2026-11-06 起），内容是我们 7 部实时互动剧的音频版：第 1 集是预制的有声剧，之后每一集按她在集尾的选择实时写、逐句配音。接口约定见 `CONTRACT.md`。

## 目录
- `app/`：前端（纯静态，index.html / style.css / app.js；`?mock=1` 不连服务器也能走完整流程）。covers/、avatars/ 来自即兴剧场 APP。
- `unscripted_audio_server.py`：中转（8913）。名字故意起得独一无二：别的会话会按 `server.py` 之类的通用名批量杀进程。
- `data/series_base.json`：7 部剧的标题、钩子、标签、主色（来自 `projects/realtime-drama-app/catalog.json`）。
- `data/world/<id>.json`：音频版世界卡，`build_world.py` 用 Opus 5.5（本机 Claude Code）从 `projects/realtime-character-packs` 提炼。
- `data/ep1/<id>.<zh|en>.json`：第 1 集剧本，`build_ep1.py` 生成（中文稿不许有英文句子）。
- `data/voices.json`：配音表。全部 ElevenLabs v4；中文用 Eleven 声音库原生中文声（voice_id），英文用预置声。主角台词句首自动加 [quietly]。
- `cache/ep1/`：第 1 集成品（逐句分轨 parts/、拼好的 mp3、字幕 json）。第一次有人播某部剧某语言时生成（40–100 秒），之后直接用 CDN 地址。改了配音表要删对应 parts 和成品再生成。
- `data/motion.json` + `cache/motion/`：播放器动态封面（Pocket FM 式），`build_motion.py` 从即兴剧场 APP 的待机/开场片段剪方形静音循环（正放+倒放），传 CDN；mock 模式用 `app/motion/`。人鱼那部开场没有 Rian 正脸 → 11-06 按定装图出海下长廊关键帧，用 Kling v4 首尾同帧生成 5 秒无缝循环（data/motion_src/）；三真四假用七位男嘉宾合影。
- `data/visuals/<id>.json` + `app/v/<id>/`：播放器剧情画面库（`build_visuals.py`，不花额度）：开场按镜头切开（o*）、实时测试片段（c*，描述=导演层逐镜头 beat + 台词）、剧照缓推（s*）、待机动态（idle）；pool = 没有对应画面时每 7 秒轮播的万能 live/剧照。
- `data/ep1_visuals/<id>.<lang>.json`：第 1 集逐句配画面（`build_ep1_visuals.py`，Opus），中转按字幕时间换成时间轴 `ep.visuals`。实时集：编剧只写台词（11-06 试过让编剧顺手标画面，提示词变长后开播从 ~20 秒拖到 ~30 秒，已撤），每写出一批台词就交给快模型（CLIP_MAPPER，默认 deepseek/deepseek-v4.1-flash，约 4 秒）并行配画面，返回 `line.clip`，通常比那句的声音先到。
- `logs/sessions/*.jsonl`：每局每集的台词、耗时、音频地址。

## perhaps-worlds 的 6 部（2026-11-06 加）
kael（订婚夜，他闻到了我）、villa（今晚十点，谁选你）、dorian（别叫我哥哥）、hear（离婚前，他听见我心声）、mask（午夜前别摘面具）、milo（男闺蜜今晚不对劲），来自私有仓库 balabalabalaja/perhaps-worlds（本机克隆 `external/perhaps-worlds`）。
- `build_pw_world.py`：原世界卡（复制在 `data/pw/<id>.world.json`）→ 音频版世界卡；第 1 集剧本照常 `build_ep1.py`（开场台词取原卡 intro.captions）；画面库 `build_visuals.py` 的 PW 段（开场视频切镜头 + 待机/场景片段 + 场景图缓推）。
- 原卡和改编出的世界卡、第 1 集剧本只留本机（.gitignore），公开仓库只有 App 播放必须的封面、头像、画面片段。

## 公开仓库和长期链接
- 公开仓库 https://github.com/lyx1265897416-lab/unscripted-audio ，Pages 从 `docs/` 发布：https://lyx1265897416-lab.github.io/unscripted-audio/ （第一次打开带 `?k=<token>&lang=zh|en`，口令存在本机后地址栏会去掉；口令不进仓库）。
- `docs/` 是 `app/` 的副本：改完前端跑 `./publish.sh "说明"`（rsync app/→docs/ 再推）。`docs/relay.json` 不覆盖，由 `relay_sync.py` 管。
- `relay_sync.py`（launchd `com.vicky.realtime.unscripted-audio-sync`，日志 logs/sync.log）：每分钟探隧道，地址变了就写 `docs/relay.json` 并推送；连续 3 次连不上就重启隧道。前端读 relay.json 找中转，所以 Pages 链接长期不变。

## 运行
- launchd：`com.vicky.realtime.unscripted-audio`（中转）、`com.vicky.realtime.unscripted-audio-tunnel`（公网隧道），入口在 `tools/realtime-relays/run.sh`。重启用 `launchctl kickstart -k gui/$(id -u)/com.vicky.realtime.unscripted-audio`。
- 公网地址：`logs/tunnel-public.log` 最后一条 trycloudflare 地址 + `/?k=<token.txt>&lang=zh`（或 en）。隧道重启地址会变。
- 编剧：DIRECTOR_CLI=claude-opus-5-5 走本机 Claude Code（续集第一句约 6–8 秒写出），失败退回 OpenRouter GLM-5.3-prime。

## 成本（Waku credits）
Eleven v4 每句 15、环境声 40、上传 4。第 1 集约 35 句 ≈ 560；实时续集每集 12–13 句（第一句三发、第二句双发）≈ 240。

## 实时集提速（2026-11-06）
- 选项预先生成：每集一开播（非 prewarm 的 `/api/play` 和每集写完后），按集尾两个选项各起一个 Opus 续集 job，只先配前 4 句；她点选项时 `/api/next` 直接返回对应 job，第 1 句 0 秒开播，剩下的句子边播边配。没被选中的那条丢弃（约 60 credits）。前端在一集最后约 45 秒取 `/api/specs`、缓存前 4 句音频，点选项时本地直接开播，同时后台调 `/api/next` 确认（省掉公网隧道 1.3–2.5 秒一次的往返）。
- 自由输入（打字/说话）：改用快模型 `EP_FAST_MODEL`（默认 z-ai/glm-5.3-prime，reasoning effort low，第一句约 3–5 秒），实测开播 11–12 秒（原 ~20 秒），主要剩配音时间。
- 中英文第 1 集 13 部全部预制好（cache/ep1），9 个新主角的中文垫场声/思考声也已预生成。
- 真正的流式 TTS（Waku `pv.speech.stream`）只能在 Waku playable 里由用户手势触发、计费给玩家，中转端用不了；没有 ElevenLabs 直连 key，所以服务器端仍是逐句合成 + 并行配音。
