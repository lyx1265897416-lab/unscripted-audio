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
- `logs/sessions/*.jsonl`：每局每集的台词、耗时、音频地址。

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
