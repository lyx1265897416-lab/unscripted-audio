# 正式版 vs 测试版 界面差异（11-20 走查）

**结论：** 正式版比测试版少 8 屏：解锁弹层、登录弹层、福利 5 屏、金币商店。另有 15 屏还在，但去掉了金币、登录、免费时长、FREE 标和锁、构建号这些元素。正式版没有新增的屏，只有一个新元素：欢迎页的「Get started」按钮（替换了 Apple / Google 登录和游客按钮）。其余屏两版一样。

- 测试版：`test/`，57 屏，0.0.1 (263240453) · 6d636d2 · 11-20 04:53，`NARRA_ENV=test`，narra-api（31 部）
- 正式版：`prod/`，49 屏，0.0.1 (263240448) · 6d636d2 · 11-20 04:48，`NARRA_ENV=prod`，narra-api-prod（15 部）
- 两版用同一个提交、同一条走查路线，都选了 magnus（Running with Wolves），在选择点点 A，并真实生成了第 2 集。两版下面的编号不一样，因为正式版少了屏，后面的编号整体往前挪。

## 一、正式版少了的屏（8 屏）

| 测试版文件 | 屏 | 正式版为什么没有 |
|---|---|---|
| 23_unlock_sheet | 解锁弹层（10 coins 解锁第 4 集） | 所有集免费，不弹解锁（kFreeAll） |
| 47_sheet_signin | 「我的」→ 登录弹层（Apple / Google） | 没有登录（kNoAccount），「我的」页没有 Sign in 按钮 |
| 52_rewards | 福利页（签到） | 没有 Rewards 标签页（kShowRewards=false），/rewards 路由会跳回首页 |
| 53_rewards_checked_in | 签到后 | 同上 |
| 54_rewards_daily | 每日任务 | 同上 |
| 55_rewards_new | 新手任务 | 同上 |
| 56_rewards_history | 金币记录 | 同上 |
| 57_store | 金币商店（金币包 + VIP） | 没有金币，顶栏没有金币胶囊，设置里也没有 Coin store |

## 二、两版都有，但元素不同的屏

| 屏（测试版 → 正式版编号） | 测试版 | 正式版 |
|---|---|---|
| 欢迎页（04 → 04） | Continue with Apple、Continue with Google、Continue as Guest（描边） | 只有一个白底黑字「Get started」 |
| 所有带底栏的屏 | 底栏三个标签：Home / Rewards / Me | 底栏两个标签：Home / Me |
| 首页顶部（11 → 11） | 顶栏右侧：搜索 + 金币胶囊（100） | 顶栏右侧只有搜索 |
| 首页 All series（13 → 13） | 前面有 Bingeworthy 等多行、31 部 | 剧目少，很快进入 All series（15 部正式剧） |
| 首页底部（14 → 14） | 列表最后有「30 min free」免费时长横条 | 没有免费时长 / 福利横条 |
| 搜索三屏（15–17 → 15–17） | 顶栏有金币胶囊；Romance 筛出 21 部 | 没有金币胶囊；Romance 筛出 12 部 |
| 详情 Episodes（21 → 21） | 顶部「30 min free」，各集标 FREE，之后带锁 | 不显示免费时长、FREE 标和锁 |
| 播放器剧集列表（27 → 26） | 前 3 集标 FREE，第 4 集起带锁 | 不标 FREE，不带锁 |
| 第 2 集时的剧集列表（36 → 35） | Ep2 标 FREE，Ep4、Ep5 带锁 | 不标 FREE，不带锁 |
| 首页底部 + 迷你条（38 → 37） | 迷你条上面是「29 min free」横条（免费时长已用掉 1 分钟） | 没有免费时长横条 |
| 有进度的剧集（42 → 41） | 「29 min free」和 FREE 标 | 不显示 |
| 我的（43 → 42） | 右上 Sign in；金币卡（Coins / Free min / VIP / Get coins） | 没有 Sign in 和金币卡；名字旁边有编辑笔（在本机改名） |
| 我的 · 在听（44 → 43） | 页面最底有构建号一行 `0.0.1 (…) · sha · 时间 · latest` | 不显示构建号，只在设置 → About 里显示 |
| 设置顶部（48 → 46） | 账户卡写「Sync across devices · Sign in」，还有 Sign-in（Not signed in）一行 | 账户卡只有名字（点进去改名），没有 Sign-in 行 |
| 设置中段（49 → 47） | 有 Coins & VIP 一组（Auto-unlock、Coin store、Purchase history、Restore purchases）；Notifications 里有 Check-in reminder | 没有 Coins & VIP；Notifications 只有 New episodes |
| 设置底部 · About（51 → 49） | Environment：Test | Environment：Production（构建号不同） |

## 三、两版一样的屏

年龄确认、麦克风说明卡、系统权限框、新手小戏（开场、问名字、问题材、接话、推荐卡）、首页中段、搜索结果、详情顶部 / 简介 / 角色 / 相似推荐、播放器、睡眠定时、收听方式、选择点（四屏）、生成中、第 2 集开播（两屏）、继续收听菜单、有进度的详情、重新开始确认、我的 · 收藏和编辑、语言页。

## 四、不是环境差异，但要注意

- **第 2 集行数不同：** 两版都生成了《The Locked Exit》，测试版 29 句，正式版 26 句。这是实时生成本身每次不一样，和环境无关。
- **正式版播放卡住：** 正式版播放器第二张（`prod/24_player_lines`）的进度停在 0:05，和第一张一样，12 秒里没往前走。测试版同一屏从 0:03 走到了 0:17。可能是正式环境第 1 集的音频卡住了，这次没细查，建议单独复现。
- **截不到的差异：** 引导结束时的 toast。测试版写「欢迎 + 100 金币」，正式版只写欢迎。走查没截到这一屏。
