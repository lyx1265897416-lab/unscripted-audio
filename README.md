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

## 收听模式：闭眼听也能参与（2026-11-06，按和阿炫的音频讨论）
讨论结论：现有“听一段 → 回应 → 生成下一段”保留，问题是每段都要拿起手机。区分两种语音：**对故事说话**（影响下一段怎么讲）和**给角色打电话**（另一条链路）。主动参与和被动收听要能共存；不互动就自动往下。
- 三种模式（播放器标题下的模式条、选择面板底部、个人页都能切；`S.mode`，支持语音识别的浏览器默认 Hands-free）：
  - **Hands-free（voice）**：集尾旁白把选择点念出来（`/api/cue`，快模型把 PROMPT+两个选项改写成贴耳的一句问话，旁白声配音；第 1 集按剧/语言存 cache/cue，实时集存会话；前端在集尾前约 45 秒预取）→ 提示音 → 自动开麦（Web Speech，约 12 秒）→ 她说的话直接提交；没出声 5 秒后（第二次 3 秒）故事自己往下走；麦克风被拒 12 秒后往下走。
  - **Lean back（auto）**：不提问，集尾 5 秒倒数后自动下一集（睡前/被动收听）。
  - **Tap to choose（tap）**：原来的选择面板，30 秒没操作也自动往下；只有这个模式集尾会来电。
- **自动往下（via=auto）**：服务器用预先写好的第一个选项那集（秒开）；没有预写就按“她只是闭眼在听、按角色意志推进一步”现写。
- **语音回答匹配选项**：`/api/next` 收到 voice/free 时，快模型（deepseek-v4.1-flash，约 1.3 秒）判断她的话是不是就是 C1/C2 的意思（没加新要求）→ 用预先写好的那集，实测 2.7 秒开播（原来现写 11–21 秒）；“你决定/继续/随便” → auto。
- **对故事说话（Talk）**：播放器 Talk 按钮，任何时候说一句想让剧情怎么走 → `/api/wish`，服务器记进 `sess.wishes` 并按它重写两个选项的下一集（仍然秒开），下一集提示词里明确要接住。面板里注明“想跟他本人说话是打电话”。
- **个性化（Your story self）**：个人页写“想成为的人、想要的生活、想被怎样对待”（参考 Manifest 类产品），随 `/api/play`、`/api/call/start` 的 `me` 进编剧和通话提示词（`me_block`：是心愿不是事实，慢慢回应，不生硬复述）。从第 2 集和通话开始生效。
- 等待时：WebAudio 低音量氛围铺底（bedStart/bedStop）+ 提示音（earcon），不花额度。
- 耳机/锁屏按键：选择点上“下一首”= 开麦回答（页面在后台时 = 让故事往下走），“上一首”= 重听问题。
- 限制：网页里的语音识别要页面在前台；锁屏/后台时只能靠自动往下。内置浏览器面板拦麦克风，真机测语音要用手机 Safari/Chrome。

## 第 1 集和首页秒开（2026-11-08）
- 快速隧道每次往返 2–7 秒，所以第 1 集不再等 `/api/play`：剧集列表的 `ep1.audio` 带上预制音频地址，点播放先直接放（本机有缓存的完整第 1 集 `ua.ep1.<id>.<lang>` 就连字幕一起），`/api/play` 回来后把会话、字幕、选项、画面时间轴合进同一个对象，不重载音频；需要会话的操作（插话、选完下一集）用 `sidReady()` 等它。
- 存储首字节约 3 秒：打开剧集详情就预取第 1 集音频（`warmEp1`，最多留 2 个），并预连接 storage.googleapis.com。实测详情页停几秒再点播放，0.13 秒出声。
- 剧集列表存本机（`ua.series.<lang>`），下次打开先用缓存渲染、后台刷新；实测首页 2.2 秒出来（原 7–14 秒）。第一次打开仍要等隧道。

## 选择点统一 5 秒、双语语音、锁屏、进度条、中文界面（2026-11-08）
- **选择点统一停 5 秒**：Hands-free 先由旁白念问题，然后开麦听 5 秒；点选模式和 Lean back 也是 5 秒倒数。碰一下选择面板（打字、点麦克风、点任何地方）就停表、停麦，等她选完或输完（`holdForHer`）。5 秒内没说话、或说了但识别不出来，都走兜底：用预写的第一个选项那集马上往下（via=auto），不暂停。免手动/自动往下遇到要金币解锁的集，金币够就自动解锁，不弹窗。
- **语音识别换成录音 + 本机 faster-whisper**（`unscripted_asr.py`，launchd `com.vicky.realtime.unscripted-audio-asr`，127.0.0.1:8917，multilingual small，int8；中继 `/api/asr?k=&lang=` 转发）：中英文自动判断（中文版说英文、英文版说中文都行），提示词让中文出简体，静音/噪声返回空（滤掉“谢谢观看”类幻觉）。实测 5 秒语音约 1.8–2.3 秒。浏览器自带的 Web Speech 只能单语言，已不用。前端 `recordAnswer()`：音量检测她开始说话后等 1.1 秒静音结束；锁屏时拿不到音量就录满整段交给识别判断。选择点、Talk、选择面板麦克风、通话按住说话都走它。编剧和通话规则加了“她可能说中文或英文，照样理解，输出用本集语言”。
- **锁屏不断**：旁白提问、等待时的铺底音（app/bed.mp3，很轻的环境声循环）和下一集都在同一个 `<audio>` 上切换（`playAux`/`keepAlive`），中间不暂停，锁屏媒体会话一直在；Hands-free 在点播放时就请求麦克风并保持（`primeMic`），这样锁屏时也有可能录到。限制：iOS Safari 锁屏后通常会暂停网页的麦克风，那时就按 5 秒兜底往下走；安卓 Chrome 锁屏可以录；要 iPhone 锁屏也稳定录音，得做原生 App 壳。iPhone 开着麦克风时外放音量可能变小（系统切到通话音频模式），戴耳机不受影响。
- **拖动进度条不卡**：第 1 集音频放到 App 同域名（app/ep1/，Pages CDN 支持分段加载），拖动时只动进度条和时间、松手才跳（以前每移动一下就跳一次，在首字节 3 秒的云存储上会卡）；实时集预载整集每句。实测跳转 2–5 毫秒、跳完立即续播。
- **中文版界面全中文**（`app/i18n.js`，`?lang=zh` 时生效）：把 app.js 的英文界面文案（含 placeholder、aria-label、title、confirm）按 EX 查表 / RX 正则换成中文，剧情、人名、她输入的话不动（`translate="no"` 的元素跳过）。新增界面文案要在 i18n.js 补中文。日期按 zh-CN 格式。英文版不变。

## 配音引擎测试开关（11-08）
- 链接带 `&tts=flash`：实时集、选择点旁白、通话改用 **Eleven Turbo v2.5**（ElevenLabs 的低延迟/实时向模型，同一批声线；不认 `[quietly]` 这类表演标签，会自动去掉）。`&tts=turbo` = Eleven v4 Turbo，`&tts=v4` 回到默认。按语言记住；测试引擎的故事和普通故事分开存（会话键带引擎名），切过去就是新故事。第 1 集是预制的，仍是 v4。
- 测速（同一 Magnus 中文声线，经 MCP 各 6 句）：v4 中位 5.2 秒/句、v4 Turbo 5.3、Turbo v2.5 3.4；端到端自由输入第一句可播 v4 11.6 秒 → Turbo v2.5 7.1 秒，整集配完 23.3 → 18.2 秒。本机转写抽查两者错字率相当（主要是 whisper small 的同音字）。
- Waku 真流式 TTS（`pv.speech.stream`，profile `tts-eleven-flash-v1`）只能在 Waku playable 里、用户手势中调用，本应用（Pages）接不了；这里用的是批量接口，每句仍有约 3 秒任务开销。
- 测速脚本在 `qa/zh-rt/`（lat3.py 单句、e2e.py 端到端）。

## 电话改成真语音通话（11-08）
- **接通提速**：第 1 轮不再用本机 Opus（19–22 秒），改快模型 `CALL_FAST_MODEL` + 完整世界卡（第 2 轮起精简），第一句文字约 1.5–1.9 秒；通话配音默认 Eleven Turbo v2.5（`CALL_TTS=flash`，可设 v4/turbo），第一句声音约 6–10 秒（主要是 Waku 配音排队）。接通瞬间先播预先配好的“喂？/Hey.”（`/api/call/fillers` 返回 `greet`，第一次合成后缓存），编剧被告知已经打过招呼，服务器也会删掉第一句开头重复的“喂/Hey”。
- **铃声**：打出去时播回铃音 `app/ringback.mp3`（标准电话回铃 440+480 Hz，响 2 秒停 4 秒），至少响 2.6 秒才接；他打来时播 `app/ring-in.mp3`（原创合成木琴三连音）。两段都在通话 `<audio>` 上循环（不像 WebAudio 会被静音键静掉），播不了退回 WebAudio。苹果自带铃声有版权，不能直接用。
- **纯语音、不打字**：通话页去掉快捷回复和输入框。他说完立刻开麦（`recordAnswer`，音量检测，停顿约 1 秒就发），9 秒没出声就当沉默、他接着说（沉默那条预先写好，约 2 秒开口）；没听清会再听一次。底部只剩 语速 / 挂断 / 静音。点拨打或接听时就要麦克风权限。快捷回复的预先生成已停（只留“沉默”）。
- 还不能在他说话时插话打断（手机外放会被麦克风收进去误判），是轮流说。

## 载入、继续播放、播放键（11-08 晚）
- 首屏：Google 字体不再阻塞首屏；`relay.json` 在 index.html 里最先去取，并按上次的中转地址预连接；这台手机来过就直接用缓存的剧集列表 + 上次中转地址打开，relay.json 后台核对。
- 点“继续/收听”：刚点过（1.2 秒内）就不等本地副本，直接播（iOS 只允许在点击里开始播放，等一下就会被拦，看起来像没反应）；打开详情页和首页“继续收听”前两条时，先把要续播的那句和后面 3 句取到本地。本地实测点继续 31 毫秒出声。
- 播放键：选择点时旁白提问/铃底音在播放器上，原来按播放键只会开选项面板、停不了声音也停不了倒数（看起来没反应）→ 现在点一下就停声音、停 5 秒倒数、打开选项。生成中/第 1 集准备中点播放会提示，不再没反应。开麦时 iOS 切音频会话可能把正在播的故事暂停 → 开麦后自动接着播。
- “继续收听”列表按当前链接的语言和配音引擎筛选（测试引擎 &tts= 的故事也能在首页继续）。
- 调试：链接加 `&debug=1`，控制台 `__ua.P` 看播放器状态。
