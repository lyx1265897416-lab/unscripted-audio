# Unscripted Audio · 前后端接口约定

Pocket FM 式的音频连载 App，内容是我们 7 部实时互动剧的音频版。
- 前端：`app/`（纯静态 index.html + style.css + app.js，无构建），由中转 `unscripted_audio_server.py` 在 `/` 下直接提供。
- 后端：`unscripted_audio_server.py`（端口 8913），所有接口带口令 `k`（页面从地址栏 `?k=` 读，存 localStorage 后从地址栏去掉）。
- 语言：`?lang=zh|en`。界面菜单、按钮、状态条一律英文；剧名、简介、台词、字幕、选项跟随 lang（zh 时显示中文）。

## 剧集模型

- 每部剧 = 一部 Series。
- 第 1 集是预制好的有声剧（旁白 + 角色配音，2–4 分钟），一个 mp3，带逐句字幕 cues，集尾有一个“你怎么做”的选择点。
- 第 2 集起都是实时生成的：她在上一集结尾选了选项、打字或说话，服务器按她的选择写出下一集（约 8–12 句，60–90 秒），逐句合成，第一句约 10 秒就能播，后面的边播边到。每集结尾同样有选择点。
- 旁白用第二人称“你”指她；角色会叫她的名字（onboarding 时填的名字），这是我们和 Pocket FM 的差异点。

## 接口

### GET `/api/series?lang=zh&k=…`
返回数组，每项：
```json
{"id":"magnus","title":"与狼为伍","lead":"Magnus · 狼人 Alpha","hook":"十分钟后他就要订婚了……","tags":["狼人","命定伴侣"],"genres":["Werewolf","Billionaire","Fated mates"],
 "accent":"#c9a227","cover":"covers/magnus.jpg","avatar":"avatars/magnus.jpg",
 "stats":{"plays":"1.2M","rating":4.8},"ep1":{"title":"车库里的十分钟","dur":182,"ready":true}}
```
`cover` 是竖版海报（9:16），`avatar` 是方形脸部裁切（192×192）。`stats` 是展示用的假数据。

### GET `/api/series/<id>?lang=zh&k=…`
Series 字段 + `synopsis`（较长简介）+ `cast`：`[{"name":"Magnus","role":"狼人 Alpha","voice":"Guan Tang Bao"}]`。

### POST `/api/play`  `{k, series, lang, name}`
开始一部剧（每次从第 1 集开始，新会话）。返回：
```json
{"sid":"…","ep":{"n":1,"title":"车库里的十分钟","kind":"produced","audio":"https://…/ep1.mp3","dur":182.4,
  "cues":[{"s":0.0,"e":3.2,"who":"NARR","text":"晚上十一点五十分……"}],
  "prompt":"他扣住你的手腕，等你回答。","choices":["我不会说出去。","放开我。"]}}
```
`audio` 可能要几十秒才生成好（第一次有人播某部剧的某种语言时）：这时返回 `{"sid":…,"job":"…"}`，按下面的 job 轮询，job 完成后 `job.ep` 就是上面 `ep` 的结构。

### POST `/api/next`  `{k, sid, text, via}`
`via` = `option` | `free`（打字）| `voice`（说话识别）| `silence`（不说话）。返回 `{"job":"…"}`。

### GET `/api/job?k=…&id=…`
```json
{"status":"writing|voicing|done|error","error":null,
 "ep":{"n":2,"title":"…","kind":"live",
   "lines":[{"who":"NARR","text":"……","url":"https://…mp3"},{"who":"Magnus","text":"……","url":null}],
   "prompt":"…","choices":["…","…"],"ending":false}}
```
- `lines` 会先出现文本（url 为 null），每句合成好就填上 url；合成失败的句子 url 为 `""`（跳过）。
- 播放规则：按顺序播，下一句 url 还是 null 就等（轮询 job），`""` 跳过；第一句好了就可以开播。
- `status=done` 时 `prompt`、`choices` 一定有；`ending=true` 表示这部剧的这条线到结局了。

### 其他
- `GET /health` → `{"ok":true}`
- 静态：`/`、`/covers/*`、`/avatars/*`、`/app.js` 等都从 `app/` 读。

## 前端自己管的（localStorage，不经服务器）
金币钱包、每日签到、任务、解锁记录、书架（Library）、收听进度、名字、倍速、睡眠定时。金币是测试币，不接真支付。

## 和主角语音通话（2026-11-06 加，参考 Magnus 午夜来电）

- `GET /api/series` 每项多一个 `callers`：`[{"key":"Magnus","name":"马格努斯·索恩","role":"…"}]`（三真四假有 Wes、Jasper 两个），`motion`：播放器动态封面 mp4。
- `GET /api/call/fillers?series=&who=&lang=&k=` → `{"urls":[…4 条], "think":[…4 条“让我想想”]}`（11-06 加 think：她自由回复后，垫场声播完他还没开口就再播一条思考声）：垫场声（“嗯。”“嗯，我在听。”“我在。”“嗯，我知道。”），她说完立刻随机播一条，盖住等待。第一次请求要合成，约 10 秒，之后秒回；通话开始时就预取。
- `POST /api/call/start {k, series, lang, name, who, sid, direction}` → `{"cid":"…","who":"Magnus","job":"…"}`。`direction` = `incoming`（他打来）| `outgoing`（她打给他）；`sid` 带上当前剧集会话，他就记得剧里发生过什么。他先开口。
- `POST /api/call/turn {k, cid, text, via}` → `{"job":"…"}`；`via` 同 `/api/next`。
- `POST /api/call/end {k, cid, seconds}`。
- job：`{"status":"writing|voicing|done|error","call":{"lines":[{"who":"Magnus","text":"…","url":null}],"choices":["…","…"],"hangup":false}}`。每轮 1–3 句；播放规则同实时集（按序、null 等、"" 跳过）。`hangup=true` 时他说完就挂断。实测她说完到他第一句 12–20 秒。

## Pages 部署
前端同时部署在 GitHub Pages（静态）。Pages 上同目录有 `relay.json`：`{"base":"https://xxx.trycloudflare.com","updated":"…"}`，由本机定时任务在隧道地址变化时自动更新并推送。前端所有 `/api/*` 请求前缀 `base`；没有 relay.json（本机中转直接提供页面时）就用同源。

## 通话提速（2026-11-06）
- 第 1 轮（响铃期间）用本机 Opus 写开场；第 2 轮起用快模型 `CALL_FAST_MODEL`（默认 deepseek/deepseek-v4.1-flash，第一句约 3 秒）+ 精简版世界卡。
- 他每轮说完，服务器按两个快捷回复和“沉默”预先写好他的下一轮、第一句先配好音。她点快捷回复 / Stay silent 时 `/api/call/turn` 直接返回那个预先生成的 job，第一句马上能播；打字、说话的自由回复照常现写（实测约 12 秒，主要花在配音）。没被选中的预先生成丢弃（每条约 15 credits 的第一句配音）。

## 收听模式接口（2026-11-06）
- `POST /api/play`、`/api/call/start` 多一个可选 `me`（她的“Your story self”，≤400 字）。
- `POST /api/next` 的 `via` 多一个 `auto`（她没回应，故事自己往下走）；返回多 `matched`（语音/打字被判成某个选项时是那个选项原文）和最终 `via`。
- `GET /api/cue?sid=&n=` → `{"url","text","n"}`：第 n 集结尾旁白念的提问。第一次约 5–10 秒，之后秒回。
- `POST /api/wish {k, sid, text}` → `{"ok":true,"wishes":[…]}`：听的过程中对故事说的话，下一集要接住（最多记 3 条，下一集开写后清空）。
- `GET /api/specs?sid=` → `{"n":下一集号,"specs":{"选项原文":{"job","n","ep"}}}`：预先写好的下一集（第 1 句已配音），前端点选项时本地直接开播。
