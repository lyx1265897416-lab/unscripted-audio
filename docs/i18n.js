/* Unscripted Audio · 中文版界面（2026-11-08 起：中文版的入口、菜单、按钮、状态条、提示全部中文；英文版不变）。
 * 做法：app.js 照常用英文写界面，这里在 ?lang=zh 时把页面上出现的界面文字（文本、placeholder、aria-label、title、confirm）
 * 换成中文——固定文案查表 EX，带数字/名字的用 RX 正则。剧情内容、人名、她自己输入的话不在表里，不会被改。
 * 加新界面文案时，在 EX / RX 里补一条中文。 */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).get('lang') !== 'zh') return;

  const EX = {
    // tabs / navigation
    'Home': '首页', 'Explore': '发现', 'Library': '书架', 'Rewards': '福利', 'Main': '主导航', 'Series': '剧集', 'Player': '播放器', 'Profile': '我的',
    'Back': '返回', '(stayed silent)': '（没有说话）', 'Preparing Ep 1…': '正在准备第 1 集…', 'Share link ready:': '分享链接：', 'Pause': '暂停', 'Resume': '继续播放', 'Close': '关闭', 'Search': '搜索', 'Share': '分享', 'Done': '完成', 'Cancel': '取消', 'Save': '保存', 'Remove': '移除', 'Delete': '删除',
    'Clear': '清空', 'Clear all': '全部清空', 'Continue': '继续', 'Choose': '去选择', 'Claim': '领取', 'Go': '去完成', 'Send': '发送', 'Play': '播放', 'Retry': '重试',
    'See all': '查看全部', 'Show less': '收起', 'More': '展开', 'Less': '收起', 'Featured': '精选', 'Genres': '分类', 'All series': '全部剧集', 'Browse genres': '按分类浏览',
    'Continue Listening': '继续收听', 'Top 10 this week': '本周 Top 10', 'New Releases': '新上架', 'More like this': '相似推荐', 'Episodes': '剧集', 'About': '简介', 'Cast': '角色',
    'Search series, characters, tropes': '搜索剧名、角色、题材', 'Try a character name or a trope.': '试试角色名或题材关键词。', 'No results': '没有找到',
    'Unscripted Audio': 'Unscripted 有声剧', 'Unscripted VIP': 'Unscripted VIP', 'Unlimited episodes': '无限畅听', 'Unscripted Audio ': 'Unscripted 有声剧', 'NOW PLAYING': '正在播放', 'LIVE': '实时', 'FREE': '免费', 'VIP': 'VIP', 'AD': '广告',
    'Written live from your choices': '每一集都按你的选择实时生成', 'WRITTEN LIVE FROM YOUR CHOICES': '按你的选择实时生成', 'WRITTEN FOR YOU': '为你而写', 'Written for you': '为你而写',
    'Play Now': '立即收听', 'Play now': '立即收听', 'Play Episode 1': '收听第 1 集', 'Start listening': '开始收听', 'Start over': '重新开始', 'Start a new story from Ep 1': '从第 1 集重新开始',
    'Add to Library': '加入书架', 'Added to Library': '已加入书架', 'Removed from Library': '已移出书架', 'Removed from Listening': '已移出收听记录',
    'Your listening history shows up here.': '你的收听记录会显示在这里。', 'Nothing in progress yet.': '还没有在听的剧。', 'Tap “+ Library” on any series to save it here.': '在任意剧集点“+ 书架”就会收藏到这里。',
    'Start any series — Ep 1–3 are free.': '随便挑一部开始吧 —— 前 3 集免费。', 'Play a new series': '听一部新剧', 'Listening': '在听', 'Saved': '收藏', 'Calls': '通话', 'History': '历史',
    // onboarding
    'Get started': '开始', 'Skip for now': '先跳过', 'Step 1 of 3': '第 1 步 / 共 3 步', 'Step 2 of 3': '第 2 步 / 共 3 步', 'Step 3 of 3': '第 3 步 / 共 3 步', 'Next': '下一步',
    'Stories that': '故事，', 'listen back.': '会回应你。', 'What should they call you?': '他们该怎么称呼你？', 'Your name': '你的名字',
    'Characters will say your name in the story.': '角色会在故事里叫你的名字。', 'Pick what you love': '选你喜欢的题材', 'We\'ll tune your home shelves. Choose as many as you like.': '我们会按你的喜好整理首页，可以多选。',
    'How it works': '怎么玩', 'Audio series where every episode ends with your choice — and the next one is written and voiced live, just for you.': '有声连载剧：每一集都停在你的选择上，下一集按你的选择实时写、实时配音，只为你一个人。',
    'Episode 1 is a produced audio drama. It ends on a choice.': '第 1 集是制作好的有声剧，结尾停在一个选择上。', 'Pick an answer, type your own, or just say it out loud.': '点一个选项、自己打字，或者直接说出来。',
    'Every episode after Ep 1 is written live from what you choose.': '第 1 集之后的每一集，都按你的选择实时生成。', 'Start listening ': '开始收听',
    // player
    'Close player': '收起播放器', 'Open player': '打开播放器', 'Previous episode': '上一集', 'Next episode': '下一集', 'Back 10 seconds': '后退 10 秒', 'Forward 10 seconds': '前进 10 秒',
    'Playback speed': '播放速度', 'Speed': '倍速', 'Sleep': '定时', 'Sleep timer': '睡眠定时', 'Episode list': '剧集列表', 'Talk': '说话', 'Talk to the story': '对故事说话',
    'Listening mode': '收听模式', 'Fall asleep to your story': '听着你的故事入睡', 'Stops at the end of this episode': '本集结束时停止', 'Off': '关闭', '5 minutes': '5 分钟', '15 minutes': '15 分钟',
    '30 minutes': '30 分钟', '1 hour': '1 小时', 'End of episode': '本集结束', 'End of ep': '本集结束', 'Sleep timer off': '已关闭睡眠定时', 'Sleep timer: stopped at end of episode': '睡眠定时：本集结束已停止',
    'Episode 1 · Preparing…': '第 1 集 · 准备中…', 'Preparing Episode 1…': '正在准备第 1 集…', 'Voicing Episode 1…': '正在为第 1 集配音…', 'First listen — this takes a few seconds': '第一次收听，稍等几秒',
    'Writing your episode…': '正在为你写这一集…', 'Voicing the first lines…': '正在配前几句…', 'Starting…': '马上开始…', 'Still writing this episode…': '这一集还在写…', 'Tap play to start listening': '点播放开始收听',
    'Could not load this episode audio': '这一集的音频没加载出来', 'On a call': '正在通话', 'Reconnecting…': '正在重新连接…', 'Server is reconnecting…': '服务器正在重新连接…', 'Server offline — demo mode': '服务器离线 · 演示模式',
    'The end — for this path': '这条线的结局', 'Your choices led here. Start again and the story will be written differently.': '是你的选择走到了这里。重新开始，故事会写成不一样的样子。',
    'Not written yet': '还没写', 'Up next': '下一集',
    // choice sheet & voice
    'or answer in your own words': '或者用你自己的话回答', 'Say it your way…': '用你的话说…', 'Your answer': '你的回答', 'Speak your answer': '说出你的回答', 'Stay silent': '保持沉默',
    'Wait for me': '等等我', 'Paused — take your time': '已暂停 —— 慢慢来', 'The story continues in': '故事将继续：', 'Lean back · the story continues in': '躺着听 · 故事将继续：',
    'Listening · the story continues in': '正在听 · 没听到就继续：', 'Mic is off · the story continues in': '麦克风已关 · 故事将继续：', 'The story carries on…': '故事继续…',
    'Didn’t catch that — the story carries on': '没听清 —— 故事先往下走', 'The story carries on by itself…': '故事正在自己往下走…', 'You stayed silent.': '你没有说话。', 'Stayed silent': '没有说话',
    'The narrator is asking…': '旁白在问你…', 'Listening — just say it': '在听 —— 直接说就好', 'I’m listening…': '我在听…', 'Got it — one moment…': '收到，马上…', 'Got it': '收到',
    'Microphone is off': '麦克风未开启', 'Say one of the two — or anything you want to happen. Chinese or English.': '说其中一个选项，或者你想让剧情怎么走都行。中文、英文都可以。',
    'Keep going, I’ll wait till you finish.': '继续说，我等你说完。', 'Allow the microphone to answer by voice, or tap a choice.': '允许使用麦克风就能直接说，或者点一个选项。',
    'Answer by voice': '用语音回答', 'Stop listening': '停止收听', 'Listening… (Chinese or English)': '在听…（中文或英文都行）', 'Didn\'t catch that — try again': '没听清，再说一次',
    'Microphone permission denied': '没有麦克风权限', 'Voice input unavailable': '这个浏览器不支持语音输入', 'Take your time': '慢慢来',
    'Say what you want to happen next': '说说你希望接下来发生什么', 'Listening…': '在听…', 'Type it below': '在下面输入', 'Or type it…': '或者打字…', 'What should happen': '你想让什么发生',
    'e.g. “I want him to finally admit it.” “Take me somewhere with just us.”': '比如：“我想让他终于承认。”“带我去只有我们两个人的地方。”',
    'Tap the mic and say it': '点麦克风说出来', 'Didn’t catch that — tap the mic and try again': '没听清 —— 点麦克风再说一次', 'Allow the microphone, or type it below.': '允许使用麦克风，或者在下面输入。',
    'Chinese or English both work.': '中文、英文都可以。', 'Speak': '说话',
    // listening modes
    'How do you want to listen?': '你想怎么听？', 'Switch any time. Calls with characters work in every mode.': '随时可以切换。和角色通话在哪种模式下都能用。', 'How you listen': '收听方式',
    'Hands-free': '免手动', 'I ask out loud, you just answer': '我念问题，你直接回答', 'Lean back': '躺着听', 'The story keeps going on its own': '故事自己往下走', 'Tap to choose': '点选', 'Pick on screen': '在屏幕上选',
    'At every choice point the narrator asks out loud and the mic listens for 5 seconds — answer in Chinese or English. Say nothing and the story carries on. Works with the screen locked too (on iPhone, open it in Safari).':
      '每到选择点，旁白会把问题念出来，麦克风听 5 秒 —— 中文、英文都能回答。不说话，故事就自己往下走。锁屏也能语音回答（iPhone 要用 Safari 打开）。',
    'No questions. The story keeps moving by itself, episode after episode — for winding down or falling asleep.': '不提问，故事一集接一集自己往下走 —— 适合放松或睡前听。',
    'Choose on screen or type your own answer. The story waits 5 seconds — touch the screen and it waits until you’re done.': '在屏幕上点选或打字回答。故事会等 5 秒 —— 碰一下屏幕，它就一直等你选完。',
    ' · not supported in this browser': ' · 这个浏览器不支持',
    // profile
    'What characters call you': '角色怎么称呼你', 'Your story self': '故事里的你', 'who you want to become, the life you want, how you want to be loved': '想成为的人、想要的生活、想被怎样对待',
    'Story language': '故事语言', 'English': 'English', 'Auto-unlock episodes': '自动解锁剧集', 'VIP (test)': 'VIP（测试）', 'Makes every episode free': '所有剧集免费', 'Coin store': '金币商店',
    'Reset all data': '清除所有数据', 'Live mode': '在线模式', 'Demo mode · mock content': '演示模式 · 示例内容', 'Listener': '听众', 'Cleared': '已清除', 'Name cleared': '已清除名字',
    'Reset all local data (coins, progress, library, name)?': '清除本机所有数据（金币、进度、书架、名字）？',
    // coins / unlock / rewards
    'Coins': '金币', 'coins': '金币', 'Coin balance': '金币余额', 'Coin history': '金币记录', 'No coin activity yet.': '还没有金币记录。', 'Get coins': '获取金币', 'Get more coins': '获取更多金币',
    'Price': '价格', 'Your balance': '你的余额', 'Auto-unlock': '自动解锁', 'Auto-unlock next episodes': '自动解锁后面的剧集', 'Use coins automatically when you make a choice': '做选择时自动用金币解锁',
    'Daily check-in': '每日签到', 'Daily tasks': '每日任务', 'Resets at midnight': '每天零点重置', 'Daily free listening': '每日免费听', 'Ep 1–3 free on every series. Check in for up to 50 coins a day.': '每部剧前 3 集免费。每天签到最多领 50 金币。',
    'Listen 5 min': '收听 5 分钟', 'Start a new series': '开始一部新剧', 'Make 3 choices': '做 3 次选择', 'Share a series': '分享一部剧', 'Claimed': '已领取',
    'POPULAR': '最受欢迎', 'BEST VALUE': '最划算', 'Every live episode unlocked': '所有实时剧集都解锁', 'No ads, no waiting': '没有广告，不用等', 'Test toggle — no charge': '测试开关，不扣费',
    'Start VIP (test)': '开通 VIP（测试）', 'VIP is on · Turn off': 'VIP 已开通 · 关闭', 'VIP · all free': 'VIP · 全部免费', 'Welcome bonus': '新人奖励',
    'Every episode unlocked. Every choice, no waiting. (Simulated ad)': '所有剧集解锁，每个选择不用等。（模拟广告）', 'Wait-free in': '免费等待：', 'Not enough coins · Get more': '金币不够 · 去获取',
    'VIP calls are free': 'VIP 通话免费', 'Test coins — no real payment. Tapping a pack just adds coins.': '测试金币，不会真实付款。点一下礼包就会加金币。', 'Link copied': '链接已复制', 'Share link ready: ': '分享链接：',
    // calls
    'Call': '打电话', 'Calling': '正在呼叫', 'Accept': '接听', 'Decline': '拒绝', 'Hang up': '挂断', 'Hanging up…': '正在挂断…', 'Call back': '回拨', 'Call ended': '通话结束', 'call ended': '通话结束', 'Call failed': '通话失败',
    'Incoming call…': '来电…', 'On call now': '通话中', 'Call history': '通话记录', 'Call history cleared': '通话记录已清空', 'Call deleted': '通话已删除', 'Delete call': '删除通话', 'Call transcript': '通话文字记录',
    'Transcript': '文字记录', 'Call speed': '通话语速', 'Replay speed': '回放速度', 'Hold to talk': '按住说话', 'Listening… release to send': '在听… 松开发送', 'Your reply': '你的回复', 'Your turn': '轮到你了',
    'Quick reply': '快捷回复', 'Who do you want to call?': '你想打给谁？', 'Call a lead from any series page.': '在任意剧集页都能给主角打电话。', 'Call your favorite': '打给你喜欢的他',
    'Live call — saved after every turn. Replay unlocks when it ends.': '通话进行中 —— 每轮自动保存，结束后可以回放。', 'Replay is available after the call': '通话结束后可以回放', 'Replay lines': '逐句回放',
    'Nothing was said in this call.': '这通电话里没有说话。', 'No conversation yet.': '还没有对话。', 'No calls yet.': '还没有通话记录。', 'Swipe left on a call to delete': '向左滑动可以删除通话',
    'Can\'t delete a call in progress': '通话进行中，不能删除', 'Delete this call and its transcript?': '删除这通电话和文字记录？', 'This call\'s transcript': '这通电话的文字记录',
    'Transcripts and replay links are removed from this device. This can’t be undone.': '文字记录和回放会从本机删除，删除后无法恢复。', 'Just now': '刚刚', 'You': '你', 'You called.': '你打来的。',
    'Stayed silent ': '没有说话', 'let me think': '让我想想', 'writing next lines…': '正在想下一句…', 'Retry with memory': '带着记忆重试', 'Interrupted': '已中断', 'The caller': '来电者',
    'Voice call · first call free · he remembers your story': '语音通话 · 第一次免费 · 他记得你们的故事', 'Generation failed': '生成失败', 'Timed out': '超时了',
  };

  const GENRE = {
    'Werewolf': '狼人', 'Billionaire': '霸总', 'Romance': '恋爱', 'Fantasy': '奇幻', 'Mystery': '悬疑', 'Thriller': '惊悚', 'Reality show': '恋综', 'Cozy': '治愈',
    'Comedy': '喜剧', 'Countdown': '倒计时', 'Dark romance': '暗黑恋爱', 'Fake dating': '假装恋爱', 'Fake engagement': '假订婚', 'Fated mates': '命定伴侣',
    'Friends to lovers': '友情变爱情', 'Healing': '治愈', 'Love triangle': '三角恋', 'Mafia': '黑帮', 'Masked man': '面具男', 'Merman': '人鱼', 'Pets': '萌宠',
    'Second chance': '破镜重圆', 'Slice of life': '日常', 'Stepbrother': '继兄', 'werewolf romance': '狼人恋爱',
  };
  Object.assign(EX, GENRE, { 'Bingeworthy': '一口气听完', 'New Releases': '新上架' });
  Object.keys(GENRE).forEach((g) => { EX[g.toLowerCase()] = GENRE[g]; });
  const RX = [
    [/^Ep (\d+) ·$/, '第 $1 集 ·'], [/^Episode (\d+) ·$/, '第 $1 集 ·'],
    [/^(\d+) calls?$/, '$1 通'], [/^(\d+) lines?$/, '$1 句'], [/^(\d+) results?( in ([\s\S]+))?$/, (m, n, x, g) => (g ? `「${tr(g)}」里有 ${n} 部` : `${n} 个结果`)],
    [/^Written for you · ([\s\S]+?)( ·)?$/, (m, r, d) => `为你而写 · ${tr(r)}${d ? ' ·' : ''}`], [/^you stayed silent$/, '你没有说话'], [/^(\d+) min$/, '$1 分钟'],
    [/^Voice: ([\s\S]+)$/, '配音：$1'], [/^\+(\d+) bonus$/, '+$1 赠送'],
    [/^(\d+) min ·$/, '$1 分钟 ·'], [/^Written live from your choice$/, '按你的选择实时生成'], [/^Depends on your choices$/, '取决于你的选择'],
    [/^(\d+) series$/, '$1 部'], [/^([\d.]+) · ([\d.]+[KM]?) plays$/, '$1 · $2 次收听'], [/^Day (\d+) of 7$/, '第 $1 / 7 天'], [/^Day (\d+) claimed · back tomorrow$/, '第 $1 天已签到 · 明天再来'],
    [/^Check in · \+(\d+) coins$/, '签到 · +$1 金币'], [/^Checked in today$/, '今天已签到'], [/^Today$/, '今天'], [/^\+(\d+) · (\d+)\/(\d+)( min)?$/, (m, a, b, c, d) => `+${a} · ${b}/${c}${d ? ' 分钟' : ''}`],
    [/^Because you like ([\s\S]+)$/, (m, g) => `因为你喜欢${GENRE[g] || EX[g] || g}`],
    [/^Episode (\d+)$/, '第 $1 集'], [/^Ep (\d+)$/, '第 $1 集'], [/^EPISODE (\d+)$/, '第 $1 集'], [/^EPISODE (\d+) · WRITTEN LIVE$/, '第 $1 集 · 实时生成'],
    [/^Episode (\d+) · Writing your episode…$/, '第 $1 集 · 正在为你写…'], [/^Episode (\d+) · Preparing…$/, '第 $1 集 · 准备中…'], [/^Episode (\d+) · ([\s\S]*)$/, (m, n, r) => `第 ${n} 集 · ${tr(r)}`],
    [/^Ep (\d+) · Your move$/, '第 $1 集 · 轮到你了'], [/^Ep (\d+) · Your move · ([\s\S]*)$/, '第 $1 集 · 轮到你了 · $2'], [/^Ep (\d+) ended · Your move$/, '第 $1 集结束 · 轮到你了'], [/^Ep (\d+) ended — your move$/, '第 $1 集结束 —— 轮到你了'],
    [/^Your move · Ep (\d+)$/, '轮到你了 · 第 $1 集'], [/^YOUR MOVE · END OF EP (\d+)$/, '轮到你了 · 第 $1 集结尾'], [/^Ep (\d+) · ([\d.]+)%$/, '第 $1 集 · $2%'], [/^Ep (\d+) · ([\s\S]*)$/, (m, n, r) => `第 ${n} 集 · ${tr(r)}`],
    [/^Continue Ep (\d+)$/, '继续第 $1 集'], [/^Writing Ep (\d+)…$/, '正在写第 $1 集…'], [/^Line (\d+) of (\d+|…)$/, '第 $1 / $2 句'], [/^UP NEXT IN (\d+)$/, '$1 秒后播下一集'],
    [/^(\d+)s$/, '$1 秒'], [/^(\d+) sec$/, '$1 秒'], [/^(\d+) min$/, '$1 分钟'], [/^(\d+) min ago$/, '$1 分钟前'], [/^(\d+) h ago$/, '$1 小时前'], [/^(\d+) d ago$/, '$1 天前'], [/^(\d+)\/5 min$/, '$1/5 分钟'],
    [/^Pausing in (\d+) min$/, '$1 分钟后暂停'], [/^Pausing in ([\d:]+)$/, '$1 后暂停'], [/^Speed ([\d.]+)x$/, '倍速 $1x'], [/^Stops at end of episode$/, '本集结束时停止'],
    [/^Ep (\d+) will be written from your answer$/, '第 $1 集会按你的回答来写'], [/^Ep (\d+) is written live from your answer$/, '第 $1 集会按你的回答实时生成'],
    [/^Ep (\d+) is written live after your earlier choices$/, '第 $1 集会按你之前的选择实时生成'], [/^Ep (\d+) · (\d+) to unlock$/, '第 $1 集 · $2 金币解锁'], [/^(\d+) to unlock$/, '$1 金币解锁'],
    [/^Finish Ep (\d+) and make your choice to write Ep (\d+)$/, '听完第 $1 集并做出选择，就会写第 $2 集'], [/^Finish Ep (\d+) and choose$/, '听完第 $1 集再选择'], [/^generating now$/, '正在生成'],
    [/^Play Ep 1 first — Ep (\d+) is written from your choice$/, '先听第 1 集 —— 第 $1 集会按你的选择来写'], [/^Ep 1–(\d+) free · then (\d+) coins each$/, '第 1–$1 集免费 · 之后每集 $2 金币'],
    [/^Say what you want to happen next — Episode (\d+) will follow it\.$/, '说说你希望接下来发生什么 —— 第 $1 集会照着走。'], [/^Got it — Episode (\d+) will follow that$/, '收到 —— 第 $1 集会照这个走'],
    [/^Unlock Episode (\d+)$/, '解锁第 $1 集'], [/^Episode (\d+) unlocked([\s\S]*)$/, '第 $1 集已解锁$2'], [/^Auto-unlocked Ep (\d+) \(−(\d+)\)$/, '已自动解锁第 $1 集（−$2）'], [/^Unlock with (\d+) coins$/, '用 $1 金币解锁'],
    [/^Call with (\d+) coins$/, '用 $1 金币通话'], [/^Watch an ad to (unlock|call free)$/, (m, a) => (a === 'unlock' ? '看广告解锁' : '看广告免费通话')], [/^Spend (\d+) coins automatically on Ep 4\+$/, '第 4 集起自动花 $1 金币解锁'],
    [/^written live from your choice$/, '按你的选择实时生成'], [/^([\s\S]+) · written live from your choice$/, '$1 · 按你的选择实时生成'], [/^([\s\S]+) · your first call was free$/, '$1 · 第一次通话免费'],
    [/^Call ([\s\S]+)$/, '打给 $1'], [/^\+(\d+) coins$/, '+$1 金币'], [/^\+(\d+) coins · Day (\d+)$/, '+$1 金币 · 第 $2 天'], [/^\+(\d+) test coins$/, '+$1 测试金币'], [/^−(\d+) coins$/, '−$1 金币'],
    [/^(\d+) coins$/, '$1 金币'], [/^(\d+) coins \/ call$/, '$1 金币 / 次'], [/^coins · (\d+) series started$/, '金币 · 已开始 $1 部剧'], [/^(\d+) records$/, '$1 条记录'], [/^Day (\d+)$/, '第 $1 天'],
    [/^Daily check-in · Day (\d+)$/, '每日签到 · 第 $1 天'], [/^Task · ([\s\S]+)$/, '任务 · $1'], [/^Coin pack (\d+)([\s\S]*) \(test\)$/, '金币礼包 $1$2（测试）'], [/^Ad unlock Ep (\d+) · ([\s\S]+)$/, '看广告解锁第 $1 集 · $2'],
    [/^Auto-unlock Ep (\d+) · ([\s\S]+)$/, '自动解锁第 $1 集 · $2'], [/^Unlock Ep (\d+) · ([\s\S]+)$/, '解锁第 $1 集 · $2'], [/^Ad call · ([\s\S]+)$/, '看广告通话 · $1'], [/^Balance:$/, '余额：'],
    [/^Welcome(?:, ([\s\S]+))?! \+30 coins$/, (m, n) => (n ? `欢迎，${n}！+30 金币` : '欢迎！+30 金币')], [/^They'll call you ([\s\S]+)$/, '他们会叫你 $1'], [/^VIP on — ([\s\S]+)$/, 'VIP 已开通 —— 通话和剧集都免费'],
    [/^Sleep timer: paused$/, '睡眠定时：已暂停'], [/^Calling([\s\S]*)$/, '正在呼叫$1'], [/^Saved to Calls$/, '已保存到通话记录'], [/^Call again$/, '再打一次'],
    [/^Call dropped: ([\s\S]+)$/, '通话中断：$1'], [/^Call failed: ([\s\S]+)$/, '通话失败：$1'], [/^Couldn't reach ([\s\S]+): ([\s\S]+)$/, '没能接通 $1：$2'], [/^Couldn't start the story\.([\s\S]*)$/, '故事没能开始。$1'],
    [/^Couldn't write the next episode \(([\s\S]+)\)\. Try again\.$/, '下一集没写出来（$1），再试一次。'], [/^Generation failed: ([\s\S]+)$/, '生成失败：$1'], [/^Interrupted · ([\s\S]+)$/, '已中断 · $1'],
    [/^Clear all (\d+) calls\?$/, '清空全部 $1 通通话？'], [/^(\d+) calls? · saved after every turn$/, '$1 通 · 每轮自动保存'], [/^([\s\S]+) · (\d+) calls?$/, '$1 · $2 通'], [/^([\s\S]+) · (\d+) lines?$/, '$1 · $2 句'],
    [/^(\d+) results?$/, '$1 个结果'], [/^(\d+) eps? · live$/, '$1 集 · 实时'], [/^([\d.]+[KM]?) plays$/, '$1 次收听'], [/^([\s\S]+) · change how you listen$/, '$1 · 换个收听方式'],
    [/^Want to talk to ([\s\S]+) himself\? That’s a call — tap the phone at the top\.$/, '想直接跟 $1 本人说话？那是打电话 —— 点顶部的电话图标。'],
    [/^You said “([\s\S]*)”$/, '你说：“$1”'], [/^The next episode is written and voiced live from what you chose([\s\S]*)\.$/, (m, r) => '下一集会按你的选择实时写、实时配音' + (r ? r.replace(/^, and they’ll call you ([\s\S]+)$/, '，角色会叫你 $1') : '') + '。'],
    [/^, and they’ll call you ([\s\S]+)$/, '，角色会叫你 $1'], [/^([\s\S]+) is waiting for what you do next\.$/, '$1 在等你下一步怎么做。'], [/^([\s\S]+) · Unscripted Audio$/, '$1 · Unscripted 有声剧'],
    [/^Your next episodes and calls will be written around you$/, '接下来的剧集和通话会围绕你来写'],
  ];

  function tr(t) {
    if (!t || !/[A-Za-z]/.test(t)) return t;
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(t);
    const core = m[2];
    let out = Object.prototype.hasOwnProperty.call(EX, core) ? EX[core] : null;
    if (out == null) {
      for (const [r, f] of RX) { if (r.test(core)) { out = core.replace(r, f); break; } }
    }
    if (out == null && /^· /.test(core)) { const r = tr(core.slice(2)); if (r !== core.slice(2)) out = '· ' + r; }
    if (out == null && core.indexOf(' · ') > 0) {  // "A · B": translate each part (e.g. mode name · short description)
      const parts = core.split(' · '), mapped = parts.map((x) => tr(x));
      if (mapped.some((x, i) => x !== parts[i])) out = mapped.join(' · ');
    }
    return out == null || out === core ? t : m[1] + out + m[3];
  }
  window.__uaTr = tr;

  const skip = (el) => !!(el && el.closest && el.closest('[translate="no"], script, style, textarea, input'));
  const ATTRS = ['placeholder', 'aria-label', 'title'];
  function doText(n) { if (skip(n.parentElement)) return; const v = tr(n.data); if (v !== n.data) n.data = v; }
  function doEl(el) {
    for (const a of ATTRS) { const v = el.getAttribute && el.getAttribute(a); if (v && /[A-Za-z]/.test(v)) { const w = tr(v); if (w !== v) el.setAttribute(a, w); } }
  }
  function walk(root) {
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 || skip(root) && root.tagName !== 'INPUT' && root.tagName !== 'TEXTAREA') { if (root.nodeType === 1) doEl(root); return; }
    doEl(root);
    const it = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let n; while ((n = it.nextNode())) { if (n.nodeType === 3) doText(n); else doEl(n); }
  }
  const mo = new MutationObserver((recs) => {
    for (const r of recs) {
      if (r.type === 'characterData') doText(r.target);
      else if (r.type === 'attributes') doEl(r.target);
      else r.addedNodes.forEach(walk);
    }
  });
  mo.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  document.addEventListener('DOMContentLoaded', () => walk(document.body));
  if (document.body) walk(document.body);
  document.title = 'Unscripted 有声剧';
  const nativeConfirm = window.confirm.bind(window);
  window.confirm = (msg) => nativeConfirm(tr(String(msg)));
})();
