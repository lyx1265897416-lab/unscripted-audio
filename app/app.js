/* Unscripted Audio — mobile web app (plain JS, no build).
 * Real mode follows CONTRACT.md; mock mode (?mock=1 or when /api/series fails) serves everything in-page. */
(() => {
'use strict';

/* =========================================================================
 * 0. Utilities
 * ========================================================================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/** strip TTS performance tags like [softly] from on-screen captions */
const cleanText = (t) => String(t == null ? '' : t).replace(/\[(?:[a-z]+(?:\s[a-z]+)*)\]\s*/gi, '').trim();
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (o) => JSON.parse(JSON.stringify(o));
const pad2 = (n) => String(n).padStart(2, '0');
const fmtTime = (sec) => {
  if (!isFinite(sec) || sec < 0) sec = 0;
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${pad2(m)}:${pad2(s)}` : `${m}:${pad2(s)}`;
};
const fmtMin = (sec) => (!sec ? '' : sec < 60 ? `${Math.max(1, Math.round(sec))} sec` : `${Math.round(sec / 60)} min`);
const dayStr = (d = new Date()) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const yesterdayStr = () => { const d = new Date(); d.setDate(d.getDate() - 1); return dayStr(d); };
const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage full / blocked */ } },
  del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
};

/* =========================================================================
 * 1. URL params: lang, mock, token
 * ========================================================================= */
const Q = new URLSearchParams(location.search);
const LANG = Q.get('lang') === 'zh' ? 'zh' : 'en';
let MOCK = Q.get('mock') === '1';
/* 11-11 a second UI kept beside the classic one: ?ui=narra — product name "narra", lyric-style player (review with 阿炫):
 * full-bleed scene picture behind, the story scrolling like lyrics (earlier lines dim, the current one bright), no cover box or
 * big title, call + share at the top right, the listening mode in the bottom toolbar, a small voice bubble at each choice point. */
const NARRA = Q.get('ui') === 'narra';
const BRAND = NARRA ? 'narra' : 'Unscripted Audio';
if (NARRA) { document.documentElement.classList.add('narra'); document.title = 'narra'; }
if (Q.has('k')) {
  store.set('ua.k', Q.get('k'));
  Q.delete('k');
  const qs = Q.toString();
  history.replaceState(history.state, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
}
const TOKEN = store.get('ua.k', '') || '';
// Voice engine test switch (11-08): &tts=turbo (Eleven v4 Turbo, low-latency) / flash (Eleven Turbo v2.5) / v4 (default). Remembered per language.
// Stories voiced with a test engine are kept apart from the normal ones (own session key), so switching starts fresh.
if (Q.has('tts')) store.set('ua.tts.' + LANG, ['turbo', 'flash'].includes(Q.get('tts')) ? Q.get('tts') : 'v4');
const TTS = store.get('ua.tts.' + LANG, 'v4') || 'v4';
document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';

/* =========================================================================
 * 2. Embedded series metadata (data/series_base.json) + mock extras
 * ========================================================================= */
const SERIES_BASE = [{"id":"magnus","pack":"magnus","title":{"zh":"与狼为伍","en":"Running with Wolves"},"lead":{"zh":"Magnus · 狼人 Alpha","en":"Magnus · Werewolf Alpha"},"hook":{"zh":"十分钟后他就要订婚了，却在车库扣住了你的手腕。之后每一幕，都由你说的话实时生成。","en":"He gets engaged in ten minutes, yet he's holding your wrist in the garage. Every scene after this is generated live from what you say."},"tags":[{"zh":"狼人","en":"Werewolf"},{"zh":"命定之番","en":"Fated mate"},{"zh":"订婚前夜","en":"Engagement night"},{"zh":"第一视角","en":"First person"}],"genres":["Werewolf","Billionaire","Fated mates"],"accent":"#c9a227","cover":"covers/magnus.jpg","avatar":"avatars/magnus.jpg","name":"Magnus"},{"id":"rafael","pack":"rafael","title":{"zh":"这次，不是演的","en":"Not Pretending This Time"},"lead":{"zh":"Rafael Ortega · 摩托车店老板","en":"Rafael Ortega · Motorcycle shop owner"},"hook":{"zh":"朋友六年，室友三年。昨晚他替你挡前任，假扮了一次男朋友，还有一个吻。今天早上他承认：临时的是身份，不是心意。你怎么回答，由你决定。","en":"Friends for six years, roommates for three. Last night he played your boyfriend to get your ex off your back, and there was a kiss. This morning he admits the role was temporary, the feeling isn't. How you answer is up to you."},"tags":[{"zh":"室友","en":"Roommates"},{"zh":"假扮情侣","en":"Fake dating"},{"zh":"告白","en":"Confession"},{"zh":"第三视角","en":"Third person"}],"genres":["Romance","Friends to lovers","Fake dating"],"accent":"#c8743c","cover":"covers/rafael.jpg","avatar":"avatars/rafael.jpg","name":"Rafael"},{"id":"rowan","pack":"rowan","title":{"zh":"今天，再喜欢我一次","en":"Meet Me, Again"},"lead":{"zh":"Rowan · 修理工","en":"Rowan · Repairman"},"hook":{"zh":"海边温室的女主人隔着院门，拦下一个来修招牌的陌生人。他叫得出你的习惯，像早就认识你。他到底是谁、要不要让他进门，由你决定。","en":"Across the garden gate of her seaside greenhouse, she stops a stranger who came to fix the sign. He knows your habits, as if he has known you for a long time. Who he is, and whether he gets in, is up to you."},"tags":[{"zh":"海边温室","en":"Seaside greenhouse"},{"zh":"治愈","en":"Healing"},{"zh":"悬念","en":"Mystery"},{"zh":"第三视角","en":"Third person"}],"genres":["Romance","Healing","Mystery"],"accent":"#8aa36b","cover":"covers/rowan.jpg","avatar":"avatars/rowan.jpg","name":"Rowan"},{"id":"rian","pack":"rian","title":{"zh":"人鱼王子的假新娘","en":"The Sea Prince's Almost Bride"},"lead":{"zh":"Rian Thalys · 人鱼王子","en":"Rian Thalys · Merman prince"},"hook":{"zh":"为了找回被潮水卷走的好友，你跟着跳进海里，被人鱼王子救进海下王宫。守门的摄政官不放外人进来，他当众说你是“我未来的新娘”。接不接这出戏，由你决定。","en":"You dive after your best friend when the tide takes her, and a merman prince pulls you into his palace beneath the sea. When the regent won't let an outsider in, he tells the whole hall you're his future bride. Whether you play along is up to you."},"tags":[{"zh":"人鱼","en":"Merman"},{"zh":"假婚约","en":"Fake engagement"},{"zh":"海下王宫","en":"Undersea palace"},{"zh":"第三视角","en":"Third person"}],"genres":["Fantasy","Merman","Fake engagement"],"accent":"#6f8fd6","cover":"covers/rian.jpg","avatar":"avatars/rian.jpg","name":"Rian"},{"id":"island","pack":"island-liars","title":{"zh":"三真四假","en":"Four Liars, One Island"},"lead":{"zh":"Wes / Jasper · 七位男嘉宾","en":"Wes / Jasper · Seven bachelors"},"hook":{"zh":"海岛恋综，七个男嘉宾：三个是真千万富翁，四个是装富豪来骗奖金的。你选一个配对，一边心动一边验真假。最后谁是真的，看你怎么查。","en":"An island dating show with seven bachelors: three are real millionaires, four are faking it for the prize money. Pair up, fall for someone, and find out who's lying. What you uncover is up to you."},"tags":[{"zh":"恋综","en":"Dating show"},{"zh":"真假富豪","en":"Real or fake"},{"zh":"选男主","en":"Pick your guy"},{"zh":"第三视角","en":"Third person"}],"genres":["Reality show","Billionaire","Mystery"],"accent":"#d9a85c","cover":"covers/island.jpg","avatar":"avatars/island.jpg","name":"Jasper"},{"id":"lena","pack":"lena","title":{"zh":"别信这段直播","en":"Don't Trust This Feed"},"lead":{"zh":"Lena Hart · 失联的档案员","en":"Lena Hart · Missing archivist"},"hook":{"zh":"今晚 00:00，Lena 被锁的那层会放气。有人提前告诉了你，她自己还不知道。转播里的她一直说没事，那是昨晚录的。隔着手机带她出来，带上证据。赶不上，三分钟后“她”会打给你。","en":"At 00:00 tonight, gas fires on the floor where Lena is locked in. Someone told you. She doesn't know. On the feed she keeps saying she's fine, but that was recorded last night. Get her out, with proof. Miss it, and three minutes later \"she\" will call you."},"tags":[{"zh":"悬疑解谜","en":"Mystery"},{"zh":"午夜倒计时","en":"Countdown"},{"zh":"6 个结局","en":"6 endings"},{"zh":"失败可重来","en":"Retry with memory"}],"genres":["Thriller","Mystery","Countdown"],"accent":"#7f8fa6","cover":"covers/lena.jpg","avatar":"avatars/lena.jpg","name":"Lena"},{"id":"mii","pack":"mii","title":{"zh":"今天不要上班，咪养你","en":"No Work Today, Mii's Got You"},"lead":{"zh":"咪 · 三个月大的小奶猫","en":"Mii · a 3-month-old kitten"},"hook":{"zh":"休假日的早上，小奶猫咪决定今天由它来照顾你。去厨房、去公园、去电影院，你说去哪就去哪。","en":"On your day off, little Mii decides it's taking care of you today. Kitchen, park, cinema: wherever you say."},"tags":[{"zh":"治愈","en":"Cozy"},{"zh":"小奶猫","en":"Kitten"},{"zh":"日常","en":"Slice of life"},{"zh":"主人视角","en":"Owner POV"}],"genres":["Cozy","Pets","Slice of life"],"accent":"#e8a25a","cover":"covers/mii.jpg","avatar":"avatars/mii.jpg","name":"Mii"}];

const L = (o) => (o && typeof o === 'object' && !Array.isArray(o) && ('en' in o || 'zh' in o)) ? (o[LANG] != null ? o[LANG] : o.en) : o;

// Mock-only extras: fake stats, Ep1 cues/prompt/choices, cast. Ep1 audio = mock/line_a.mp3 (8.9 s).
const MX = {
  magnus: {
    stats: { plays: '1.2M', rating: 4.8 },
    ep1: { en: 'Ten Minutes in the Garage', zh: '车库里的十分钟' },
    cues: [
      ['NARR', '11:50 p.m. The garage lights hum. Someone grabs your wrist.', '晚上十一点五十分，车库的灯嗡嗡作响。有人扣住了你的手腕。'],
      ['Magnus', "Ten minutes. That's all I have before I'm promised to someone else.", '十分钟。十分钟后，我就是别人的未婚夫了。'],
      ['NARR', "His grip is warm. He isn't letting go.", '他的手很烫，没有松开的意思。'],
    ],
    prompt: { en: 'He holds your wrist, waiting for your answer.', zh: '他扣住你的手腕，等你回答。' },
    choices: { en: ["I won't tell anyone.", 'Let go of me.'], zh: ['我不会说出去。', '放开我。'] },
    cast: [['Magnus', { en: 'Werewolf Alpha', zh: '狼人 Alpha' }, { en: 'Brian', zh: 'Guan Tang Bao' }], ['Narrator', { en: 'Narrator (you)', zh: '旁白（你）' }, { en: 'Aria', zh: 'Xiao Yu' }]],
  },
  rafael: {
    stats: { plays: '864K', rating: 4.7 },
    ep1: { en: 'The Temporary Boyfriend', zh: '临时男友' },
    cues: [
      ['NARR', "Morning. Two mugs on the counter. Rafael hasn't touched his.", '早上，台面上两杯咖啡，Rafael 那杯一口没动。'],
      ['Rafael', "About last night… the boyfriend part was fake. The rest wasn't.", '昨晚……男朋友是假的，别的不是。'],
      ['NARR', 'He finally looks up at you.', '他终于抬头看你。'],
    ],
    prompt: { en: "He's waiting for you to say something.", zh: '他在等你开口。' },
    choices: { en: ['Then kiss me again. For real.', "We can't. We live together."], zh: ['那就再吻我一次，这次来真的。', '不行，我们住在一起。'] },
    cast: [['Rafael Ortega', { en: 'Motorcycle shop owner', zh: '摩托车店老板' }, { en: 'Adam', zh: 'Lin Feng' }], ['Daniel', { en: 'Your ex', zh: '前任' }, { en: 'Josh', zh: 'Chen Mo' }], ['Narrator', { en: 'Narrator', zh: '旁白' }, { en: 'Aria', zh: 'Xiao Yu' }]],
  },
  rowan: {
    stats: { plays: '542K', rating: 4.8 },
    ep1: { en: 'The Stranger at the Gate', zh: '院门外的陌生人' },
    cues: [
      ['NARR', 'The sign over the greenhouse gate creaks in the sea wind.', '海风里，温室门上的招牌吱呀作响。'],
      ['Rowan', "You still water the roses before breakfast, don't you?", '你还是早饭前先给玫瑰浇水，对吧？'],
      ['NARR', 'You never told him that.', '你从来没告诉过他。'],
    ],
    prompt: { en: "He's standing at the gate. Do you let him in?", zh: '他站在院门外。让不让他进来？' },
    choices: { en: ['Open the gate.', 'Who told you that?'], zh: ['打开院门。', '谁告诉你的？'] },
    cast: [['Rowan', { en: 'Repairman', zh: '修理工' }, { en: 'Callum', zh: 'Bai Ye' }], ['Narrator', { en: 'Narrator', zh: '旁白' }, { en: 'Aria', zh: 'Xiao Yu' }]],
  },
  rian: {
    stats: { plays: '993K', rating: 4.9 },
    ep1: { en: 'A Bride Before the Court', zh: '当众的新娘' },
    cues: [
      ['NARR', 'The throne hall goes silent. Every eye in the sea is on you.', '王座大厅一片寂静，整片海的目光都落在你身上。'],
      ['Rian', 'She is my future bride. Anyone who doubts it can ask her.', '她是我未来的新娘。谁有疑问，可以问她。'],
      ['NARR', 'The regent turns to you.', '摄政官转向了你。'],
    ],
    prompt: { en: "The regent asks if it's true.", zh: '摄政官问你：是真的吗？' },
    choices: { en: ["It's true. I'm his.", "I've never seen him before."], zh: ['是真的，我是他的人。', '我根本不认识他。'] },
    cast: [['Rian Thalys', { en: 'Merman prince', zh: '人鱼王子' }, { en: 'Liam', zh: 'Yun Shen' }], ['Regent Cassian', { en: 'Regent of the palace', zh: '摄政官' }, { en: 'George', zh: 'Lao Zhou' }], ['Narrator', { en: 'Narrator', zh: '旁白' }, { en: 'Aria', zh: 'Xiao Yu' }]],
  },
  island: {
    stats: { plays: '1.5M', rating: 4.6 },
    ep1: { en: 'First Night on the Island', zh: '登岛第一夜' },
    cues: [
      ['NARR', 'Seven men. One bonfire. Four of them are lying.', '七个男人，一堆篝火，其中四个在撒谎。'],
      ['Jasper', 'So which one of us did you come here for?', '所以，你是为我们当中哪一个来的？'],
      ['NARR', 'The host hands you the first pairing card.', '主持人把第一张配对卡递给你。'],
    ],
    prompt: { en: 'Who gets your first pairing card?', zh: '第一张配对卡给谁？' },
    choices: { en: ['Jasper, the quiet one.', 'Wes, the loud one.'], zh: ['给安静的 Jasper。', '给张扬的 Wes。'] },
    cast: [['Jasper', { en: 'Bachelor #3', zh: '三号男嘉宾' }, { en: 'Eric', zh: 'Su Hang' }], ['Wes', { en: 'Bachelor #5', zh: '五号男嘉宾' }, { en: 'Chris', zh: 'Ah Jie' }], ['Host', { en: 'Show host', zh: '主持人' }, { en: 'Sarah', zh: 'Mei Lin' }]],
  },
  lena: {
    stats: { plays: '721K', rating: 4.7 },
    ep1: { en: 'Countdown to 00:00', zh: '00:00 倒计时' },
    cues: [
      ['NARR', '23:41. The feed flickers. Lena waves at the camera.', '23:41，转播画面闪了一下，Lena 对着镜头挥手。'],
      ['Lena', "I'm fine, really. Nobody's coming up here tonight.", '我没事，真的。今晚不会有人上来。'],
      ['NARR', 'But that clip is from last night.', '可这段画面是昨晚录的。'],
    ],
    prompt: { en: 'You have nineteen minutes. What do you do first?', zh: '还剩十九分钟。你先做什么？' },
    choices: { en: ['Call her real number.', 'Search the building plans.'], zh: ['打她真正的号码。', '查大楼平面图。'] },
    cast: [['Lena Hart', { en: 'Missing archivist', zh: '失联的档案员' }, { en: 'Jessica', zh: 'Qing Qing' }], ['Voss', { en: 'Building security', zh: '大楼保安' }, { en: 'Bill', zh: 'Lao Wang' }], ['Hollis', { en: 'The caller', zh: '来电的人' }, { en: 'Daniel', zh: 'Ye Chen' }]],
  },
  mii: {
    stats: { plays: '436K', rating: 4.9 },
    ep1: { en: "Mii's First Shift", zh: '咪的上班第一天' },
    cues: [
      ['NARR', 'Your alarm never rings. Someone small turned it off.', '闹钟没有响。有个小家伙把它关掉了。'],
      ['Mii', "Mrrp. No work today. I'm in charge now.", '喵呜。今天不上班，我说了算。'],
      ['NARR', 'Mii sits on your chest, very serious.', '咪一本正经地坐在你胸口。'],
    ],
    prompt: { en: 'Where should Mii take you first?', zh: '咪先带你去哪？' },
    choices: { en: ['The kitchen. Breakfast first.', 'The park. Sunshine!'], zh: ['厨房，先吃早饭。', '公园，晒太阳！'] },
    cast: [['Mii', { en: 'A 3-month-old kitten', zh: '三个月大的小奶猫' }, { en: 'Lily', zh: 'Tang Tang' }], ['Narrator', { en: 'Narrator', zh: '旁白' }, { en: 'Aria', zh: 'Xiao Yu' }]],
  },
};
const MOCK_CALLERS = {
  magnus: [['Magnus', { en: 'Magnus Thorne', zh: '马格努斯·索恩' }]],
  rafael: [['Rafael', { en: 'Rafael Ortega', zh: '拉斐尔·奥尔特加' }]],
  rowan: [['Rowan', { en: 'Rowan', zh: '洛温' }]],
  rian: [['Rian', { en: 'Rian Thalys', zh: '雷恩·瑟里斯' }]],
  island: [['Wes', { en: 'Wes', zh: '韦斯' }, { en: 'Bachelor A · says he runs a surf bar in San Diego', zh: '男嘉宾，男主 A，自称在圣地亚哥开冲浪酒吧' }],
    ['Jasper', { en: 'Jasper', zh: '贾斯珀' }, { en: 'Bachelor B · quiet, changes the subject when money comes up', zh: '男嘉宾，男主 B，话少冷淡，被问到钱就转开话题' }]],
  lena: [['Lena', { en: 'Lena Hart', zh: 'Lena' }]],
  mii: [['Mii', { en: 'Mii', zh: '咪' }]],
};
const MOCK_SYN_TAIL = {
  en: 'Episode 1 is a fully produced audio drama. From Episode 2 on, every episode is written and voiced live from the choice you make at the end of the last one, and the characters call you by your name.',
  zh: '第 1 集是完整制作的有声剧。从第 2 集起，每一集都按你在上一集结尾的选择实时写出、实时配音，角色会叫你的名字。',
};
const MOCK_EP_TITLES = {
  en: ['What You Said', 'One Step Closer', 'The Door Opens', "Don't Look Away", 'Say My Name', 'Before Midnight', 'The Last Choice'],
  zh: ['你说的那句话', '再近一步', '门开了', '别移开视线', '叫我的名字', '午夜之前', '最后的选择'],
};
const MOCK_CHOICES = {
  en: [['Tell the truth.', 'Keep it a secret.'], ['Step closer.', 'Walk away.'], ["Ask what they're hiding.", 'Trust them for now.'], ['Stay.', "Leave before it's too late."]],
  zh: [['说实话。', '先瞒着。'], ['再靠近一点。', '转身离开。'], ['问他到底瞒了什么。', '先相信他。'], ['留下。', '趁还来得及，走。']],
};

/* =========================================================================
 * 3. Local state (localStorage, try/catch wrapped)
 * ========================================================================= */
const DEF = () => ({
  v: 1, onboarded: false, name: '', genres: [], speed: 1, coins: 0, vip: false, autoUnlock: false,
  checkin: { last: null, streak: 0 },
  tasks: { date: null, listen: 0, newSeries: 0, choices: 0, share: 0, claimed: {} },
  ledger: [], unlocks: {}, saved: [], progress: {}, hist: [], played: [], waitFree: {}, sleep: null,
  calls: [], callsUsed: {}, inDay: {}, callSpeed: 1,
});
let S = Object.assign(DEF(), store.get('ua.state', {}) || {});
let SESS = store.get('ua.sess', {}) || {};
let saveT = 0;
const save = (now) => {
  clearTimeout(saveT);
  const f = () => { store.set('ua.state', S); store.set('ua.sess', SESS); };
  if (now) f(); else saveT = setTimeout(f, 250);
};
window.addEventListener('pagehide', () => save(true));
document.addEventListener('visibilitychange', () => { if (document.hidden) save(true); });

const skey = (id) => `${MOCK ? 'm' : 'r'}:${id}:${LANG}${TTS !== 'v4' ? ':' + TTS : ''}`;
const getSess = (id) => SESS[skey(id)] || null;

function ensureToday() {
  const t = dayStr();
  if (S.tasks.date !== t) S.tasks = { date: t, listen: 0, newSeries: 0, choices: 0, share: 0, call: 0, claimed: {} };
}
function addCoins(delta, label) {
  S.coins = Math.max(0, (S.coins || 0) + delta);
  S.ledger.unshift({ t: Date.now(), d: delta, l: label });
  S.ledger = S.ledger.slice(0, 60);
  save();
  refreshCoins();
}
const PRICE = 10;
const FREE_EPS = 3;
const isUnlocked = (id, n) => S.vip || n <= FREE_EPS || ((S.unlocks[id] || []).indexOf(n) >= 0);
function markUnlocked(id, n) { (S.unlocks[id] = S.unlocks[id] || []).push(n); save(); }

/* =========================================================================
 * 4. APIs: real (contract) + mock
 * ========================================================================= */
/* API base: GitHub Pages serves the app statically and puts relay.json ({"base": tunnel URL}) next to it.
 * No relay.json → same origin (the local relay serves the page itself). */
let API_BASE = '';
let API_BASES = [];   // 11-09: two independent tunnels; if one drops (they do, for ~10 s at a time) switch to the other at once
async function loadRelay() {
  try {
    let j = null;
    if (window.__relayP) { j = await window.__relayP; window.__relayP = null; }  // started in index.html, before app.js loaded
    else { const r = await fetch('relay.json?t=' + Date.now(), { cache: 'no-store' }); j = r.ok ? await r.json() : null; }
    const clean = (x) => String(x || '').trim().replace(/\/+$/, '');
    API_BASES = ((j && j.bases) || (j && j.base ? [j.base] : [])).map(clean).filter(Boolean);
    if (!API_BASES.includes(API_BASE)) API_BASE = API_BASES[0] || '';
    if (API_BASE) store.set('ua.relay', API_BASE);
    return !!API_BASE;
  } catch (e) { API_BASE = API_BASE || ''; return !!API_BASE; }
}
/** two tunnels: ask both for /health once and stay on whichever answers first (one of them is often seconds slower) */
function pickFastBase() {
  if (API_BASES.length < 2) return;
  let done = false;
  API_BASES.forEach((b) => { fetch(b + '/health', withTimeout({ cache: 'no-store' }, 8000)).then((r) => { if (r.ok && !done) { done = true; if (API_BASE !== b) { API_BASE = b; store.set('ua.relay', b); } } }).catch(() => {}); });
}
function nextBase() {
  if (API_BASES.length < 2) return false;
  API_BASE = API_BASES[(API_BASES.indexOf(API_BASE) + 1) % API_BASES.length];
  store.set('ua.relay', API_BASE);
  return true;
}
let relayP = null;
function reconnect() {
  if (nextBase()) return Promise.resolve(true);   // the other tunnel: no wait
  if (!relayP) {
    toast(tz('Reconnecting…', '正在重新连接…'));
    relayP = loadRelay();
    relayP.finally(() => setTimeout(() => { relayP = null; }, 4000));
  }
  return relayP;
}
const apiUrl = (path) => (API_BASE ? API_BASE + '/' + path.replace(/^\//, '') : new URL(path, location.href).toString());
/** Server-relative media URLs ("/x.mp3") must hit the API host when the page is on Pages. */
const absUrl = (u) => (u && API_BASE && u[0] === '/' && u[1] !== '/' ? API_BASE + u : u);
/** fetch with one retry after re-reading relay.json when the tunnel may have rotated (network error only). */
function withTimeout(init, ms) {  // a stalled tunnel request must not hang the player (phones wait 60 s+ by default); short, so we fail over fast
  if (init && init.signal) return init;
  const c = new AbortController(); setTimeout(() => c.abort(), ms || ((init && init.method === 'POST') ? 25000 : 12000));
  return Object.assign({}, init, { signal: c.signal });
}
/* 11-11 slow links (she tested on ~30 KB/s to GitHub / Cloudflare): everything heavy that used to preload in parallel
 * (five Episode-1 files, 40 scene clips) starved the page itself. NET keeps a rough picture of the link so preloading
 * only happens when it can afford to: kbs = download speed of the page's own files, rt = a plain API round trip. */
const NET = { kbs: 0, rt: 0 };
function netProbe() {
  try {
    const v = performance.getEntriesByType('resource')
      .filter((e) => /\/(app\.js|style\.css|i18n\.js|covers\/)/.test(e.name) && e.transferSize > 6000 && e.responseEnd > e.responseStart)
      .map((e) => e.transferSize / 1024 / Math.max(0.03, (e.responseEnd - e.responseStart) / 1000)).sort((a, b) => b - a);
    if (v.length) NET.kbs = v[0];
  } catch (e) { /* ignore */ }
}
const slowNet = () => {
  if (Q.get('net') === 'slow') return true;   // test switches: &net=slow behaves as on a slow link, &net=fast as on a good one
  if (Q.get('net') === 'fast') return false;
  if (!NET.kbs) netProbe();
  const c = navigator.connection;
  return (NET.kbs > 0 && NET.kbs < 150) || NET.rt > 2500 || !!(c && (c.saveData || /(^|-)2g|3g/.test(c.effectiveType || '')));
};
async function apiFetch(build, init, ms) {
  try {
    const t0 = performance.now();
    const r = await fetch(build(), withTimeout(init, ms));
    if (!ms && !(init && init.method === 'POST')) { const dt = performance.now() - t0; NET.rt = NET.rt ? NET.rt * 0.5 + dt * 0.5 : dt; }
    if (r.status === 502 || r.status === 530 || r.status === 1033) throw new Error('tunnel ' + r.status);   // Cloudflare: tunnel is down
    return r;
  } catch (e) {
    if (e && e.name === 'AbortError' && init && init.signal) throw e;
    await reconnect();
    return fetch(build(), withTimeout(init, ms));
  }
}
const RealAPI = {
  async get(path, params, withLang) {
    const build = () => {
      const u = new URL(apiUrl(path));
      if (withLang) u.searchParams.set('lang', LANG);
      u.searchParams.set('k', TOKEN);
      Object.entries(params || {}).forEach(([k, v]) => { if (v != null) u.searchParams.set(k, v); });
      return u.toString();
    };
    const r = await apiFetch(build, { cache: 'no-store' }, params && params.wait ? 14000 : 0);
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  },
  async post(path, body) {
    const r = await apiFetch(() => apiUrl(path), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ k: TOKEN }, body)),
    });
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  },
  series() { return this.get('api/series', null, true); },
  seriesDetail(id) { return this.get('api/series/' + encodeURIComponent(id), null, true); },
  play({ series, name }) { return this.post('api/play', { series, lang: LANG, name, me: S.me || '', tts: TTS }); },
  next({ sid, text, via }) { return this.post('api/next', { sid, text, via }); },
  job(id, have) { return this.get('api/job', have == null ? { id } : { id, wait: 8, have }, false); },  // have: long-poll until a new line is voiced
  async callChunk(cid, blob, q) { return this.callSay(cid, blob, q, 'api/call/chunk'); },
  async callSay(cid, blob, q, path) {
    const r = await apiFetch(() => { const u = new URL(apiUrl(path || 'api/call/say')); u.searchParams.set('k', TOKEN); u.searchParams.set('cid', cid); Object.entries(q || {}).forEach(([k, v]) => u.searchParams.set(k, v)); return u.toString(); },
      { method: 'POST', headers: { 'Content-Type': blob.type || 'audio/wav' }, body: blob });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  },
  ep(sid, n) { return this.get('api/ep', { sid, n }, false); },
  specs(sid) { return this.get('api/specs', { sid }, false); },
  cue(sid, n) { return this.get('api/cue', { sid, n }, false); },
  wish(sid, text) { return this.post('api/wish', { sid, text }); },
  async asr(blob, opt) {   // opt.partial: what she has said so far, shown while she is still talking (never starts the next episode)
    const part = !!(opt && opt.partial);
    const r = await apiFetch(() => { const u = new URL(apiUrl('api/asr')); u.searchParams.set('k', TOKEN); u.searchParams.set('lang', LANG); const ss = P.id && getSess(P.id); if (ss && ss.sid) u.searchParams.set('sid', ss.sid); if (part) u.searchParams.set('partial', '1'); else if (P.needChoice) u.searchParams.set('go', '1'); return u.toString(); },
      { method: 'POST', headers: { 'Content-Type': blob.type || 'audio/webm' }, body: blob });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  },
  fillers({ series, who }) { return this.get('api/call/fillers', { series, who }, true); },
  callStart({ series, who, sid, direction, ckey }) { return this.post('api/call/start', { series, lang: LANG, name: S.name || '', who, sid: sid || null, direction, me: S.me || '', tts: TTS, ckey }); },
  callTurn({ cid, text, via }) { return this.post('api/call/turn', { cid, text, via }); },
  callEnd({ cid, seconds }) { return this.post('api/call/end', { cid, seconds }); },
  callPrepare({ series, who, sid }) { return this.post('api/call/prepare', { series, lang: LANG, name: S.name || '', who, sid: sid || null, me: S.me || '', tts: TTS }); },
};

const MockAPI = {
  jobs: new Map(), sessions: new Map(), firstPlay: new Set(), seq: 0,
  shape(b) {
    const x = MX[b.id] || {};
    return {
      id: b.id, title: L(b.title), lead: L(b.lead), hook: L(b.hook), tags: (b.tags || []).map(L), genres: b.genres,
      accent: b.accent, cover: b.cover, avatar: b.avatar, name: b.name,
      stats: x.stats || { plays: '100K', rating: 4.5 }, ep1: { title: L(x.ep1) || 'Episode 1', dur: 8.9, ready: true },
      callers: (MOCK_CALLERS[b.id] || [[b.name, { en: b.name, zh: b.name }]]).map(([key, nm, role]) => ({ key, name: L(nm), role: role ? L(role) : L(b.lead) })),
    };
  },
  calls: new Map(),
  async specs() { return { n: 0, specs: {} }; },
  async callSay() { return { text: '' }; },
  async callChunk() { return { text: '' }; },
  async ep() { throw new Error('no episode'); },
  async cue() { await sleep(400); return { url: 'mock/line_a.mp3', text: 'Mock question: this way, or that way?' }; },
  async wish() { return { ok: true }; },
  async asr() { await sleep(600); return { text: '' }; },
  async fillers() { await sleep(300); return { urls: ['mock/line_c.mp3'], think: ['mock/line_a.mp3', 'mock/line_b.mp3'] }; },
  async callStart({ series, who, direction }) {
    await sleep(200);
    const cid = 'mc' + (++this.seq);
    this.calls.set(cid, { series, who, direction, n: 0, name: S.name || '' });
    return { cid, who, job: this.mockCallJob(cid, '', 'start') };
  },
  async callTurn({ cid, text, via }) {
    await sleep(200);
    if (!this.calls.has(cid)) throw new Error('call ended');
    return { job: this.mockCallJob(cid, text, via) };
  },
  async callEnd({ cid }) { this.calls.delete(cid); return { ok: true }; },
  mockCallJob(cid, text, via) {
    const c = this.calls.get(cid);
    c.n += 1;
    const zh = LANG === 'zh', nm = c.name || (zh ? '你' : 'you');
    const t = (text || '').trim().replace(/[。！？.!?]+$/, '');
    let lines;
    if (c.n === 1) {
      lines = c.direction === 'incoming'
        ? (zh ? [`${nm}？……是我。`, '我知道很晚了。就是想听听你的声音。', '你现在方便说话吗？'] : [`${nm}? …It's me.`, "I know it's late. I just wanted to hear your voice.", 'Can you talk right now?'])
        : (zh ? ['你打来了。', '我刚还在想，要不要先打给你。'] : ['You called.', 'I was just deciding whether to call you first.']);
    } else {
      const first = via === 'silence' || !t ? (zh ? '你不说话，我也听得见你在呼吸。' : "You're quiet. I can still hear you breathing.") : (zh ? `“${t}”……我记住了。` : `"${t}"… I'll remember that.`);
      const pool = zh ? [`${nm}，你那边现在在下雨吗？`, '下次见面，我想当面跟你说完这句话。', '别挂，再陪我一会儿。', '我有件事一直没告诉你。'] : [`${nm}, is it raining where you are?`, 'Next time I see you, I want to finish this sentence in person.', "Don't hang up. Stay a little longer.", "There's something I never told you."];
      lines = [first, pool[(c.n - 2) % pool.length]];
      if (c.n % 2 === 1) lines.push(pool[(c.n - 1) % pool.length]);
    }
    const hangup = c.n >= 6;
    if (hangup) lines = lines.slice(0, 1).concat([zh ? '我得挂了。明天，等我电话。' : "I have to go. Tomorrow — wait for my call."]);
    const files = ['mock/line_c.mp3', 'mock/line_b.mp3', 'mock/line_a.mp3'];
    const t0 = 1.0 + Math.random() * 0.6 + (c.n === 3 ? 8 : 0); // turn 3 is slow on purpose so the "let me think" clip plays
    const pc = zh ? [['我也想你了。', '你怎么这么晚还不睡？'], ['那你现在说。', '我在听。'], ['你在哪？', '别挂。'], ['明天见？', '晚安。']]
      : [['I missed you too.', 'Why are you still awake?'], ['Then tell me now.', "I'm listening."], ['Where are you?', "Don't hang up."], ['See you tomorrow?', 'Good night.']];
    const id = 'mj' + (++this.seq);
    this.jobs.set(id, { kind: 'call', t0: Date.now(), writeT: 0.5, times: lines.map((_, i) => t0 + i * 0.7), call: {
      lines: lines.map((x, i) => ({ who: c.who, text: x, url: files[i % 3] })), choices: hangup ? [] : pc[(c.n - 1) % pc.length], hangup } });
    return id;
  },
  async series() { await sleep(120); return SERIES_BASE.map((b) => this.shape(b)); },
  async seriesDetail(id) {
    await sleep(160);
    const b = SERIES_BASE.find((s) => s.id === id); if (!b) throw new Error('not found');
    const x = MX[id] || {};
    return Object.assign(this.shape(b), {
      synopsis: L(b.hook) + (LANG === 'zh' ? '' : ' ') + L(MOCK_SYN_TAIL),
      cast: (x.cast || []).map(([name, role, voice]) => ({ name, role: L(role), voice: L(voice) })),
    });
  },
  ep1(id) {
    const x = MX[id];
    const cues = x.cues.map((c, i) => ({ s: [0, 3.0, 6.3][i], e: [3.0, 6.3, 8.9][i], who: c[0], text: LANG === 'zh' ? c[2] : c[1] }));
    return { n: 1, title: L(x.ep1), kind: 'produced', audio: 'mock/line_a.mp3', dur: 8.9, cues, prompt: L(x.prompt), choices: L(x.choices) };
  },
  async play({ series, name }) {
    await sleep(200);
    const sid = `mock-${series}-${Date.now().toString(36)}`;
    this.sessions.set(sid, { series, n: 1, name: name || '' });
    const ep = this.ep1(series);
    if (!this.firstPlay.has(series)) { // first play of this series in this page: exercise the job path
      this.firstPlay.add(series);
      const id = 'mj' + (++this.seq);
      this.jobs.set(id, { kind: 'play', t0: Date.now(), ep });
      return { sid, job: id };
    }
    return { sid, ep };
  },
  restore(sid) { // page reloaded: rebuild mock session from what the app stored
    if (this.sessions.has(sid)) return this.sessions.get(sid);
    const key = Object.keys(SESS).find((k) => SESS[k] && SESS[k].sid === sid);
    if (!key) return null;
    const ss = SESS[key]; const last = ss.eps[ss.eps.length - 1];
    const s = { series: key.split(':')[1], n: last ? last.n : 1, name: S.name };
    this.sessions.set(sid, s); return s;
  },
  async next({ sid, text, via }) {
    await sleep(220);
    const s = this.restore(sid); if (!s) throw new Error('session expired');
    s.n += 1;
    const n = s.n;
    const b = SERIES_BASE.find((x) => x.id === s.series);
    const who = b.name, nm = s.name || (LANG === 'zh' ? '你' : 'you');
    const t = (text || '').trim().replace(/[。！？.!?]+$/, '');
    const zh = LANG === 'zh';
    const pool = zh ? [
      via === 'silence' || !t ? `你一个字也没说，${who}却好像听懂了。` : `你说：“${t}”。${who}一下子安静了。`,
      `${nm}，再说一遍。慢一点。`,
      '你们之间的距离，又近了一步。',
      `${nm}，你总是让我意外。`,
      '不远处有扇门开了。不是所有人都希望这件事顺利。',
      '留在我身边。不管接下来发生什么。',
    ] : [
      via === 'silence' || !t ? `You don't say a word. ${who} seems to hear it anyway.` : `You answer: “${t}”. ${who} goes very still.`,
      `${nm}. Say that again. Slower.`,
      'The distance between you closes by one more step.',
      `You keep surprising me, ${nm}.`,
      'Somewhere close, a door opens. Not everyone wants this to go well.',
      'Stay with me. Whatever happens next, stay.',
    ];
    const count = 4 + (n % 3); // 4–6 lines
    const files = ['mock/line_c.mp3', 'mock/line_a.mp3', 'mock/line_b.mp3'];
    const lines = [];
    for (let i = 0; i < count; i++) lines.push({ who: i % 2 === 0 ? 'NARR' : who, text: pool[i % pool.length], url: files[i % 3] });
    if (n === 3 && count > 4) lines[3].url = ''; // one failed line to exercise the "" skip rule
    // url arrival times (s): line 0 ≈1.3 s, line 1 deliberately late so the "writing next lines…" wait shows, rest by ≈4 s
    const t0 = 1.1 + Math.random() * 0.5;
    const times = lines.map((_, i) => (i === 0 ? t0 : i === 1 ? t0 + 4.9 : Math.min(4.2, t0 + 0.5 * i + Math.random() * 1.2)));
    const ch = L(MOCK_CHOICES)[(n - 2) % 4];
    const ending = n >= 8;
    const ep = {
      n, title: L(MOCK_EP_TITLES)[(n - 2) % 7], kind: 'live', lines,
      prompt: ending ? '' : (zh ? `${who}在等你的下一步。` : `${who} is waiting for what you do next.`),
      choices: ending ? [] : ch, ending,
    };
    const id = 'mj' + (++this.seq);
    this.jobs.set(id, { kind: 'next', t0: Date.now(), writeT: 0.6, times, ep });
    return { job: id };
  },
  async job(id) {
    await sleep(40);
    const j = this.jobs.get(id); if (!j) return { status: 'error', error: 'unknown job', ep: null };
    const el = (Date.now() - j.t0) / 1000;
    if (j.kind === 'call') {
      if (el < j.writeT) return { status: 'writing', error: null, call: { lines: [], choices: [], hangup: false } };
      const done = j.times.every((t) => el >= t);
      return { status: done ? 'done' : 'voicing', error: null, call: {
        lines: j.call.lines.map((ln, i) => ({ who: ln.who, text: ln.text, url: el >= j.times[i] ? ln.url : null })),
        choices: done ? j.call.choices : [], hangup: done ? j.call.hangup : false } };
    }
    if (j.kind === 'play') return el < 1.4 ? { status: 'voicing', error: null, ep: null } : { status: 'done', error: null, ep: clone(j.ep) };
    if (el < j.writeT) return { status: 'writing', error: null, ep: null };
    const done = j.times.every((t) => el >= t);
    const ep = { n: j.ep.n, title: j.ep.title, kind: 'live', lines: j.ep.lines.map((ln, i) => ({ who: ln.who, text: ln.text, url: el >= j.times[i] ? ln.url : null })) };
    if (done) Object.assign(ep, { prompt: j.ep.prompt, choices: j.ep.choices, ending: j.ep.ending });
    return { status: done ? 'done' : 'voicing', error: null, ep };
  },
};
let API = MOCK ? MockAPI : RealAPI;

/* =========================================================================
 * 5. Icons
 * ========================================================================= */
const ICON = {
  home: '<path d="M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1H15v-6.5H9V21H4.5a1 1 0 0 1-1-1z"/>',
  explore: '<circle cx="12" cy="12" r="9"/><path d="m15.8 8.2-2.3 5.3-5.3 2.3 2.3-5.3z"/>',
  library: '<rect x="3.5" y="4" width="4.5" height="16" rx="1"/><rect x="10" y="4" width="4.5" height="16" rx="1"/><path d="m16.6 5.4 3-.7 2.9 14.6-3 .7z"/>',
  rewards: '<rect x="3" y="8" width="18" height="4.5" rx="1"/><path d="M5 12.5V20h14v-7.5M12 8v12"/><path d="M12 8C10.5 5 6.5 4.3 6.5 6.5S10 8 12 8zm0 0c1.5-3 5.5-3.7 5.5-1.5S14 8 12 8z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
  play: '<path d="M8 5.6v12.8a1 1 0 0 0 1.53.85l10.2-6.4a1 1 0 0 0 0-1.7L9.53 4.75A1 1 0 0 0 8 5.6z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6.5" y="5" width="4" height="14" rx="1.3" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="4" height="14" rx="1.3" fill="currentColor" stroke="none"/>',
  back10: '<path d="M4.5 12.5a8 8 0 1 0 2.7-6"/><path d="M4 3.5v4.5h4.5"/><text x="13" y="15.6" font-size="7.4" font-weight="800" text-anchor="middle" fill="currentColor" stroke="none" font-family="system-ui, sans-serif">10</text>',
  fwd10: '<path d="M19.5 12.5a8 8 0 1 1-2.7-6"/><path d="M20 3.5v4.5h-4.5"/><text x="11" y="15.6" font-size="7.4" font-weight="800" text-anchor="middle" fill="currentColor" stroke="none" font-family="system-ui, sans-serif">10</text>',
  prev: '<path d="M6 5v14"/><path d="M18.5 6.2v11.6a.8.8 0 0 1-1.25.66L9.3 12.66a.8.8 0 0 1 0-1.32l7.95-5.8a.8.8 0 0 1 1.25.66z" fill="currentColor"/>',
  next: '<path d="M18 5v14"/><path d="M5.5 6.2v11.6a.8.8 0 0 0 1.25.66l7.95-5.8a.8.8 0 0 0 0-1.32L6.75 5.54a.8.8 0 0 0-1.25.66z" fill="currentColor"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.2" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="4.5" cy="18" r="1.2" fill="currentColor" stroke="none"/>',
  moon: '<path d="M20 14.6A8.2 8.2 0 1 1 9.4 4a6.6 6.6 0 0 0 10.6 10.6z"/>',
  share: '<path d="M12 3.5v12"/><path d="m7.5 8 4.5-4.5L16.5 8"/><path d="M5 13v5.5A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V13"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
  unlock: '<rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path d="M8 10.5V8a4 4 0 0 1 7.7-1.5"/>',
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V5.5a1.5 1.5 0 0 1 3 0V13M17 10.5a1.5 1.5 0 0 1 3 0V15a7 7 0 0 1-7 7h-1.2a6 6 0 0 1-4.6-2.2L4 16.2a1.5 1.5 0 0 1 2.3-1.9L8 16"/>',
  mic: '<rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  volume: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
  send: '<path d="M4.5 12 20 4.5 15 20l-3.2-6.8z"/><path d="m11.8 13.2 3.7-3.7"/>',
  close: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  down: '<path d="m6 9.5 6 6 6-6"/>',
  back: '<path d="m15 5-7 7 7 7"/>',
  chevR: '<path d="m9.5 5.5 6.5 6.5-6.5 6.5"/>',
  star: '<path d="m12 3.6 2.6 5.3 5.8.85-4.2 4.1 1 5.8L12 16.9l-5.2 2.75 1-5.8-4.2-4.1 5.8-.85z" fill="currentColor" stroke="none"/>',
  headphones: '<path d="M4 15.5V12a8 8 0 0 1 16 0v3.5"/><rect x="3" y="14" width="4.5" height="7" rx="1.6"/><rect x="16.5" y="14" width="4.5" height="7" rx="1.6"/>',
  trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.9 13h9.2l.9-13"/>',
  spark: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z"/><path d="M19 16.5l.8 1.9 1.7.6-1.7.7-.8 1.8-.7-1.8-1.8-.7 1.8-.6z"/>',
  crown: '<path d="M3.5 8.5 8 12l4-6.5 4 6.5 4.5-3.5-1.8 10H5.3z"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  tv: '<rect x="3" y="5" width="18" height="12" rx="2.2"/><path d="M8.5 20.5h7"/><path d="M10.3 8.6v4.8l4-2.4z" fill="currentColor"/>',
  hourglass: '<path d="M6.5 3.5h11M6.5 20.5h11M7.5 3.5c0 4.5 4.5 5.5 4.5 8.5s-4.5 4-4.5 8.5M16.5 3.5c0 4.5-4.5 5.5-4.5 8.5s4.5 4 4.5 8.5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.4 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.4-3.5-8.5S9.6 5.9 12 3.5z"/>',
  wave: '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10.5v3"/>',
  quote: '<path d="M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  restart: '<path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5"/><path d="M4.5 4v4.5H9"/>',
  pen: '<path d="M4 20l1-4.2L15.6 5.2a2 2 0 0 1 2.8 0l.4.4a2 2 0 0 1 0 2.8L8.2 19z"/><path d="M13.5 7.3l3.2 3.2"/>',
  bag: '<path d="M5.5 8h13l-1 12.5h-11z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
  phone: '<path d="M6.6 3.5h2.6l1.6 4.3-2.1 1.4a11.5 11.5 0 0 0 6.1 6.1l1.4-2.1 4.3 1.6v2.6a1.6 1.6 0 0 1-1.7 1.6A16.6 16.6 0 0 1 5 5.2a1.6 1.6 0 0 1 1.6-1.7z"/>',
  phoneDown: '<g transform="rotate(135 12 12)"><path d="M6.6 3.5h2.6l1.6 4.3-2.1 1.4a11.5 11.5 0 0 0 6.1 6.1l1.4-2.1 4.3 1.6v2.6a1.6 1.6 0 0 1-1.7 1.6A16.6 16.6 0 0 1 5 5.2a1.6 1.6 0 0 1 1.6-1.7z"/></g>',
  sparkles: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z"/>',
};
const ic = (name, cls = '') => `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ''}</svg>`;
const coinIc = (cls = '') => `<svg class="coin ${cls}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="url(#ua-coin)"/><circle cx="12" cy="12" r="7.2" fill="none" stroke="#B8711A" stroke-opacity=".55" stroke-width="1.3"/><path d="M14.9 9.3a3.6 3.6 0 1 0 0 5.4" fill="none" stroke="#8A4A0E" stroke-width="2.1" stroke-linecap="round"/></svg>`;
const LOGO = `<span class="logo-mark"><svg viewBox="0 0 24 24" fill="none" stroke="#140906" stroke-width="2.6" stroke-linecap="round"><path d="M5 10v4M9.5 6.5v11M14 9v6M18.5 7.5v9"/></svg></span>`;
const waveBars = (n = 18) => `<span class="wave">${Array.from({ length: n }, () => '<i></i>').join('')}</span>`;

/* =========================================================================
 * 6. Series data
 * ========================================================================= */
let SERIES = [];
const WELCOME = 100;  // coins every new listener starts with
/* shelf order: the Prota Top 10 batch (11-10) is woven in among the earlier series instead of trailing at the end;
 * any series not listed here goes after, in the server's order */
const SHELF_ORDER = ['magnus', 'reborn', 'rian', 'hellqueen', 'island', 'starmate', 'lena', 'crackhigh', 'rafael', 'mythborne', 'kael',
  'onestat', 'dorian', 'heroacad', 'villa', 'academia', 'rowan', 'mask', 'hear', 'mii', 'milo'];
const NEW_BATCH = ['reborn', 'hellqueen', 'crackhigh', 'onestat', 'mythborne', 'heroacad', 'starmate', 'academia'];
/** keep a shelf's order but alternate earlier series and the new batch, so neither clumps (taste-sorted rows stay roughly taste-sorted) */
/* 11-11 (2): she wants the photoreal series in front everywhere, the others after them (replaces the 11-10 interleaving).
 * &real=1 leaves the anime ones out altogether — for screen recordings. */
const STYLE_REAL = ['magnus', 'rafael', 'island', 'lena', 'kael', 'villa', 'hear', 'mask', 'milo', 'mii'];
const STYLE_SEMI = ['dorian', 'rian', 'rowan'];   // painted, semi-real
const REAL_ONLY = Q.get('real') === '1';
const styleRank = (id) => (STYLE_REAL.indexOf(id) >= 0 ? 0 : STYLE_SEMI.indexOf(id) >= 0 ? 1 : NEW_BATCH.indexOf(id) >= 0 ? 3 : 2);
/** keeps a shelf's own order inside each group, with the groups in the order real → painted → anime */
const weave = (list) => list.map((x, i) => [x, styleRank(x.id), i]).sort((p, q) => p[1] - q[1] || p[2] - q[2]).map((x) => x[0]);
const shelfSort = (list) => weave((REAL_ONLY ? list.filter((x) => NEW_BATCH.indexOf(x.id) < 0) : list)
  .map((x, i) => [x, SHELF_ORDER.indexOf(x.id), i]).sort((p, q) => (p[1] < 0 ? 999 + p[2] : p[1]) - (q[1] < 0 ? 999 + q[2] : q[1])).map((x) => x[0]));
const DETAIL = {};
const byId = (id) => SERIES.find((s) => s.id === id);
const GENRES = ['Werewolf', 'Billionaire', 'Romance', 'Fantasy', 'Adventure', 'Academy', 'Mystery', 'Thriller', 'Reality show', 'Cozy'];  // 11-10 Prota Top10 加冒险、学院
const GENRE_MAP = {
  Romance: ['Romance', 'Fated mates', 'Friends to lovers', 'Fake dating', 'Fake engagement'],
  Cozy: ['Cozy', 'Healing', 'Pets', 'Slice of life'],
  Fantasy: ['Fantasy', 'Merman', 'Werewolf', 'Isekai'],
  Adventure: ['Adventure', 'Isekai', 'Action'],
  Academy: ['Academy', 'Superpowers'],
  Thriller: ['Thriller', 'Countdown'],
};
const GENRE_TILE = {
  Werewolf: '#6B4E16', Billionaire: '#2F4A3A', Romance: '#8A2E3B', Fantasy: '#2D3F7A',
  Mystery: '#3B3550', Thriller: '#4A2A2A', 'Reality show': '#7A4A1C', Cozy: '#6E5532', Adventure: '#5A4A1E', Academy: '#3A4A6E',
};
/** how well a series fits the tastes she picked in onboarding (first pick weighs most) + what she's been listening to */
function prefScore(s) {
  let n = 0;
  (S.genres || []).forEach((g, i) => {
    const w = i === 0 ? 1.5 : 1;   // her first pick weighs most
    if ((s.genres || []).indexOf(g) >= 0) n += 4 * w;                 // the series is literally that genre (Fantasy → the merman)
    else if ((s.genres || [])[0] && (GENRE_MAP[g] || []).indexOf(s.genres[0]) >= 0) n += 2.5 * w;  // its main genre belongs to it
    else if (matchGenre(s, g)) n += 1.5 * w;                          // a side tag belongs to it
  });
  const played = Object.values(S.progress || {}).map((x) => byId(x.id)).filter(Boolean);
  if (played.some((p) => p.id !== s.id && (p.genres || []).some((g) => (s.genres || []).indexOf(g) >= 0))) n += 0.5;
  return n;
}
const byPref = (list) => list.map((s, i) => [s, prefScore(s), i]).sort((a, b) => b[1] - a[1] || a[2] - b[2]).map((x) => x[0]);
const matchGenre = (s, g) => {
  const keys = GENRE_MAP[g] || [g];
  return (s.genres || []).some((x) => keys.indexOf(x) >= 0) || (s.tags || []).some((t) => keys.indexOf(t) >= 0);
};
const coverOf = (s) => s.cover || `covers/${s.id}.jpg`;
/** small covers for cards (covers/t = 360 px ≈ 40 KB, the full one is ≈ 160 KB); falls back to the full cover if the small one is missing */
const thumbOf = (s) => { const c = coverOf(s); return /^covers\/[\w-]+\.jpg$/.test(c) ? c.replace('covers/', 'covers/t/') : c; };
/** super-resolved cover (covers/x/<id>.jpg, 1080 px wide) for the big spots — hero, series page, player — on a good link */
const bigCover = (s) => { const c = coverOf(s); return slowNet() ? thumbOf(s) : (/^covers\/[\w-]+\.jpg$/.test(c) ? c.replace('covers/', 'covers/x/') : c); };
const thumbImg = (s) => `<img src="${esc(thumbOf(s))}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${esc(coverOf(s))}'">`;
const motionOf = (s) => s.motion || (MOCK ? `motion/${s.id}.mp4` : null);
const avatarOf = (s) => s.avatar || `avatars/${s.id}.jpg`;

/* =========================================================================
 * 7. Toast / sheets / ad overlay
 * ========================================================================= */
let toastT = 0;
function toast(msg) {
  const t = $('#toast');
  t.innerHTML = msg;
  t.classList.add('on');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('on'), 2400);
}

const sheetStack = [];
function openSheet(html, opts = {}) {
  const root = $('#sheets');
  const el = document.createElement('div');
  el.className = 'sheet ' + (opts.cls || '');
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.innerHTML = '<div class="grab"></div>' + html;
  root.appendChild(el);
  const prev = sheetStack[sheetStack.length - 1];
  if (prev) prev.el.classList.add('under');
  const entry = Object.assign({ el }, opts);
  sheetStack.push(entry);
  root.classList.add('on'); syncPass();
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('on')));
  return entry;
}
function closeSheet(entry) {
  const i = entry ? sheetStack.indexOf(entry) : sheetStack.length - 1;
  if (i < 0) return;
  const [s] = sheetStack.splice(i, 1);
  s.el.classList.remove('on');
  setTimeout(() => s.el.remove(), 360);
  if (s.onClose) try { s.onClose(); } catch (e) { console.warn(e); }
  const top = sheetStack[sheetStack.length - 1];
  if (top) top.el.classList.remove('under');
  else $('#sheets').classList.remove('on');
  syncPass();
}
function syncPass() { const t = sheetStack[sheetStack.length - 1]; $('#sheets').classList.toggle('nr-pass', !!(t && t.mini)); }
function closeAllSheets() { while (sheetStack.length) closeSheet(); }
const topSheet = () => sheetStack[sheetStack.length - 1];
function refreshSheets() { sheetStack.forEach((s) => s.refresh && s.refresh()); }

/* =========================================================================
 * 8. Audio engine
 * ========================================================================= */
const audio = $('#voice');
const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
let audioPrimed = false;
let preloader = null;

/** Player state */
const P = {
  id: null,           // series id
  ep: null,           // episode object (reference into SESS eps)
  idx: 0,             // live: current line index
  want: false,        // user intends to be playing
  waiting: false,     // live: waiting for next url
  jobDone: true,      // live: job finished for current ep
  gen: null,          // {n, text, via} while next episode is being written
  needChoice: false,  // episode ended, waiting for her choice
  loading: false,     // Ep1 being prepared
  cur: '',            // current voice src
  lineStart: 0,       // live: accumulated seconds before current line
  upNext: null,       // replay autoplay countdown
};

function setAudioRate() {
  try {
    audio.defaultPlaybackRate = S.speed;
    audio.playbackRate = S.speed;
    audio.preservesPitch = true; audio.mozPreservesPitch = true; audio.webkitPreservesPitch = true;
  } catch (e) { /* ignore */ }
}

/** iOS: call synchronously inside a user gesture so later async play() calls are allowed. */
function primeAudio() {
  if (audioPrimed) return;
  audioPrimed = true;
  if (P.cur) return; // something already loaded via gesture
  try {
    audio.src = SILENT;
    const p = audio.play();
    if (p && p.then) p.then(() => { if (audio.src === SILENT || audio.src.startsWith('data:')) audio.pause(); }).catch(() => { audioPrimed = false; });
  } catch (e) { audioPrimed = false; }
}
document.addEventListener('pointerdown', () => primeAudio(), { capture: true, once: false, passive: true });

/* Line audio lives on Google storage (no CORS, 1–2.5 s to first byte from China), and phones re-download it when the
 * main <audio> switches lines even if a hidden <audio> preloaded it — that was the gap/stutter between lines.
 * Now every line is fetched once through the relay (/api/a, cached on the relay) into a local blob ahead of time;
 * the main element plays the blob with no network. Same-origin files (Episode 1, bed) play directly. */
const BLOB = new Map();
let lastTap = 0;
document.addEventListener('pointerdown', () => { lastTap = Date.now(); }, { capture: true, passive: true });
const blobable = (u) => !MOCK && !!u && /^https:\/\/storage\.googleapis\.com\//.test(u);
function fetchBlob(u) {
  if (!blobable(u)) return Promise.resolve(null);
  let r = BLOB.get(u);
  if (!r) {
    r = { obj: null };
    r.p = (async () => {
      for (let i = 0; i < 2 && !r.obj; i++) {
        try {
          const q = new URL(apiUrl('api/a')); q.searchParams.set('k', TOKEN); q.searchParams.set('u', u);
          const res = await fetch(q.toString(), withTimeout({}));
          if (res.ok) { const b = await res.blob(); if (b.size) r.obj = URL.createObjectURL(b.type ? b : new Blob([b], { type: 'audio/mpeg' })); }
        } catch (e) { /* retry once, then fall back to the direct URL */ }
      }
      return r.obj;
    })();
    BLOB.set(u, r);
    if (BLOB.size > 120) for (const [k, v] of BLOB) { if (BLOB.size <= 100) break; if (k !== P.cur && v.obj) { URL.revokeObjectURL(v.obj); BLOB.delete(k); } }
  }
  return r.p;
}
const blobNow = (u) => { const r = BLOB.get(u); return r && r.obj; };
/** Episode 1 lives next to the page (ep1/<id>.<lang>.mp3, ~2 MB): fetch the whole file into memory ahead of the tap,
 * so "Play now" starts with zero network (11-09: phones still waited on the first range request). Max 4 kept. */
const EP1_KEEP = [];
function fetchLocalBlob(u) {
  if (MOCK || !u || /^https?:/.test(u) || BLOB.has(u)) return;
  const r = { obj: null }; BLOB.set(u, r);
  r.p = fetch(absUrl(u)).then((x) => (x.ok ? x.blob() : null)).then((b) => { if (b && b.size) r.obj = URL.createObjectURL(b.type ? b : new Blob([b], { type: 'audio/mpeg' })); return r.obj; }).catch(() => { BLOB.delete(u); return null; });
  EP1_KEEP.push(u);
  while (EP1_KEEP.length > 4) { const k = EP1_KEEP.shift(); const o = BLOB.get(k); if (o && o.obj && k !== P.cur) { URL.revokeObjectURL(o.obj); BLOB.delete(k); } }
}
const srcFor = (u) => blobNow(u) || absUrl(u);
function loadSrc(url, at) {
  P.aux = false; P.auxEnd = null; audio.loop = false; audio.volume = 1;  // swap straight from the bed/question to the story (no pause: keeps the lock screen alive)
  P.cur = url;
  audio.src = srcFor(url);
  setAudioRate();
  if (at) {
    const seek = () => { try { audio.currentTime = at; } catch (e) { /* ignore */ } audio.removeEventListener('loadedmetadata', seek); };
    audio.addEventListener('loadedmetadata', seek);
  }
}
function doPlay() {
  if (callActive()) { P.want = false; updatePlayerUI(); toast(tz('On a call', '正在通话')); return; }
  P.want = true;
  if (P.cur && (audio.error || audio.networkState === 3 || WD.stuck)) { WD.stuck = false; reloadCurrent('tap'); updatePlayerUI(); return; }  // the element got stuck: start it fresh inside this tap
  const p = audio.play();
  if (p && p.catch) p.catch((err) => {
    if (err && err.name === 'NotAllowedError') { P.want = false; updatePlayerUI(); toast(tz('Tap play to start listening', '点一下播放开始收听')); }
  });
  updatePlayerUI();
}
function doPause() { if (WD.n >= 2) WD.stuck = true; P.want = false; P.pausedAt = Date.now(); audio.pause(); updatePlayerUI(); }
if (Q.has('debug')) window.__ua = { get P() { return P; }, audio, get C() { return C; }, get EAR() { return EAR; }, earFrame: (x) => earFrame(x), get callAudio() { return callAudio; }, get WD() { return WD; } };  // ?debug=1: inspect player state from the console
function togglePlay() {
  primeMic(); setTimeout(micHold, 0);
  if ((P.gen && !P.ep) || (P.loading && !P.ep)) { toast(tz(P.gen ? 'Writing your next episode — it starts on its own' : 'Starting Episode 1…', P.gen ? '正在写下一集，好了会自动播放' : '第 1 集马上开始…')); return; }
  // at a choice point the narrator's question / the quiet bed are on the player: a tap stops them (and the 5 s countdown) and opens the choices
  if (P.needChoice) { holdForHer(); if (P.aux) { try { audio.pause(); } catch (e) { /* ignore */ } } openChoiceSheet(); updatePlayerUI(); return; }
  if (!P.ep) return;
  if (P.want && (!audio.paused || P.waiting)) { doPause(); return; }
  if (P.ep.kind === 'live' && (P.waiting || !P.cur)) { P.want = true; liveAdvance(); updatePlayerUI(); return; }
  doPlay();
}
const isPlaying = () => P.want && (!audio.paused || P.waiting);

/** Start an episode (produced: one mp3 + cues; live: sequential lines). */
function playEpisode(id, ep, opts = {}) {
  cancelUpNext(); stopAutoCountdown(); hfStop(true);
  P.id = id; P.ep = ep; P.needChoice = false; P.waiting = false; P.loading = false;
  P.idx = opts.line || 0; P.lineStart = 0;
  P.jobDone = ep.kind !== 'live' || ep._done !== false;
  const s = byId(id);
  document.documentElement.style.setProperty('--accent', s ? s.accent : '#FF8448');
  logHistory(id, ep);
  if (ep.kind === 'produced' || ep.audio) {
    loadSrc(ep.audio, opts.at || 0);
    if (opts.autoplay !== false) doPlay();
  } else {
    P.want = opts.autoplay !== false;
    ep.durs = ep.durs || {};
    liveAdvance();
  }
  setMediaSession();
  renderPlayer();
  updatePlayerUI();
  renderMini();
  saveProgress();
}

function liveAdvance() {
  const ep = P.ep; if (!ep || ep.kind !== 'live') return;
  const lines = ep.lines || [];
  while (P.idx < lines.length && lines[P.idx].url === '') P.idx++;
  if (P.idx >= lines.length) {
    if (P.jobDone) { P.waiting = false; onEpisodeEnd(); }
    else { P.waiting = true; updatePlayerUI(); }
    return;
  }
  const ln = lines[P.idx];
  if (!ln.url) {
    P.waiting = true; updatePlayerUI();
    const e0 = ep, i0 = P.idx;
    setTimeout(() => { if (P.ep === e0 && P.idx === i0 && P.waiting && P.want && !lines[i0].url) keepAlive(); }, 700);   // no dead air while the line is voiced
    return;
  }
  if (blobable(ln.url) && !blobNow(ln.url) && P.blobWait !== ln.url && Date.now() - lastTap > 1200) {  // its local copy is on the way: wait up to 4 s for it (a direct download is no faster and would compete with it)
    P.blobWait = ln.url; P.waiting = true; updatePlayerUI();
    const ep0 = ep, i0 = P.idx;
    Promise.race([fetchBlob(ln.url), sleep(4000)]).then(() => { if (P.ep === ep0 && P.idx === i0 && P.waiting) liveAdvance(); });
    return;
  }
  P.blobWait = null;
  P.waiting = false;
  P.lineStart = 0;
  for (let i = 0; i < P.idx; i++) P.lineStart += (ep.durs && ep.durs[i]) || 0;
  loadSrc(ln.url, 0);
  if (P.want) doPlay();
  preloadNext(); warmLines(ep);
  renderVisual();
  saveProgress();
  setMediaSession();
  updatePlayerUI(true);
}
function preloadNext() {
  const lines = (P.ep && P.ep.lines) || [];
  let j = P.idx + 1;
  while (j < lines.length && lines[j].url === '') j++;
  const u = lines[j] && lines[j].url;
  if (!u) return;
  if (blobable(u)) { fetchBlob(u); return; }
  try {
    if (!preloader) { preloader = new Audio(); preloader.preload = 'auto'; preloader.muted = true; }
    if (preloader.dataset.u !== u) { preloader.dataset.u = u; preloader.src = absUrl(u); preloader.load(); }
  } catch (e) { /* ignore */ }
}

audio.addEventListener('ended', () => {
  if (P.aux) { const f = P.auxEnd; P.auxEnd = null; if (f) f(); return; }
  if (!P.cur || audio.src.startsWith('data:')) return;
  if (!P.ep) return;
  if (P.ep.kind === 'live') {
    P.ep.durs = P.ep.durs || {};
    if (isFinite(audio.duration)) P.ep.durs[P.idx] = audio.duration;
    P.idx += 1;
    while (P.ep.lines && P.ep.lines[P.idx] && P.ep.lines[P.idx].url === '') P.idx++; // skip failed lines before the gap
    P.waiting = true; // brief inter-line gap
    updatePlayerUI();
    setTimeout(liveAdvance, 120);
  } else {
    onEpisodeEnd();
  }
});
audio.addEventListener('loadedmetadata', () => {
  if (!P.aux && P.ep && P.ep.kind === 'live' && isFinite(audio.duration)) { P.ep.durs = P.ep.durs || {}; P.ep.durs[P.idx] = audio.duration; }
  updatePlayerUI();
});
audio.addEventListener('play', () => updatePlayerUI());
audio.addEventListener('pause', () => updatePlayerUI());
audio.addEventListener('timeupdate', () => { tickUI(); maybeSpecs(); if (P.ep && P.ep.visuals && !P.aux && playerOpen) renderVisual(); });

/* Speculative next episodes: the relay pre-writes the next episode for both choices while she listens.
 * Near the end of the episode we fetch them and warm the first line's audio, so tapping a choice
 * starts the next episode locally with no network round trip. */
const SPEC = { key: '', at: 0, n: 0, map: {}, warm: [] };
function maybeSpecs(force) {
  const ss = P.id && getSess(P.id); const ep = P.ep;
  if (!ss || !ss.sid || !ep || ep.ending || ss.eps[ss.eps.length - 1] !== ep) return;
  if (modeOf() === 'voice' && (ep.choices || []).length && (ep.kind !== 'live' || P.jobDone) && !CUE[ss.sid + ':' + ep.n]) fetchCue(ss.sid, ep.n);  // the narrator's question is ready long before the end (11-09)
  const key = ss.sid + ':' + (ep.n + 1);
  if (SPEC.key === key && Object.keys(SPEC.map).length >= Math.min(2, (ep.choices || []).length)) return;
  let near = !!force;
  if (!near && ep.kind === 'live') near = P.jobDone && P.idx >= Math.max(0, (ep.lines || []).length - 8);
  else if (!near && isFinite(audio.duration) && audio.duration > 0) near = audio.duration - audio.currentTime < 45;
  if (!near || Date.now() - SPEC.at < 6000) return;
  SPEC.at = Date.now();
  if (modeOf() === 'voice') fetchCue(ss.sid, ep.n);
  if (SPEC.key !== key) { SPEC.key = key; SPEC.map = {}; SPEC.n = ep.n + 1; SPEC.warm = []; }
  API.specs(ss.sid).then((r) => {
    if (!r || SPEC.key !== key || r.n !== ep.n + 1) return;
    if (r.bridge) noteBridge(ss.sid, ep.n, r.bridge);
    if (r.beats) noteBeats(ss.sid, ep.n, r.beats);
    Object.entries(r.specs || {}).forEach(([ch, sp]) => {
      if (SPEC.map[ch]) return;
      SPEC.map[ch] = sp;
      (sp.ep.lines || []).slice(0, 4).forEach((l) => {
        if (!l.url) return;
        if (blobable(l.url)) fetchBlob(l.url);
    else try { const a = new Audio(); a.preload = 'auto'; a.muted = true; a.src = absUrl(l.url); a.load(); SPEC.warm.push(a); } catch (e) { /* ignore */ }
      });
    });
  }).catch(() => { /* ignore: falls back to the normal path */ });
}
audio.addEventListener('error', () => {
  if (P.aux) { const f = P.auxEnd; P.auxEnd = null; if (f) f(); return; }
  if (!P.cur || audio.src.startsWith('data:')) return;
  if (P.ep && P.ep.kind === 'live') { P.idx += 1; setTimeout(liveAdvance, 120); }
  else toast('Could not load this episode audio');
});

/* Watchdog (11-09): "playing" but the clock hasn't moved for 4 s (stalled load, iOS audio-session hiccup) → reload the same
 * audio at the same spot; the second time, try the other copy of Episode 1 (storage) if there is one. */
const WD = { t: -1, n: 0, tries: 0 };
function reloadCurrent(why) {
  if (!P.cur) return;
  const ep = P.ep, t = audio.currentTime || 0, keep = P.cur;
  WD.tries += 1; WD.n = 0;
  const url = WD.tries >= 2 && ep && ep.kind !== 'live' && ep.audio_cdn && keep === ep.audio ? ep.audio_cdn : keep;
  if (WD.tries === 1 && why !== 'tap') toast(tz('Connection hiccup — reloading the audio…', '网络卡了一下，正在重新加载…'));
  loadSrc(url, t > 0.5 ? t : 0); P.cur = keep;
  if (P.want) { const p = audio.play(); if (p && p.catch) p.catch(() => {}); }
}
setInterval(() => {
  const on = P.want && P.cur && !P.aux && !P.waiting && !audio.paused && !audio.src.startsWith('data:');
  if (!on) { WD.n = 0; WD.t = -1; return; }
  if (Math.abs(audio.currentTime - WD.t) < 0.05) { if (++WD.n >= (audio.currentTime < 0.05 ? 2 : 4)) reloadCurrent(); }   // stuck at 0:00 → rebuild after 2 s
  else { WD.n = 0; WD.t = audio.currentTime; if (audio.currentTime > 1) WD.tries = 0; }
}, 1000);

/* Listening time (task), sleep timer, progress persistence */
let lastTick = 0;
setInterval(() => {
  const playing = P.cur && !audio.paused && !audio.src.startsWith('data:');
  if (playing) {
    ensureToday();
    S.tasks.listen += 1;
    if (++lastTick % 5 === 0) { saveProgress(); save(); }
  }
  if (S.sleep && S.sleep.until && Date.now() >= S.sleep.until) {
    S.sleep = null; save();
    if (isPlaying()) { doPause(); toast(`${ic('moon', 'sm')} Sleep timer: paused`); }
  }
  updateSleepTool();
}, 1000);

function epFraction() {
  const ep = P.ep; if (!ep) return 0;
  if (ep.kind !== 'live') {
    const d = audio.duration || ep.dur || 0;
    return d ? clamp(audio.currentTime / d, 0, 1) : 0;
  }
  const n = (ep.lines || []).length || 1;
  const frac = audio.duration && P.cur && !P.waiting ? clamp(audio.currentTime / audio.duration, 0, 1) : 0;
  return clamp((P.idx + frac) / n, 0, 1);
}
function saveProgress() {
  if (!P.id || !P.ep) return;
  const k = skey(P.id);
  const pct = P.needChoice ? 1 : epFraction();
  S.progress[k] = {
    id: P.id, ep: P.ep.n, title: P.ep.title, pct, t: P.ep.kind === 'live' ? 0 : audio.currentTime || 0,
    line: P.ep.kind === 'live' ? P.idx : 0, at: Date.now(), needChoice: P.needChoice,
  };
  save();
}
function logHistory(id, ep) {
  const k = skey(id);
  const h0 = S.hist[0];
  if (h0 && h0.k === k && h0.n === ep.n) { h0.at = Date.now(); return; }
  S.hist.unshift({ k, id, n: ep.n, title: ep.title, at: Date.now() });
  S.hist = S.hist.slice(0, 50);
  save();
}

/* Media Session */
function setMediaSession() {
  if (!('mediaSession' in navigator) || !P.ep) return;
  const s = byId(P.id); if (!s) return;
  try {
    const art = new URL(coverOf(s), location.href).toString();
    navigator.mediaSession.metadata = new MediaMetadata({
      title: `Ep ${P.ep.n} · ${P.ep.title || ''}`, artist: s.title, album: BRAND,
      artwork: [{ src: art, sizes: '720x1280', type: 'image/jpeg' }],
    });
  } catch (e) { /* ignore */ }
}
if ('mediaSession' in navigator) {
  const ms = navigator.mediaSession;
  const h = (a, f) => { try { ms.setActionHandler(a, f); } catch (e) { /* unsupported */ } };
  h('play', () => { if (P.ep && !P.needChoice) { P.want = true; P.ep.kind === 'live' && P.waiting ? liveAdvance() : doPlay(); } });
  h('pause', () => doPause());
  h('seekbackward', () => skip(-10));
  h('seekforward', () => skip(10));
  // headphone / lock-screen buttons at a cliffhanger: next = answer by voice (or let it carry on), previous = hear the question again
  h('previoustrack', () => { if (P.needChoice && modeOf() === 'voice') startHandsFree(); else prevEpisode(); });
  h('nexttrack', () => { if (P.needChoice) { if (VOICE_OK && modeOf() !== 'tap') hfListen(); else continueOnItsOwn(); } else nextEpisode(); });
  h('seekto', (d) => { if (P.ep && P.ep.kind !== 'live' && d && isFinite(d.seekTime)) audio.currentTime = d.seekTime; });
}

function skip(sec) {
  if (!P.ep || !P.cur) return;
  VS.fastUntil = Date.now() + 1500;
  const d = audio.duration || 0;
  if (P.ep.kind !== 'live') { audio.currentTime = clamp(audio.currentTime + sec, 0, Math.max(0, d - 0.2)); tickUI(); return; }
  if (sec < 0) {
    if (audio.currentTime > 2) audio.currentTime = Math.max(0, audio.currentTime + sec);
    else { let j = P.idx - 1; while (j >= 0 && P.ep.lines[j].url === '') j--; if (j >= 0) { P.idx = j; liveAdvance(); } else audio.currentTime = 0; }
  } else {
    if (d && audio.currentTime + sec < d - 0.3) audio.currentTime += sec;
    else { audio.pause(); P.idx += 1; liveAdvance(); }
  }
  tickUI();
}

/* =========================================================================
 * 9. Story flow: start / resume / episode end / choice / generating
 * ========================================================================= */
function recordStart(id) {
  if (S.played.indexOf(id) < 0) {
    S.played.push(id);
    ensureToday();
    S.tasks.newSeries = 1;
  }
  save();
}

async function newSession(id) {
  const s = byId(id); if (!s) return;
  primeAudio(); primeMic(); setTimeout(micHold, 0);
  cancelGen();
  audio.pause();
  P.id = id; P.ep = null; P.loading = true; P.needChoice = false; P.want = true; P.cur = '';
  document.documentElement.style.setProperty('--accent', s.accent);
  renderPlayer(); updatePlayerUI(); renderMini(); openPlayer();
  // Instant start: Episode 1 is pre-produced, so play its audio right away (full script from this device's cache,
  // or audio-only from the series list) and merge the session / cues / choices when /api/play comes back through the tunnel.
  const k1 = 'ua.ep1.' + id + '.' + LANG;
  const cached = store.get(k1, null);
  const audioUrl = (s.ep1 && s.ep1.audio) || (cached && cached.audio) || (!MOCK ? `ep1/${id}.${LANG}.mp3` : null);
  let early = null;
  if (!MOCK && audioUrl) {
    early = (cached && cached.audio === audioUrl) ? JSON.parse(JSON.stringify(cached))
      : { n: 1, kind: 'produced', title: (s.ep1 && s.ep1.title) || 'Episode 1', audio: audioUrl, dur: (s.ep1 && s.ep1.dur) || 0, cues: [], choices: [], prompt: '', visuals: (s.ep1 && s.ep1.visuals) || undefined };
    early.kind = 'produced';
    SESS[skey(id)] = { sid: null, eps: [early], chosen: {}, job: null, started: Date.now() };
    recordStart(id); save();
    playEpisode(id, early);
  }
  const mine = getSess(id);
  const sidP = SIDP[skey(id)] = (async () => {
    // 11-11 the tunnel can take 10–25 s or drop a request; Episode 1 is already playing from the page's own file,
    // so keep asking in the background instead of giving up after one try
    const waits = early ? [0, 1500, 3000, 6000, 10000, 15000] : [0, 2000];
    let err = null;
    for (let i = 0; i < waits.length; i++) {
      if (waits[i]) await sleep(waits[i]);
      if (early && getSess(id) !== mine) throw new Error('restarted');
      try {
        const res = await API.play({ series: id, name: S.name || '' });
        let ep = res.ep;
        if (!ep && res.job) ep = await waitJobEp(res.job, (j) => { P.loadStatus = j.status; updatePlayerUI(); });
        if (!ep) throw new Error('No episode returned');
        return { res, ep };
      } catch (e) { err = e; }
    }
    throw err || new Error('no answer');
  })();
  try {
    const { res, ep } = await sidP;
    if (ep.audio) store.set(k1, ep);
    const ss = getSess(id);
    if (early && ss && ss.eps[0] === early && ep.audio === early.audio) {
      Object.assign(early, ep, { kind: 'produced' }); ss.sid = res.sid; save();
      if (P.ep === early) { updatePlayerUI(true); if (s.visuals) renderVisual(true); }
      return;
    }
    if (P.id !== id) return;
    SESS[skey(id)] = { sid: res.sid, eps: [ep], chosen: {}, job: null, started: Date.now() };
    recordStart(id);
    save();
    playEpisode(id, ep);
  } catch (e) {
    delete SIDP[skey(id)];
    console.warn(e);
    if (early && getSess(id) === mine) {   // the audio is already playing: let it play; the script and the session join as soon as the relay answers (sidReady)
      P.loading = false; updatePlayerUI();
      if (e && e.message !== 'restarted') toast(tz('Still connecting to the story server — keep listening', '还在连接服务器，先接着听'));
      return;
    }
    P.loading = false; P.want = false;
    updatePlayerUI();
    toast(`Couldn't start the story. ${esc(e.message || '')}`);
  }
}
const SIDP = {}, SIDLATE = {};
async function prefetchScripts() {
  if (MOCK || !API || !API.get || !SERIES.length) return;
  const tk = 'ua.ep1pack.' + LANG, last = store.get(tk, 0) || 0;
  const missing = SERIES.some((s) => s.ep1 && s.ep1.ready && !((store.get('ua.ep1.' + s.id + '.' + LANG, null) || {}).cues || []).length);
  if (!missing && Date.now() - last < 6 * 3600e3) return;
  try {
    const pack = await API.get('api/ep1pack', null, true);
    Object.entries(pack || {}).forEach(([id, ep]) => { if (ep && ep.audio && (ep.cues || []).length) store.set('ua.ep1.' + id + '.' + LANG, ep); });
    store.set(tk, Date.now());
    const ss = P.id && getSess(P.id);   // the one playing right now gets its text at once
    if (ss && P.ep && P.ep === ss.eps[0] && !(P.ep.cues || []).length && pack[P.id] && pack[P.id].audio === P.ep.audio) { Object.assign(P.ep, pack[P.id], { kind: 'produced' }); updatePlayerUI(true); }
  } catch (e) { /* older relay or unreachable: /api/play still brings the script */ }
}
async function sidReady(id) {  // Episode 1 starts before /api/play returns; anything that needs the server session waits here
  const ss = getSess(id); if (!ss) return null;
  if (!ss.sid && SIDP[skey(id)]) { try { const r = await SIDP[skey(id)]; if (!ss.sid) ss.sid = r.res.sid; } catch (e) { /* ignore */ } }
  if (!ss.sid && !MOCK && ss.eps && ss.eps.length === 1 && ss.eps[0].kind === 'produced') {
    // the start never reached the relay (it was down / the link dropped): open the server session now, for the same Episode 1
    if (!SIDLATE[skey(id)]) SIDLATE[skey(id)] = API.play({ series: id, name: S.name || '' }).finally(() => { setTimeout(() => { delete SIDLATE[skey(id)]; }, 3000); });
    try {
      const res = await SIDLATE[skey(id)];
      if (res && res.sid && !ss.sid) {
        ss.sid = res.sid;
        if (res.ep && res.ep.audio === ss.eps[0].audio) { Object.assign(ss.eps[0], res.ep, { kind: 'produced' }); store.set('ua.ep1.' + id + '.' + LANG, res.ep); }
        save();
        if (P.id === id && P.ep === ss.eps[0]) updatePlayerUI(true);
      }
    } catch (e) { /* still unreachable */ }
  }
  return ss.sid;
}
async function waitJobEp(jobId, onTick) {
  const t0 = Date.now();
  for (;;) {
    const j = await API.job(jobId);
    onTick && onTick(j);
    if (j.status === 'done' && j.ep) return j.ep;
    if (j.status === 'error') throw new Error(j.error || 'Generation failed');
    if (Date.now() - t0 > 180000) throw new Error('Timed out');
    await sleep(600);
  }
}

/** Detail CTA: play Ep1 (new) or continue where she left off. */
function startOrContinue(id) {
  let ss = getSess(id);
  // 11-11 a start that never reached the relay (it was down / the tunnel dropped) leaves an Episode 1 with no script and no
  // server session: start it again instead of resuming a story that can show no text and can't continue
  if (ss && !ss.sid && !SIDP[skey(id)] && ss.eps && ss.eps.length === 1 && ss.eps[0].kind === 'produced' && !MOCK) {
    const c = store.get('ua.ep1.' + id + '.' + LANG, null);
    if (c && c.audio === ss.eps[0].audio && !(ss.eps[0].cues || []).length) Object.assign(ss.eps[0], c, { kind: 'produced' });   // the script is on this device already
    sidReady(id);
  }
  if (!ss || !ss.eps || !ss.eps.length) { newSession(id); return; }
  primeAudio(); setTimeout(micHold, 0);
  if (P.id === id && (P.ep || P.loading)) { openPlayer(); if (P.needChoice) setTimeout(openChoiceSheet, 380); else if (!isPlaying() && !P.gen && !P.loading) togglePlay(); return; }
  const last = ss.eps[ss.eps.length - 1];
  const pr = S.progress[skey(id)];
  if (ss.job && ss.job.n) { // generation was in flight when the page closed: resume polling
    cancelGen();
    P.id = id;
    P.ep = ss.eps.find((e) => e.n === ss.job.n - 1) || last;
    P.needChoice = false; P.cur = ''; audio.pause();
    startGeneration(ss.job.id, ss.job.n, ss.job.text || '', true);
    openPlayer();
    return;
  }
  const ep = (pr && ss.eps.find((e) => e.n === pr.ep)) || last;
  if (pr && pr.needChoice && ep === last && !last.ending) {
    P.id = id; P.ep = last; P.cur = ''; P.needChoice = true; P.want = false; audio.pause();
    document.documentElement.style.setProperty('--accent', (byId(id) || {}).accent || '#FF8448');
    renderPlayer(); updatePlayerUI(); renderMini(); openPlayer();
    setTimeout(openChoiceSheet, 380);
    return;
  }
  const opts = pr && pr.ep === ep.n ? (ep.kind === 'live' ? { line: pr.line || 0 } : { at: pr.pct > 0.98 ? 0 : pr.t || 0 }) : {};
  playEpisode(id, ep, opts);
  openPlayer();
}
function playStored(id, n) {
  const ss = getSess(id); if (!ss) return;
  const ep = ss.eps.find((e) => e.n === n); if (!ep) return;
  primeAudio();
  cancelGen();
  playEpisode(id, ep);
  openPlayer();
}

function onEpisodeEnd() {
  const ss = getSess(P.id);
  const ep = P.ep; if (!ss || !ep) return;
  P.want = false; P.waiting = false;
  if (ep.kind === 'live') { ep.dur = Object.values(ep.durs || {}).reduce((a, b) => a + b, 0) || ep.dur; }
  const last = ss.eps[ss.eps.length - 1];
  const sleepEoe = S.sleep && S.sleep.eoe;
  if (sleepEoe) { S.sleep = null; save(); }
  if (ep !== last) {
    saveProgressDone();
    if (sleepEoe) { toast('Sleep timer: stopped at end of episode'); updatePlayerUI(); return; }
    startUpNext(ss.eps[ss.eps.indexOf(ep) + 1]);
    return;
  }
  if (ep.ending) {
    saveProgressDone();
    updatePlayerUI();
    openEndingSheet();
    return;
  }
  P.needChoice = true;
  saveProgress();
  updatePlayerUI(); renderMini();
  if (!sleepEoe) endOfEpisodeFlow();
  else toast('Sleep timer: stopped at end of episode');
}
function saveProgressDone() {
  const k = skey(P.id);
  S.progress[k] = Object.assign({}, S.progress[k] || {}, { id: P.id, ep: P.ep.n, title: P.ep.title, pct: 1, at: Date.now(), needChoice: false, line: 0, t: 0 });
  save();
}

/* Replay autoplay-next countdown (Pocket FM style) */
function startUpNext(nextEp) {
  if (!nextEp) return;
  cancelUpNext();
  P.upNext = { ep: nextEp, left: 5, t: setInterval(() => {
    if (!P.upNext) return;
    P.upNext.left -= 1;
    if (P.upNext.left <= 0) { const e = P.upNext.ep; cancelUpNext(); playEpisode(P.id, e); }
    else updatePlayerUI();
  }, 1000) };
  updatePlayerUI();
}
function cancelUpNext() { if (P.upNext) { clearInterval(P.upNext.t); P.upNext = null; } }

/* --- choice sheet --- */
let recog = null;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;  // no longer used for input (single-language); kept for reference
const VOICE_OK = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
/* Lock-screen answers (11-09): on iPhone only a Safari tab keeps recording once the screen locks (WebKit bugs 239602 / 226620);
 * apps' built-in browsers (Feishu, WeChat…) and home-screen web apps lose the mic as soon as the phone locks. */
const UA_ = navigator.userAgent || '';
const IOS = /iP(hone|ad|od)/.test(UA_) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const IN_APP = /MicroMessenger|Lark|Feishu|DingTalk|\bQQ\/|Weibo|FBAN|FBAV|Instagram|Line\/|TikTok|aweme|NewsArticle|Bytedance/i.test(UA_) || (IOS && !/Safari\//.test(UA_));
const STANDALONE = navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches);
const LOCK_VOICE_OK = VOICE_OK && !(IOS && (IN_APP || STANDALONE));

function openChoiceSheet() {
  if (!P.ep || !P.needChoice) return;
  if (topSheet() && topSheet().kind === 'choice') return;
  maybeSpecs(true);
  if (askInline()) { updatePlayerUI(); return; }   // narra player: the question, A, B and the answer box are lines of the lyric stream — no sheet
  const s = byId(P.id);
  const ep = P.ep;
  const nextN = ep.n + 1;
  const locked = !isUnlocked(P.id, nextN);
  const choices = (ep.choices || []).slice(0, 2);
  const html = `
    <div class="ch-top">
      <img src="${esc(avatarOf(s))}" alt="">
      <div><small>YOUR MOVE · END OF EP ${ep.n}</small><b>${esc(s.title)}</b></div>
      <button class="icon-btn" data-act="sheet-close" aria-label="Close" style="margin-left:auto">${ic('close')}</button>
    </div>
    <div class="ch-hf" id="ch-hf" hidden></div>
    <h3 class="ch-prompt">${esc(ep.prompt || (LANG === 'zh' ? '你怎么做？' : 'What do you do?'))}</h3>
    <div class="ch-opts">
      ${choices.map((c, i) => `<button class="ch-opt" data-act="choose" data-i="${i}"><i>${'AB'[i]}</i><span>${esc(c)}</span></button>`).join('')}
    </div>
    <div class="ch-or">${VOICE_OK ? 'say A or B, or answer in your own words' : 'or answer in your own words'}</div>
    <form class="ch-input" data-form="free" autocomplete="off">
      <div class="fld">
        <input id="ch-text" type="text" maxlength="200" placeholder="Say it your way…" enterkeyhint="send" aria-label="Your answer">
        <button class="ch-send" type="submit" aria-label="Send" disabled>${ic('send')}</button>
      </div>
      ${VOICE_OK ? `<button class="ch-mic" type="button" data-act="mic" aria-label="Speak your answer">${ic('mic')}</button>` : ''}
    </form>
    <div class="ch-foot">
      <span class="lockinfo">${locked ? `${ic('lock', 'xs')} Ep ${nextN} · ${coinIc('sm')} ${PRICE} to unlock` : `${ic('spark', 'xs')} Ep ${nextN} is written live from your answer`}</span>
      <button class="link-btn" data-act="silent">Stay silent</button>
    </div>
    <div class="ch-auto" id="ch-auto" hidden></div>
    <button class="ch-mode" data-act="mode-sheet">${ic(MODES[modeOf()].icon, 'xs')} ${MODES[modeOf()].name} · change how you listen</button>
    <div class="ch-err" id="ch-err" hidden></div>`;
  const entry = openSheet(html, { cls: 'choice-sheet', kind: 'choice', onClose: () => { stopMic(); hfStop(); stopAutoCountdown(); } });
  const inp = $('#ch-text', entry.el), send = $('.ch-send', entry.el);
  inp.addEventListener('input', () => { send.disabled = !inp.value.trim(); stopAutoCountdown(); });
  inp.addEventListener('focus', holdForHer);
  entry.el.addEventListener('pointerdown', (e) => { if (!e.target.closest('[data-act="choose"],[data-act="silent"],.ch-send')) holdForHer(); }, { capture: true });
  $('form', entry.el).addEventListener('submit', (e) => {
    e.preventDefault();
    const t = inp.value.trim(); if (!t) return;
    submitChoice(t, 'free');
  });
}
function stopMic() { if (recog) { const r = recog; recog = null; r.cancel(); } }
function toggleMic(btn) {
  if (!VOICE_OK) return;
  holdForHer();
  if (recog) { recog.stop(); return; }
  const inp = $('#ch-text');
  btn.classList.add('rec');
  if (inp) inp.placeholder = 'Listening… (Chinese or English)';
  const h = recog = recordAnswer({ wait: 8000, max: 20000, onState: (st) => { if (st === 'thinking' && inp) inp.placeholder = 'Got it — one moment…'; if (st === 'denied') toast('Microphone permission denied'); } });
  h.done.then((r) => {
    if (recog === h) recog = null;
    btn.classList.remove('rec');
    if (inp) inp.placeholder = 'Say it your way…';
    if (r.canceled) return;
    if (r.text) { if (inp) { inp.value = r.text; inp.dispatchEvent(new Event('input')); } submitChoice(r.text, 'voice'); }
    else if (r.spoke) toast("Didn't catch that — try again");
  });
}

/* =========================================================================
 * 9b. Listening modes (11-06, from the audio discussion with 阿炫):
 *   voice — Hands-free: at each cliffhanger the narrator asks out loud, the mic opens, she just answers.
 *           Stays quiet → the story carries on by itself. No need to pick up the phone.
 *   auto  — Lean back: no questions, the story keeps going on its own (sleep / passive listening).
 *   tap   — Tap to choose: the choice sheet; if she doesn't answer the story carries on after 30 s.
 * "Talk to the story" (any time) steers what happens next. Calling a character is a separate thing.
 * ========================================================================= */
const MODES = {
  voice: { icon: 'mic', name: 'Hands-free', short: 'I ask out loud, you just answer', desc: 'At every choice point the narrator asks out loud and the mic listens for 5 seconds — answer in Chinese or English. Say nothing and the story carries on. Works with the screen locked too (on iPhone, open it in Safari).' },
  auto: { icon: 'moon', name: 'Lean back', short: 'The story keeps going on its own', desc: 'No questions. The story keeps moving by itself, episode after episode — for winding down or falling asleep.' },
  tap: { icon: 'hand', name: 'Tap to choose', short: 'Pick on screen', desc: 'Choose on screen or type your own answer. The story waits 5 seconds — touch the screen and it waits until you\u2019re done.' },
};
if (!MODES[S.mode]) S.mode = VOICE_OK ? 'voice' : 'tap';
const modeOf = () => (S.mode === 'voice' && !VOICE_OK ? 'tap' : S.mode);

/* earcons + a soft ambient bed while the next episode is being written (WebAudio, no network, no credits) */
function earcon(kind) {
  unlockCtx();
  if (!actx || actx.state !== 'running') return;
  const t = actx.currentTime + 0.02;
  if (kind === 'open') { tone(t, 784, 0.22, 0.07); tone(t + 0.12, 1175, 0.32, 0.06); }
  else if (kind === 'ok') { tone(t, 1175, 0.18, 0.05); tone(t + 0.09, 1568, 0.36, 0.05); }
  else { tone(t, 660, 0.25, 0.05); tone(t + 0.12, 494, 0.35, 0.045); }
}
let bed = null;
function bedStart() {
  unlockCtx();
  if (bed || !actx || actx.state !== 'running') return;
  try {
    const g = actx.createGain(); g.gain.value = 0.0001;
    const lp = actx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 900;
    lp.connect(g); g.connect(actx.destination);
    const oscs = [110, 164.81, 220.5, 277.18].map((f, i) => {
      const o = actx.createOscillator(); o.type = i % 2 ? 'triangle' : 'sine'; o.frequency.value = f; o.detune.value = (i - 1.5) * 4;
      const og = actx.createGain(); og.gain.value = [0.5, 0.25, 0.3, 0.12][i];
      const l = actx.createOscillator(); l.frequency.value = 0.07 + i * 0.03; const lg = actx.createGain(); lg.gain.value = 0.12; l.connect(lg); lg.connect(og.gain);
      o.connect(og); og.connect(lp); o.start(); l.start(); return [o, l];
    }).flat();
    g.gain.exponentialRampToValueAtTime(0.05, actx.currentTime + 1.6);
    bed = { g, oscs };
  } catch (e) { bed = null; }
}
function bedStop() {
  if (!bed || !actx) return;
  const b = bed; bed = null;
  try { b.g.gain.cancelScheduledValues(actx.currentTime); b.g.gain.setValueAtTime(Math.max(b.g.gain.value, 0.0001), actx.currentTime); b.g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + 0.7); } catch (e) { /* ignore */ }
  setTimeout(() => b.oscs.forEach((o) => { try { o.stop(); } catch (e) { /* ignore */ } }), 900);
}

/* 11-09 the narrator's bridge: the moment she has answered, "Okay — your way." and then one pre-voiced narrator line
 * about this very moment (it never guesses her answer). Meanwhile the relay is already writing her episode from her words
 * (it starts as soon as her speech is recognised), so by the end of the bridge the first line is usually voiced. */
const BRIDGES = {};   // sid:n -> {text, url} (prefetched)
const BR = { n: 0, url: '', played: false, ackDone: true, t0: 0 };
function noteBridge(sid, n, b) {
  if (!b || !b.url) return;
  BRIDGES[sid + ':' + n] = b;
  if (blobable(b.url)) fetchBlob(b.url);
}
const auxTalking = () => P.aux && !audio.loop && !!P.auxEnd && !audio.paused;   // the ack / bridge is being spoken
/* the lead's half-line after the bridge ("You want to know that…" / "…I heard you."), only when her episode still isn't ready */
const BEATS = {};
let BEAT_KEY = '';
function noteBeats(sid, n, b) {
  if (!b || !b.q || !b.s) return;
  BEATS[sid + ':' + n] = b; BEAT_KEY = sid + ':' + n;
  [...b.q, ...b.s].forEach((x) => { if (x.url && blobable(x.url)) fetchBlob(x.url); });
}
const isQuestion = (t) => /[?？]|吗|呢|什么|为什么|怎么|谁|哪|几时|是不是|有没有|能不能|会不会|^(who|what|why|how|when|where|is|are|do|does|did|can|could|will|would|should)\b/i.test((t || '').trim());
function afterBridge() {
  if (!P.gen) return;
  const b = BEATS[BEAT_KEY];
  if (b && !P.gen.ready && !P.gen.beat && P.gen.text) {
    P.gen.beat = true;
    const list = isQuestion(P.gen.text) ? b.q : b.s, x = list[Math.floor(Math.random() * list.length)];
    if (x && x.url) { playAux(x.url).then(() => { if (P.gen) keepAlive(); }); return; }
  }
  keepAlive();
}
function maybeBridge() {
  if (!P.gen || P.gen.n !== BR.n || !BR.url || BR.played || !BR.ackDone || Date.now() - BR.t0 > 7000) return false;
  BR.played = true;
  playAux(BR.url).then(afterBridge);
  return true;
}
/** 11-09 (2): she has just stopped talking — play the bridge right away, before her words are even recognised (~1 s sooner). */
let EARLY = { n: 0, url: '' };
function earlyBridge() {
  const ss = P.id && getSess(P.id); if (!ss || !P.ep || !P.needChoice) return;
  const b = BRIDGES[ss.sid + ':' + P.ep.n]; if (!b || !b.url) return;
  EARLY = { n: P.ep.n + 1, url: b.url };
  playAux(b.url).then(afterBridge);
}
const afterAux = (fn) => { const w = () => (auxTalking() ? setTimeout(w, 100) : fn()); w(); };   // never cut the narrator mid-sentence

/* narrator's spoken question at the end of an episode (prefetched ~45 s before the end) */
const CUE = {};
function fetchCue(sid, n) {
  const k = sid + ':' + n;
  if (!CUE[k]) {
    CUE[k] = API.cue(sid, n).then((d) => {
      if (d && d.bridge) noteBridge(sid, n, d.bridge);
      if (d && d.url) { if (blobable(d.url)) fetchBlob(d.url); else try { const a = new Audio(); a.preload = 'auto'; a.src = absUrl(d.url); a.load(); } catch (e) { /* ignore */ } }
      return d;
    }).catch(() => { delete CUE[k]; return null; });
  }
  return CUE[k];
}

/* ---------- Voice input (11-08): record a few seconds → local faster-whisper on the relay (/api/asr).
 * Chinese and English both work in either version (the model detects the language); the story answers in the version's language.
 * In Hands-free the mic stream is opened once (first Play tap) and kept, so she can answer with the screen locked where the
 * browser allows it (Android Chrome; iOS Safari may suspend capture when locked — then the story simply carries on). */
const VI = { stream: null, an: null, buf: null, denied: false, primed: false };
async function micStream() {
  if (VI.stream && VI.stream.getAudioTracks().some((t) => t.readyState === 'live')) return VI.stream;
  try { if (navigator.audioSession) navigator.audioSession.type = 'auto'; } catch (e) { /* ignore */ }  // let Safari pick record+play itself (forcing it was one suspect for the 0:00 stall)
  VI.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, voiceIsolation: true } });  // 11-10 voiceIsolation: browsers that support it keep only the nearest voice
  VI.denied = false;
  // iOS switches the audio session when the mic opens and may pause the story that is playing: pick it straight back up
  [150, 700].forEach((ms) => setTimeout(() => {
    if (((P.want && P.cur && !P.waiting) || (P.aux && audio.loop)) && audio.paused && !callActive()) audio.play().catch(() => {});
    if (callActive() && callAudio.paused && (callAudio.dataset.loop || (C && (C.playing || C.fillerPlaying) && !C.held))) callAudio.play().catch(() => {});  // ring / his line
  }, ms));
  unlockCtx();
  try {
    if (actx) { const src = actx.createMediaStreamSource(VI.stream); VI.an = actx.createAnalyser(); VI.an.fftSize = 1024; src.connect(VI.an); VI.buf = new Float32Array(VI.an.fftSize); }
  } catch (e) { VI.an = null; }
  return VI.stream;
}
/** Mic off unless something is listening right now (11-09): on iPhone an open mic puts the page in play-and-record,
 * and the story's <audio> could then sit at 0:00 "playing" with no sound. Permission stays granted for the page. */
let micBusy = 0;
const lockHold = () => LOCK_VOICE_OK && modeOf() === 'voice' && S.onboarded && !VI.denied;  // Safari + Hands-free: mic stays on from opening the app (switching it on at Play delayed the start)
function micPark() {
  if (callActive() || HF.rec || callRecog || talkRec || micBusy || lockHold()) return;
  micRelease();
}
/** Hands-free in Safari: open the mic inside the Play tap and keep it for the whole story, so answers work on the lock screen.
 * (The mic can't be started once the phone is locked — it has to be running already.) */
function micHold() {
  if (!lockHold() || VI.denied) return;
  micStream().then(() => { VI.primed = true; }).catch((e) => { if (e && e.name === 'NotAllowedError') VI.denied = true; });
}
document.addEventListener('visibilitychange', () => {
  // back from the lock screen: if iOS ended or muted the mic track, open it again (WebKit workaround)
  if (document.hidden || !lockHold() || !VI.stream) return;
  const t = VI.stream.getAudioTracks()[0];
  if (!t || t.readyState !== 'live' || t.muted) { try { VI.stream.getTracks().forEach((x) => x.stop()); } catch (e) { /* ignore */ } VI.stream = null; micHold(); }
});
setInterval(() => { if (VI.stream && !lockHold() && !callActive()) micPark(); }, 15000);
function micRelease() {
  if (VI.stream) { VI.stream.getTracks().forEach((t) => t.stop()); VI.stream = null; VI.an = null; }
  try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) { /* ignore */ }
}
/** Hands-free asks for the mic up front (opening the app / choosing Hands-free), never for the first time at a choice point.
 * force: she chose Hands-free or tapped a mic herself — ask even if she said no before. */
function primeMic(force) {
  if (VI.primed || !VOICE_OK || modeOf() !== 'voice') return;
  if (VI.denied && !force) return;
  VI.primed = true;
  micStream().then(() => setTimeout(micPark, 300)).catch((e) => {
    VI.primed = false;
    if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) {
      VI.denied = true;
      toast(LANG === 'zh' ? '没开麦克风：选择点会显示选项，5 秒不选就自动往下。想用语音，可在收听模式里重新选 Hands-free。' : 'Mic is off: choices show on screen and the story moves on after 5 seconds. Pick Hands-free again in listening modes to use your voice.');
    }
  });
}
async function micPermission() {
  try { return (await navigator.permissions.query({ name: 'microphone' })).state; } catch (e) { return ''; }
}
/** Opening the app in Hands-free: ask right away (open the stream silently if already allowed); the first tap anywhere asks too,
 * for browsers that only show the prompt after a gesture. */
async function primeMicOnEntry() {
  if (!S.onboarded || !VOICE_OK || modeOf() !== 'voice') return;
  const st = await micPermission();
  if (st === 'denied') { VI.denied = true; return; }
  if (st !== 'granted') toast(LANG === 'zh' ? `${ic('mic', 'sm')} Hands-free 需要麦克风：到选择点直接说出你的回答` : `${ic('mic', 'sm')} Hands-free uses your mic: just say your answer at each choice`);
  VI.primed = true;
  micStream().then(() => setTimeout(micPark, 300)).catch((e) => { VI.primed = false; if (st === 'prompt' && e && e.name === 'NotAllowedError') VI.denied = true; });
}
document.addEventListener('pointerdown', () => { if (S.onboarded) primeMic(); }, { capture: true, passive: true });
function micLevel() {
  if (!VI.an || !actx || actx.state !== 'running') return -1;
  VI.an.getFloatTimeDomainData(VI.buf);
  let s = 0; for (let i = 0; i < VI.buf.length; i++) s += VI.buf[i] * VI.buf[i];
  return Math.sqrt(s / VI.buf.length);
}
/** Record one answer. Waits up to `wait` ms for her to start speaking; after she starts, stops after ~1.1 s of quiet (or `max`).
 * manual: hold-to-talk (no auto stop; call stop()). When the level meter is unavailable (page locked, audio context asleep)
 * it records the whole window and lets the recognizer decide whether anything was said. */
function recordAnswer({ wait = 5000, max = 15000, manual = false, onState, onPartial } = {}) {
  let rec = null, chunks = [], t0 = 0, speechAt = 0, lastVoice = 0, timer = 0, finished = false, canceled = false, floor = 0, n = 0, blind = false;
  let pBusy = false, pAt = 0, pN = 0;
  /* live transcript (11-11): while she talks, what has been recorded so far is recognised again every ~0.7 s and handed to onPartial */
  const partial = async () => {
    if (!onPartial || pBusy || finished || !speechAt || chunks.length === pN || Date.now() - pAt < 700) return;
    pBusy = true; pN = chunks.length;
    try { const r = await API.asr(new Blob(chunks.slice(), { type: (rec && rec.mimeType) || 'audio/webm' }), { partial: true }); const t = ((r && r.text) || '').trim(); if (!finished && t) onPartial(t); } catch (e) { /* ignore */ }
    pBusy = false; pAt = Date.now();
  };
  let resolve; const done = new Promise((r) => { resolve = r; });
  const st = (s, x) => { try { onState && onState(s, x); } catch (e) { /* ignore */ } };
  micBusy++;
  const finish = async (spoke) => {
    if (finished) return; finished = true; clearInterval(timer);
    if (rec && rec.state !== 'inactive') {
      await new Promise((r) => { rec.onstop = () => r(); try { rec.stop(); } catch (e) { r(); } setTimeout(r, 900); });
    }
    micBusy = Math.max(0, micBusy - 1); setTimeout(micPark, 50);
    if (canceled) { resolve({ text: '', spoke: false, canceled: true }); return; }
    if (!spoke || !chunks.length) { resolve({ text: '', spoke: false }); return; }
    st('thinking', { spoke: speechAt ? lastVoice - speechAt : 0 });
    try {
      const r = await API.asr(new Blob(chunks, { type: (rec && rec.mimeType) || 'audio/webm' }));
      resolve({ text: ((r && r.text) || '').trim(), lang: r && r.lang, spoke: true });
    } catch (e) { resolve({ text: '', spoke: true, error: e.message }); }
  };
  (async () => {
    try { await micStream(); } catch (e) { VI.denied = true; st('denied'); resolve({ text: '', spoke: false, denied: true }); finished = true; return; }
    if (finished) return;
    const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/aac'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
    try { rec = new MediaRecorder(VI.stream, type ? { mimeType: type } : undefined); } catch (e) { st('denied'); resolve({ text: '', spoke: false, denied: true }); finished = true; return; }
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.start(250);
    t0 = Date.now(); st('listening');
    timer = setInterval(() => {
      const now = Date.now(), lv = micLevel();
      if (lv < 0) blind = true;
      else {
        n += 1; if (n <= 4) floor = Math.max(floor, lv);
        if (n > 2 && lv > Math.max(0.02, floor * 2.4)) { if (!speechAt) { speechAt = now; st('speaking'); } lastVoice = now; }
      }
      partial();
      if (manual) { if (now - t0 > max) finish(true); return; }
      if (blind) { if (now - t0 > wait + 1500) finish(true); return; }  // can't hear levels: send the whole window, the recognizer decides
      if (!speechAt && now - t0 > wait) { finish(false); return; }
      if (speechAt && (now - lastVoice > 800 || now - t0 > max)) finish(true);   // she stopped → recognise and go (11-09: was 1.1 s)
    }, 100);
  })();
  return { done, stop: () => finish(true), cancel: () => { canceled = true; finish(false); } };
}

/* ---------- main-audio helpers: the narrator's question and a quiet ambient bed play on the SAME <audio> element as the story,
 * so the lock-screen media session never stops between episodes (a separate element can't start while the phone is locked). */
function playAux(url, { loop = false, volume = 1 } = {}) {
  return new Promise((res) => {
    P.aux = true; P.auxEnd = loop ? null : res;
    audio.loop = loop; audio.volume = volume;
    audio.src = srcFor(url); audio.playbackRate = 1;
    const p = audio.play();
    if (p && p.catch) p.catch(() => { if (P.auxEnd === res) { P.auxEnd = null; res(); } });
    if (loop) res();
  });
}
function keepAlive() { if (!P.aux || !audio.loop) playAux('bed.mp3', { loop: true, volume: 0.6 }); }
function stopAux() { if (P.aux) { P.aux = false; P.auxEnd = null; audio.loop = false; audio.volume = 1; try { audio.pause(); } catch (e) { /* ignore */ } } }
function bedStart() { keepAlive(); }
function bedStop() { stopAux(); }

const HF = { phase: '', rec: null, heard: '', key: '', ask: '' };
let autoT = 0, autoLeft = 0;
const WAIT = 5;  // every choice point waits 5 s (touching the screen pauses it until she's done)

function endOfEpisodeFlow() {
  const m = modeOf();
  openChoiceSheet();
  if (m === 'voice' && VOICE_OK && !VI.denied) { startHandsFree(); return; }
  keepAlive();
  startAutoCountdown(WAIT, m === 'auto' ? 'Lean back · the story continues in' : 'The story continues in');
}
function startAutoCountdown(sec, label, visualOnly) {
  stopAutoCountdown();
  autoLeft = sec;
  const n = P.ep && P.ep.n;
  const paint = () => {
    const el = autoEl(); if (!el) return;
    el.hidden = false;
    el.innerHTML = `<span class="ca-ring" style="--p:${(autoLeft / sec) * 100}"></span><span>${esc(label)} <b class="tnum">${autoLeft}s</b></span><button class="link-btn" data-act="ch-wait">Wait for me</button>`;
  };
  paint();
  autoT = setInterval(() => {
    if (!P.needChoice || !P.ep || P.ep.n !== n) { stopAutoCountdown(); return; }
    autoLeft -= 1;
    if (autoLeft <= 0) { stopAutoCountdown(); if (!visualOnly) continueOnItsOwn(); return; }
    paint();
  }, 1000);
}
const autoEl = () => $('#ch-auto') || $('#nr-hint');   // the choice sheet's countdown row, or (narra player) the small line under the answer box
function stopAutoCountdown() { clearInterval(autoT); autoT = 0; ['#ch-auto', '#nr-hint'].forEach((q) => { const el = $(q); if (el) { el.hidden = true; el.innerHTML = ''; } }); }
/** She touched the choice sheet: stop the clock and the mic, wait for her to pick or finish typing. */
function holdForHer() {
  if (!P.needChoice) return;
  const was = autoT || HF.rec;
  stopAutoCountdown(); hfStop();
  if (was) { const el = autoEl(); if (el) { el.hidden = false; el.innerHTML = `${ic('hand', 'sm')}<span>Paused — take your time</span>`; } }
}
function continueOnItsOwn(why) {
  if (!P.needChoice) return;
  earcon('ok');
  toast(`${ic('spark', 'sm')} ${why === 'unclear' ? 'Didn’t catch that — the story carries on' : 'The story carries on…'}`);
  submitChoice('', 'auto');
}

async function startHandsFree() {
  const ss = getSess(P.id), ep = P.ep; if (!ss || !ep) return;
  hfStop(true);
  HF.key = (ss.sid || 'x') + ':' + ep.n;
  const key = HF.key;
  HF.phase = 'ask'; HF.ask = ''; paintHF();
  P.want = false; P.needChoice = true;
  let d = null;
  try { d = await Promise.race([ss.sid ? fetchCue(ss.sid, ep.n) : null, sleep(4000).then(() => null)]); } catch (e) { d = null; }
  if (HF.key !== key || !P.needChoice) return;
  if (d && d.text) { HF.ask = d.text; paintHF(); }
  if (d && d.url) await playAux(d.url);  // the narrator asks (on the story's own audio element)
  if (HF.key !== key || !P.needChoice || HF.phase !== 'ask') return;
  hfListen();
}
/** Lock screen at a choice point (11-09): the page can't hear levels, so instead of recording the whole 6.5 s window,
 * send 1.5 s pieces; the relay stitches them and answers as soon as she has finished her sentence. */
const LOCK_WAIT = 5000;  // 11-09：锁屏给她 5 秒开口；5 秒内没声音才自动往下走，开口了就一直听到她说完
const LOCK_PIECE = 1250;  // 每段 1.25 秒：第 4 段正好录到第 5 秒
const LOCK_CAP = 90000;   // 一口气最多听 90 秒，到了就把已说的识别掉
function hfListenLocked(key) {
  const t0 = Date.now(); let first = true, heard = false, over = false, rec = null, timer = 0, pending = 0, voiceEnd = 0;
  const type = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
  const stop = () => { over = true; clearTimeout(timer); if (rec && rec.state !== 'inactive') { try { rec.stop(); } catch (e) { /* ignore */ } } micBusy = Math.max(0, micBusy - 1); };
  const ok = () => HF.key === key && P.needChoice && !over;
  const piece = () => {
    if (!ok()) return;
    // “没说话”只在回包里判断（下面 onstop）：按时间判的话，回包还在隧道上她已经开口了，结果先自动续播、她的话被丢掉
    if (!heard && Date.now() - t0 > LOCK_WAIT + 9000) { stop(); continueOnItsOwn('quiet'); return; }   // 回包一直不来（断网）
    try { rec = new MediaRecorder(VI.stream, type ? { mimeType: type } : undefined); } catch (e) { stop(); continueOnItsOwn('quiet'); return; }
    const chunks = [], pStart = Date.now() - t0, last = pStart + LOCK_PIECE >= LOCK_CAP;
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      const b = new Blob(chunks, { type: rec.mimeType || type || 'audio/mp4' });
      const f = first; first = false;
      let r = null; pending++;
      try {
        const ss = getSess(P.id);
        const u = new URL(apiUrl('api/asr/chunk')); u.searchParams.set('k', TOKEN); u.searchParams.set('sid', (ss && ss.sid) || ''); if (f) u.searchParams.set('first', '1'); if (last) u.searchParams.set('end', '1');
        const res = await fetch(u.toString(), { method: 'POST', headers: { 'Content-Type': b.type || 'audio/mp4' }, body: b });
        r = res.ok ? await res.json() : null;
      } catch (e) { r = null; }
      pending--;
      if (!ok() && !(r && r.text)) return;
      const pEnd = pStart + LOCK_PIECE;
      if (r && (r.speaking || r.heard)) { heard = true; voiceEnd = Math.max(voiceEnd, pEnd); stopAutoCountdown(); HF.phase = 'speaking'; paintHF(); }
      else if (r && !r.done) {
        heard = false;  // 咳嗽、碰一下这种没成句的声音不算开口
        // 录到第 5 秒（或上次出声后 3 秒）还是没声音，而且前面的段都回来了 → 她真的没说话，故事自己往下走
        if (pEnd >= Math.max(LOCK_WAIT, voiceEnd ? voiceEnd + 3000 : 0) && pending === 0) { stop(); continueOnItsOwn('quiet'); return; }
      }
      if (r && r.done) {
        stop();
        if (HF.key !== key || !P.needChoice) return;
        if (r.text) { HF.phase = 'heard'; HF.heard = r.text; paintHF(); submitChoice(r.text, 'voice'); }
        else continueOnItsOwn('unclear');
      } else if (last && ok()) { stop(); continueOnItsOwn(heard ? 'unclear' : 'quiet'); }
    };
    try { rec.start(); } catch (e) { stop(); continueOnItsOwn('quiet'); return; }
    timer = setTimeout(() => { if (rec.state !== 'inactive') { try { rec.stop(); } catch (e) { /* ignore */ } } if (!last) piece(); }, LOCK_PIECE);
  };
  micBusy++;
  HF.rec = { cancel: stop };
  piece();
}
function hfListen() {
  if (!P.needChoice || !VOICE_OK) return;
  if (VI.stream && (document.hidden || !actx || actx.state !== 'running')) {   // locked: piece-by-piece, ends when she does
    stopAutoCountdown(); if (HF.rec) { HF.rec.cancel(); HF.rec = null; }
    keepAlive(); HF.phase = 'listen'; HF.heard = ''; askText(''); paintHF();
    hfListenLocked(HF.key); return;
  }
  stopAutoCountdown();
  if (HF.rec) { HF.rec.cancel(); HF.rec = null; }
  keepAlive();
  HF.phase = 'listen'; HF.heard = ''; askText(''); paintHF();
  earcon('open');
  const key = HF.key;
  startAutoCountdown(WAIT, 'Listening · the story continues in', true);
  const h = HF.rec = recordAnswer({
    wait: WAIT * 1000, max: 15000,
    onPartial: (t) => { if (HF.rec === h) askText(t); },   // her words appear in the answer box as she says them
    onState: (s, x) => {
      if (HF.rec !== h) return;
      if (s === 'speaking') { stopAutoCountdown(); HF.phase = 'speaking'; paintHF(); }
      else if (s === 'thinking') { stopAutoCountdown(); HF.phase = 'thinking'; paintHF(); if (x && x.spoke >= 1200) earlyBridge(); }   // a real sentence (not “A/B”): the story reacts the moment she stops, while it is recognised
    },
  });
  h.done.then((r) => {
    if (HF.rec !== h) return;
    HF.rec = null;
    if (HF.key !== key || !P.needChoice || r.canceled) return;
    stopAutoCountdown();
    if (r.text) {
      // heard her (also on the lock screen): the story goes her way right away, and the narrator says so out loud
      HF.phase = 'heard'; HF.heard = r.text; paintHF(); earcon('ok');
      submitChoice(r.text, 'voice');   // sendNext says "Okay — your way" + the bridge while her episode is written (not over a pre-written one)
      return;
    }
    if (r.denied) { HF.phase = 'denied'; paintHF(); startAutoCountdown(WAIT, 'Mic is off · the story continues in'); return; }
    continueOnItsOwn(r.spoke ? 'unclear' : 'quiet');  // nothing said, or nothing recognizable → the fallback path, no pause
  });
}
function hfStop(silent) {
  if (HF.rec) { const r = HF.rec; HF.rec = null; r.cancel(); }
  if (P.aux && !audio.loop && P.auxEnd) { const f = P.auxEnd; P.auxEnd = null; try { audio.pause(); } catch (e) { /* ignore */ } f(); }
  if (!silent) { HF.phase = ''; paintHF(); }
}
/* narra player (11-11): the answer box under A and B — same size as an option. She can type in it (a real caret once tapped) or
 * just talk: while the mic is open a ring turns at its end and her words fill in as they are recognised. */
const askInline = () => NARRA && playerOpen;
function askText(t) {
  const inp = $('#nr-in'); if (!inp || document.activeElement === inp) return;
  inp.value = t; paintAsk(); placeLyrics();
}
function askSend() {
  const inp = $('#nr-in'), t = inp ? inp.value.trim() : ''; if (!t) return;
  inp.blur(); submitChoice(t, 'free');
}
function paintAsk() {
  const box = $('#nr-inbox'); if (!box) return;
  const ph = HF.phase, inp = $('#nr-in'), ghost = $('#nr-ghost'), ring = $('#nr-ring'), send = $('#nr-send'), mic = $('.in-mic', box), hint = $('#nr-hint');
  const focused = document.activeElement === inp, hearing = ph === 'listen' || ph === 'speaking', busy = hearing || ph === 'thinking';
  if (ph === 'heard' && HF.heard && !focused) inp.value = HF.heard;
  const val = inp.value;
  box.classList.toggle('live', busy); box.classList.toggle('focus', focused);
  ring.hidden = !busy; ring.classList.toggle('wait', ph === 'listen');
  send.hidden = busy || !val.trim();
  if (mic) { mic.dataset.act = hearing ? 'hf-stop' : 'nr-mic'; mic.setAttribute('aria-label', hearing ? 'Stop listening' : 'Speak your answer'); }
  const tip = !VOICE_OK ? 'Type your answer…' : busy ? 'Listening — say your answer…' : 'Say or type your answer…';
  inp.placeholder = tip;
  ghost.className = 'in-ghost' + (val ? '' : ' ph');
  if (val) { ghost.setAttribute('translate', 'no'); ghost.innerHTML = esc(val) + '<i class="caret"></i>'; }
  else { ghost.removeAttribute('translate'); ghost.innerHTML = '<i class="caret"></i><span>' + tip + '</span>'; }
  if (hint && !autoT) {
    const t = ph === 'ask' ? `${ic('headphones', 'xs')}<span>The narrator is asking…</span>` : ph === 'thinking' ? '<span>Got it — one moment…</span>' : ph === 'denied' ? '<span>Microphone is off — type your answer or tap a choice</span>' : '';
    hint.hidden = !t; hint.innerHTML = t;
  }
}
function bindAsk() {
  const inp = $('#nr-in'), box = $('#nr-inbox'); if (!inp || !box || box.dataset.bound) return;
  box.dataset.bound = '1';
  const opts = box.parentNode.querySelectorAll('.ll.opt');
  if (opts.length) box.style.minHeight = opts[opts.length - 1].offsetHeight + 'px';   // the same height as the option above it
  inp.addEventListener('focus', () => { holdForHer(); paintAsk(); });
  inp.addEventListener('blur', paintAsk);
  inp.addEventListener('input', () => { stopAutoCountdown(); paintAsk(); placeLyrics(); });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); askSend(); } });
  paintAsk();
}
function paintHF() {
  paintAsk();
  const el = $('#ch-hf'); if (!el) return;
  const ph = HF.phase;
  if (!ph) { el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  const label = {
    ask: `${ic('headphones', 'sm')} The narrator is asking…`,
    listen: 'Listening — just say it',
    speaking: 'I’m listening…',
    thinking: 'Got it — one moment…',
    heard: 'Got it',
    denied: 'Microphone is off',
  }[ph];
  const sub = ph === 'ask' ? esc(HF.ask || '')
    : ph === 'listen' ? 'Say one of the two — or anything you want to happen. Chinese or English.'
    : ph === 'speaking' ? 'Keep going, I’ll wait till you finish.'
    : ph === 'thinking' ? ''
    : ph === 'heard' ? `“${esc(HF.heard)}”` : 'Allow the microphone to answer by voice, or tap a choice.';
  el.className = 'ch-hf ' + (ph === 'speaking' || ph === 'thinking' ? 'listen' : ph);
  el.innerHTML = `
    <button class="hf-orb" data-act="${ph === 'listen' || ph === 'speaking' ? 'hf-stop' : 'hf-again'}" aria-label="${ph === 'listen' || ph === 'speaking' ? 'Stop listening' : 'Answer by voice'}">${ic('mic')}<i></i><i></i></button>
    <div class="hf-t"><b>${label}</b>${sub ? `<span>${sub}</span>` : ''}</div>`;
}

/* Talk to the story (any time while listening): steers the next episode. Not a call with a character. */
let talkRec = null;
function openTalkSheet() {
  const s = byId(P.id); if (!s || !P.ep) return;
  if (P.needChoice) { if (VOICE_OK) { holdForHer(); hfListen(); return; } openChoiceSheet(); return; }
  const wasPlaying = isPlaying();
  if (wasPlaying) doPause();
  const lead = shortName(callerOf(s));
  const entry = openSheet(`
    <div class="sh-h"><div><h3>Talk to the story</h3><p>Say what you want to happen next — Episode ${P.ep.n + 1} will follow it.</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="ch-hf listen" id="tk-hf">
      <button class="hf-orb" data-act="talk-mic" aria-label="Speak">${ic('mic')}<i></i><i></i></button>
      <div class="hf-t"><b id="tk-l">${VOICE_OK ? 'Listening…' : 'Type it below'}</b><span id="tk-s">e.g. “I want him to finally admit it.” “Take me somewhere with just us.”</span></div>
    </div>
    <form class="ch-input" data-form="wish" autocomplete="off"><div class="fld"><input id="tk-text" type="text" maxlength="200" placeholder="Or type it…" enterkeyhint="send" aria-label="What should happen"><button class="ch-send" type="submit" aria-label="Send">${ic('send')}</button></div></form>
    <p class="tk-note">${ic('phone', 'xs')} Want to talk to ${esc(lead)} himself? That’s a call — tap the phone at the top.</p>`, { kind: 'talk', onClose: () => { stopTalk(); if (wasPlaying && !P.needChoice) { P.want = true; P.ep.kind === 'live' && (P.waiting || !P.cur) ? liveAdvance() : doPlay(); } } });
  entry.wasPlaying = wasPlaying;
  const inp = $('#tk-text', entry.el); if (inp) inp.addEventListener('focus', stopTalk);
  if (VOICE_OK) talkListen();
}
function stopTalk() { if (talkRec) { const r = talkRec; talkRec = null; r.cancel(); } }
function talkListen() {
  stopTalk(); earcon('open');
  const l = $('#tk-l'), sub = $('#tk-s'), box = $('#tk-hf');
  if (box) box.className = 'ch-hf listen';
  if (l) l.textContent = 'Listening…';
  const h = talkRec = recordAnswer({
    wait: 7000, max: 20000,
    onState: (s) => { if (talkRec !== h) return; if (s === 'speaking' && l) l.textContent = 'I’m listening…'; if (s === 'thinking' && l) l.textContent = 'Got it — one moment…'; },
  });
  h.done.then((r) => {
    if (talkRec !== h) return; talkRec = null;
    if (r.canceled) return;
    if (r.text) { sendWish(r.text); return; }
    if (box) box.className = 'ch-hf quiet';
    if (l) l.textContent = r.denied ? 'Microphone is off' : r.spoke ? 'Didn’t catch that — tap the mic and try again' : 'Tap the mic and say it';
    if (sub) sub.textContent = r.denied ? 'Allow the microphone, or type it below.' : 'Chinese or English both work.';
  });
}
async function sendWish(text) {
  const ss = getSess(P.id); if (!ss || !text) return;
  earcon('ok');
  const top = topSheet(); if (top && top.kind === 'talk') closeSheet(top);
  toast(`${ic('spark', 'sm')} Got it — Episode ${P.ep.n + 1} will follow that`);
  ss.wishes = (ss.wishes || []).concat(text).slice(-3); save();
  SPEC.key = ''; SPEC.map = {}; // the pre-written next episodes are being rewritten around her wish
  try { await sidReady(P.id); await API.wish(ss.sid, text); } catch (e) { console.warn(e); }
}

function openModeSheet() {
  const cur = modeOf();
  openSheet(`
    <div class="sh-h"><div><h3>How do you want to listen?</h3><p>Switch any time. Calls with characters work in every mode.</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="mode-list">
      ${Object.entries(MODES).map(([k, m]) => `<button class="mode-opt ${cur === k ? 'on' : ''}" data-act="set-mode" data-m="${k}" ${k === 'voice' && !VOICE_OK ? 'disabled' : ''}>
        <span class="mo-ic">${ic(m.icon)}</span><span class="mo-t"><b>${m.name}${k === 'voice' && !VOICE_OK ? ' · not supported in this browser' : ''}</b><small>${m.desc}</small></span>${cur === k ? ic('check') : ''}</button>`).join('')}
    </div>`, { kind: 'mode' });
}
function setMode(m) {
  if (!MODES[m] || (m === 'voice' && !VOICE_OK)) return;
  S.mode = m; save();
  if (m === 'voice') { VI.denied = false; primeMic(true); } else micRelease();
  closeSheet(); toast(`${ic(MODES[m].icon, 'sm')} ${MODES[m].name}`);
  updateModePill();
  if (P.needChoice) { closeAllSheets(); hfStop(); stopAutoCountdown(); endOfEpisodeFlow(); }
}
function updateModePill() {
  const el = $('#pl-mode'); if (!el) return;
  const note = $('#pl-note');
  if (note) note.hidden = !(VOICE_OK && !LOCK_VOICE_OK && IOS && modeOf() === 'voice');
  const m = MODES[modeOf()];
  if (NARRA) {
    if (el.dataset.m !== modeOf()) { el.dataset.m = modeOf(); el.innerHTML = `${ic({ voice: 'headphones', auto: 'volume', tap: 'hand' }[modeOf()])}<span>${{ voice: 'Hands-free', auto: 'Lean back', tap: 'Tap' }[modeOf()]}</span>`; }  // its own icons: Talk (mic) and Sleep (moon) sit in the same row
    return;
  }
  const html = `${ic(m.icon, 'sm')}<span><b>${m.name}</b> · ${m.short}</span>${ic('chevR', 'xs')}`;
  if (el.dataset.m !== modeOf()) { el.dataset.m = modeOf(); el.innerHTML = html; }
}

/* 11-09 她要求：语音说“A / 选B / 第一个 / option B / the second one”或直接说出选项内容，和点那个选项一样（预写好的下一集马上开播）。
 * 服务器 pick_letter + match_choice 同样会认（转述也认）；这里先认字母/序号和几乎原样的选项文字，好走本地秒开。 */
const LET_ZH = /^(大写)?(我|那)?(就|还是|要)?(选|要|挑|走)?(选项)?(?<k>a|ａ|b|ｂ|1|2|一|二|第一个|第二个|第一|第二|前面那个|后面那个|前一个|后一个|上面那个|下面那个|左边那个|右边那个)(个|吧|八|8|呀|啊|哦|嘛|了|好了|这个|那个)*$/;
const LET_ZH2 = /^(我|那)?(就|还是|要)?(选|挑|上|宣|旋|悬|学)(选项)?(?<k>诶|欸|哎|唉|地|比|必|逼|币|笔|臂|壁|毕|闭|鼻|避|碧|彼)(吧|八|呀|啊|了)*$/;
const LET_EN = /^(i ?(ll|will|d|would)? ?(choose|pick|go with|take|select|say|want)|(let ?s|lets) go with|go with|choose|pick|take|select|maybe)? ?(option|letter|choice|the)? ?(?<k>a|b|ay|bee|be|1|2|one|two|first|second|first one|second one|top one|bottom one|left one|right one)( one| option)?( please)?$/;
const FIRST = new Set(['a', 'ａ', '1', '一', '第一个', '第一', '前面那个', '前一个', '上面那个', '左边那个', '诶', '欸', '哎', '唉', '地', 'ay', 'one', 'first', 'first one', 'top one', 'left one']);
function pickSpoken(text, choices) {
  if (!choices || choices.length < 2 || !text) return -1;
  const t = String(text).trim().toLowerCase();
  const z = t.replace(/[\s，。！？、,.!?~…“”"'：:]+/g, '');
  let m = z.match(LET_ZH) || z.match(LET_ZH2);
  if (m) return FIRST.has(m.groups.k) ? 0 : 1;
  const e = t.replace(/'/g, '').replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
  m = e.match(LET_EN);
  if (m) return FIRST.has(m.groups.k) ? 0 : 1;
  const norm = (x) => String(x).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
  for (let i = 0; i < 2; i++) { const c = norm(choices[i]); if (c && (z === c || norm(t) === c)) return i; }
  return -1;
}
function submitChoice(text, via) {
  if (!P.ep || !P.needChoice) return;
  if (via === 'voice' || via === 'free') {
    const k = pickSpoken(text, P.ep.choices);
    if (k >= 0) { text = P.ep.choices[k]; via = 'option'; toast((LANG === 'zh' ? '已选 ' : 'Picked ') + 'AB'[k]); }
  }
  stopAutoCountdown(); hfStop(true);
  const id = P.id, nextN = P.ep.n + 1;
  primeAudio();
  if (!isUnlocked(id, nextN)) {
    // eyes-free answers (voice / no answer) never stop for a sheet when she has the coins
    if ((S.autoUnlock || via === 'auto' || via === 'voice') && S.coins >= PRICE) {
      addCoins(-PRICE, `Auto-unlock Ep ${nextN} · ${byId(id).title}`);
      markUnlocked(id, nextN);
      toast(`${coinIc('sm')} Auto-unlocked Ep ${nextN} (−${PRICE})`);
    } else {
      openUnlockSheet(id, nextN, () => submitChoice(text, via));
      return;
    }
  }
  stopMic();
  closeAllSheets();
  sendNext(id, text, via);
}
async function sendNext(id, text, via) {
  const ss = getSess(id); if (!ss) return;
  if (!ss.sid) await sidReady(id);
  const nextN = P.ep.n + 1;
  ss.chosen = ss.chosen || {};
  ss.chosen[P.ep.n] = via === 'silence' ? '' : text;
  ensureToday(); S.tasks.choices += 1;
  P.needChoice = false;
  if (!P.aux) audio.pause(); P.cur = '';
  const specText = via === 'auto' ? ((P.ep.choices || [])[0] || '') : text;
  const sp = (via === 'option' || via === 'auto') && SPEC.key === ss.sid + ':' + nextN ? SPEC.map[specText] : null;
  if (sp && sp.ep && sp.ep.n === nextN && sp.ep.lines && sp.ep.lines[0] && sp.ep.lines[0].url) {
    // Instant start: the next episode for this choice was pre-written and its first lines are voiced.
    SPEC.key = '';
    const ep = Object.assign({ durs: {} }, sp.ep, { kind: 'live' });
    ss.eps = ss.eps.filter((e) => e.n !== nextN); ss.eps.push(ep); ss.eps.sort((a, b) => a.n - b.n);
    ss.job = { id: sp.job, n: nextN, text, via };
    ep._done = false; P.gen = null; save();
    EARLY = { n: 0, url: '' };
    afterAux(() => { if (P.ep !== ep && ss.job && ss.job.id === sp.job) playEpisode(id, ep, { autoplay: true }); });
    P.jobDone = false;
    openPlayer(); updatePlayerUI(); renderMini();
    API.next({ sid: ss.sid, text: via === 'auto' ? '' : text, via }).then((res) => {
      if (res && res.job === sp.job) startGeneration(res.job, nextN, text, false, true);
      else if (res && res.job) { // relay could not use the pre-written episode: fall back to the fresh one
        ss.eps = ss.eps.filter((e) => e !== ep); audio.pause(); P.cur = ''; P.ep = null;
        P.gen = { n: nextN, text, via, status: 'writing', err: null, t0: Date.now() };
        ss.job = { id: res.job, n: nextN, text, via }; save();
        startGeneration(res.job, nextN, text, false);
      }
    }).catch((e) => { console.warn(e); startGeneration(sp.job, nextN, text, false, true); });
    return;
  }
  P.gen = { n: nextN, text, via, status: 'writing', err: null, t0: Date.now() };
  save();
  const pre = via !== 'auto' && via !== 'silence' ? BRIDGES[ss.sid + ':' + (nextN - 1)] : null;
  const early = EARLY.n === nextN && EARLY.url; EARLY = { n: 0, url: '' };
  Object.assign(BR, { n: nextN, url: early || (pre && pre.url) || '', played: !!early, ackDone: true, t0: Date.now() });
  // the bridge itself tells her she was heard (no separate “Okay — your way” first: that cost 1.8 s); no bridge → the old ack
  if (early) { if (!auxTalking()) afterBridge(); }
  else if (maybeBridge()) { /* bridge playing */ }
  else if (via === 'voice') { BR.ackDone = false; playAux(`ack.${LANG}.mp3`).then(() => { BR.ackDone = true; if (P.gen && !maybeBridge()) keepAlive(); }); }
  else bedStart();
  updatePlayerUI(); renderMini(); openPlayer();
  try {
    const res = await API.next({ sid: ss.sid, text: via === 'silence' ? '' : text, via });
    if (!res || !res.job) throw new Error('No job returned');
    if (res.bridge && res.bridge.url && BR.n === nextN && !BR.played && res.bridge.url !== BR.url) { BR.url = res.bridge.url; if (BR.ackDone) maybeBridge(); }   // the relay picked a different line (the bespoke one became ready)
    ss.job = { id: res.job, n: nextN, text, via }; save();
    startGeneration(res.job, nextN, text, false);
  } catch (e) {
    console.warn(e);
    P.gen = null; P.needChoice = true; bedStop();
    updatePlayerUI(); renderMini();
    openChoiceSheet();
    const err = $('#ch-err'); if (err) { err.hidden = false; err.textContent = `Couldn't write the next episode (${e.message || 'error'}). Try again.`; }
  }
}

let genToken = 0;
function cancelGen() { genToken++; P.gen = null; bedStop(); }
function startGeneration(jobId, n, text, resumed, alreadyPlaying) {
  const my = ++genToken;
  const id = P.id;
  if (!alreadyPlaying) {
    P.gen = P.gen && P.gen.n === n ? P.gen : { n, text, via: 'option', status: 'writing', t0: Date.now() };
    P.want = true;
  }
  updatePlayerUI(); renderMini();
  const ss = getSess(id);
  let started = !!alreadyPlaying;
  let fails = 0;
  let have = null;   // long-poll: the relay answers as soon as one more line is voiced (no 600 ms polling over the tunnel)
  const getJob = async () => {
    try {
      const j = await API.job(jobId, started ? null : have); fails = 0;
      if (j && j.ep && j.ep.lines) have = j.ep.lines.filter((l) => l.url != null).length; else if (j) have = 0;
      return j;
    } catch (e) {
      if (!/no job/i.test(e.message || '')) { fails++; return null; }
      // The relay restarted and forgot this job. If the episode was finished, the relay still has it (rebuilt from its log).
      try { const r = await API.ep(ss.sid, n); if (r && r.ep) return { status: 'done', error: null, ep: r.ep }; } catch (e2) { /* not finished */ }
      return { status: 'lost' };
    }
  };
  const poll = async () => {
    if (my !== genToken && started === false) return;
    const j = await getJob();
    if (!j) {
      if (fails === 12 && my === genToken && !started) toast(LANG === 'zh' ? '网络有点慢，还在连…' : 'The connection is slow — still trying…');
      setTimeout(poll, fails > 12 ? 2500 : 1200); return;
    }
    if (j.status === 'lost') {
      const epLive = ss.eps.find((e) => e.n === n);
      if (started && epLive) { // was already playing the first lines: play what is voiced, then the choice point
        ss.job = null; save();
        P.jobDone = true; (epLive.lines || []).forEach((l) => { if (l.url == null) l.url = ''; }); if (P.ep === epLive && P.waiting) liveAdvance();
        return;
      }
      if (my !== genToken) return;
      // Ask for the episode again (same answer). The relay rebuilds the session from its log if it restarted.
      const prevEp = ss.eps.find((e) => e.n === n - 1);
      const via = (ss.job && ss.job.via) || (((prevEp && prevEp.choices) || []).includes(text) ? 'option' : 'free');
      ss.eps = ss.eps.filter((e) => e.n !== n);
      try {
        const res = await API.next({ sid: ss.sid, text: via === 'auto' || via === 'silence' ? '' : text, via });
        if (!res || !res.job || my !== genToken) throw new Error('No job returned');
        ss.job = { id: res.job, n, text, via }; save();
        startGeneration(res.job, n, text, false);
      } catch (e) {
        console.warn(e);
        ss.job = null; P.gen = null; P.needChoice = true; bedStop(); save();
        updatePlayerUI(); renderMini(); openChoiceSheet();
        const err = $('#ch-err'); if (err) { err.hidden = false; err.textContent = LANG === 'zh' ? `下一集没接上（${e.message || '出错'}），再选一次试试。` : `Couldn't write the next episode (${e.message || 'error'}). Try again.`; }
      }
      return;
    }
    if (j.status === 'error') {
      if (my === genToken) {
        P.gen = null;
        ss.job = null; save();
        const epLive = ss.eps.find((e) => e.n === n);
        if (epLive && P.ep === epLive) { P.jobDone = true; (epLive.lines || []).forEach((l) => { if (l.url == null) l.url = ''; }); if (P.waiting) liveAdvance(); }
        else { P.needChoice = true; updatePlayerUI(); renderMini(); openChoiceSheet(); }
        toast(`Generation failed: ${esc(j.error || 'unknown error')}`);
      }
      return;
    }
    if (P.gen && P.gen.n === n) P.gen.status = j.status;
    if (j.ep) {
      let ep = ss.eps.find((e) => e.n === j.ep.n);
      if (!ep) { ep = { durs: {} }; ss.eps.push(ep); ss.eps.sort((a, b) => a.n - b.n); }
      const durs = ep.durs || {};
      Object.assign(ep, j.ep, { durs, kind: j.ep.kind || 'live' });
      ep._done = j.status === 'done';
      if (ep._done) { ss.job = null; delete ep._done; }
      save();
      if (!started && my === genToken && P.gen && P.gen.n === ep.n) {
        const lines = ep.lines || [];
        let k = 0; while (k < lines.length && lines[k].url === '') k++;
        let ready = 0; for (let x = k; x < lines.length && lines[x].url; x++) ready++;
        // 11-09: start on the first voiced line (the others are being voiced in parallel; the bridge already covered the wait).
        // Never cut the ack / bridge mid-sentence: check again the moment it ends.
        if (((lines[k] && lines[k].url && ready >= 1) || j.status === 'done') && auxTalking()) { if (P.gen) P.gen.ready = true; const w = () => (auxTalking() ? setTimeout(w, 100) : poll()); setTimeout(w, 100); return; }
        if ((lines[k] && lines[k].url && ready >= 1) || (j.status === 'done')) {
          started = true;
          P.gen = null;
          ep._done = j.status === 'done' ? undefined : false;
          playEpisode(id, ep, { autoplay: true });
          P.jobDone = j.status === 'done';
          if (!P.want) updatePlayerUI();
        }
      } else if (P.ep === ep) {
        P.jobDone = j.status === 'done';
        if (P.waiting && P.want) liveAdvance();
        else updatePlayerUI();
      }
      if (isDetailOpen(id)) renderDetailEpisodes();
    }
    updatePlayerUI();
    if (j.status !== 'done') setTimeout(poll, started ? 600 : 30);
    else if (P.ep && P.ep.n === n && P.waiting && P.want) liveAdvance();
  };
  poll();
}

function prevEpisode() {
  if (!P.ep) return;
  if (P.cur && audio.currentTime > 3 && P.ep.kind !== 'live') { audio.currentTime = 0; return; }
  const ss = getSess(P.id); if (!ss) return;
  const i = ss.eps.indexOf(P.ep);
  if (i > 0) playEpisode(P.id, ss.eps[i - 1]);
  else if (P.ep.kind !== 'live') audio.currentTime = 0;
  else { P.idx = 0; liveAdvance(); }
}
function nextEpisode() {
  if (!P.ep) return;
  const ss = getSess(P.id); if (!ss) return;
  const i = ss.eps.indexOf(P.ep);
  if (i >= 0 && i < ss.eps.length - 1) { playEpisode(P.id, ss.eps[i + 1]); return; }
  if (P.gen) return;
  if (P.ep.ending) { openEndingSheet(); return; }
  if (P.ep.kind === 'live' && !P.jobDone) { toast('Still writing this episode…'); return; }
  audio.pause();
  P.idx = (P.ep.lines || []).length;
  onEpisodeEnd();
}

function openEndingSheet() {
  const s = byId(P.id);
  openSheet(`
    <div class="ul-head">
      <div class="ul-art"><img src="${esc(coverOf(s))}" alt=""></div>
      <h3>The end — for this path</h3>
      <p>Your choices led here. Start again and the story will be written differently.</p>
    </div>
    <div class="ul-btns">
      <button class="btn btn-grad" data-act="restart" data-id="${esc(s.id)}">${ic('restart', 'sm')} Start over</button>
      <button class="btn btn-ghost" data-act="sheet-close">Close</button>
    </div>`);
}

/* =========================================================================
 * 10. Unlock / store / ad / sleep / speed / episodes / profile sheets
 * ========================================================================= */
let wfTimer = 0;
function openUnlockSheet(id, n, onDone, opts = {}) {
  const s = byId(id);
  const isCall = !!opts.call;
  const price = isCall ? CALL_PRICE : PRICE;
  const caller = isCall ? callerOf(s, opts.who) : null;
  const k = isCall ? `call:${id}` : `${id}:${n}`;
  if (!S.waitFree[k]) { S.waitFree[k] = Date.now() + 24 * 3600 * 1000; save(); }
  const body = () => {
    const enough = S.coins >= price;
    return `
    <div class="sh-h"><div></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="ul-head" style="margin-top:-30px">
      <div class="ul-art ${isCall ? 'round' : ''}"><img src="${esc(isCall ? callerAv(s, caller && caller.key) : coverOf(s))}" alt=""><div class="lk">${ic(isCall ? 'phone' : 'lock', 'lg')}</div></div>
      <h3>${isCall ? `Call ${esc(shortName(caller))}` : `Unlock Episode ${n}`}</h3>
      <p>${isCall ? `${esc(s.title)} · your first call was free` : `${esc(s.title)} · written live from your choice`}</p>
    </div>
    <div class="ul-price"><span>Price</span><b>${coinIc()} ${price} coins${isCall ? ' / call' : ''}</b></div>
    <div class="ul-price"><span>Your balance</span><b><span class="coins-n">${S.coins}</span> coins</b></div>
    <div class="ul-btns">
      ${enough
        ? `<button class="btn btn-grad" data-act="ul-coins">${coinIc()} ${isCall ? 'Call' : 'Unlock'} with ${price} coins</button>`
        : `<button class="btn btn-grad" data-act="store">${coinIc()} Not enough coins · Get more</button>`}
      <button class="btn btn-ghost" data-act="ul-ad">${ic('tv', 'sm')} Watch an ad to ${isCall ? 'call free' : 'unlock'}</button>
      ${isCall ? '' : `<div class="wait-free" aria-disabled="true">${ic('hourglass', 'sm')} Wait-free in <span id="wf-t">${fmtWait(S.waitFree[k])}</span></div>`}
      ${isCall ? `<button class="link-btn" data-act="vip-from-call">${ic('crown', 'xs')} VIP calls are free</button>` : enough ? `<button class="link-btn" data-act="store">Get more coins</button>` : ''}
    </div>
    ${isCall ? '' : `<div class="toggle-row">
      <span>Auto-unlock next episodes<small>Use coins automatically when you make a choice</small></span>
      <button class="switch ${S.autoUnlock ? 'on' : ''}" data-act="auto-unlock" role="switch" aria-checked="${S.autoUnlock}" aria-label="Auto-unlock"></button>
    </div>`}`;
  };
  const entry = openSheet(body(), { kind: 'unlock', id, n, onDone, call: isCall, price, who: opts.who, onClose: () => clearInterval(wfTimer) });
  entry.refresh = () => { entry.el.innerHTML = '<div class="grab"></div>' + body(); };
  clearInterval(wfTimer);
  wfTimer = setInterval(() => { const t = $('#wf-t'); if (t) t.textContent = fmtWait(S.waitFree[k]); }, 1000);
}
const fmtWait = (until) => { const s = Math.max(0, Math.floor((until - Date.now()) / 1000)); return `${pad2(Math.floor(s / 3600))}:${pad2(Math.floor((s % 3600) / 60))}:${pad2(s % 60)}`; };
function finishUnlock(entry, how) {
  if (entry.call) toast(`${ic('phone', 'sm')} Calling${how ? ' · ' + how : ''}`);
  else { markUnlocked(entry.id, entry.n); toast(`${ic('unlock', 'sm')} Episode ${entry.n} unlocked${how ? ' · ' + how : ''}`); }
  const cb = entry.onDone;
  closeSheet(entry);
  if (isDetailOpen(entry.id)) renderDetailEpisodes();
  if (cb) cb();
}

function playAd(onDone) {
  const ad = $('#ad');
  ad.hidden = false;
  ad.innerHTML = `
    <span class="ad-tag">AD</span><span class="ad-count" id="ad-c">5</span>
    <div class="ad-art"><svg viewBox="0 0 24 24" fill="none" stroke="#140906" stroke-width="2.6" stroke-linecap="round"><path d="M5 10v4M9.5 6.5v11M14 9v6M18.5 7.5v9"/></svg></div>
    <h3>${NARRA ? 'narra' : 'Unscripted'} VIP</h3>
    <p>Every episode unlocked. Every choice, no waiting. (Simulated ad)</p>
    <div class="ad-bar"><i id="ad-bar"></i></div>`;
  requestAnimationFrame(() => requestAnimationFrame(() => { const b = $('#ad-bar'); if (b) b.style.width = '100%'; }));
  let left = 5;
  const t = setInterval(() => {
    left -= 1;
    const c = $('#ad-c'); if (c) c.textContent = left > 0 ? left : '✓';
    if (left <= 0) { clearInterval(t); setTimeout(() => { ad.hidden = true; ad.innerHTML = ''; onDone(); }, 350); }
  }, 1000);
}

const PACKS = [
  { n: 100, price: '$0.99', bonus: '' },
  { n: 300, price: '$2.99', bonus: '+30 bonus', hot: '' },
  { n: 600, price: '$4.99', bonus: '+80 bonus', hot: 'POPULAR' },
  { n: 1500, price: '$9.99', bonus: '+300 bonus', hot: 'BEST VALUE' },
];
function openStore() {
  const body = () => `
    <div class="sh-h"><div><h3>Coin store</h3><p>Balance: ${coinIc('sm')} <b class="coins-n tnum">${S.coins}</b></p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="packs">
      ${PACKS.map((p, i) => `<button class="pack" data-act="buy" data-i="${i}">${p.hot ? `<span class="hot">${p.hot}</span>` : ''}${coinIc('lg')}<b>${p.n}</b><small>${p.bonus}</small><span class="pr">${p.price}</span></button>`).join('')}
    </div>
    <div class="test-note">${ic('spark', 'xs')} Test coins — no real payment. Tapping a pack just adds coins.</div>
    <div class="vip-card">
      <h4>${ic('crown', 'sm')} VIP · Unlimited episodes</h4>
      <ul>
        <li>${ic('check')} Every live episode unlocked</li>
        <li>${ic('check')} No ads, no waiting</li>
        <li>${ic('check')} Test toggle — no charge</li>
      </ul>
      <button class="btn ${S.vip ? 'btn-ghost' : 'btn-grad'} btn-block" data-act="vip">${S.vip ? 'VIP is on · Turn off' : 'Start VIP (test)'}</button>
    </div>`;
  const entry = openSheet(body(), { kind: 'store' });
  entry.refresh = () => { entry.el.innerHTML = '<div class="grab"></div>' + body(); };
}

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
function cycleSpeed() {
  const i = SPEEDS.indexOf(S.speed);
  S.speed = SPEEDS[(i + 1) % SPEEDS.length];
  setAudioRate(); save(); updatePlayerUI();
  toast(`Speed ${S.speed}x`);
}
const SLEEPS = [['Off', 0], ['5 minutes', 5], ['15 minutes', 15], ['30 minutes', 30], ['1 hour', 60], ['End of episode', -1]];
function openSleepSheet() {
  const cur = S.sleep ? (S.sleep.eoe ? -1 : 'timer') : 0;
  openSheet(`
    <div class="sh-h"><div><h3>Sleep timer</h3><p>${S.sleep && S.sleep.until ? `Pausing in ${fmtTime((S.sleep.until - Date.now()) / 1000)}` : S.sleep && S.sleep.eoe ? 'Stops at the end of this episode' : 'Fall asleep to your story'}</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="sh-list">
      ${SLEEPS.map(([l, m]) => `<button class="opt ${(m === 0 && cur === 0) || (m === -1 && cur === -1) ? 'on' : ''}" data-act="sleep" data-m="${m}">${l}${(m === 0 && cur === 0) || (m === -1 && cur === -1) ? ic('check') : ''}</button>`).join('')}
    </div>`);
}
function updateSleepTool() {
  const el = $('#pl-sleep'); if (!el) return;
  const lbl = S.sleep ? (S.sleep.eoe ? 'End of ep' : fmtTime((S.sleep.until - Date.now()) / 1000)) : 'Sleep';
  el.classList.toggle('on', !!S.sleep);
  const sp = el.querySelector('span'); if (sp && sp.textContent !== lbl) sp.textContent = lbl;
}

function openEpisodesSheet() {
  const s = byId(P.id); if (!s) return;
  openSheet(`
    <div class="sh-h"><div><h3>Episodes</h3><p>${esc(s.title)}</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="ep-list">${episodeRows(s)}</div>`, { kind: 'eps' });
}

function openProfile() {
  const body = () => `
    <div class="sh-h"><div></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="pf-head" style="margin-top:-34px">
      <div class="pf-av">${esc((S.name || '?').slice(0, 1).toUpperCase())}</div>
      <div><b>${esc(S.name || 'Listener')}</b>${S.vip ? `<span class="vip-chip">${ic('crown')} VIP</span>` : ''}<p class="pf-meta">${coinIc('sm')} <span class="coins-n">${S.coins}</span> coins · ${S.played.length} series started</p></div>
    </div>
    <label class="field-l" for="pf-name">What characters call you</label>
    <form class="field" data-form="name"><input id="pf-name" maxlength="24" value="${esc(S.name)}" placeholder="Your name" autocomplete="given-name"><button class="btn btn-ghost" type="submit">Save</button></form>
    <label class="field-l" for="pf-me">Your story self <small>who you want to become, the life you want, how you want to be loved</small></label>
    <form class="field me" data-form="me"><textarea id="pf-me" maxlength="400" rows="3" placeholder="${LANG === 'zh' ? '比如：我在海边开了一家花店。我想被毫不犹豫地选择，被温柔又笃定地爱着。' : 'e.g. I run my own flower shop. I want to be chosen without hesitation, and loved gently but surely.'}">${esc(S.me || '')}</textarea><button class="btn btn-ghost" type="submit">Save</button></form>
    <div class="me-chips">${(LANG === 'zh' ? ['我想被坚定地选择。', '我是在上海开工作室的设计师。', '我想被好好地宠着、护着。', '我比自己以为的更勇敢。'] : ['I want to be chosen, firmly.', 'I\u2019m a successful designer in New York.', 'I want to feel safe and adored.', 'I\u2019m braver than I think.']).map((t) => `<button class="chip" data-act="me-chip" data-t="${esc(t)}">${esc(t)}</button>`).join('')}</div>
    <span class="field-l">How you listen</span>
    <button class="opt mode-row" data-act="mode-sheet"><span class="ol">${ic(MODES[modeOf()].icon)} ${MODES[modeOf()].name} · ${MODES[modeOf()].short}</span>${ic('chevR', 'sm')}</button>
    <span class="field-l">Story language</span>
    <div class="segc"><button class="${LANG === 'en' ? 'on' : ''}" data-act="lang" data-l="en">English</button><button class="${LANG === 'zh' ? 'on' : ''}" data-act="lang" data-l="zh">中文</button></div>
    <div class="toggle-row"><span>Auto-unlock episodes<small>Spend ${PRICE} coins automatically on Ep 4+</small></span><button class="switch ${S.autoUnlock ? 'on' : ''}" data-act="auto-unlock" role="switch" aria-checked="${S.autoUnlock}" aria-label="Auto-unlock"></button></div>
    <div class="toggle-row"><span>VIP (test)<small>Makes every episode free</small></span><button class="switch ${S.vip ? 'on' : ''}" data-act="vip" role="switch" aria-checked="${S.vip}" aria-label="VIP"></button></div>
    <div class="sh-list" style="margin-top:12px">
      <button class="opt" data-act="store"><span class="ol">${coinIc()} Coin store</span>${ic('chevR', 'sm')}</button>
      <button class="opt danger" data-act="reset"><span class="ol">Reset all data</span>${ic('trash', 'sm')}</button>
    </div>
    <p class="foot-note" style="padding-bottom:0">${MOCK ? 'Demo mode · mock content' : 'Live mode'} · ${BRAND}</p>`;
  const entry = openSheet(body(), { kind: 'profile' });
  entry.refresh = () => { const v = ($('#pf-name', entry.el) || {}).value; entry.el.innerHTML = '<div class="grab"></div>' + body(); if (v != null) $('#pf-name', entry.el).value = v; };
}
function langUrl(l) {
  const q = new URLSearchParams(location.search); q.set('lang', l); q.delete('k');
  if (MOCK) q.set('mock', '1');
  return location.pathname + '?' + q.toString() + location.hash.replace('#/player', '#/home');
}

/* =========================================================================
 * 10b. Voice calls with the lead (incoming / outgoing / in-call / ended)
 * ========================================================================= */
const CALL_PRICE = 20;
const tz = (en, zh) => (LANG === 'zh' ? zh : en);
const CALL_WAIT = 3500;   // 11-09: a real call doesn't wait for "your turn" — if she says nothing he carries on / draws her in   // after he finishes: how long the mic waits for her to start talking before he carries on
const MAX_RING = 6500;    // …but never longer than this: then "Hey." and a "let me think" while his line finishes
const MIN_RING = 1100;    // an outgoing call rings at least this long before he picks up (feels like a real call; covers his first line)
const callAudio = new Audio();
callAudio.preload = 'auto';
callAudio.setAttribute('playsinline', '');
let callPre = null;
let C = null;            // current call
let callSeq = 0;
let callRecog = null;
const callActive = () => !!(C && C.phase !== 'ended');

/* WebAudio: unlocked on the first gesture so the ring can play later without one */
let actx = null;
function unlockCtx() {
  try {
    if (!actx) { const AC = window.AudioContext || window.webkitAudioContext; if (AC) actx = new AC(); }
    if (actx && actx.state === 'suspended') actx.resume().catch(() => {});
  } catch (e) { actx = null; }
}
document.addEventListener('pointerdown', unlockCtx, { capture: true, passive: true });
function tone(t, f, dur, peak, type) {
  const o = actx.createOscillator(), g = actx.createGain();
  o.type = type || 'sine'; o.frequency.value = f;
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g); g.connect(actx.destination);
  o.start(t); o.stop(t + dur + 0.05);
}
function ringOnce() {
  if (!actx || actx.state !== 'running') return;
  const t = actx.currentTime + 0.03;
  [[0, 659.25], [0.17, 830.61], [0.34, 987.77], [1.0, 659.25], [1.17, 830.61], [1.34, 987.77]].forEach(([d, f]) => {
    tone(t + d, f, 1.1, 0.12); tone(t + d, f * 2, 0.5, 0.025);
  });
}
function startRing() {
  unlockCtx(); stopRing();
  if (playLoop('ring-in.mp3')) return;
  ringOnce(); if (C) C.ringT = setInterval(ringOnce, 3200);
}
function stopRing() { if (C && C.ringT) { clearInterval(C.ringT); C.ringT = 0; } if (C) clearInterval(C.ringW); stopLoop(); }
/* 11-10 "the ring should start the instant you call": both ring files are kept in memory from app start, so the
 * element never waits on the network; the watchdog below switches to a WebAudio ring within ~0.5 s if iOS holds it. */
const RINGB = {};
function warmRings() {
  if (MOCK) return;
  ['ringback.mp3', 'ring-in.mp3'].forEach((u) => {
    if (RINGB[u]) return; RINGB[u] = 1;
    fetch(absUrl(u)).then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b && b.size) RINGB[u] = URL.createObjectURL(b.type ? b : new Blob([b], { type: 'audio/mpeg' })); else delete RINGB[u]; }).catch(() => { delete RINGB[u]; });
  });
}
const ringSrc = (u) => (typeof RINGB[u] === 'string' ? RINGB[u] : u);
/** ringtone / ringback on the call element itself (loops until he picks up) */
function playLoop(url) {
  try {
    callSrcTok++;
    callAudio.loop = true; callAudio.src = ringSrc(url); callAudio.dataset.loop = '1'; callAudio.dataset.ring = url;
    const p = callAudio.play(); if (p && p.catch) p.catch(() => { if (C && !C.ringT && callAudio.dataset.loop) { delete callAudio.dataset.loop; unlockCtx(); const f = C.direction === 'incoming' ? ringOnce : ringbackOnce; f(); C.ringT = setInterval(f, C.direction === 'incoming' ? 3200 : 4000); } });
    return true;
  } catch (e) { return false; }
}
/* 11-09 she heard no ring: iOS can pause the <audio> when the mic is (re)opened for the call. While it rings, keep
 * checking that the tone is really playing (time moves); if the element won't play, fall back to a WebAudio ringback. */
function ringbackOnce() {
  if (!actx || actx.state !== 'running') return;
  const t = actx.currentTime + 0.03;
  tone(t, 440, 1.9, 0.07); tone(t, 480, 1.9, 0.07);
}
function ringWatch(call) {
  clearInterval(call.ringW); let last = -1, stuck = 0;
  call.ringW = setInterval(() => {
    if (C !== call || call.pickedUp || call.phase === 'ended' || !(call.phase === 'connecting' || call.phase === 'incoming')) { clearInterval(call.ringW); return; }
    if (call.ringT) return;   // already on the WebAudio fallback
    const playing = callAudio.dataset.loop && !callAudio.paused && callAudio.currentTime !== last;
    last = callAudio.currentTime;
    if (playing) { stuck = 0; return; }
    stuck += 1;
    if (stuck <= 1) { try { callAudio.dataset.loop = '1'; callAudio.loop = true; if (!/ring/.test(callAudio.dataset.ring || '')) { const u = call.direction === 'incoming' ? 'ring-in.mp3' : 'ringback.mp3'; callAudio.dataset.ring = u; callAudio.src = ringSrc(u); } const p = callAudio.play(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* ignore */ } return; }
    unlockCtx();
    const f = call.direction === 'incoming' ? ringOnce : ringbackOnce;
    f(); call.ringT = setInterval(f, call.direction === 'incoming' ? 3200 : 4000);
  }, 250);
}
function stopLoop() { delete callAudio.dataset.ring; if (callAudio.dataset.loop) { delete callAudio.dataset.loop; callAudio.loop = false; try { callAudio.pause(); } catch (e) { /* ignore */ } } }
function hangupTone() {
  unlockCtx();
  if (!actx || actx.state !== 'running') return;
  const t = actx.currentTime + 0.02;
  [0, 0.28, 0.56].forEach((d) => tone(t + d, 480, 0.18, 0.09, 'triangle'));
}

/* call audio element (iOS: primed inside the Accept / Call tap) */
function primeCallAudio() {
  try {
    if (callAudio.dataset.primed) return;
    callAudio.dataset.primed = '1';
    callAudio.src = SILENT;
    const p = callAudio.play();
    if (p && p.catch) p.catch(() => { delete callAudio.dataset.primed; });
  } catch (e) { /* ignore */ }
}
let callGain = null, callSrcTok = 0;
function callRoute() {
  return;  // 11-09: disabled — routing <audio> through WebAudio made the ring/his voice silent whenever iOS suspended the AudioContext
  if (callGain || !actx) return;
  try { const src = actx.createMediaElementSource(callAudio); callGain = actx.createGain(); src.connect(callGain); callGain.connect(actx.destination); } catch (e) { callGain = null; }
}
/** 免提 (speaker) = full level; 听筒 (earpiece) = low, for holding the phone to your ear. Browsers can't pick the earpiece itself. */
function applyCallVolume() {
  const v = C && C.speaker === false ? 0.3 : 1;
  if (callGain && actx) { try { callGain.gain.setTargetAtTime(v, actx.currentTime, 0.04); } catch (e) { callGain.gain.value = v; } }
  else { try { callAudio.volume = v; } catch (e) { /* ignore */ } }
}
function playCallSrc(url) {
  delete callAudio.dataset.loop; callAudio.loop = false;
  const tok = ++callSrcTok;
  // through WebAudio the line must be same-origin: wait (briefly) for its local copy
  if (callGain && blobable(url) && !blobNow(url)) { Promise.race([fetchBlob(url), sleep(4000)]).then(() => { if (tok === callSrcTok && C) playCallSrcNow(url); }); return; }
  playCallSrcNow(url);
}
function playCallSrcNow(url) {
  callAudio.src = srcFor(url);
  try { callAudio.defaultPlaybackRate = S.callSpeed || 1; callAudio.playbackRate = S.callSpeed || 1; callAudio.preservesPitch = true; callAudio.webkitPreservesPitch = true; } catch (e) { /* ignore */ }
  const p = callAudio.play();
  if (p && p.catch) p.catch((err) => { if (err && err.name === 'NotAllowedError' && C) { C.blocked = true; renderCallUI(); } });
}
callAudio.addEventListener('ended', onCallAudioDone);
/* 11-09 "he said hi, then nothing": if his line should be playing but the element sits paused (iOS audio-session change
 * when the mic opens) → play it again; if its time stops moving for 5 s → treat that line as done and go on. */
const CW = { last: -1, stuck: 0 };
setInterval(() => {
  const call = C;
  if (!call || !call.pickedUp || call.phase === 'ended' || call.held || EAR.utt || callAudio.dataset.loop || !(call.playing || call.fillerPlaying) || callAudio.src.startsWith('data:')) { CW.stuck = 0; CW.last = -1; return; }
  if (callAudio.paused && !callAudio.ended) { const p = callAudio.play(); if (p && p.catch) p.catch(() => {}); }
  if (callAudio.currentTime === CW.last) { CW.stuck += 1; if (CW.stuck >= 5) { CW.stuck = 0; onCallAudioDone(); } } else CW.stuck = 0;
  CW.last = callAudio.currentTime;
}, 1000);
callAudio.addEventListener('error', () => { if (!callAudio.src.startsWith('data:') && !callAudio.dataset.loop) onCallAudioDone(); });
function onCallAudioDone() {
  if (!C || callAudio.src.startsWith('data:') || callAudio.dataset.loop) return;
  if (C.fillerPlaying) {
    const wasThink = C.thinkPlaying || C.greeting;
    C.fillerPlaying = false; C.thinkPlaying = false; C.greeting = false;
    if (!wasThink) scheduleThink(C, C.turn);
  } else if (C.playing) { C.playing = false; C.idx += 1; gapFill(C); }
  else return;
  renderCallUI();
  setTimeout(callAdvance, 120);
}

function callersOf(s) {
  if (!s) return [];
  if (Array.isArray(s.callers) && s.callers.length) return s.callers;
  return [{ key: s.name || s.id, name: s.name || s.id, role: s.lead || '' }];
}
const callerOf = (s, key) => callersOf(s).find((c) => c.key === key) || callersOf(s)[0];
/** each caller's own face (villa: Jace / Theo / Kai…); falls back to the series avatar */
const callerAv = (s, key) => { const c = s && key ? callersOf(s).find((x) => x.key === key) : null; return (c && c.avatar) || avatarOf(s); };
const shortName = (c) => String((c && (c.name || c.key)) || '').split(/\s*[·•]\s*/)[0].trim();
const callCost = (id) => (S.vip || !(S.callsUsed || {})[id] ? 0 : CALL_PRICE);

/* 11-10 "connect faster": while she is on a series page / the caller list / the player, the relay already writes and
 * voices his first two lines for an outgoing call (POST /api/call/prepare); tapping Call then picks up in ~1 s.
 * Once per caller and story point every 8 min (each prepare costs a short write + two voiced lines). */
const PREPD = {};
function prepareCall(id, who) {
  if (MOCK || !API.callPrepare || callActive()) return;
  const s = byId(id); if (!s) return;
  who = who || (callersOf(s)[0] || {}).key; if (!who) return;
  const ss = getSess(id); const key = `${id}|${who}|${ss ? ss.sid + ':' + ss.eps.length : ''}|${LANG}`;
  if (PREPD[key] && Date.now() - PREPD[key] < 8 * 60e3) return;
  PREPD[key] = Date.now();
  API.callPrepare({ series: id, who, sid: ss ? ss.sid : null }).catch(() => { delete PREPD[key]; });
}

/** Outgoing entry point (detail / player / library / call again). */
function requestCall(id, opts = {}) {
  const s = byId(id); if (!s || callActive()) return;
  const cs = callersOf(s);
  if (!opts.who && cs.length > 1) { openCallerChooser(id, opts); return; }
  const who = opts.who || cs[0].key;
  primeCallAudio(); unlockCtx(); callRoute(); callMicPrime();
  const sid = opts.sid || (getSess(id) || {}).sid || null;
  const go = () => startCall(id, who, { direction: 'outgoing', sid });
  if (callCost(id) > 0) { openUnlockSheet(id, 0, go, { call: true, who }); return; }
  go();
}
function openCallerChooser(id, opts) {
  const s = byId(id);
  callersOf(s).slice(0, 3).forEach((c) => prepareCall(id, c.key));
  const cost = callCost(id);
  openSheet(`
    <div class="sh-h"><div><h3>Who do you want to call?</h3><p>${esc(s.title)} · ${cost ? `${coinIc('sm')} ${cost} coins per call` : 'First call is free'}</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
    <div class="sh-list">
      ${callersOf(s).map((c) => `
        <button class="caller-row" data-act="call-who" data-id="${esc(id)}" data-who="${esc(c.key)}">
          <img src="${esc(c.avatar || avatarOf(s))}" alt="">
          <span class="ct"><b>${esc(c.name || c.key)}</b><span>${esc(c.role || '')}</span></span>
          <span class="call-go">${ic('phone')}</span>
        </button>`).join('')}
    </div>`, { kind: 'chooser', opts });
}

function newCall(id, who, direction, sid) {
  const s = byId(id);
  stopCallPoll();
  C = {
    seq: ++callSeq, id, who, caller: callerOf(s, who), direction, sid: sid || null, cid: null,
    phase: direction === 'incoming' ? 'incoming' : 'connecting',
    lines: [], idx: 0, jobDone: false, hangup: false, choices: [], logged: new Set(),
    transcript: [], t0: 0, secs: 0, timer: 0, ringT: 0, turn: 0, fillers: [], fillerPlaying: false, playing: false,
    waiting: false, startP: null, accepted: direction !== 'incoming',
  };
  C.rec = createCallRec(C);
  if (P.cur && !audio.paused) doPause(); else P.want = false;
  return C;
}
/** Begin the server-side call (POST /api/call/start). Called on accept (incoming, pre-started while ringing) or on outgoing. */
function beginCallRequest(call) {
  if (call.startP) return call.startP;
  call.startP = (async () => {
    try {
      // the quick tunnel sometimes loses an answer: retry after 8 s with the same key (the relay hands back the same call)
      call.ckey = call.ckey || ('k' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7));
      let r = null, err = null;
      for (let i = 0; i < 3 && !r && C === call; i++) {
        try { r = await Promise.race([API.callStart({ series: call.id, who: call.who, sid: call.sid, direction: call.direction, ckey: call.ckey }), sleep(8000).then(() => { throw new Error('timeout'); })]); } catch (e) { err = e; }
      }
      if (!r) throw err || new Error('no answer');
      if (C !== call) { if (r && r.cid) API.callEnd({ cid: r.cid, seconds: 0 }).catch(() => {}); return; }
      call.cid = r.cid; if (r.who) call.who = r.who; call.job = r.job;
      if (r.prepared && (r.lines || []).length && !call.lines.length) {  // 11-10 prepared while she was on the page: his first lines are already voiced
        call.lines = r.lines.map((l) => ({ who: l.who, text: cleanText(l.text), url: l.url }));
        call.lines.forEach((l) => fetchBlob(l.url).then(() => { if (C === call && !call.pickedUp) callAdvance(); }));
      }
      if (r.greet && !(call.greet || []).length) { call.greet = [r.greet]; fetchBlob(r.greet); callAdvance(); }
      lowFetch(call, r.bridges || []);   // his "first sentence" replies: fetched after the first lines (browsers open only ~6 connections; 11-10 they queued the first line 9 s)
      pollCall(r.job, call.turn);
    } catch (e) {
      if (C !== call) return;
      toast(`Call failed: ${esc(e.message || 'error')}`);
      endCall('error');
    }
  })();
  return call.startP;
}
/** fillers / bridges are fetched two at a time once his first lines are in (or after 2.5 s), so they never queue ahead of them */
function lowFetch(call, urls) {
  call.lowQ = (call.lowQ || []).concat(urls.filter((u) => u && !BLOB.has(u)));
  if (call.lowRun) return;
  call.lowRun = true;
  const firstIn = () => { const l = call.lines.slice(0, 2).filter((x) => x.url); return l.length && l.every((x) => !blobable(x.url) || blobNow(x.url)); };
  const t0 = Date.now();
  const pump = () => {
    if (C !== call) return;
    if (!call.pickedUp && !firstIn() && Date.now() - t0 < 2500) { setTimeout(pump, 200); return; }
    const next = () => { const u = call.lowQ.shift(); if (!u) return Promise.resolve(); return fetchBlob(u).then(next, next); };
    next(); next();
  };
  pump();
}
function prefetchFillers(call) {
  // {urls:[short fillers], think:["let me think" lines]} — older servers send only urls
  API.fillers({ series: call.id, who: call.who }).then((r) => {
    if (C !== call) return;
    call.fillers = (r && r.urls) || []; call.thinks = (r && r.think) || []; call.greet = (r && r.greet) || [];
    call.greet.forEach((u) => fetchBlob(u));
    lowFetch(call, [...call.fillers, ...call.thinks]);
    callAdvance();
  }).catch(() => {});
}
function startCall(id, who, o) {
  closeAllSheets();
  const call = newCall(id, who, 'outgoing', o.sid);
  S.callsUsed = S.callsUsed || {}; S.callsUsed[id] = true;
  ensureToday(); S.tasks.call = (S.tasks.call || 0) + 1; save();
  call.dialAt = Date.now();
  renderCall();
  playLoop('ringback.mp3');  // the ringback tone you hear while it rings on his side
  ringWatch(call);
  prefetchFillers(call);
  beginCallRequest(call);
}
/** a voice call needs the mic: ask inside the tap that starts / accepts it, so the prompt never lands mid-call */
function callMicPrime() {
  if (!VOICE_OK) return;
  micStream().then(() => { if (C && !C.pickedUp && callAudio.dataset.loop && callAudio.paused) callAudio.play().catch(() => {}); }).catch(() => { VI.denied = true; });
}
/** He picks up: "Hello?" right away (pre-voiced), then his first line as soon as it's voiced. */
function maybePickUp(call) {
  if (call.pickedUp) return true;
  const l0 = call.lines.find((l) => l.url);
  const firstReady = !!l0 && (!blobable(l0.url) || !!blobNow(l0.url));   // voiced AND already on the phone → no gap after "Hey."
  const greet = (call.greet || [])[0];
  // outgoing: it rings ≥1.8 s, and keeps ringing (like a real phone, up to ~7 s) until his first real line is voiced,
  // so "Hey." is followed straight away by what he has to say instead of a silent gap (11-09)
  const rang = Date.now() - (call.dialAt || 0);
  if (call.direction === 'outgoing' && (rang < MIN_RING || (!firstReady && rang < MAX_RING))) {
    if (!call.pickT) call.pickT = setTimeout(() => { call.pickT = 0; if (C === call) callAdvance(); }, Math.max(200, (rang < MIN_RING ? MIN_RING : MAX_RING) - rang + 30));
    return false;
  }
  if (!greet && !firstReady) return false;
  call.pickedUp = true; stopRing();
  if (!call.t0) { call.t0 = Date.now(); call.timer = setInterval(updateCallTimer, 1000); }
  if (greet) { call.fillerPlaying = true; call.greeting = true; playCallSrc(greet); renderCallUI(); return false; }
  return true;
}
/** He calls you: shows the ringing screen; generation of his first line starts while it rings. */
function showIncoming(id, who, sid) {
  if (callActive()) return;
  const call = newCall(id, who, 'incoming', sid);
  renderCall();
  startRing(); ringWatch(call);
  prefetchFillers(call);
  beginCallRequest(call);
}
function acceptCall() {
  if (!C || C.phase !== 'incoming') return;
  primeCallAudio(); unlockCtx(); callRoute(); callMicPrime();
  stopRing();
  C.accepted = true; C.phase = 'connecting'; C.acceptedAt = Date.now();
  if (C.rec) { C.rec.status = 'live'; saveCalls(true); }
  ensureToday(); S.tasks.call = (S.tasks.call || 0) + 1; save();
  renderCall();
  callAdvance(); // lines may already be ready
}
function declineCall() {
  if (!C) return;
  stopRing();
  const call = C;
  if (call.cid) API.callEnd({ cid: call.cid, seconds: 0 }).catch(() => {});
  recFinish(call, 'declined');
  C = null; stopCallPoll();
  hideCall();
  if (P.needChoice && !(topSheet() && topSheet().kind === 'choice')) openChoiceSheet();
}

let callPollT = 0;
function stopCallPoll() { clearTimeout(callPollT); callPollT = 0; }
function pollCall(jobId, turn) {
  const call = C;
  const tick = async () => {
    if (C !== call || call.turn !== turn || call.phase === 'ended') return;
    let j = null;
    const have = call.lines.filter((l) => l.url != null).length;
    try { j = await API.job(jobId, have); } catch (e) { j = null; }
    if (C !== call || call.turn !== turn || call.phase === 'ended') return;
    if (!j) { callPollT = setTimeout(tick, 1200); return; }
    if (j.status === 'error') { toast(`Call dropped: ${esc(j.error || 'error')}`); endCall('error'); return; }
    if (j.call) {
      call.lines = (j.call.lines || []).map((l) => ({ who: l.who, text: cleanText(l.text), url: l.url }));
      call.lines.forEach((l) => { if (l.url && blobable(l.url) && !blobNow(l.url)) fetchBlob(l.url).then(() => { if (C === call && !call.pickedUp) callAdvance(); }); });
      if (j.status === 'done') { call.jobDone = true; call.choices = (j.call.choices || []).slice(0, 2); call.hangup = !!j.call.hangup; }
      recSyncHim(call);
    } else if (j.status === 'done') call.jobDone = true;
    if (!call.playing && !call.fillerPlaying) callAdvance(); else preloadCallNext();
    renderCallUI();
    if (j.status !== 'done') callPollT = setTimeout(tick, 120);  // the server holds each request until something changes
  };
  tick();
}
function callAdvance() {
  const call = C;
  if (!call || !call.accepted || call.phase === 'ended' || call.phase === 'incoming' || call.phase === 'hanging') return;
  if (call.playing || call.fillerPlaying || call.held) return;
  if (!maybePickUp(call)) { renderCallUI(); return; }
  earStart(call);
  const L = call.lines;
  while (call.idx < L.length && L[call.idx].url === '') call.idx++;
  if (call.idx >= L.length) {
    if (call.jobDone && L.length) { turnDone(); return; }
    call.waiting = true; renderCallUI(); return;
  }
  const ln = L[call.idx];
  if (!ln.url) { call.waiting = true; renderCallUI(); return; }
  call.waiting = false;
  if (!call.t0) { call.t0 = Date.now(); call.timer = setInterval(updateCallTimer, 1000); }
  call.phase = 'talking';
  if (!call.logged.has(call.idx)) { call.logged.add(call.idx); call.transcript.push({ who: call.who, text: ln.text }); }
  call.caption = ln;
  call.playing = true;
  playCallSrc(ln.url);
  preloadCallNext();
  renderCallUI();
}
function preloadCallNext() {
  if (!C) return;
  let j = C.idx + 1;
  while (j < C.lines.length && C.lines[j].url === '') j++;
  const u = C.lines[j] && C.lines[j].url; if (!u) return;
  C.lines.forEach((l) => l.url && fetchBlob(l.url));
  if (blobable(u)) return;
  try {
    if (!callPre) { callPre = new Audio(); callPre.preload = 'auto'; callPre.muted = true; }
    if (callPre.dataset.u !== u) { callPre.dataset.u = u; callPre.src = absUrl(u); callPre.load(); }
  } catch (e) { /* ignore */ }
}
function turnDone() {
  const call = C;
  if (call.hangup) {
    call.phase = 'hanging';
    renderCallUI();
    hangupTone();
    setTimeout(() => { if (C === call) endCall('his'); }, 1300);
    return;
  }
  call.phase = 'your-turn';
  renderCallUI();
  if (EAR.on || lockEarWanted()) earIdle(call); else callListen(call);
}
/** Hands-free call: as soon as he stops, the mic listens. She talks → sent when she pauses (~1 s). Nothing for 9 s → he carries on. */
function callListen(call, retry) {
  if (C !== call || call.phase !== 'your-turn' || callRecog) return;
  const turn = call.turn;
  if (call.muted || VI.denied) {
    call.listen = call.muted ? 'muted' : 'denied'; renderCallUI();
    clearTimeout(call.silentT);
    call.silentT = setTimeout(() => { if (C === call && call.turn === turn && call.phase === 'your-turn' && !callRecog) sendCallTurn('', 'silence'); }, CALL_WAIT);
    return;
  }
  call.listen = 'listening'; renderCallUI();
  const h = callRecog = recordAnswer({ wait: CALL_WAIT, max: 30000, onState: (st) => { if (C === call) { call.listen = st; renderCallUI(); } } });
  h.done.then((r) => {
    if (callRecog === h) callRecog = null;
    if (C !== call || call.turn !== turn || call.phase !== 'your-turn' || r.canceled) return;
    if (r.denied) { VI.denied = true; toast(tz('Microphone is off — allow it to talk on the call', '麦克风没开，允许后才能通话')); callListen(call); return; }
    if (r.text) { sendCallTurn(r.text, 'voice'); return; }
    if (r.spoke && !retry) { call.listen = 'again'; renderCallUI(); setTimeout(() => callListen(call, true), 600); return; }
    sendCallTurn('', 'silence');
  });
}
function toggleCallMute() {
  const call = C; if (!call) return;
  call.muted = !call.muted;
  if (call.muted) { stopCallMic(); if (EAR.utt) { EAR.utt = null; earResume(call); } }
  clearTimeout(call.silentT);
  if (call.phase === 'your-turn') { if (EAR.on) earIdle(call); else callListen(call); }
  renderCallUI(true);
}
function toggleCallSpeaker() {
  const call = C; if (!call) return;
  call.speaker = call.speaker === false;
  applyCallVolume(); renderCallUI(true);
  if (IOS) toast(call.speaker === false ? tz('Earpiece: hold the phone to your ear and turn the volume down', '听筒：把手机贴近耳朵，用侧边音量键调小') : tz('Speaker on', '免提已打开'));
}

/* ---------- full-duplex call ear (11-08): the mic listens for the whole call. She can talk any time — over him too:
 * he stops the moment she starts (resumes if it was just a cough / noise), what she said goes up in ONE request
 * (/api/call/say: recognition + his next turn) and his reply streams back line by line. */
const EAR = { node: null, src: null, sink: null, on: false, pre: [], utt: null, floor: 0.008, above: 0, sr: 48000, level: 0 };
function earStart(call) {
  if (EAR.on || !call || !VI.stream || call.muted === 'never') return EAR.on;
  unlockCtx();
  if (!actx || !actx.createScriptProcessor) return false;
  try {
    EAR.sr = actx.sampleRate;
    EAR.src = actx.createMediaStreamSource(VI.stream);
    EAR.node = actx.createScriptProcessor(2048, 1, 1);
    EAR.sink = actx.createGain(); EAR.sink.gain.value = 0;
    EAR.src.connect(EAR.node); EAR.node.connect(EAR.sink); EAR.sink.connect(actx.destination);
    EAR.node.onaudioprocess = (e) => earFrame(e.inputBuffer.getChannelData(0));
    Object.assign(EAR, { on: true, pre: [], utt: null, floor: 0.008, above: 0 });
    return true;
  } catch (err) { earStop(); return false; }
}
function earStop() {
  try { if (EAR.node) { EAR.node.onaudioprocess = null; EAR.node.disconnect(); } if (EAR.src) EAR.src.disconnect(); if (EAR.sink) EAR.sink.disconnect(); } catch (e) { /* ignore */ }
  Object.assign(EAR, { node: null, src: null, sink: null, on: false, utt: null, pre: [] });
}
const himTalking = (call) => (call.playing || call.fillerPlaying) && !callAudio.paused;
function earFrame(x) {
  const call = C; if (!call || !EAR.on) return;
  let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i];
  const lv = Math.sqrt(s / x.length), dt = x.length / EAR.sr;
  EAR.level = lv;
  if (call.muted || !call.pickedUp || call.phase === 'ended' || call.phase === 'hanging') { EAR.utt = null; EAR.above = 0; return; }
  const over = himTalking(call);
  // his voice can leak back into the mic on speaker: while he talks she has to be clearly louder than the room + echo
  const th = over ? Math.max(0.045, EAR.floor * 4.5) : Math.max(0.016, EAR.floor * 2.8);
  const frame = new Float32Array(x);
  if (!EAR.utt) {
    EAR.pre.push(frame); while (EAR.pre.length * dt > 0.45) EAR.pre.shift();   // keep the start of her first syllable
    if (!over && lv < th) EAR.floor = EAR.floor * 0.95 + lv * 0.05;
    if (lv > th) { EAR.above += dt; if (EAR.above >= (over ? 0.3 : 0.12)) earBegin(call, over); } else EAR.above = 0;
    return;
  }
  const u = EAR.utt; u.buf.push(frame); u.dur += dt;
  if (lv > th * 0.6) { u.voiced += dt; u.quiet = 0; } else u.quiet += dt;
  if (u.quiet >= 0.6 || u.dur >= 20) earEnd(call);
}
function earBegin(call, over) {
  EAR.utt = { buf: EAR.pre.slice(), dur: EAR.pre.length * 2048 / EAR.sr, voiced: EAR.above, quiet: 0, over, idx: call.idx, turn: call.turn };
  EAR.pre = []; EAR.above = 0;
  clearTimeout(call.silentT); clearTimeout(call.thinkT);
  if (over) { call.held = true; try { callAudio.pause(); } catch (e) { /* ignore */ } }   // he stops as soon as she starts
  call.listen = 'speaking'; renderCallUI();
}
function earResume(call) {
  if (C !== call) return;
  call.listen = '';
  if (call.held) {
    call.held = false;
    if ((call.playing || call.fillerPlaying) && callAudio.src && !callAudio.ended) callAudio.play().catch(() => {}); else callAdvance();
  }
  if (call.phase === 'your-turn') earIdle(call);
  renderCallUI();
}
/* ---------- lock-screen call ear (11-09): once the phone locks the AudioContext stops, so the on-screen ear goes deaf.
 * MediaRecorder keeps recording in Safari, so record ~2 s pieces and let the relay stitch them and find where she finished
 * a sentence (/api/call/chunk: energy detection → recognition → his next turn; his own voice leaking back is filtered there). */
const LOCKEAR = { on: false, rec: null, t: 0 };
const lockEarWanted = () => !!(C && C.cid && C.pickedUp && callActive() && C.phase !== 'hanging' && !C.muted && VI.stream && window.MediaRecorder
  && (document.hidden || !actx || actx.state !== 'running'));
function lockEarTick() { if (!lockEarWanted()) { lockEarStop(); return; } if (!LOCKEAR.on) { LOCKEAR.on = true; lockEarSeg(); } }
function lockEarSeg() {
  if (!LOCKEAR.on || !lockEarWanted()) { lockEarStop(); return; }
  const type = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'].find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
  let rec;
  try { rec = new MediaRecorder(VI.stream, type ? { mimeType: type } : undefined); } catch (e) { LOCKEAR.on = false; return; }
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = () => { const b = new Blob(chunks, { type: rec.mimeType || type || 'audio/mp4' }); if (b.size > 200) lockEarSend(b); };
  LOCKEAR.rec = rec;
  try { rec.start(); } catch (e) { LOCKEAR.on = false; return; }
  LOCKEAR.t = setTimeout(() => { try { rec.stop(); } catch (e) { /* ignore */ } lockEarSeg(); }, 2000);
}
function lockEarStop() {
  LOCKEAR.on = false; clearTimeout(LOCKEAR.t);
  if (LOCKEAR.rec && LOCKEAR.rec.state !== 'inactive') { try { LOCKEAR.rec.stop(); } catch (e) { /* ignore */ } }
  LOCKEAR.rec = null;
}
async function lockEarSend(blob) {
  const call = C; if (!call || !call.cid) return;
  const unfinished = !call.jobDone || call.phase === 'thinking' || himTalking(call);
  let r = null;
  try { r = await API.callChunk(call.cid, blob, unfinished ? { prev: call.job || '', played: call.idx + (call.playing ? 1 : 0), cut: 1 } : {}); } catch (e) { r = null; }
  if (C !== call || !r || call.phase === 'ended') return;
  if (r.speaking && call.phase === 'your-turn') earIdle(call);   // she's mid-sentence: don't let him carry on over her yet
  if (r.text) { if (call.playing || call.fillerPlaying) { try { callAudio.pause(); } catch (e) { /* ignore */ } } takeHerTurn(call, r); }
}
document.addEventListener('visibilitychange', () => setTimeout(lockEarTick, 50));
setInterval(() => { if (C) lockEarTick(); }, 1000);

/** after he finishes: nothing from her for 9 s → he carries on */
function earIdle(call) {
  clearTimeout(call.silentT);
  const turn = call.turn;
  call.silentT = setTimeout(() => { if (C === call && call.turn === turn && call.phase === 'your-turn' && !EAR.utt) sendCallTurn('', 'silence'); }, CALL_WAIT);
}
function earEnd(call) {
  const u = EAR.utt; EAR.utt = null;
  if (u.voiced < (u.over ? 0.45 : 0.3)) { earResume(call); return; }   // a click, a cough, a short "mm" over him
  sendCallSay(call, toWav16k(u.buf, EAR.sr), u);
}
function toWav16k(chunks, sr) {
  const n = chunks.reduce((a, c) => a + c.length, 0), ratio = sr / 16000, m = Math.floor(n / ratio);
  const flat = new Float32Array(n); let o = 0; chunks.forEach((c) => { flat.set(c, o); o += c.length; });
  const buf = new ArrayBuffer(44 + m * 2), v = new DataView(buf);
  const w = (p, str) => { for (let i = 0; i < str.length; i++) v.setUint8(p + i, str.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + m * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, m * 2, true);
  for (let i = 0; i < m; i++) { let acc = 0, k0 = Math.floor(i * ratio), k1 = Math.min(n, Math.floor((i + 1) * ratio)); for (let k = k0; k < k1; k++) acc += flat[k]; const x = Math.max(-1, Math.min(1, acc / Math.max(1, k1 - k0))); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true); }
  return new Blob([buf], { type: 'audio/wav' });
}
async function sendCallSay(call, wav, u) {
  if (!call.cid) { earResume(call); return; }
  const unfinished = !call.jobDone || call.held || call.phase === 'thinking';   // she spoke before he finished his turn
  const played = u.over ? call.idx + 1 : call.lines.filter((l, i) => i < call.idx).length;
  call.listen = 'thinking'; renderCallUI();
  let r = null;
  try { r = await API.callSay(call.cid, wav, unfinished ? { prev: call.job || '', played, cut: 1 } : {}); } catch (e) { r = null; }
  if (C !== call || call.phase === 'ended') return;
  if (!r || !r.text) { earResume(call); return; }   // nothing recognisable: he just carries on
  takeHerTurn(call, r);
}
/** what she said is in (on-screen ear or lock-screen pieces): he stops and answers it */
function takeHerTurn(call, r) {
  stopCallPoll(); clearTimeout(call.thinkT); clearTimeout(call.silentT);
  if (call.held || call.playing) { try { callAudio.pause(); } catch (e) { /* ignore */ } }
  call.transcript.push({ who: 'you', text: r.text }); recHer(call, r.text, 'voice');
  call.turn += 1;
  Object.assign(call, { lines: [], idx: 0, jobDone: false, choices: [], logged: new Set(), caption: null, phase: 'thinking', waiting: true, playing: false, held: false, listen: '', job: r.job, said: r.text });
  // 11-09: the relay hands back the whole sentence he says first (pre-voiced, e.g. "That's a good question. Let me tell you.")
  // → it plays the moment her words are recognised, while the rest of his turn is written and voiced
  if (r.first && r.first.url) { call.lines = [{ who: r.first.who || call.who, text: cleanText(r.first.text), url: r.first.url }]; fetchBlob(r.first.url); }
  scheduleThink(call, call.turn);
  renderCall();
  if (call.lines.length) callAdvance();
  pollCall(r.job, call.turn);
}
/** ~3.5 s after the filler, if his first line still has no audio: one "let me think" clip
 *  (at most once per turn, never the same clip as last turn); skipped when his line is already there. */
function scheduleThink(call, turn) {
  clearTimeout(call.thinkT);
  if (call.phase !== 'thinking' || !call.thinks || !call.thinks.length) return;
  call.thinkT = setTimeout(() => {
    if (C !== call || call.turn !== turn || call.phase !== 'thinking' || call.playing || call.fillerPlaying || call.thinkTurn === turn) return;
    const L = call.lines; let i = call.idx;
    while (i < L.length && L[i].url === '') i++;
    if (L[i] && L[i].url) return;
    const pool = call.thinks.filter((u) => u !== call.lastThink);
    if (!pool.length) return;
    const u = pool[Math.floor(Math.random() * pool.length)];
    call.thinkTurn = turn; call.lastThink = u;
    call.fillerPlaying = true; call.thinkPlaying = true;
    playCallSrc(u);
  }, 3500);
}
/** 11-09: his next line isn't voiced yet when one ends (Waku takes 4–9 s a line): after 1.4 s of quiet,
 *  one soft "let me think" clip so the call never sits dead — at most once per turn. */
function gapFill(call) {
  clearTimeout(call.gapT);
  if (!call.thinks || !call.thinks.length || call.thinkTurn === call.turn) return;
  const turn = call.turn, idx = call.idx;
  call.gapT = setTimeout(() => {
    if (C !== call || call.turn !== turn || call.idx !== idx || call.playing || call.fillerPlaying || call.held || EAR.utt || call.phase === 'ended' || call.phase === 'your-turn') return;
    const L = call.lines; let i = call.idx; while (i < L.length && L[i].url === '') i++;
    if (L[i] && L[i].url) return;
    if (call.jobDone && i >= L.length) return;
    const pool = call.thinks.filter((u) => u !== call.lastThink); if (!pool.length) return;
    const u = pool[Math.floor(Math.random() * pool.length)];
    call.thinkTurn = turn; call.lastThink = u; call.fillerPlaying = true; call.thinkPlaying = true;
    playCallSrc(u);
  }, 1400);
}
function playFiller() {
  const call = C; if (!call || !call.fillers.length) return;
  call.fillerPlaying = true;
  playCallSrc(call.fillers[Math.floor(Math.random() * call.fillers.length)]);
}
async function sendCallTurn(text, via) {
  const call = C;
  if (!call || call.phase !== 'your-turn' || !call.cid) return;
  stopCallMic(); clearTimeout(call.silentT); call.listen = '';
  primeCallAudio();
  const silent = via === 'silence';
  call.transcript.push({ who: 'you', text: silent ? '' : text, silent });
  call.turn += 1;
  recHer(call, text, via);
  const turn = call.turn;
  Object.assign(call, { lines: [], idx: 0, jobDone: false, choices: [], logged: new Set(), caption: null, phase: 'thinking', waiting: true });
  if (!silent) playFiller();   // when she stayed quiet he just carries on — no "Mm." first
  if (!call.fillerPlaying && !silent) scheduleThink(call, turn); // no filler available: count from the send
  renderCall();
  try {
    const r = await API.callTurn({ cid: call.cid, text: silent ? '' : text, via });
    if (C !== call || call.turn !== turn) return;
    call.job = r.job;
    pollCall(r.job, turn);
  } catch (e) {
    if (C !== call) return;
    toast(`Couldn't reach ${esc(shortName(call.caller))}: ${esc(e.message || 'error')}`);
    call.transcript.pop(); if (call.rec) { call.rec.turns.splice(call.turn); saveCalls(true); } call.turn -= 1; call.phase = 'your-turn';
    renderCall();
  }
}
function hangUp() {
  if (!C) return;
  if (C.phase === 'incoming') { declineCall(); return; }
  hangupTone();
  endCall('you');
}
function endCall(reason) {
  const call = C;
  if (!call || call.phase === 'ended') return;
  stopRing(); stopCallPoll(); stopCallMic(); clearTimeout(call.thinkT); clearTimeout(call.silentT); earStop(); lockEarStop(); setTimeout(micPark, 100);
  try { callAudio.pause(); } catch (e) { /* ignore */ }
  clearInterval(call.timer);
  const base = call.t0 || call.acceptedAt;  // 计时从他开口算；没开口就从接通算，不会记成 0:00
  call.secs = base ? Math.round((Date.now() - base) / 1000) : 0;
  call.phase = 'ended'; call.endReason = reason;
  if (call.cid) API.callEnd({ cid: call.cid, seconds: call.secs }).catch(() => {});
  recFinish(call, reason === 'error' && !call.t0 ? 'failed' : 'done');
  renderCall();
}
function closeCallScreen() {
  C = null; stopCallPoll();
  hideCall();
  if (P.needChoice && playerOpen && !(topSheet() && topSheet().kind === 'choice')) openChoiceSheet();
}
function cycleCallSpeed() {
  const i = SPEEDS.indexOf(S.callSpeed || 1);
  S.callSpeed = SPEEDS[(i + 1) % SPEEDS.length];
  try { callAudio.playbackRate = S.callSpeed; } catch (e) { /* ignore */ }
  save(); renderCallUI();
}

/* hold-to-talk */
function startCallMic(btn) {
  if (!VOICE_OK || !C || C.phase !== 'your-turn' || callRecog) return;
  const inp = $('#cl-text');
  btn.classList.add('rec');
  if (inp) inp.placeholder = 'Listening… release to send';
  const h = callRecog = recordAnswer({ manual: true, max: 30000, onState: (st) => { if (st === 'thinking' && inp) inp.placeholder = 'Got it — one moment…'; if (st === 'denied') toast('Microphone permission denied'); } });
  h.done.then((r) => {
    if (callRecog === h) callRecog = null;
    btn.classList.remove('rec');
    if (inp) inp.placeholder = 'Your reply';
    if (r.canceled) return;
    if (r.text && C && C.phase === 'your-turn') sendCallTurn(r.text, 'voice');
    else if (r.spoke) toast("Didn't catch that — try again");
  });
}
function releaseCallMic() { if (callRecog) callRecog.stop(); }
function stopCallMic() { if (callRecog) { const r = callRecog; callRecog = null; r.cancel(); } }

/* ---------- call screens ---------- */
function hideCall() {
  const el = $('#call');
  el.classList.remove('on');
  setTimeout(() => { if (!C) { el.hidden = true; el.innerHTML = ''; el.dataset.key = ''; } }, 320);
}
function renderCall() {
  const el = $('#call'); const call = C; if (!call) return;
  const s = byId(call.id);
  const mo = motionOf(s);
  const name = (call.caller && call.caller.name) || call.who;
  el.hidden = false;
  el.style.setProperty('--accent', s.accent || '#FF8448');
  const shellKey = `${call.seq}:${call.phase === 'ended' ? 'end' : 'live'}`;
  if (el.dataset.key !== shellKey) {
    el.dataset.key = shellKey;
    const own = callerAv(s, call.who), solo = own === avatarOf(s);   // a caller with their own face: no series motion clip over it
    const circle = `<div class="cl-circle"><img src="${esc(own)}" alt="">${mo && solo && !reduceMotion() ? `<video src="${esc(absUrl(mo))}" muted loop playsinline autoplay preload="auto" aria-hidden="true"></video>` : ''}</div>`;
    if (call.phase === 'ended') {
      el.className = 'call on ph-ended';
      el.innerHTML = `
        <div class="cl-bgw"><div class="cl-bg" style="background-image:url('${esc(coverOf(s))}')"></div></div>
        <div class="cl-end-top"><span></span><button class="icon-btn" data-act="go-calls" aria-label="Call history">${ic('clock')}</button></div>
        <div class="cl-end">
          <div class="cl-av sm">${circle}</div>
          <h2 class="cl-name">${esc(name)}</h2>
          <p class="cl-status">${call.endReason === 'error' && !call.t0 ? 'Call failed' : 'Call ended'} · <span class="tnum">${fmtTime(call.secs)}</span></p>
          <button class="saved-chip" data-act="call-live-tr">${ic('check', 'xs')} Saved to Calls</button>
          <div class="cl-end-btns">
            <button class="btn btn-grad" data-act="call-again">${ic('phone', 'sm')} Call again</button>
            <button class="btn btn-ghost" data-act="call-close">Done</button>
          </div>
          <div class="cl-tr-h"><h4>Transcript</h4><button class="link-btn" data-act="call-live-tr">${ic('play', 'xs')} Replay lines</button></div>
          <div class="cl-tr">${transcriptHtml(call.rec)}</div>
        </div>`;
    } else {
      el.innerHTML = `
        <div class="cl-bgw"><div class="cl-bg" style="background-image:url('${esc(coverOf(s))}')"></div></div>
        <div class="cl-top"><i class="cl-top-pad"></i><span>${ic('phone', 'xs')} ${esc(s.title)}</span><button class="icon-btn cl-hist" data-act="call-live-tr" aria-label="This call's transcript">${ic('clock')}</button></div>
        <div class="cl-hero">
          <div class="cl-av" id="cl-av"><i class="cl-pulse"></i><i class="cl-pulse p2"></i><i class="cl-pulse p3"></i>${circle}</div>
          <h2 class="cl-name">${esc(name)}</h2>
          <p class="cl-status" id="cl-status"></p>
        </div>
        <div class="cl-cap" id="cl-cap"></div>
        <div class="cl-bottom" id="cl-bottom"></div>`;
      const v = $('video', el); if (v) { v.addEventListener('canplay', () => { v.classList.add('on'); v.play().catch(() => {}); }); }
    }
    requestAnimationFrame(() => el.classList.add('on'));
  }
  renderCallUI(true);
}
function updateCallTimer() {
  if (C && C.rec && C.t0 && callActive()) { const secs = Math.round((Date.now() - C.t0) / 1000); C.rec.dur = secs; if (secs % 5 === 0) saveCalls(); }
  const st = $('#cl-status'); if (!st || !C || !C.t0) return;
  if (C.phase === 'talking' || C.phase === 'your-turn' || C.phase === 'thinking') st.textContent = fmtTime((Date.now() - C.t0) / 1000);
}
function renderCallUI(force) {
  const call = C; const el = $('#call');
  if (!call || el.hidden || call.phase === 'ended') return;
  const name = shortName(call.caller) || call.who;
  el.className = `call on ph-${call.phase}${call.playing ? ' speaking' : ''}`;
  const st = $('#cl-status');
  if (st) {
    st.textContent = call.phase === 'incoming' ? 'Incoming call…'
      : call.phase === 'hanging' ? 'Hanging up…'
      : !call.t0 ? (call.direction === 'outgoing' ? tz('Calling…', '正在呼叫…') : tz('Connecting…', '正在接通…'))
      : fmtTime((Date.now() - call.t0) / 1000);
  }
  const cap = $('#cl-cap');
  if (cap) {
    let key, html;
    if (call.phase === 'incoming') { key = 'in'; html = `<p class="cl-hint">${esc(call.caller && call.caller.role ? call.caller.role : '')}</p>`; }
    else if (call.phase === 'thinking' || (call.waiting && !call.playing && call.phase !== 'your-turn')) {
      key = 'think' + call.turn + (call.greeting ? 'g' : '') + (call.t0 ? 't' : '');
      html = call.greeting ? `<span class="who">${esc(name)}</span><p class="txt fade">${esc(tz('Hey.', '喂？'))}</p>`
        : `<div class="cl-think">${!call.t0 ? tz('Connecting', '正在接通') : call.direction === 'outgoing' && call.turn === 0 ? tz(`${esc(name)} picked up`, `${esc(name)} 接起来了`) : tz(`${esc(name)} is thinking`, `${esc(name)} 在想`)}<span class="dots-pulse"><i></i><i></i><i></i></span></div>`;
    } else if (call.phase === 'your-turn' && EAR.on) {
      key = 'live' + call.turn + ':' + call.idx;
      html = `${call.said ? `<p class="cl-you">${tz('You', '你')}：${esc(call.said)}</p>` : ''}${call.caption ? `<span class="who">${esc(name)}</span><p class="txt dim">${esc(call.caption.text)}</p>` : ''}<p class="cl-hint2">${call.muted ? tz('Mic muted', '麦克风已静音') : tz('On the call — talk any time', '通话中 · 随时可以说话')}</p>`;
    } else if (call.phase === 'your-turn') {
      const ls = call.listen || 'listening';
      key = 'you' + call.turn + ls;
      const msg = { listening: tz('Your turn — just talk', '轮到你了，直接说'), speaking: tz('Listening…', '在听你说…'), thinking: tz('Got it…', '听到了…'),
        again: tz("Didn't catch that — say it again", '没听清，再说一遍'), muted: tz('Mic muted — he’ll keep talking', '麦克风已静音，他会接着说'), denied: tz('Mic is off', '麦克风没开') }[ls] || '';
      html = `${call.caption ? `<p class="txt dim">${esc(call.caption.text)}</p>` : ''}<div class="cl-listen ${ls}"><i class="cl-wave"><b></b><b></b><b></b><b></b><b></b></i><span>${msg}</span></div>`;
    } else if (EAR.on && (call.listen === 'speaking' || call.listen === 'thinking')) {
      key = 'ear' + call.listen + call.turn;
      html = `<div class="cl-listen ${call.listen}"><i class="cl-wave"><b></b><b></b><b></b><b></b><b></b></i><span>${call.listen === 'speaking' ? tz('Listening…', '在听你说…') : tz('Got it…', '听到了…')}</span></div>`;
    } else if (call.caption) {
      key = 'cap' + call.turn + ':' + call.idx;
      html = `${call.said ? `<p class="cl-you">${tz('You', '你')}：${esc(call.said)}</p>` : ''}<span class="who">${esc(name)}</span><p class="txt fade ${call.phase === 'your-turn' ? 'dim' : ''}">${esc(call.caption.text)}</p>${EAR.on && !call.muted ? `<p class="cl-hint2">${tz('Talk any time — he’ll stop and listen', '随时可以插话，他会停下来听你说')}</p>` : ''}`;
    } else { key = 'empty'; html = ''; }
    if (cap.dataset.k !== key || force) { cap.dataset.k = key; cap.innerHTML = html; }
  }
  const bot = $('#cl-bottom');
  if (bot) {
    const key = call.phase === 'incoming' ? 'in' : 'live' + (S.callSpeed || 1) + (call.blocked ? 'b' : '') + (call.muted ? 'm' : '') + (call.speaker === false ? 'e' : 's');
    if (bot.dataset.k !== key || force) {
      bot.dataset.k = key;
      if (call.phase === 'incoming') {
        bot.innerHTML = `
          <div class="cl-answer">
            <div><button class="cl-btn red" data-act="call-decline" aria-label="Decline">${ic('phoneDown', 'lg')}</button><span>Decline</span></div>
            <div><button class="cl-btn green" data-act="call-accept" aria-label="Accept">${ic('phone', 'lg')}</button><span>Accept</span></div>
          </div>`;
      } else {
        // voice only, like a real phone call: no typing, no reply chips — he talks, then the mic listens to her
        bot.innerHTML = `
          ${call.blocked ? `<button class="btn btn-grad btn-block" data-act="call-resume" style="margin-bottom:12px">${ic('play', 'sm')} ${tz(`Tap to hear ${esc(name)}`, `点一下听 ${esc(name)} 说话`)}</button>` : ''}
          <div class="cl-keys">
            <button class="cl-key ${call.muted ? 'on' : ''}" data-act="call-mute" aria-pressed="${call.muted ? 'true' : 'false'}"><i>${ic('mic')}</i><span>${tz('Mute', '静音')}</span></button>
            <button class="cl-key ${call.speaker === false ? '' : 'on'}" data-act="call-speaker" aria-pressed="${call.speaker === false ? 'false' : 'true'}"><i>${ic('volume')}</i><span>${call.speaker === false ? tz('Earpiece', '听筒') : tz('Speaker', '免提')}</span></button>
            <button class="cl-key" data-act="call-speed"><i><b>${S.callSpeed || 1}x</b></i><span>${tz('Speed', '语速')}</span></button>
          </div>
          <div class="cl-ctrl one"><button class="cl-btn red" data-act="call-hangup" aria-label="Hang up">${ic('phoneDown', 'lg')}</button></div>`;
      }
    }
  }
}

/* he calls you at the choice point (Ep ≥ 2), once per series per day */
function maybeIncomingCall() {
  const id = P.id, ep = P.ep;
  if (!ep || ep.n < 2 || callActive()) return;
  S.inDay = S.inDay || {};
  if (S.inDay[id] === dayStr()) return;
  setTimeout(() => {
    if (!P.needChoice || P.id !== id || !P.ep || P.ep.n !== ep.n || callActive() || P.gen) return;
    if (topSheet() && topSheet().kind !== 'choice') return; // don't ring over the unlock / store sheets
    if (!$('#ad').hidden) return;
    S.inDay[id] = dayStr(); save();
    const cs = callersOf(byId(id));
    const c = cs[Math.floor(Math.random() * cs.length)];
    showIncoming(id, c.key, (getSess(id) || {}).sid);
  }, 2000);
}

/* =========================================================================
 * 10c. Call history — autosaved after every turn (localStorage `ua.calls`, newest first, max 200)
 * record: {rid, series, who, name, title, lang, mode, direction, startedAt, endedAt, dur, status,
 *          turns:[{her:{text,via,at}|null, him:[{text,url,at}]}]}
 * status: live | ringing | done | declined | failed | interrupted | missed
 * ========================================================================= */
const CALLS_KEY = 'ua.calls';
const CALLS_MAX = 200;
let CALLS = store.get(CALLS_KEY, []) || [];
if (!Array.isArray(CALLS)) CALLS = [];
(function migrateCalls() {
  // older builds kept calls in S.calls with a flat transcript
  if (Array.isArray(S.calls) && S.calls.length) {
    S.calls.forEach((h) => {
      const turns = [{ her: null, him: [] }];
      (h.transcript || []).forEach((t) => {
        if (t.who === 'you') turns.push({ her: { text: t.text || '', via: t.silent ? 'silence' : 'free', at: h.at }, him: [] });
        else turns[turns.length - 1].him.push({ text: t.text, url: null, at: h.at });
      });
      CALLS.push({ rid: 'm' + h.at + Math.random().toString(36).slice(2, 6), series: h.id, who: h.who, name: h.name, title: h.title, lang: h.lang || LANG,
        mode: h.mode || 'm', direction: h.dir || 'outgoing', startedAt: h.at, endedAt: h.at, dur: h.secs || 0, status: h.status === 'declined' ? 'declined' : 'done', turns });
    });
    S.calls = []; save();
    CALLS.sort((a, b) => b.startedAt - a.startedAt);
  }
  // a call that was live when the page closed is kept, marked interrupted
  CALLS.forEach((r) => { if (r.status === 'live') r.status = 'interrupted'; else if (r.status === 'ringing') r.status = 'missed'; });
})();
let callsSaveT = 0;
function saveCalls(now) {
  clearTimeout(callsSaveT);
  const f = () => { CALLS = CALLS.slice(0, CALLS_MAX); store.set(CALLS_KEY, CALLS); };
  if (now) f(); else callsSaveT = setTimeout(f, 150);
}
saveCalls(true);
window.addEventListener('pagehide', () => { if (C && C.rec && C.t0) C.rec.dur = Math.round((Date.now() - C.t0) / 1000); saveCalls(true); });
document.addEventListener('visibilitychange', () => { if (document.hidden) { if (C && C.rec && C.t0) C.rec.dur = Math.round((Date.now() - C.t0) / 1000); saveCalls(true); } });

function createCallRec(call) {
  const s = byId(call.id);
  const rec = {
    rid: 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    series: call.id, who: call.who, name: (call.caller && call.caller.name) || call.who, title: s ? s.title : '',
    lang: LANG, mode: MOCK ? 'm' : 'r', direction: call.direction, startedAt: Date.now(), endedAt: null, dur: 0,
    status: call.direction === 'incoming' ? 'ringing' : 'live', turns: [{ her: null, him: [] }],
  };
  CALLS.unshift(rec);
  saveCalls(true);
  return rec;
}
/** copy his lines for the current turn (text + permanent url) into the record; saves only on change */
function recSyncHim(call) {
  const rec = call.rec; if (!rec) return;
  const t = rec.turns[call.turn] || (rec.turns[call.turn] = { her: null, him: [] });
  const prev = JSON.stringify(t.him.map((h) => [h.text, h.url]));
  const now = Date.now();
  t.him = call.lines.map((l, i) => ({ text: l.text, url: l.url, at: (t.him[i] && t.him[i].at) || now }));
  if (JSON.stringify(t.him.map((h) => [h.text, h.url])) !== prev) { saveCalls(); if (TR && TR.rid === rec.rid) renderTranscriptView(); }
}
function recHer(call, text, via) {
  const rec = call.rec; if (!rec) return;
  rec.turns[call.turn] = { her: { text: via === 'silence' ? '' : text, via, at: Date.now() }, him: [] };
  rec.dur = call.t0 ? Math.round((Date.now() - call.t0) / 1000) : rec.dur;
  saveCalls(true);
  if (TR && TR.rid === rec.rid) renderTranscriptView();
}
function recFinish(call, status) {
  const rec = call.rec; if (!rec) return;
  rec.status = status; rec.endedAt = Date.now();
  rec.dur = call.secs || rec.dur || 0;
  rec.turns = rec.turns.filter((t, i) => i === 0 || t.her || t.him.length);
  saveCalls(true);
  refreshCallLists();
  if (TR && TR.rid === rec.rid) renderTranscriptView();
}
function refreshCallLists() {
  if (curTab === 'library' && libTab === 'calls' && $('#v-library').classList.contains('on')) renderLibrary();
  if (isDetailOpen()) renderDetail();
}
const callsFor = (sid) => CALLS.filter((r) => r.mode === (MOCK ? 'm' : 'r') && (!sid || r.series === sid) && byId(r.series));
const recById = (rid) => CALLS.find((r) => r.rid === rid);
const recLines = (r) => r.turns.reduce((n, t) => n + t.him.length + (t.her ? 1 : 0), 0);
const fmtWhen = (t) => new Date(t).toLocaleString(LANG === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
function transcriptHtml(r) {
  if (!r || !r.turns.some((t) => t.her || t.him.length)) return '<p class="cl-tr-empty">No conversation yet.</p>';
  return r.turns.map((t) => (t.her ? `<div class="tr-row you"><span>You</span><p>${t.her.via === 'silence' || !t.her.text ? '<em>(stayed silent)</em>' : esc(t.her.text)}</p></div>` : '')
    + t.him.map((h) => `<div class="tr-row"><span>${esc(shortName({ name: r.name }))}</span><p>${esc(cleanText(h.text))}</p></div>`).join('')).join('');
}
function recStatusLabel(r) {
  return ({ declined: 'Declined', missed: 'Missed', failed: 'Failed', interrupted: `Interrupted · ${fmtTime(r.dur)}`, live: 'On call now', ringing: 'Ringing' })[r.status] || fmtTime(r.dur);
}

/** one swipeable history row (Library › Calls, detail sheet) */
function callRowHtml(r) {
  const s = byId(r.series);
  const bad = ['declined', 'missed', 'failed'].indexOf(r.status) >= 0;
  return `<div class="swipe-row" data-rid="${esc(r.rid)}">
    <button class="swipe-del" data-act="call-del" data-rid="${esc(r.rid)}" aria-label="Delete call">${ic('trash', 'sm')}<span>Delete</span></button>
    <div class="swipe-body lib-row">
      <button class="open" data-act="call-tr" data-rid="${esc(r.rid)}">
        <span class="cv round"><img src="${esc(callerAv(s, r.who))}" alt="" loading="lazy"></span>
        <span class="lt"><b>${esc(r.name)}</b><span>${esc(s.title)} · ${recLines(r)} line${recLines(r) === 1 ? '' : 's'}</span><span class="call-meta ${bad ? 'miss' : ''}">${ic(r.direction === 'incoming' ? 'phone' : 'send', 'xs')} ${r.direction === 'incoming' ? 'Incoming' : 'Outgoing'} · ${fmtWhen(r.startedAt)} · ${esc(recStatusLabel(r))}</span></span>
      </button>
      <button class="rm call-back-btn" data-act="call-back" data-id="${esc(r.series)}" data-who="${esc(r.who)}" aria-label="Call back">${ic('phone', 'sm')}</button>
    </div>
  </div>`;
}
/* swipe-left to reveal Delete */
let swipeSt = null, swipeSuppress = 0;
document.addEventListener('pointerdown', (e) => {
  const row = e.target.closest('.swipe-row'); if (!row || e.target.closest('.swipe-del')) return;
  $$('.swipe-row.open').forEach((r) => { if (r !== row) r.classList.remove('open'); });
  swipeSt = { row, x: e.clientX, y: e.clientY, dx: 0, base: row.classList.contains('open') ? -88 : 0, moved: false };
}, { passive: true });
document.addEventListener('pointermove', (e) => {
  if (!swipeSt) return;
  const dx = e.clientX - swipeSt.x, dy = e.clientY - swipeSt.y;
  if (!swipeSt.moved && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) swipeSt.moved = true;
  if (!swipeSt.moved) return;
  swipeSt.dx = dx;
  const body = swipeSt.row.querySelector('.swipe-body');
  body.style.transition = 'none';
  body.style.transform = `translateX(${clamp(swipeSt.base + dx, -110, 0)}px)`;
}, { passive: true });
const endSwipe = () => {
  if (!swipeSt) return;
  const st = swipeSt; swipeSt = null;
  const body = st.row.querySelector('.swipe-body');
  body.style.transition = ''; body.style.transform = '';
  if (st.moved) { swipeSuppress = Date.now(); st.row.classList.toggle('open', st.base + st.dx < -44); }
};
document.addEventListener('pointerup', endSwipe, { passive: true });
document.addEventListener('pointercancel', endSwipe, { passive: true });
document.addEventListener('click', (e) => { if (Date.now() - swipeSuppress < 300 && e.target.closest('.swipe-row')) { e.stopPropagation(); e.preventDefault(); } }, true);

function deleteCallRec(rid) {
  const i = CALLS.findIndex((r) => r.rid === rid); if (i < 0) return;
  if (C && C.rec && C.rec.rid === rid && callActive()) { toast("Can't delete a call in progress"); return; }
  if (TR && TR.rid === rid) closeTranscriptView();
  CALLS.splice(i, 1); saveCalls(true);
  toast('Call deleted');
  refreshCallLists(); refreshSheets();
}
function confirmSheet(title, body, okLabel, onOk) {
  const entry = openSheet(`
    <div class="sh-h"><div><h3>${esc(title)}</h3><p>${esc(body)}</p></div></div>
    <div class="ul-btns"><button class="btn btn-grad danger-btn" data-act="confirm-ok">${esc(okLabel)}</button><button class="btn btn-ghost" data-act="sheet-close">Cancel</button></div>`, { kind: 'confirm', onOk });
  return entry;
}
function clearAllCalls() {
  const n = callsFor().length; if (!n) return;
  confirmSheet(`Clear all ${n} calls?`, 'Transcripts and replay links are removed from this device. This can’t be undone.', 'Clear all', () => {
    const keep = C && C.rec && callActive() ? C.rec.rid : null;
    const mode = MOCK ? 'm' : 'r';
    CALLS = CALLS.filter((r) => r.mode !== mode || r.rid === keep);
    saveCalls(true); toast('Call history cleared'); refreshCallLists();
  });
}
function openSeriesCalls(id) {
  const s = byId(id);
  const entry = openSheet('', { kind: 'series-calls' });
  entry.refresh = () => {
    const list = callsFor(id);
    entry.el.innerHTML = `<div class="grab"></div>
      <div class="sh-h"><div><h3>Call history</h3><p>${esc(s.title)} · ${list.length} call${list.length === 1 ? '' : 's'}</p></div><button class="icon-btn" data-act="sheet-close" aria-label="Close">${ic('close')}</button></div>
      <div class="calls-list">${list.length ? list.map(callRowHtml).join('') : `<div class="empty">${ic('phone')}No calls with ${esc(s.title)} yet.</div>`}</div>
      <p class="swipe-hint">Swipe left on a call to delete</p>`;
  };
  entry.refresh();
}

/* ---------- transcript view: chat log + replay ---------- */
const trAudio = new Audio();
trAudio.preload = 'auto';
trAudio.setAttribute('playsinline', '');
let TR = null; // {rid, queue:[{t,i}], qi, whole, cur:'t:i'}
function openTranscriptView(rid) {
  const r = recById(rid); if (!r) return;
  closeAllSheets();
  stopTrPlayback();
  TR = { rid, queue: [], qi: 0, whole: false, cur: '' };
  const el = $('#trv');
  el.hidden = false;
  renderTranscriptView();
  requestAnimationFrame(() => el.classList.add('on'));
}
function closeTranscriptView() {
  stopTrPlayback();
  TR = null;
  const el = $('#trv');
  el.classList.remove('on');
  setTimeout(() => { if (!TR) { el.hidden = true; el.innerHTML = ''; } }, 300);
}
function renderTranscriptView() {
  if (!TR) return;
  const r = recById(TR.rid); if (!r) { closeTranscriptView(); return; }
  const s = byId(r.series);
  const el = $('#trv');
  const live = C && C.rec === r && callActive();
  const t0 = r.startedAt;
  const rel = (t) => (t ? fmtTime(Math.max(0, (t - t0) / 1000)) : '');
  const viaLbl = { option: 'Quick reply', free: 'Typed', voice: 'Spoke', silence: 'Stayed silent' };
  const playable = r.turns.some((t) => t.him.some((h) => h.url));
  const msgs = r.turns.map((t, ti) => {
    let out = '';
    if (t.her) out += `<div class="msg you"><div class="bub">${t.her.via === 'silence' || !t.her.text ? '<em>(stayed silent)</em>' : esc(t.her.text)}</div><span class="meta">${esc(viaLbl[t.her.via] || 'You')} · ${rel(t.her.at)}</span></div>`;
    t.him.forEach((h, hi) => {
      const key = `${ti}:${hi}`;
      const can = !!h.url && !live;
      const on = TR.cur === key;
      out += `<div class="msg him ${on ? 'playing' : ''}" data-k="${key}">
        <img class="av" src="${esc(callerAv(s, r.who))}" alt="">
        <div class="col"><span class="nm">${esc(shortName({ name: r.name }))}<i>${rel(h.at)}</i></span>
          <div class="bub-row"><div class="bub">${esc(cleanText(h.text))}</div>
          <button class="line-play" data-act="tr-line" data-k="${key}" ${can ? '' : 'disabled'} aria-label="${on ? 'Pause line' : 'Play line'}">${ic(on && !trAudio.paused ? 'pause' : 'play')}</button></div></div>
      </div>`;
    });
    return out;
  }).join('');
  el.style.setProperty('--accent', s.accent || '#FF8448');
  const oldBody = $('#trv-body'); const keep = oldBody ? oldBody.scrollTop : 0;
  el.innerHTML = `
    <header class="trv-top">
      <button class="icon-btn" data-act="tr-close" aria-label="Back">${ic('back')}</button>
      <div class="trv-who"><img src="${esc(callerAv(s, r.who))}" alt=""><div><b>${esc(r.name)}</b><span>${esc(s.title)} · ${r.direction === 'incoming' ? 'Incoming' : 'Outgoing'} · ${fmtWhen(r.startedAt)} · ${esc(recStatusLabel(r))}</span></div></div>
      <button class="icon-btn" data-act="tr-del" aria-label="Delete call" ${live ? 'disabled' : ''}>${ic('trash', 'sm')}</button>
    </header>
    ${live ? `<div class="trv-live"><span class="dot"></span> Live call — saved after every turn. Replay unlocks when it ends.</div>` : ''}
    <div class="trv-body" id="trv-body">${msgs || '<p class="cl-tr-empty">Nothing was said in this call.</p>'}</div>
    <footer class="trv-foot">
      <button class="tool" data-act="tr-speed" aria-label="Replay speed"><b>${S.trSpeed || 1}x</b>Speed</button>
      <button class="btn btn-grad" data-act="tr-whole" ${playable && !live ? '' : 'disabled'}>${ic(TR.whole && !trAudio.paused ? 'pause' : 'play', 'sm')} ${TR.whole && !trAudio.paused ? 'Pause' : 'Play whole call'}</button>
      <button class="tool" data-act="call-back" data-id="${esc(r.series)}" data-who="${esc(r.who)}" ${live ? 'disabled' : ''} aria-label="Call back">${ic('phone')}<span>Call back</span></button>
    </footer>
    ${TR.confirmDel ? `<div class="trv-confirm" role="alertdialog"><p>Delete this call and its transcript?</p><div><button class="btn btn-ghost btn-sm" data-act="tr-del-cancel">Cancel</button><button class="btn btn-sm danger-btn" data-act="tr-del-ok">Delete</button></div></div>` : ''}`;
  const nb = $('#trv-body'); if (nb) nb.scrollTop = keep;
}
function trLines(r) {
  const q = [];
  r.turns.forEach((t, ti) => t.him.forEach((h, hi) => { if (h.url) q.push({ key: `${ti}:${hi}`, url: h.url }); }));
  return q; // null / "" urls are skipped, same rule as live playback
}
function trPlayKey(key, whole) {
  const r = TR && recById(TR.rid); if (!r) return;
  const q = trLines(r);
  const i = q.findIndex((x) => x.key === key); if (i < 0) return;
  TR.queue = whole ? q : [q[i]]; TR.qi = whole ? i : 0; TR.whole = whole;
  trPlayCurrent();
}
function trPlayCurrent() {
  const it = TR && TR.queue[TR.qi];
  if (!it) { stopTrPlayback(); renderTranscriptView(); return; }
  TR.cur = it.key;
  trAudio.src = absUrl(it.url);
  try { trAudio.defaultPlaybackRate = S.trSpeed || 1; trAudio.playbackRate = S.trSpeed || 1; trAudio.preservesPitch = true; trAudio.webkitPreservesPitch = true; } catch (e) { /* ignore */ }
  trAudio.play().catch(() => {});
  renderTranscriptView();
  const m = $(`#trv .msg[data-k="${it.key}"]`); if (m) m.scrollIntoView({ block: 'nearest', behavior: reduceMotion() ? 'auto' : 'smooth' });
}
function stopTrPlayback() {
  try { trAudio.pause(); } catch (e) { /* ignore */ }
  if (TR) { TR.cur = ''; TR.whole = false; TR.queue = []; }
}
trAudio.addEventListener('ended', () => { if (!TR) return; TR.qi += 1; setTimeout(trPlayCurrent, 120); });
trAudio.addEventListener('error', () => { if (!TR || !TR.cur) return; TR.qi += 1; setTimeout(trPlayCurrent, 120); });
trAudio.addEventListener('play', () => renderTranscriptView());
trAudio.addEventListener('pause', () => { if (TR && !trAudio.ended) renderTranscriptView(); });
function trToggleLine(key) {
  if (!TR) return;
  if (callActive()) { toast('Replay is available after the call'); return; }
  if (TR.cur === key && !TR.whole) { if (trAudio.paused) trAudio.play().catch(() => {}); else trAudio.pause(); return; }
  if (P.cur && !audio.paused) doPause();
  trPlayKey(key, false);
}
function trToggleWhole() {
  if (!TR) return;
  if (TR.whole && TR.cur) { if (trAudio.paused) trAudio.play().catch(() => {}); else trAudio.pause(); return; }
  const r = recById(TR.rid); const q = trLines(r); if (!q.length) return;
  if (P.cur && !audio.paused) doPause();
  trPlayKey(q[0].key, true);
}
function cycleTrSpeed() {
  const i = SPEEDS.indexOf(S.trSpeed || 1);
  S.trSpeed = SPEEDS[(i + 1) % SPEEDS.length];
  try { trAudio.playbackRate = S.trSpeed; } catch (e) { /* ignore */ }
  save(); renderTranscriptView();
}

/* =========================================================================
 * 11. Rendering: shell, tabs, views
 * ========================================================================= */
const TABS = [['home', 'Home'], ['explore', 'Explore'], ['library', 'Library'], ['rewards', 'Rewards']];
let curTab = 'home';
function renderTabbar() {
  $('#tabbar').innerHTML = TABS.map(([k, l]) => `<button class="tab ${curTab === k ? 'on' : ''}" data-act="go" data-to="${k}" aria-label="${l}" ${curTab === k ? 'aria-current="page"' : ''}>${ic(k)}<span>${l}</span></button>`).join('');
}
function refreshCoins() {
  $$('.coins-n').forEach((el) => { el.textContent = S.coins; });
  refreshSheets();
}

const topbar = () => `
  <header class="topbar">
    <div class="logo">${LOGO}<span class="logo-word">${NARRA ? 'narra' : 'unscripted'}<em>.</em></span></div>
    <div class="tb-actions">
      <button class="icon-btn" data-act="go" data-to="explore" aria-label="Search">${ic('search')}</button>
      <button class="coin-pill" data-act="store" aria-label="Coins">${coinIc()}<span class="coins-n">${S.coins}</span></button>
      <button class="avatar-btn" data-act="profile" aria-label="Profile">${esc((S.name || '?').slice(0, 1).toUpperCase())}</button>
    </div>
  </header>`;

const card = (s, extra = '') => `
  <button class="card" data-act="open" data-id="${esc(s.id)}">
    <div class="cv">${thumbImg(s)}<span class="tag-live">LIVE</span></div>
    <div class="t">${esc(s.title)}</div>
    <div class="m">${extra || `${ic('headphones')} ${esc((s.stats || {}).plays || '')}`}</div>
  </button>`;
const shelf = (title, items, more) => items.length ? `
  <section class="shelf">
    <div class="shelf-h"><h3>${esc(title)}</h3>${more ? `<button class="more" data-act="go" data-to="${more}">See all</button>` : ''}</div>
    <div class="row">${items.join('')}</div>
  </section>` : '';

function continueItems() {
  return Object.keys(S.progress)
    .filter((k) => SESS[k] && S.progress[k] && byId(S.progress[k].id) && k === skey(S.progress[k].id))  // same language and voice engine as this link
    .map((k) => S.progress[k]).sort((a, b) => b.at - a.at);
}
function progressLabel(pr) {
  if (!pr) return '';
  if (pr.needChoice) return `Ep ${pr.ep} · Your move`;
  return `Ep ${pr.ep} · ${Math.round((pr.pct || 0) * 100)}%`;
}

let heroTimer = 0;
function renderHome() {
  const el = $('#v-home');
  const sorted = weave(byPref(SERIES));  // her picked tastes first, earlier series and the new batch alternating  // her picked tastes first
  const heroes = sorted.slice(0, 5);
  const cont = continueItems();
  setTimeout(() => cont.slice(0, 2).forEach((x) => warmResume(x.id || (x.s && x.s.id))), 400);  // the top "continue" rows start instantly
  setTimeout(() => { if (!slowNet()) heroes.slice(0, 2).forEach((s) => warmEp1(s)); }, 1500);  // "Play now" on the first featured stories starts from memory
  const fav = (S.genres && S.genres[0]) || 'Werewolf';
  const becauseLabel = fav === 'Werewolf' ? 'werewolf romance' : fav.toLowerCase();
  const because = SERIES.filter((s) => (S.genres.length ? S.genres.some((g) => matchGenre(s, g)) : matchGenre(s, 'Werewolf') || matchGenre(s, 'Romance')));
  const becauseList = weave(byPref(because).concat(SERIES.filter((s) => because.indexOf(s) < 0)));
  const top = weave(SERIES.slice().sort((a, b) => parseFloat(rankScore(b)) - parseFloat(rankScore(a))));
  const fresh = weave(byPref(['reborn', 'lena', 'hellqueen', 'rian', 'starmate', 'island', 'crackhigh', 'mii', 'mythborne', 'rowan', 'onestat', 'rafael', 'heroacad', 'magnus', 'academia'].map(byId).filter(Boolean)));
  const binge = weave(SERIES.slice().sort((a, b) => ((b.stats || {}).rating || 0) - ((a.stats || {}).rating || 0)));
  el.innerHTML = `
    ${topbar()}
    <section class="hero" aria-label="Featured">
      <div class="hero-track" id="hero">
        ${heroes.map((s, i) => `
          <div class="hero-slide" data-act="open" data-id="${esc(s.id)}" role="button" tabindex="0" aria-label="${esc(s.title)}">
            <img src="${esc(bigCover(s))}" alt="" ${i ? 'loading="lazy"' : ''} onerror="this.onerror=null;this.src='${esc(coverOf(s))}'">
            <div class="hero-info">
              <span class="hero-badge"><span class="dot"></span>Written live from your choices</span>
              <h2 class="hero-title">${esc(s.title)}</h2>
              <p class="hero-hook">${esc(s.hook)}</p>
              <div class="hero-row">
                <button class="btn btn-grad btn-play-now" data-act="play-series" data-id="${esc(s.id)}">${ic('play')} Play Now</button>
                <span class="hero-tags">${(s.tags || []).slice(0, 3).map(esc).join(' · ')}</span>
              </div>
            </div>
          </div>`).join('')}
      </div>
      <div class="hero-dots" id="hero-dots">${heroes.map((_, i) => `<i class="${i ? '' : 'on'}"></i>`).join('')}</div>
    </section>
    ${cont.length ? `
    <section class="shelf">
      <div class="shelf-h"><h3>Continue Listening</h3><button class="more" data-act="go" data-to="library">See all</button></div>
      <div class="row">${cont.map((pr) => { const s = byId(pr.id); return `
        <button class="card wide" data-act="continue" data-id="${esc(s.id)}">
          <div class="cv">${thumbImg(s)}<span class="cont-play">${ic(pr.needChoice ? 'spark' : 'play')}</span></div>
          <div class="t">${esc(s.title)}</div>
          <div class="m">${esc(progressLabel(pr))}</div>
          <div class="cont-bar"><i style="width:${Math.round((pr.pct || 0) * 100)}%"></i></div>
        </button>`; }).join('')}</div>
    </section>` : ''}
    <div class="chips" role="list">${(S.genres || []).filter((g) => GENRES.indexOf(g) >= 0).concat(GENRES.filter((g) => (S.genres || []).indexOf(g) < 0)).map((g) => `<button class="chip" data-act="genre" data-g="${esc(g)}">${esc(g)}</button>`).join('')}</div>
    <section class="shelf">
      <div class="shelf-h"><h3>Top 10 this week</h3></div>
      <div class="row">${top.slice(0, 10).map((s, i) => `
        <button class="top-card" data-act="open" data-id="${esc(s.id)}" aria-label="#${i + 1} ${esc(s.title)}">
          <span class="rank">${i + 1}</span>
          <span class="cv">${thumbImg(s)}</span>
        </button>`).join('')}</div>
    </section>
    ${shelf('New Releases', fresh.map((s) => card(s)))}
    <button class="promo" data-act="go" data-to="rewards">
      <span class="pi">${coinIc('lg')}</span>
      <span class="pt"><b>Daily free listening</b><span>Ep 1–3 free on every series. Check in for up to 50 coins a day.</span></span>
      <span class="go">Claim</span>
    </button>
    ${shelf(`Because you like ${becauseLabel}`, becauseList.map((s) => card(s)))}
    ${shelf('Bingeworthy', binge.map((s) => card(s, `${ic('star')} ${esc(String((s.stats || {}).rating || ''))} · ${esc((s.stats || {}).plays || '')}`)))}
    <p class="foot-note">Every episode after Ep 1 is written live from what you choose.</p>`;
  setupHero();
}
function rankScore(s) {
  const p = String((s.stats || {}).plays || '0');
  const n = parseFloat(p) * (/M/i.test(p) ? 1e6 : /K/i.test(p) ? 1e3 : 1);
  return String(n);
}
function setupHero() {
  clearInterval(heroTimer);
  const track = $('#hero'); const dots = $$('#hero-dots i');
  if (!track) return;
  let i = 0, hold = 0;
  const upd = () => {
    const w = track.clientWidth; if (!w) return;
    i = Math.round(track.scrollLeft / (track.firstElementChild.clientWidth + 10));
    const sl = track.children[i]; if (sl && sl.dataset.id && !slowNet()) warmEp1(byId(sl.dataset.id));
    dots.forEach((d, k) => d.classList.toggle('on', k === i));
  };
  track.addEventListener('scroll', () => { requestAnimationFrame(upd); }, { passive: true });
  track.addEventListener('pointerdown', () => { hold = Date.now(); }, { passive: true });
  heroTimer = setInterval(() => {
    if (curTab !== 'home' || isDetailOpen() || playerOpen || Date.now() - hold < 6000 || document.hidden) return;
    const n = track.children.length; if (!n) return;
    const next = (i + 1) % n;
    track.scrollTo({ left: next * (track.firstElementChild.clientWidth + 10), behavior: reduceMotion() ? 'auto' : 'smooth' });
  }, 4500);
}

/* Explore */
let exQuery = '', exGenre = '';
function renderExplore() {
  const el = $('#v-explore');
  el.innerHTML = `
    <h1 class="page-title">Explore</h1>
    <form class="search" data-form="search" role="search">
      ${ic('search', 'sm')}
      <input id="ex-q" type="search" placeholder="Search series, characters, tropes" value="${esc(exQuery)}" enterkeyhint="search" aria-label="Search">
      ${exQuery || exGenre ? `<button class="clear" type="button" data-act="ex-clear" aria-label="Clear">${ic('close', 'sm')}</button>` : ''}
    </form>
    <div class="chips">${GENRES.map((g) => `<button class="chip ${exGenre === g ? 'on' : ''}" data-act="ex-genre" data-g="${esc(g)}">${esc(g)}</button>`).join('')}</div>
    <div id="ex-res"></div>`;
  const q = $('#ex-q');
  q.addEventListener('input', () => { exQuery = q.value; renderExploreResults(); const c = $('.search .clear'); if (!c && (exQuery || exGenre)) { /* keep focus, skip re-render */ } });
  renderExploreResults();
}
function renderExploreResults() {
  const box = $('#ex-res'); if (!box) return;
  const q = exQuery.trim().toLowerCase();
  if (!q && !exGenre) {
    const usedTile = [];
    box.innerHTML = `<h3 class="sec-h">Browse genres</h3>
      <div class="genre-grid">${GENRES.map((g) => {
        const s = SERIES.find((x) => matchGenre(x, g) && usedTile.indexOf(x) < 0) || SERIES.find((x) => matchGenre(x, g)) || SERIES[0];
        usedTile.push(s);
        const count = SERIES.filter((x) => matchGenre(x, g)).length;
        return `<button class="genre-tile" style="--tile:${GENRE_TILE[g] || '#333'}" data-act="ex-genre" data-g="${esc(g)}"><span>${esc(g)}</span><small>${count} series</small>${s ? `<img src="${esc(coverOf(s))}" alt="" loading="lazy">` : ''}</button>`;
      }).join('')}</div>
      <h3 class="sec-h">All series</h3>
      <div class="res-list">${SERIES.map(resRow).join('')}</div>`;
    return;
  }
  const list = SERIES.filter((s) => (!exGenre || matchGenre(s, exGenre)) && (!q || [s.title, s.lead, s.hook, s.name, (s.tags || []).join(' '), (s.genres || []).join(' ')].join(' ').toLowerCase().indexOf(q) >= 0));
  box.innerHTML = `<h3 class="sec-h">${list.length} result${list.length === 1 ? '' : 's'}${exGenre ? ` in ${esc(exGenre)}` : ''}</h3>
    ${list.length ? `<div class="res-list">${list.map(resRow).join('')}</div>` : `<div class="empty">${ic('search')}No series match “${esc(exQuery)}”.<br>Try a character name or a trope.</div>`}`;
}
const resRow = (s) => `
  <button class="res-row" data-act="open" data-id="${esc(s.id)}">
    <span class="cv">${thumbImg(s)}</span>
    <span class="rt"><b>${esc(s.title)}</b><span>${esc(s.lead)} · ${ic('star', 'xs')} ${esc(String((s.stats || {}).rating || ''))} · ${esc((s.stats || {}).plays || '')} plays</span><p>${esc(s.hook)}</p></span>
  </button>`;

/* Library */
let libTab = 'listening';
function renderLibrary() {
  const el = $('#v-library');
  let rows = '';
  if (libTab === 'listening') {
    const items = continueItems();
    rows = items.length ? items.map((pr) => {
      const s = byId(pr.id);
      return `<div class="lib-row">
        <button class="open" data-act="continue" data-id="${esc(s.id)}">
          <span class="cv">${thumbImg(s)}</span>
          <span class="lt"><b>${esc(s.title)}</b><span>${esc(progressLabel(pr))}${pr.title ? ' · ' + esc(pr.title) : ''}</span><span class="cont-bar"><i style="width:${Math.round((pr.pct || 0) * 100)}%"></i></span></span>
        </button>
        <button class="rm" data-act="lib-rm" data-k="${esc(skey(s.id))}" aria-label="Remove">${ic('trash', 'sm')}</button>
      </div>`;
    }).join('') : `<div class="empty">${ic('headphones')}Nothing in progress yet.<br>Start any series — Ep 1–3 are free.</div>`;
  } else if (libTab === 'saved') {
    const items = S.saved.map(byId).filter(Boolean);
    rows = items.length ? items.map((s) => {
      const pr = S.progress[skey(s.id)];
      return `<div class="lib-row">
        <button class="open" data-act="open" data-id="${esc(s.id)}">
          <span class="cv">${thumbImg(s)}</span>
          <span class="lt"><b>${esc(s.title)}</b><span>${pr ? esc(progressLabel(pr)) : esc(s.lead)}</span>${pr ? `<span class="cont-bar"><i style="width:${Math.round((pr.pct || 0) * 100)}%"></i></span>` : ''}</span>
        </button>
        <button class="rm" data-act="unsave" data-id="${esc(s.id)}" aria-label="Remove">${ic('trash', 'sm')}</button>
      </div>`;
    }).join('') : `<div class="empty">${ic('plus')}Tap “+ Library” on any series to save it here.</div>`;
  } else if (libTab === 'calls') {
    const all = callsFor();
    rows = all.length ? `<div class="calls-head"><span>${all.length} call${all.length === 1 ? '' : 's'} · saved after every turn</span><button class="link-btn" data-act="calls-clear">Clear all</button></div>
      <div class="calls-list">${all.map(callRowHtml).join('')}</div><p class="swipe-hint">Swipe left on a call to delete</p>`
      : `<div class="empty">${ic('phone')}No calls yet.<br>Call a lead from any series page.</div>`;
  } else {
    const items = S.hist.filter((h) => h.k && h.k.endsWith(`:${LANG}`) && h.k.startsWith(`${MOCK ? 'm' : 'r'}:`) && byId(h.id));
    rows = items.length ? items.map((h, i) => {
      const s = byId(h.id);
      return `<div class="lib-row">
        <button class="open" data-act="hist-play" data-id="${esc(s.id)}" data-n="${h.n}">
          <span class="cv">${thumbImg(s)}</span>
          <span class="lt"><b>${esc(s.title)}</b><span>Ep ${h.n} · ${esc(h.title || '')}</span><span>${timeAgo(h.at)}</span></span>
        </button>
        <button class="rm" data-act="hist-rm" data-at="${h.at}" aria-label="Remove">${ic('trash', 'sm')}</button>
      </div>`;
    }).join('') : `<div class="empty">${ic('clock')}Your listening history shows up here.</div>`;
  }
  el.innerHTML = `
    <h1 class="page-title">Library</h1>
    <div class="seg">${[['listening', 'Listening'], ['saved', 'Saved'], ['history', 'History'], ['calls', 'Calls']].map(([k, l]) => `<button class="chip ${libTab === k ? 'on' : ''}" data-act="lib-tab" data-t="${k}">${l}</button>`).join('')}</div>
    ${rows}`;
}
function timeAgo(t) {
  const s = (Date.now() - t) / 1000;
  if (s < 60) return 'Just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

/* Rewards */
const CHECKIN = [10, 15, 20, 25, 30, 40, 50];
const TASKS = [
  { k: 'listen', label: 'Listen 5 min', goal: 300, reward: 10, icon: 'headphones', fmt: (v) => `${Math.min(5, Math.floor(v / 60))}/5 min` },
  { k: 'newSeries', label: 'Play a new series', goal: 1, reward: 10, icon: 'sparkles', fmt: (v) => `${Math.min(1, v)}/1` },
  { k: 'choices', label: 'Make 3 choices', goal: 3, reward: 15, icon: 'pen', fmt: (v) => `${Math.min(3, v)}/3` },
  { k: 'share', label: 'Share a series', goal: 1, reward: 5, icon: 'share', fmt: (v) => `${Math.min(1, v)}/1` },
  { k: 'call', label: 'Call your favorite', goal: 1, reward: 10, icon: 'phone', fmt: (v) => `${Math.min(1, v)}/1` },
];
function checkinInfo() {
  const t = dayStr(), y = yesterdayStr();
  const c = S.checkin || { last: null, streak: 0 };
  const today = c.last === t;
  let streak = c.streak || 0;
  if (!today && c.last !== y) streak = 0;
  if (!today && streak >= 7) streak = 0;
  return { today, streak, idx: today ? streak - 1 : streak };
}
function renderRewards() {
  ensureToday();
  const el = $('#v-rewards');
  const ci = checkinInfo();
  el.innerHTML = `
    <h1 class="page-title">Rewards</h1>
    <div class="wallet">
      ${coinIc('xl')}
      <div class="wt"><small>Coin balance</small><b><span class="coins-n">${S.coins}</span>${S.vip ? `<span class="vip-chip">${ic('crown')} VIP</span>` : ''}</b></div>
      <button class="btn btn-grad btn-sm" data-act="store">Get coins</button>
    </div>
    <section class="panel">
      <div class="panel-h"><h3>Daily check-in</h3><span>${ci.today ? `Day ${ci.streak} claimed · back tomorrow` : `Day ${ci.streak + 1} of 7`}</span></div>
      <div class="days">${CHECKIN.map((c, i) => {
        const done = ci.today ? i < ci.streak : i < ci.streak;
        const isToday = !ci.today && i === ci.streak;
        return `<div class="day ${done ? 'done' : ''} ${isToday ? 'today' : ''}"><small>${isToday ? 'Today' : 'Day ' + (i + 1)}</small>${done ? `<span class="ok">${ic('check')}</span>` : coinIc()}<b>+${c}</b></div>`;
      }).join('')}</div>
      <button class="btn ${ci.today ? 'btn-ghost' : 'btn-grad'} btn-block checkin-btn" data-act="checkin" ${ci.today ? 'disabled' : ''}>${ci.today ? `${ic('check', 'sm')} Checked in today` : `Check in · +${CHECKIN[ci.streak]} coins`}</button>
    </section>
    <section class="panel">
      <div class="panel-h"><h3>Daily tasks</h3><span>Resets at midnight</span></div>
      ${TASKS.map((t) => {
        const v = S.tasks[t.k] || 0; const ok = v >= t.goal; const claimed = S.tasks.claimed[t.k];
        return `<div class="task">
          <span class="ti">${ic(t.icon)}</span>
          <span class="tt"><b>${t.label}</b><span>${coinIc('sm')} +${t.reward} · ${t.fmt(v)}</span><span class="tbar"><i style="width:${Math.round(clamp(v / t.goal, 0, 1) * 100)}%"></i></span></span>
          ${claimed ? `<span class="claimed">${ic('check', 'xs')} Claimed</span>` : `<button class="btn ${ok ? 'btn-grad' : 'btn-ghost'} btn-sm" data-act="claim" data-k="${t.k}" ${ok ? '' : 'disabled'}>${ok ? 'Claim' : 'Go'}</button>`}
        </div>`;
      }).join('')}
    </section>
    <section class="panel">
      <div class="panel-h"><h3>Coin history</h3><span>${S.ledger.length} records</span></div>
      ${S.ledger.length ? S.ledger.slice(0, 30).map((h) => `
        <div class="hist-row"><span>${esc(h.l)}<small>${new Date(h.t).toLocaleString(LANG === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</small></span><b class="${h.d >= 0 ? 'plus' : 'minus'}">${h.d >= 0 ? '+' : ''}${h.d}</b></div>`).join('') : '<div class="empty" style="padding:16px">No coin activity yet.</div>'}
    </section>`;
}

/* Detail */
let detailId = null, detailTab = 'episodes', synOpen = false;
const isDetailOpen = (id) => $('#detail').classList.contains('on') && (!id || detailId === id);
/* Episode 1 audio lives on cloud storage whose first byte takes ~3 s; warm it as soon as she opens a series so Play starts at once */
const WARM = [];
/** her saved story: fetch the line she resumes from (and the next few) into local blobs, so Continue starts at once */
function warmResume(id) {
  const ss = getSess(id); if (!ss || !ss.eps || !ss.eps.length) return;
  const pr = S.progress[skey(id)] || {};
  const ep = ss.eps.find((e) => e.n === pr.ep) || ss.eps[ss.eps.length - 1];
  if (!ep) return;
  if (ep.kind === 'live') (ep.lines || []).slice(pr.ep === ep.n ? pr.line || 0 : 0).filter((l) => l.url).slice(0, 4).forEach((l) => fetchBlob(l.url));
  else if (ep.audio && !slowNet() && !WARM.some((a) => a.dataset.u === ep.audio)) { try { const a = new Audio(); a.preload = 'auto'; a.muted = true; a.dataset.u = ep.audio; a.src = absUrl(ep.audio); a.load(); WARM.push(a); while (WARM.length > 3) { const o = WARM.shift(); o.removeAttribute('src'); o.load(); } } catch (e) { /* ignore */ } }
}
function warmEp1(s, must) {
  const u = s && s.ep1 && s.ep1.audio;
  if (slowNet() && !must) return;   // slow link: no whole-file preloads; Play streams from the first bytes instead
  if (u && !getSess(s.id)) fetchLocalBlob(u);
  if (!u || MOCK || getSess(s.id) || /^ep1\//.test(u) || WARM.some((a) => a.dataset.u === u)) return;
  try {
    const a = new Audio(); a.preload = 'auto'; a.muted = true; a.dataset.u = u; a.src = absUrl(u); a.load();
    WARM.push(a); while (WARM.length > 2) { const o = WARM.shift(); o.removeAttribute('src'); o.load(); }
  } catch (e) { /* ignore */ }
}
async function showDetail(id) {
  const s = byId(id); if (!s) { location.hash = '#/home'; return; }
  warmEp1(s); warmResume(id);
  if (s.visuals) [...((s.ep1 && s.ep1.visuals) || []).slice(0, 3).map((x) => x.clip), ...(s.visuals.pool || []).slice(0, 1)].forEach((c) => {
    const u = s.visuals.clips[c]; if (!u) return;
    if (NARRA) { stillIndex(id); hdIndex(id); return; }   // narra: stills only (their lists first; the pictures follow in warmStills)
    if (!slowNet()) clipBlob(u);
  });  // first pictures ready before Play
  if (detailId !== id) { detailTab = 'episodes'; synOpen = false; }
  detailId = id;
  renderDetail();
  const page = $('#detail');
  page.classList.add('on');
  if (!DETAIL[id]) {
    try { DETAIL[id] = await API.seriesDetail(id); if (detailId === id) renderDetail(); } catch (e) { console.warn('detail', e); }
  }
}
function hideDetail() { $('#detail').classList.remove('on'); }
function renderDetail() {
  const s = byId(detailId); if (!s) return;
  setTimeout(() => { if (detailId === s.id && isDetailOpen()) { warmRings(); prepareCall(s.id); } }, 1200);
  const d = DETAIL[s.id] || {};
  const ss = getSess(s.id);
  const pr = S.progress[skey(s.id)];
  const saved = S.saved.indexOf(s.id) >= 0;
  const nEps = ss ? ss.eps.length : 1;
  let cta = `${ic('play')} Play Episode 1`;
  if (ss && pr) cta = pr.needChoice ? `${ic('spark')} Your move · Ep ${pr.ep}` : `${ic('play')} Continue Ep ${pr.ep}`;
  else if (ss) cta = `${ic('play')} Continue Ep ${ss.eps[ss.eps.length - 1].n}`;
  const page = $('#detail');
  const keepScroll = page.classList.contains('on') ? page.scrollTop : 0;
  page.style.setProperty('--accent', s.accent || '#FF8448');
  page.innerHTML = `
    <div class="dt-hero">
      <div class="dt-bg" style="background-image:url('${esc(coverOf(s))}')"></div>
      <div class="dt-top">
        <button class="icon-btn" data-act="back" aria-label="Back">${ic('back')}</button>
        <span class="dt-top-r">
          <button class="icon-btn ${saved ? 'on' : ''}" data-act="save" data-id="${esc(s.id)}" aria-label="${saved ? 'Saved to Library' : 'Add to Library'}">${ic(saved ? 'check' : 'plus', 'sm')}</button>
          <button class="icon-btn" data-act="share" data-id="${esc(s.id)}" aria-label="Share">${ic('share', 'sm')}</button>
        </span>
      </div>
      <div class="dt-main">
        <div class="dt-cover"><img src="${esc(slowNet() ? coverOf(s) : bigCover(s))}" alt="" onerror="this.onerror=null;this.src='${esc(coverOf(s))}'"></div>
        <h1 class="dt-title">${esc(s.title)}</h1>
        <p class="dt-lead">${esc(s.lead)}</p>
        <div class="stats">
          <span>${ic('headphones')} ${esc((s.stats || {}).plays || '—')}</span><i></i>
          <span><span class="star">${ic('star')}</span> ${esc(String((s.stats || {}).rating || '—'))}</span><i></i>
          <span>${ic('list')} ${nEps} ep${nEps === 1 ? '' : 's'} · live</span>
        </div>
        <div class="tags">${(s.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>
        <div class="dt-cta">
          <button class="btn btn-grad" data-act="play-series" data-id="${esc(s.id)}">${cta}</button>
          <button class="btn btn-ghost call-btn" data-act="call-lead" data-id="${esc(s.id)}" aria-label="Call">${ic('phone', 'sm')}<span>${callersOf(s).length > 1 ? 'Call' : `Call ${esc(shortName(callersOf(s)[0]).split(' ')[0])}`}</span></button>
        </div>
        <p class="call-note">${ic('phone', 'xs')} ${callCost(s.id) ? `Voice call · ${CALL_PRICE} coins` : 'Voice call · first call free'} · ${((s.callers || [])[0] || {}).gender === 'female' ? 'she' : 'he'} remembers your story</p>
        ${(() => { const cl = callsFor(s.id); return cl.length ? `<button class="hist-btn" data-act="series-calls" data-id="${esc(s.id)}">${ic('clock', 'sm')}<span><b>Call history</b><small>${cl.length} call${cl.length === 1 ? '' : 's'} · latest ${fmtWhen(cl[0].startedAt)} · ${esc(recStatusLabel(cl[0]))}</small></span>${ic('chevR', 'sm')}</button>` : ''; })()}
        ${ss ? `<button class="restart" data-act="restart" data-id="${esc(s.id)}">${ic('restart')} Start a new story from Ep 1</button>` : ''}
      </div>
    </div>
    <div class="synopsis ${synOpen ? 'open' : ''}"><p>${esc(d.synopsis || s.hook)}</p><button data-act="syn">${synOpen ? 'Show less' : 'More'}</button></div>
    <div class="tabs" role="tablist">
      ${[['episodes', 'Episodes'], ['about', 'About'], ['more', 'More like this']].map(([k, l]) => `<button role="tab" class="${detailTab === k ? 'on' : ''}" aria-selected="${detailTab === k}" data-act="dt-tab" data-t="${k}">${l}</button>`).join('')}
    </div>
    <div class="tab-pane" id="dt-pane"></div>`;
  renderDetailPane();
  page.scrollTop = keepScroll;
}
function renderDetailPane() {
  const s = byId(detailId); const box = $('#dt-pane'); if (!s || !box) return;
  const d = DETAIL[s.id] || {};
  if (detailTab === 'episodes') {
    box.innerHTML = `<div class="ep-head"><span>Ep 1–${FREE_EPS} free · then ${PRICE} coins each</span><span>${S.vip ? 'VIP · all free' : ''}</span></div><div class="ep-list" id="dt-eps">${episodeRows(s)}</div>`;
  } else if (detailTab === 'about') {
    const cast = d.cast || [];
    box.innerHTML = `
      <div class="about-block"><h4>Cast</h4>
        <div class="cast">${cast.length ? cast.map((c, i) => `
          <div class="cast-row">${i === 0 ? `<img src="${esc(avatarOf(s))}" alt="">` : `<span class="ph">${esc((c.name || '?').slice(0, 1))}</span>`}
            <div><b>${esc(c.name)}</b><span>${esc(c.role)}</span><em>${ic('mic')} Voice: ${esc(c.voice || '—')}</em></div></div>`).join('') : '<div class="skel" style="height:52px"></div>'}
        </div></div>
      <div class="about-block"><h4>How it works</h4>
        <div class="how">
          <div><b>1</b><span>Episode 1 is a produced audio drama. It ends on a choice.</span></div>
          <div><b>2</b><span>Pick an answer, type your own, or just say it out loud.</span></div>
          <div><b>3</b><span>The next episode is written and voiced live from what you chose${S.name ? `, and they’ll call you ${esc(S.name)}` : ''}.</span></div>
        </div></div>
      <div class="about-block"><h4>Genres</h4><div class="tags" style="justify-content:flex-start">${(s.genres || []).map((g) => `<span class="tag">${esc(g)}</span>`).join('')}</div></div>`;
  } else {
    const others = weave(SERIES.filter((x) => x.id !== s.id).sort((a, b) => sharedGenres(b, s) - sharedGenres(a, s)));
    box.innerHTML = `<div class="mlt-grid">${others.map((x) => card(x)).join('')}</div>`;
  }
}
const sharedGenres = (a, b) => (a.genres || []).filter((g) => (b.genres || []).indexOf(g) >= 0).length;
function renderDetailEpisodes() {
  const box = $('#dt-eps'); const s = byId(detailId);
  if (box && s) box.innerHTML = episodeRows(s);
}

function episodeRows(s) {
  const ss = getSess(s.id);
  const eps = ss ? ss.eps : [];
  const chosen = (ss && ss.chosen) || {};
  const rows = [];
  const playingThis = P.id === s.id;
  const priceTag = (n) => {
    if (n <= FREE_EPS) return '<span class="free">FREE</span>';
    if (isUnlocked(s.id, n)) return `<span class="lock-ic">${ic('unlock', 'sm')}</span>`;
    return `<span class="price">${ic('lock', 'xs')} ${coinIc('sm')} ${PRICE}</span>`;
  };
  const list = eps.length ? eps : [{ n: 1, title: (s.ep1 || {}).title || 'Episode 1', dur: (s.ep1 || {}).dur, kind: 'produced', _placeholder: true }];
  list.forEach((ep) => {
    const now = playingThis && P.ep && P.ep.n === ep.n && !ep._placeholder;
    const said = chosen[ep.n - 1];
    const meta = ep.n === 1
      ? `${ic('clock')} ${fmtMin(ep.dur || (s.ep1 || {}).dur) || '3 min'} · ${ic('headphones')} ${esc((s.stats || {}).plays || '')}`
      : `${ic('spark')} Written for you${ep.dur ? ' · ' + fmtMin(ep.dur) : ` · ${(ep.lines || []).length} lines`}${said != null ? ` · <span class="you">${said ? '“' + esc(said.slice(0, 28)) + (said.length > 28 ? '…' : '') + '”' : 'you stayed silent'}</span>` : ''}`;
    rows.push(`
      <button class="ep-row ${now ? 'now' : ''} ${now && !isPlaying() ? 'paused' : ''}" data-act="ep" data-id="${esc(s.id)}" data-n="${ep.n}" data-k="${ep._placeholder ? 'start' : 'stored'}">
        <span class="ep-n">${now ? '<span class="eq"><i></i><i></i><i></i></span>' : ep.n}</span>
        <span class="ep-t"><b>Ep ${ep.n} · ${esc(ep.title || '')}</b><span>${meta}</span></span>
        <span class="ep-r">${priceTag(ep.n)}<span class="ep-play">${ic(now && isPlaying() ? 'pause' : 'play')}</span></span>
      </button>`);
  });
  const last = list[list.length - 1];
  if (!last.ending) {
    const nextN = last.n + 1;
    const generating = playingThis && P.gen && P.gen.n === nextN;
    const upto = Math.max(nextN + 2, 5);
    for (let n = nextN; n <= upto; n++) {
      const isNext = n === nextN;
      rows.push(`
        <button class="ep-row ghost ${isNext ? 'next' : ''}" data-act="ep" data-id="${esc(s.id)}" data-n="${n}" data-k="${isNext ? 'next' : 'future'}">
          <span class="ep-n">${n}</span>
          <span class="ep-t"><b>${isNext ? (generating ? `Ep ${n} · Writing your episode…` : `Ep ${n} · Written live from your choice`) : `Ep ${n} · Depends on your choices`}</b>
            <span>${isNext ? (generating ? `<span class="dots-pulse"><i></i><i></i><i></i></span> generating now` : `${ic('spark')} Finish Ep ${n - 1} and choose`) : 'Not written yet'}</span></span>
          <span class="ep-r">${priceTag(n)}</span>
        </button>`);
    }
  }
  return rows.join('');
}

/* Mini player */
function renderMini() {
  const m = $('#mini');
  const s = P.id && byId(P.id);
  const show = !!(s && (P.ep || P.gen || P.loading));
  m.hidden = !show;
  m.dataset.sig = miniSig();
  $('#app').classList.toggle('has-mini', show);
  if (!show) return;
  let sub;
  if (P.gen) sub = `<span class="live"><span class="dots-pulse"><i></i><i></i><i></i></span> Writing Ep ${P.gen.n}…</span>`;
  else if (P.loading) sub = `<span class="live"><span class="dots-pulse"><i></i><i></i><i></i></span> Preparing Ep 1…</span>`;
  else if (P.needChoice) sub = `<span class="live">${ic('spark', 'xs')} Ep ${P.ep.n} ended · Your move</span>`;
  else sub = `<span>Ep ${P.ep.n} · ${esc(P.ep.title || '')}</span>`;
  m.innerHTML = `
    <button class="open" data-act="open-player" aria-label="Open player">
      <img src="${esc(coverOf(s))}" alt="">
      <span class="mt"><b>${esc(s.title)}</b>${sub}</span>
    </button>
    <button class="pp" data-act="${P.needChoice ? 'open-choice' : 'toggle'}" aria-label="${isPlaying() ? 'Pause' : 'Play'}">${ic(P.needChoice ? 'spark' : isPlaying() ? 'pause' : 'play')}</button>
    <span class="mbar"><i id="mini-bar"></i></span>`;
  tickUI();
}

/* Full player */
let playerOpen = false, playerPushed = false;
function renderPlayer() {
  const el = $('#player');
  if (!el.dataset.built) {
    el.dataset.built = '1';
    const vids = `<img id="pl-art" alt=""><video id="pl-vid" muted loop playsinline autoplay preload="auto" aria-hidden="true"></video><video id="pl-vid2" muted loop playsinline preload="auto" aria-hidden="true"></video>`;
    const note = `<button class="pl-note" id="pl-note" data-act="open-safari" hidden>${ic('lock', 'xs')}<span>${tz('Answering with the screen locked needs Safari — tap to copy the link', '锁屏也能语音回答需要用 Safari 打开 · 点这里复制链接')}</span></button>`;
    const transport = `
        <div class="pl-prog">
          <div class="pbar" id="pl-bar"><div class="trk"><div class="fill" id="pl-fill"></div><span class="knob" id="pl-knob"></span><div class="segs" id="pl-segs" hidden></div></div></div>
          <div class="times"><span id="pl-el">0:00</span><span id="pl-tot">0:00</span></div>
        </div>
        <div class="pl-ctrl">
          <button class="icon-btn edge" data-act="prev" aria-label="Previous episode">${ic('prev')}</button>
          <button class="icon-btn" data-act="back10" aria-label="Back 10 seconds">${ic('back10')}</button>
          <button class="big-play" data-act="toggle" id="pl-play" aria-label="Play">${ic('play')}</button>
          <button class="icon-btn" data-act="fwd10" aria-label="Forward 10 seconds">${ic('fwd10')}</button>
          <button class="icon-btn edge" data-act="next" aria-label="Next episode">${ic('next')}</button>
        </div>`;
    // narra: no cover box, no big title. The picture fills the top behind everything, the story scrolls like lyrics,
    // call + share sit at the top right, and the listening mode is the last item of the bottom toolbar (where Share was).
    el.innerHTML = NARRA ? `
      <div class="pl-bg"><div class="pl-bg-img" id="pl-bgimg"></div></div>
      <div class="nr-stage"><div class="pl-art">${vids.replace('<video', '<img class="pst" id="pl-pst" alt=""><img class="pst" id="pl-pst2" alt=""><video')}</div></div>
      <div class="nr-shade"></div>
      <header class="pl-top">
        <button class="icon-btn" data-act="close-player" aria-label="Close player">${ic('down')}</button>
        <div class="pl-top-t"><b id="pl-series" translate="no"></b><small id="pl-ep"></small></div>
        <button class="icon-btn" data-act="pl-call" aria-label="Call">${ic('phone')}</button>
        <button class="icon-btn" data-act="share" id="pl-share" aria-label="Share">${ic('share')}</button>
      </header>
      <div class="pl-body">
        <div class="nr-gap"><span class="pl-badge" id="pl-badge" hidden></span></div>
        ${note}
        <div class="nr-lyr" id="nr-lyr"><div class="nr-roll" id="nr-roll"></div></div>
        <div class="pl-sub" id="pl-sub" hidden></div>
        <div class="pl-gen" id="pl-gen" hidden></div>${transport}
        <div class="pl-tools">
          <button class="tool" data-act="speed" id="pl-speed" aria-label="Playback speed"><b>1x</b>Speed</button>
          <button class="tool" data-act="sleep-sheet" id="pl-sleep" aria-label="Sleep timer">${ic('moon')}<span>Sleep</span></button>
          <button class="tool talk" data-act="talk" aria-label="Talk to the story">${ic('mic')}<span>Talk</span></button>
          <button class="tool" data-act="pl-eps" aria-label="Episode list">${ic('list')}<span>Episodes</span></button>
          <button class="tool" data-act="mode-sheet" id="pl-mode" aria-label="Listening mode"></button>
        </div>
        <span hidden><b id="pl-title"></b><button data-act="pl-save" id="pl-save"></button></span>
      </div>` : `
      <div class="pl-bg"><div class="pl-bg-img" id="pl-bgimg"></div></div>
      <header class="pl-top">
        <button class="icon-btn" data-act="close-player" aria-label="Close player">${ic('down')}</button>
        <div class="pl-top-t"><small>NOW PLAYING</small><b id="pl-series"></b></div>
        <button class="icon-btn" data-act="pl-call" aria-label="Call">${ic('phone')}</button>
      </header>
      <div class="pl-body">
        <div class="pl-art-wrap"><div class="pl-art"><img id="pl-art" alt=""><video id="pl-vid" muted loop playsinline autoplay preload="auto" aria-hidden="true"></video><video id="pl-vid2" muted loop playsinline preload="auto" aria-hidden="true"></video><span class="pl-badge" id="pl-badge" hidden></span></div></div>
        <div class="pl-titles"><div class="tt"><h2 id="pl-title"></h2><p id="pl-ep"></p></div>
          <button class="icon-btn" data-act="pl-save" id="pl-save" aria-label="Add to Library">${ic('plus')}</button></div>
        <button class="pl-mode" id="pl-mode" data-act="mode-sheet" aria-label="Listening mode"></button>
        <button class="pl-note" id="pl-note" data-act="open-safari" hidden>${ic('lock', 'xs')}<span>${tz('Answering with the screen locked needs Safari — tap to copy the link', '锁屏也能语音回答需要用 Safari 打开 · 点这里复制链接')}</span></button>
        <div class="pl-sub" id="pl-sub" aria-live="polite"></div>
        <div class="pl-gen" id="pl-gen" hidden></div>
        <div class="pl-prog">
          <div class="pbar" id="pl-bar"><div class="trk"><div class="fill" id="pl-fill"></div><span class="knob" id="pl-knob"></span><div class="segs" id="pl-segs" hidden></div></div></div>
          <div class="times"><span id="pl-el">0:00</span><span id="pl-tot">0:00</span></div>
        </div>
        <div class="pl-ctrl">
          <button class="icon-btn edge" data-act="prev" aria-label="Previous episode">${ic('prev')}</button>
          <button class="icon-btn" data-act="back10" aria-label="Back 10 seconds">${ic('back10')}</button>
          <button class="big-play" data-act="toggle" id="pl-play" aria-label="Play">${ic('play')}</button>
          <button class="icon-btn" data-act="fwd10" aria-label="Forward 10 seconds">${ic('fwd10')}</button>
          <button class="icon-btn edge" data-act="next" aria-label="Next episode">${ic('next')}</button>
        </div>
        <div class="pl-tools">
          <button class="tool" data-act="speed" id="pl-speed" aria-label="Playback speed"><b>1x</b>Speed</button>
          <button class="tool" data-act="sleep-sheet" id="pl-sleep" aria-label="Sleep timer">${ic('moon')}<span>Sleep</span></button>
          <button class="tool talk" data-act="talk" aria-label="Talk to the story">${ic('mic')}<span>Talk</span></button>
          <button class="tool" data-act="pl-eps" aria-label="Episode list">${ic('list')}<span>Episodes</span></button>
          <button class="tool" data-act="share" id="pl-share" aria-label="Share">${ic('share')}<span>Share</span></button>
        </div>
      </div>`;
    bindScrub($('#pl-bar'));
  }
  const s = byId(P.id); if (!s) return;
  const cov = bigCover(s);   // good link: the super-resolved cover; slow link: the small one (≈40 KB)
  $('#pl-bgimg').style.backgroundImage = `url('${slowNet() ? thumbOf(s) : coverOf(s)}')`;   // blurred backdrop: the plain cover is enough
  const art = $('#pl-art'); if (art.getAttribute('src') !== cov) { art.onerror = () => { art.onerror = null; art.src = coverOf(s); }; art.src = cov; }
  // 动态封面（Pocket FM 式）：静音循环短片盖在封面上，能播了才淡入；没有短片就只显示封面
  const vid = $('#pl-vid'), mo = NARRA ? '' : motionOf(s);   // narra: a still background, no moving cover
  if (VS.sid !== s.id) {  // another series: drop the old one's picture at once (its cover shows) instead of leaving it up until the new clip loads
    VS.sid = s.id; VS.url = null; VS.tok++; stillIndex(s.id); hdIndex(s.id); PS.url = ''; PS.tok++; ['#pl-pst', '#pl-pst2'].forEach((q) => { const x = $(q); if (x) { x.classList.remove('on'); x.removeAttribute('src'); } });
    [vid, $('#pl-vid2')].forEach((v) => { v.classList.remove('on'); v.oncanplay = null; v.onplaying = null; try { v.pause(); v.removeAttribute('src'); v.load(); } catch (e) { /* ignore */ } delete v.dataset.src; });
    warmVisuals(s);
  }
  if (s.visuals) { renderVisual(true); }  // 有画面库：按台词切剧情画面（renderVisual），不用单一动态封面
  else if (!mo) { vid.removeAttribute('src'); vid.classList.remove('on'); }
  else if (vid.dataset.src !== mo) {
    vid.dataset.src = mo; vid.classList.remove('on'); vid.src = mo;
    vid.oncanplay = () => { vid.classList.add('on'); vid.play().catch(() => {}); };
  } else if (vid.paused) vid.play().catch(() => {});
  if (NARRA) fitTitle(s.title); else $('#pl-series').textContent = s.title;
  $('#pl-share').dataset.id = s.id;
  updateModePill();
  updatePlayerUI();
}
/* 剧情画面：播放器封面区跟着音频切静音循环片段（服务器给的画面库 s.visuals = {clips:{id:src}, pool:[id…]}）。
 * 第 1 集按 ep.visuals 时间轴 [{s,e,clip}]；实时集按当前这句的 line.clip；没有对应画面（等待、选择点、没标）就在 pool 里每 7 秒轮播
 * 万能 live / 剧照。两个 <video> 交替淡入，片段能播了才切。 */
const VS = { url: null, sid: null, tok: 0 };
/* clips are small same-origin mp4s: keep local blobs so a switch is instant (no re-download, no black frame) */
const VBLOB = new Map();
function clipBlob(url) {
  if (!url || VBLOB.has(url)) return VBLOB.get(url) || null;
  const r = { obj: null }; VBLOB.set(url, r);
  r.p = fetch(absUrl(url)).then((x) => (x.ok ? x.blob() : null)).then((b) => { if (b && b.size) r.obj = URL.createObjectURL(b); return r.obj; }).catch(() => null);
  return r;
}
function warmVisuals(s) {
  const V = s && s.visuals; if (!V) return;
  if (NARRA) { warmStills(s); return; }   // narra shows stills only: no clips to fetch
  const ids = new Set(V.pool || []);
  const ss = getSess(s.id), ep = P.id === s.id && P.ep;
  ((ep && ep.visuals) || (s.ep1 && s.ep1.visuals) || []).forEach((x) => ids.add(x.clip));
  ((ep && ep.lines) || []).forEach((l) => l.clip && ids.add(l.clip));
  if (ss && !ep) ((ss.eps[ss.eps.length - 1] || {}).lines || []).forEach((l) => l.clip && ids.add(l.clip));
  queueClips([...ids].slice(0, 40).map((id) => V.clips[id]).filter(Boolean));
}
/* clips load a few at a time, in the order they will be needed (was: up to 40 at once, which stalled the audio on slow links) */
const CQ = { list: [], busy: 0 };
function queueClips(urls) {
  CQ.list = urls.filter((u) => !VBLOB.has(u)).concat(CQ.list.filter((u) => urls.indexOf(u) < 0 && !VBLOB.has(u))).slice(0, 60);
  const pump = () => {
    while (CQ.busy < (slowNet() ? 1 : 3) && CQ.list.length) {
      const u = CQ.list.shift(); if (VBLOB.has(u)) continue;
      const r = clipBlob(u); CQ.busy++;
      const done = () => { CQ.busy--; pump(); };
      (r && r.p ? r.p : Promise.resolve()).then(done, done);
    }
  };
  pump();
}
/* narra: every clip has a poster (same name, .jpg). It is on screen as soon as the line starts; the moving clip fades in over it when it has loaded. */
const PS = { url: '', tok: 0, seen: new Set(), req: new Set(), fail: 0, busy: 0 };
const posterOf = (clipUrl) => String(clipUrl || '').replace(/\.mp4$/, '.jpg');
/* 11-11 (2) sharper backgrounds: the 13 realtime series have portrait HD versions of their scenes (build_hd.py →
 * v/<id>/hd/<clip>.mp4 + .jpg, up to 720×1080 like the covers; the stills are HD pictures only and move by CSS).
 * hd/index.json says which clips have one; until it has loaded, and for everything else, the square clips are used. */
const HDX = {};
const HD_IDS = new Set(STYLE_REAL.concat(STYLE_SEMI));
/* 11-11 (5) static backgrounds ("a still picture that fits what is being told, not a moving clip"): every scene clip has a
 * portrait still (build_stills.py → v/<id>/still/<clip>.jpg, 1080×1620, super-resolved where the source was small);
 * still/index.json lists them. narra shows stills only — the <video> layers stay empty. */
const STX = {};
function stillIndex(sid) {
  if (!NARRA || STX[sid]) return;
  STX[sid] = { set: new Set(), ready: false };
  const done = (j) => { STX[sid] = { set: new Set((j && j.still) || []), ready: true }; PS.url = ''; if (P.id === sid && playerOpen) renderVisual(true); };
  fetch(absUrl(`v/${sid}/still/index.json`)).then((r) => (r.ok ? r.json() : null)).then(done).catch(() => done(null));
}
/** the pictures of one scene clip: hi = the sharpest there is, low = a small one to put up first on a slow link */
function stillOf(s, id) {
  const V = s.visuals, c = V && V.clips[id]; if (!c) return { low: '', hi: '' };
  const st = STX[s.id] && STX[s.id].set.has(id) ? `v/${s.id}/still/${id}.jpg` : '', hd = hdOf(c).poster || '', sq = posterOf(c);
  if (slowNet()) return { low: hd ? '' : sq, hi: hd || st || sq };   // slow link: the 720 px picture (≈50 KB) is enough
  return { low: '', hi: st || hd || sq };
}
/** Which picture belongs to which part of the episode — a pure function of the position, so dragging the bar, tapping a line
 * or skipping lands on that part's picture at once. It follows the story's own picture timeline (the picture changes where the
 * scene changes) but holds each picture at least MIN, so the background doesn't flicker through short cuts.
 * Units: seconds (Episode 1) or lines (written episodes). */
function stillPlan(s, ep) {
  const V = s.visuals, produced = ep.kind !== 'live';
  const units = produced ? (ep.visuals || []).map((x) => [x.s, x.clip]) : (ep.lines || []).map((l, i) => [i, l.clip]);
  const key = [s.id, ep.n, ep.kind, units.length].join(':');
  if (V._planKey === key && V._plan) return V._plan;
  const MIN = produced ? 12 : 3, ok = (id) => id && V.clips[id] && !(V.prefer && id !== 'idle' && !id.startsWith(V.prefer));
  const pts = [];
  units.forEach(([at, id]) => {
    if (!ok(id)) return;
    const last = pts[pts.length - 1];
    if (last && (last[1] === id || at - last[0] < MIN)) return;
    pts.push([at, id]);
  });
  if (!pts.length) { const pool = (V.pool || []).filter(ok); if (pool.length) pts.push([0, pool[(ep.n || 0) % pool.length]]); }
  if (pts.length) pts[0][0] = 0;
  V._planKey = key; V._plan = pts;
  return pts;
}
function stillClip(s) {
  const V = s.visuals, ep = P.ep; if (!V || !ep) return V && V._cur && V._curSid === s.id ? V._cur : null;
  if (!P.aux && !P.needChoice && !P.gen && !P.loading) {   // while the narrator asks / she answers / the next episode is written, the picture that was up stays
    const plan = stillPlan(s, ep); if (!plan.length) return null;
    let pos;
    if (ep.kind !== 'live') { const d = audio.duration || ep.dur || 0; pos = P.scrubF != null ? P.scrubF * d : (audio.currentTime || 0); }
    else { const n = (ep.lines || []).length; pos = P.scrubF != null ? Math.min(n - 1, Math.floor(P.scrubF * n)) : P.idx; }
    let id = plan[0][1];
    for (let j = 0; j < plan.length && plan[j][0] <= pos; j++) id = plan[j][1];
    V._cur = id; V._curSid = s.id;
  } else if (!V._cur) { const plan = stillPlan(s, ep); if (plan.length) V._cur = plan[plan.length - 1][1]; }
  return V._cur || null;
}
/** keep this episode's pictures in memory so a switch (or a drag) never waits for the network: two at a time, the one on
 * screen first, then in the order the episode uses them; on a slow link only the next two. */
function warmStills(s) {
  const V = s.visuals, ep = P.ep; if (!V || !ep || PS.busy >= 2) return;
  const plan = stillPlan(s, ep), cur = Math.max(0, plan.findIndex((p) => p[1] === V._cur));
  const order = plan.slice(cur).concat(slowNet() ? [] : plan.slice(0, cur)).slice(0, slowNet() ? 3 : 60);
  for (const p of order) {
    const u = stillOf(s, p[1]).hi; if (!u || PS.seen.has(u) || PS.req.has(u)) continue;
    PS.req.add(u); PS.busy += 1;
    const im = new Image(), fin = (good) => { PS.busy -= 1; if (good) PS.seen.add(u); else setTimeout(() => PS.req.delete(u), 4000); if (P.id === s.id) warmStills(s); };
    im.onload = () => fin(true); im.onerror = () => fin(false); im.src = absUrl(u);
    if (PS.busy >= 2) return;
  }
}
function hdIndex(sid) {
  if (!NARRA || HDX[sid] || !HD_IDS.has(sid)) return;
  HDX[sid] = { video: new Set(), poster: new Set() };
  fetch(absUrl(`v/${sid}/hd/index.json`)).then((r) => (r.ok ? r.json() : null)).then((j) => {
    HDX[sid] = { video: new Set((j && j.video) || []), poster: new Set((j && j.poster) || []), ready: true };
    PS.url = ''; if (P.id === sid && playerOpen) renderVisual(true);
  }).catch(() => { HDX[sid].ready = true; });
}
function hdOf(clipUrl) {
  const m = /^v\/([\w-]+)\/([\w-]+)\.mp4$/.exec(clipUrl || ''), x = m && HDX[m[1]];
  if (!x) return {};
  return { poster: x.poster.has(m[2]) ? `v/${m[1]}/hd/${m[2]}.jpg` : '', video: x.video.has(m[2]) ? `v/${m[1]}/hd/${m[2]}.mp4` : '' };
}
/** put a picture up: the small one at once (slow link), the sharp one over it as soon as it has loaded */
function showPoster(low, hi) {
  const a = $('#pl-pst'), b = $('#pl-pst2'); if (!a || !b) return;
  const key = hi || low; if (!key || key === PS.url) return;
  PS.url = key; const tok = ++PS.tok; let gotHi = false;
  const put = (src, isHi) => {
    if (PS.tok !== tok || (gotHi && !isHi)) return;
    if (isHi) gotHi = true;
    const front = a.classList.contains('on') ? a : b, back = front === a ? b : a;
    back.src = src; back.classList.add('on'); front.classList.remove('on');
  };
  const load = (u, isHi) => { const im = new Image(); im.onload = () => { PS.seen.add(u); put(im.src, isHi); }; im.onerror = () => { if (!isHi) PS.fail += 1; setTimeout(() => { if (PS.tok === tok && !gotHi && PS.url === key) PS.url = ''; }, 1500); }; im.src = absUrl(u); };   // a failed picture is asked for again (was: the old background stayed for good)
  if (hi && PS.seen.has(hi)) { load(hi, true); return; }
  if (low && low !== hi) load(low, false);
  if (hi) load(hi, true);
}
function visualClipId(s) {
  const V = s.visuals, ep = P.ep;
  if (!V) return null;
  let id = null;
  if (ep && !P.needChoice && !P.aux) {  // P.aux: the bed / spoken question is on the audio element, its time is not the episode's
    const sf = P.scrubF;   // the bar is being dragged: the picture of the spot under the finger, not of what is still playing
    if (ep.kind !== 'live' && ep.visuals) { const t = sf != null ? sf * (audio.duration || ep.dur || 0) : (audio.currentTime || 0); const v = ep.visuals.find(x => t >= x.s && t < x.e) || ep.visuals[ep.visuals.length - 1]; id = v && v.clip; }
    else if (ep.kind === 'live') { const ls = ep.lines || []; const ln = ls[sf != null ? Math.min(ls.length - 1, Math.floor(sf * ls.length)) : P.idx]; id = ln && ln.clip; }
  }
  if (id && V.prefer && id !== 'idle' && !id.startsWith(V.prefer)) id = null;  // 有预设完整版切片的剧：之前写好的集里配的旧画面也换成预设片段轮播
  if (!id || !V.clips[id]) { const pool = (V.pool || []).filter(x => V.clips[x]); if (!pool.length) return null; id = pool[Math.floor(Date.now() / 7000) % pool.length]; }
  return id;
}
function renderVisual(force) {
  const s = byId(P.id); if (!s || !s.visuals) return;
  const a = $('#pl-vid'), b = $('#pl-vid2'); if (!a || !b) return;
  if (NARRA) {
    // 11-11 (5): a still picture that fits what is being told right now; no moving clips
    stillIndex(s.id); hdIndex(s.id);
    if (!STX[s.id].ready || (HD_IDS.has(s.id) && !(HDX[s.id] || {}).ready)) return;   // two tiny lists; the cover is up meanwhile
    const sid = stillClip(s); if (!sid) return;
    a.parentNode.classList.toggle('nr-fast', Date.now() < (VS.fastUntil || 0));   // right after a drag / jump the change is quick, not a slow dissolve
    const pic = stillOf(s, sid);
    showPoster(pic.low, pic.hi); warmStills(s);
    return;
  }
  const id = visualClipId(s); if (!id) return;
  const url = s.visuals.clips[id];
  if (url === VS.url) {
    const f = a.dataset.clip === url ? a : (b.dataset.clip === url ? b : null);
    // back on a clip whose picture had stepped in front of it (jump away and back): bring the loaded clip up again
    if (f && !f.classList.contains('on') && f.readyState >= 3) { f.play().catch(() => {}); f.classList.add('on'); (f === a ? b : a).classList.remove('on'); }
    else if (force && f && f.classList.contains('on') && f.paused) f.play().catch(() => {});
    return;
  }
  VS.url = url;
  const tok = ++VS.tok;
  const front = a.classList.contains('on') ? a : (b.classList.contains('on') ? b : null), back = front === a ? b : a;
  const br = clipBlob(url);
  back.oncanplay = null; back.onplaying = null;
  const start = (src) => {
    if (VS.tok !== tok) return;
    back.src = src; back.dataset.clip = url;
    // phones often don't load a hidden video until play() is called: start it now (muted) and fade it in on its first frame
    const show = () => {
      back.oncanplay = null; back.onplaying = null;
      if (VS.tok !== tok) return;
      back.classList.add('on');
      if (front && front !== back) { front.classList.remove('on'); setTimeout(() => { if (!front.classList.contains('on')) front.pause(); }, 700); }
    };
    back.onplaying = show;
    back.oncanplay = () => { back.play().then(show).catch(show); };
    try { back.load(); back.play().catch(() => {}); } catch (e) { /* ignore */ }
  };
  start((br && br.obj) || absUrl(url));
  warmVisuals(s);
}
setInterval(() => { const pl = $('#player'); if (pl && pl.dataset.built && P.id) renderVisual(); }, NARRA ? 400 : 1000);
/* a jump (drag released, ±10 s, a tapped line, lock-screen seek): the background of the new spot at once, with a quick change */
audio.addEventListener('seeking', () => { VS.fastUntil = Date.now() + 1500; if (P.ep && !P.aux && playerOpen) renderVisual(); });
let lastSubKey = '';
function updatePlayerUI(force) {
  renderMiniLight();
  const el = $('#player'); if (!el.dataset.built) return;
  const s = byId(P.id); if (!s) return;
  const ep = P.ep;
  const playing = isPlaying();
  $('#pl-title').textContent = s.title;
  $('#pl-ep').textContent = P.gen ? `Episode ${P.gen.n} · Writing your episode…` : P.loading ? 'Episode 1 · Preparing…' : ep ? `Episode ${ep.n} · ${ep.title || ''}` : '';
  const saved = S.saved.indexOf(s.id) >= 0;
  const sv = $('#pl-save'); sv.innerHTML = ic(saved ? 'check' : 'plus'); sv.style.color = saved ? 'var(--b)' : '';
  const badge = $('#pl-badge');
  if (ep && ep.kind === 'live' && !P.gen) { badge.hidden = false; badge.innerHTML = P.jobDone ? `${ic('spark', 'xs')} WRITTEN FOR YOU` : '<span class="dot"></span> LIVE · WRITING'; }
  else badge.hidden = true;
  const pb = $('#pl-play');
  pb.innerHTML = ic(P.needChoice ? 'spark' : playing ? 'pause' : 'play');
  pb.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  pb.classList.toggle('busy', !!(P.loading || P.gen || (P.waiting && P.want)));
  $('#pl-speed').querySelector('b').textContent = `${S.speed}x`;
  updateSleepTool();
  $('[data-act="prev"]', el).disabled = !ep;
  $('[data-act="next"]', el).disabled = !ep || !!P.gen;

  // generating card / up-next card
  const gen = $('#pl-gen'), sub = $('#pl-sub');
  if (NARRA) el.classList.toggle('nr-ask', !!P.needChoice);   // choice point: the transport steps aside, the lyric stream (question, A, B, answer box) gets the room
  if (NARRA && !P.upNext) { gen.hidden = true; gen.dataset.k = ''; sub.hidden = true; renderVisual(); renderLyrics(force); }  // narra: writing / loading states are lines of the lyric stream
  else if (P.gen || P.loading || P.upNext) {
    gen.hidden = false; sub.hidden = true;
    if (NARRA) renderLyrics(force);
    const key = P.gen ? `gen${P.gen.n}:${P.gen.status}` : P.loading ? 'load' : `up${P.upNext.ep.n}:${P.upNext.left}`;
    if (gen.dataset.k !== key) {
      gen.dataset.k = key;
      if (P.upNext) {
        const off = 160 - (160 * (5 - P.upNext.left)) / 5;
        gen.innerHTML = `<span class="ring count"><svg viewBox="0 0 58 58"><circle class="trk" cx="29" cy="29" r="25.5"/><circle class="arc" cx="29" cy="29" r="25.5" style="stroke-dashoffset:${off}"/></svg><img src="${esc(coverOf(s))}" alt=""></span>
          <span class="gt"><small>UP NEXT IN ${P.upNext.left}</small><b>Ep ${P.upNext.ep.n} · ${esc(P.upNext.ep.title || '')}</b>
          <span class="gbtns"><button class="btn btn-grad btn-sm" data-act="upnext-now">Play now</button><button class="btn btn-ghost btn-sm" data-act="upnext-cancel">Cancel</button></span></span>`;
      } else {
        const n = P.gen ? P.gen.n : 1;
        const status = P.gen ? ({ writing: 'Writing your episode…', voicing: 'Voicing the first lines…', done: 'Starting…' }[P.gen.status] || 'Writing your episode…') : (P.loadStatus === 'voicing' ? 'Voicing Episode 1…' : 'Preparing Episode 1…');
        const said = P.gen ? (P.gen.via === 'auto' ? 'The story carries on by itself…' : P.gen.via === 'silence' || !P.gen.text ? 'You stayed silent.' : `You said “${P.gen.text}”`) : 'First listen — this takes a few seconds';
        gen.innerHTML = `<span class="ring"><svg viewBox="0 0 58 58"><circle class="trk" cx="29" cy="29" r="25.5"/><circle class="arc" cx="29" cy="29" r="25.5"/></svg><img src="${esc(coverOf(s))}" alt=""></span>
          <span class="gt"><small>EPISODE ${n}${P.gen ? ' · WRITTEN LIVE' : ''}</small><b>${status}</b>${waveBars(22)}<span class="said">${esc(said)}</span></span>`;
      }
    }
  } else {
    gen.hidden = true; gen.dataset.k = ''; sub.hidden = false;
    renderSubtitle(force);
  }
  // progress mode
  const live = ep && ep.kind === 'live';
  const segs = $('#pl-segs');
  segs.hidden = !live;
  $('#pl-fill').style.display = live ? 'none' : '';
  $('#pl-knob').style.display = live ? 'none' : '';
  if (live) {
    const lines = ep.lines || [];
    if (segs.childElementCount !== lines.length) segs.innerHTML = lines.map(() => '<i></i>').join('');
    Array.from(segs.children).forEach((c, i) => {
      c.classList.toggle('pend', lines[i].url == null);
      c.classList.toggle('skip', lines[i].url === '');
    });
  }
  tickUI();
}
/* ---------- narra: the story as scrolling lyrics ----------
 * Items: her answer that led here → every line of the episode → at a choice point the question + the two choices →
 * while the next episode is written: what she said + the writing status. Earlier lines are dim, the current one is bright
 * and fills in word by word as it is spoken (timing is linear inside the line), the next two are faint. Tap a line to jump to it. */
const LY = { sig: '', cur: -2, it: [], nodes: [], tok: null, placed: 0 };
function lyricState() {
  const ep = P.ep, s = byId(P.id), ss = getSess(P.id);
  const it = []; let cur = -1;
  const add = (o) => it.push(o) - 1;
  if (!ep || P.loading) {
    if (s && s.hook) cur = add({ k: 'line', who: 'NARR', text: s.hook, i: -1 });
    if (P.loading || !s) cur = add({ k: 'sys', text: P.loadStatus === 'voicing' ? 'Voicing Episode 1…' : 'Preparing Episode 1…' });   // only while it really is loading (not after a failed start)
    return { it, cur };
  }
  const said = ss && ss.chosen ? ss.chosen[ep.n - 1] : '';
  if (ep.n > 1 && said) add({ k: 'you', text: said });
  if (ep.kind === 'live') {
    const lines = ep.lines || [], n = lines.length, at = [];
    lines.forEach((l, i) => { at[i] = add({ k: 'line', who: l.who, text: cleanText(l.text), i, pend: l.url == null }); });
    const unvoiced = P.idx < n && lines[P.idx].url == null;          // written, its voice is still on the way
    const li = P.idx >= n ? n - 1 : unvoiced ? P.idx - 1 : P.idx;
    cur = li >= 0 ? at[li] : -1;
    if (!P.jobDone && !P.needChoice) { const w = add({ k: 'sys', text: 'writing next lines…' }); if (cur < 0) cur = w; }
  } else {
    const cues = ep.cues || [], base = it.length, t = audio.currentTime || 0;
    cues.forEach((c, i) => add({ k: 'line', who: c.who, text: cleanText(c.text), i }));
    if (!cues.length) cur = add({ k: 'line', who: 'NARR', text: s ? s.hook : '', i: -1 });
    else {
      let k = cues.findIndex((x) => t >= x.s && t < x.e);
      if (k < 0) { for (let i = cues.length - 1; i >= 0; i--) if (cues[i].s <= t) { k = i; break; } }
      cur = base + Math.max(0, k);
    }
  }
  if (P.needChoice || P.gen) {
    const q = add({ k: 'q', text: ep.prompt || (LANG === 'zh' ? '你怎么做？' : 'What do you do?') });
    if (P.needChoice) { cur = q; (ep.choices || []).slice(0, 2).forEach((c, i) => add({ k: 'opt', i, text: c })); add({ k: 'in', text: '' }); add({ k: 'hint', text: '' }); }
    else {
      const g = P.gen;
      if (g.via === 'auto') add({ k: 'note', text: 'The story carries on by itself…' });
      else if (g.via === 'silence' || !g.text) add({ k: 'you', text: '(stayed silent)', ui: true });
      else add({ k: 'you', text: g.text });
      cur = add({ k: 'sys', text: { writing: 'Writing your episode…', voicing: 'Voicing the first lines…', done: 'Starting…' }[g.status] || 'Writing your episode…' });
    }
  }
  return { it, cur };
}
function lyHtml(o, j) {
  const t = `<span class="ll-t" ${o.ui ? '' : 'translate="no"'}>${esc(o.text)}</span>`;
  if (o.k === 'line') {
    const nr = !o.who || o.who === 'NARR';
    return `<div class="ll ${nr ? 'narr' : 'say'}${o.pend ? ' pend' : ''}" ${o.i >= 0 ? `data-act="ly-seek" data-j="${j}"` : ''}>${nr ? '' : `<span class="ll-who" translate="no">${esc(o.who)}</span>`}${t}</div>`;
  }
  if (o.k === 'you') return `<div class="ll you"><span class="ll-who">You</span>${t}</div>`;
  if (o.k === 'q') return `<div class="ll q"><span class="ll-who">Your move</span>${t}</div>`;
  if (o.k === 'opt') return `<button class="ll opt" data-act="choose" data-i="${o.i}"><i>${'AB'[o.i]}</i>${t}</button>`;
  if (o.k === 'in') return `<div class="ll inp" id="nr-inbox">${VOICE_OK ? `<button class="in-mic" data-act="nr-mic" aria-label="Speak your answer">${ic('mic')}</button>` : `<span class="in-mic">${ic('pen')}</span>`}<div class="in-f"><div class="in-ghost ph" id="nr-ghost"></div><textarea id="nr-in" rows="1" maxlength="200" enterkeyhint="send" autocomplete="off" autocapitalize="sentences" aria-label="Your answer"></textarea></div><span class="in-ring" id="nr-ring" hidden></span><button class="in-send" id="nr-send" data-act="nr-send" aria-label="Send" hidden>${ic('send')}</button></div>`;
  if (o.k === 'hint') return '<div class="ll hint" id="nr-hint" hidden></div>';
  if (o.k === 'note') return `<div class="ll note"><span class="ll-t">${esc(o.text)}</span></div>`;
  return `<div class="ll sys">${waveBars(7)}<span class="ll-t">${esc(o.text)}</span></div>`;
}
function renderLyrics(force) {
  const box = $('#nr-lyr'), roll = $('#nr-roll'); if (!box || !roll) return;
  const s = byId(P.id);
  const { it, cur } = lyricState();
  const sig = [P.id, P.ep ? P.ep.n : 0, P.needChoice ? 'c' : '', P.gen ? 'g' + P.gen.status : ''].join('|') + '|' + it.map((o) => o.k[0] + (o.pend ? 'p' : '') + o.text.length).join(',');
  if ((force && !(P.needChoice && sig === LY.sig)) || sig !== LY.sig) {   // at a choice point the answer box holds what she is typing: never rebuilt for a plain refresh
    LY.sig = sig; LY.cur = -2; LY.tok = null;
    box.style.setProperty('--accent-l', s && s.accent ? `color-mix(in srgb, ${s.accent} 58%, #fff)` : 'var(--b)');
    roll.innerHTML = it.map(lyHtml).join('');
    LY.nodes = Array.from(roll.children);
    bindAsk();
  }
  LY.it = it;
  if (cur !== LY.cur) {
    const old = LY.nodes[LY.cur], oi = old && it[LY.cur];
    if (old && oi && LY.tok) { const t = $('.ll-t', old); if (t) t.textContent = oi.text; }
    LY.tok = null; LY.cur = cur;
    LY.nodes.forEach((n, j) => { n.classList.toggle('cur', j === cur); n.classList.toggle('past', j < cur); n.classList.toggle('far', j > cur + 2 && !(it[cur] && it[cur].k === 'q')); });
    const o = it[cur], node = LY.nodes[cur];
    if (o && node && o.k === 'line' && !o.pend && o.i >= 0) {   // split the current line so it can fill in as it is spoken
      const parts = o.text.match(/[㐀-鿿豈-﫿぀-ヿ]|[^\s㐀-鿿豈-﫿぀-ヿ]+\s*|\s+/g) || [o.text];
      let n = 0; const ends = parts.map((x) => (n += x.trim().length || 0));
      const t = $('.ll-t', node);
      if (t && n) { t.innerHTML = parts.map((x) => `<span class="w">${esc(x)}</span>`).join(''); LY.tok = { els: Array.from(t.children), ends, total: n, on: -1 }; }
    }
    placeLyrics();
  }
  karaoke();
}
function placeLyrics() {
  const box = $('#nr-lyr'), roll = $('#nr-roll'), n = LY.nodes[LY.cur]; if (!box || !roll || !n) return;
  LY.placed = Date.now();
  const H = box.clientHeight, room = H - n.offsetHeight;
  let extra = 0;   // a question keeps its two choices in view
  if (LY.it[LY.cur] && LY.it[LY.cur].k === 'q') for (let j = LY.cur + 1; j < LY.nodes.length; j++) extra += LY.nodes[j].offsetHeight + 8;
  const lastOne = !LY.nodes.slice(LY.cur + 1).some((x) => !x.classList.contains('far'));   // nothing after it (e.g. "Writing your episode…"): sit lower, more of what came before stays in view
  let top = Math.max(H * 0.06, Math.min(H * (lastOne ? 0.56 : 0.42), room - extra - H * 0.08));
  if (extra && top + n.offsetHeight + extra > H - 6) top = H - 6 - n.offsetHeight - extra;   // a long question on a short screen: the answer box stays in view, the question slides up   // the current line sits a little below the middle-top: two earlier lines stay readable above it
  roll.style.transform = `translateY(${Math.round(top - n.offsetTop)}px)`;
}
function lyProgress() {
  const o = LY.it[LY.cur], ep = P.ep; if (!o || o.k !== 'line' || !ep) return 0;
  if (P.needChoice || P.gen) return 1;
  if (P.aux) return 0;
  if (ep.kind === 'live') return !P.waiting && audio.duration ? clamp((audio.currentTime / audio.duration) * 1.04, 0, 1) : 0;
  const c = (ep.cues || [])[o.i]; if (!c) return 0;
  return clamp((((audio.currentTime || 0) - c.s) / Math.max(0.4, c.e - c.s)) * 1.08, 0, 1);
}
function karaoke() {
  const k = LY.tok; if (!k) return;
  const done = lyProgress() * k.total;
  let on = -1; for (let i = 0; i < k.ends.length; i++) { if (k.ends[i] <= done + 0.5) on = i; else break; }
  if (on === k.on) return;
  k.els.forEach((e, i) => e.classList.toggle('on', i <= on)); k.on = on;
}
function lySeek(j) {
  const o = (LY.it || [])[j], ep = P.ep;
  if (!o || o.k !== 'line' || !ep || P.needChoice || P.gen || P.loading || j === LY.cur) return;
  VS.fastUntil = Date.now() + 1500;
  if (ep.kind === 'live') { const l = (ep.lines || [])[o.i]; if (l && l.url) { P.idx = o.i; liveAdvance(); renderVisual(); } return; }
  const c = (ep.cues || [])[o.i]; if (!c) return;
  try { audio.currentTime = c.s + 0.02; } catch (e) { /* ignore */ }
  tickUI();
}
if (NARRA) {
  setInterval(() => {
    if (!playerOpen) return;
    if (LY.tok && isPlaying()) karaoke();
    if (Date.now() - LY.placed > 1500) placeLyrics();   // fonts / the address bar change heights after the first paint
  }, 110);
  window.addEventListener('resize', () => placeLyrics());
}
/** narra header: the series title; scrolls slowly when it doesn't fit */
function fitTitle(title) {
  const b = $('#pl-series'); if (!b || b.dataset.t === title) return;
  b.dataset.t = title; b.classList.remove('mq'); b.textContent = title;
  requestAnimationFrame(() => {
    if (b.dataset.t !== title || b.scrollWidth <= b.clientWidth + 2) return;
    b.classList.add('mq'); b.innerHTML = `<span>${esc(title)}<i></i>${esc(title)}<i></i></span>`;
  });
}
const miniSig = () => [P.id, P.ep && P.ep.n, P.ep && P.ep.title, !!P.gen, P.gen && P.gen.n, P.loading, P.needChoice, isPlaying()].join('|');
function renderMiniLight() {
  const m = $('#mini');
  if (m.dataset.sig !== miniSig()) renderMini();
}
function renderSubtitle(force) {
  renderVisual();
  if (NARRA) { renderLyrics(force); return; }
  const sub = $('#pl-sub'); const ep = P.ep;
  if (!ep) { sub.innerHTML = ''; return; }
  const s = byId(P.id);
  let who = '', text = '', key = '';
  if (P.needChoice) {
    key = 'choice' + ep.n;
    if (sub.dataset.k === key && !force) return;
    sub.dataset.k = key;
    sub.innerHTML = `<div class="yourmove"><div><b>${ep.n >= 1 ? `Ep ${ep.n} ended — your move` : ''}</b><span>Ep ${ep.n + 1} will be written from your answer</span></div><button class="btn btn-grad btn-sm" data-act="open-choice">Choose</button></div>`;
    return;
  }
  if (ep.kind === 'live') {
    if (P.waiting && P.want && P.idx < (ep.lines || []).length && (ep.lines[P.idx] || {}).url == null) {
      key = 'wait' + P.idx;
      if (sub.dataset.k === key && !force) return;
      sub.dataset.k = key;
      const prev = ep.lines[P.idx - 1];
      sub.innerHTML = `${prev ? `<span class="who">${prev.who === 'NARR' ? '' : esc(prev.who)}</span><p class="txt ${prev.who === 'NARR' ? 'narr' : ''}" style="opacity:.45">${esc(prev.text)}</p>` : ''}<div class="wait" style="margin-top:${prev ? 8 : 0}px">${waveBars(8)} writing next lines…</div>`;
      return;
    }
    if (P.waiting && P.want && P.idx >= (ep.lines || []).length && !P.jobDone) {
      key = 'waitend';
      if (sub.dataset.k === key && !force) return;
      sub.dataset.k = key;
      sub.innerHTML = `<div class="wait">${waveBars(8)} writing next lines…</div>`;
      return;
    }
    const ln = (ep.lines || [])[Math.min(P.idx, (ep.lines || []).length - 1)];
    if (ln) { who = ln.who; text = ln.text; key = 'l' + ep.n + ':' + P.idx; }
  } else {
    const t = audio.currentTime || 0;
    const cues = ep.cues || [];
    let c = cues.find((x) => t >= x.s && t < x.e);
    if (!c) { for (let i = cues.length - 1; i >= 0; i--) if (cues[i].s <= t) { c = cues[i]; break; } }
    if (!c) c = cues[0];
    if (c) { who = c.who; text = c.text; key = 'c' + ep.n + ':' + cues.indexOf(c); }
  }
  if (!key) { key = 'none'; text = s ? s.hook : ''; who = 'NARR'; }
  if (sub.dataset.k === key && !force) return;
  sub.dataset.k = key;
  const narr = !who || who === 'NARR';
  sub.style.setProperty('--accent-l', (s && s.accent) ? `color-mix(in srgb, ${s.accent} 70%, #fff)` : 'var(--b)');
  sub.innerHTML = `${narr ? '' : `<span class="who">${esc(who)}</span>`}<p class="txt fade ${narr ? 'narr' : ''}">${esc(cleanText(text))}</p>`;
}
function tickUI() {
  const ep = P.ep;
  const f = P.needChoice ? 1 : epFraction();
  const mb = $('#mini-bar'); if (mb) mb.style.width = (f * 100).toFixed(2) + '%';
  if (!playerOpen && !$('#player').classList.contains('on')) return;
  if (P.scrubF != null) return;
  if (!ep || P.gen || P.loading) { $('#pl-el').textContent = '0:00'; $('#pl-tot').innerHTML = P.gen ? '<span class="live"><span class="dots-pulse"><i></i><i></i><i></i></span> LIVE</span>' : '--:--'; $('#pl-fill').style.width = '0%'; $('#pl-knob').style.left = '0%'; return; }
  if (ep.kind !== 'live') {
    const d = audio.duration || ep.dur || 0, t = P.needChoice ? d : audio.currentTime || 0;
    $('#pl-fill').style.width = (d ? (t / d) * 100 : 0) + '%';
    $('#pl-knob').style.left = (d ? (t / d) * 100 : 0) + '%';
    $('#pl-el').textContent = fmtTime(t);
    $('#pl-tot').textContent = fmtTime(d);
    renderSubtitle();
  } else {
    const lines = ep.lines || [];
    const segs = $('#pl-segs');
    const frac = audio.duration && !P.waiting ? clamp(audio.currentTime / audio.duration, 0, 1) : 0;
    Array.from(segs.children).forEach((c, i) => {
      const p = P.needChoice ? 1 : i < P.idx ? 1 : i === P.idx ? frac : 0;
      c.style.setProperty('--p', p.toFixed(3));
    });
    const el = P.needChoice ? Object.values(ep.durs || {}).reduce((a, b) => a + b, 0) : P.lineStart + (P.waiting ? 0 : audio.currentTime || 0);
    $('#pl-el').textContent = fmtTime(el);
    const allKnown = P.jobDone && lines.every((l, i) => l.url === '' || (ep.durs && ep.durs[i]));
    if (allKnown) $('#pl-tot').textContent = fmtTime(Object.values(ep.durs).reduce((a, b) => a + b, 0));
    else $('#pl-tot').innerHTML = P.jobDone
      ? `Line ${Math.min(P.idx + 1, lines.length)} of ${lines.length}`
      : `<span class="live"><span class="dots-pulse"><i></i><i></i><i></i></span> Line ${Math.min(P.idx + 1, Math.max(1, lines.length))} of ${lines.length || '…'}</span>`;
    renderSubtitle();
  }
}
function bindScrub(bar) {
  let drag = false;
  const at = (e) => { const r = bar.getBoundingClientRect(); return clamp((e.clientX - r.left) / r.width, 0, 1); };
  const preview = (f) => {  // move the knob and the time only; seeking on every pointermove made the audio stutter
    const ep = P.ep; if (!ep || !P.cur || P.needChoice || P.gen) return;
    P.scrubF = f;
    $('#pl-fill').style.width = (f * 100) + '%'; $('#pl-knob').style.left = (f * 100) + '%';
    if (ep.kind !== 'live') { const d = audio.duration || ep.dur || 0; $('#pl-el').textContent = fmtTime(f * d); }
    VS.fastUntil = Date.now() + 1500; renderVisual();   // the background follows the finger
  };
  const apply = (f) => {
    P.scrubF = null; VS.fastUntil = Date.now() + 1500;
    const ep = P.ep; if (!ep || !P.cur || P.needChoice || P.gen) return;
    if (ep.kind !== 'live') { const d = audio.duration || ep.dur; if (d) { audio.currentTime = f * d; tickUI(); } return; }
    const lines = ep.lines || [];
    const i = Math.min(lines.length - 1, Math.floor(f * lines.length));
    if (i !== P.idx && lines[i] && lines[i].url) { P.idx = i; liveAdvance(); }
    renderVisual();
  };
  bar.addEventListener('pointerdown', (e) => { drag = true; try { bar.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ } preview(at(e)); });
  bar.addEventListener('pointermove', (e) => { if (drag) preview(at(e)); });
  bar.addEventListener('pointerup', (e) => { if (drag) { drag = false; apply(at(e)); } });
  bar.addEventListener('pointercancel', () => { drag = false; P.scrubF = null; tickUI(); });
}
const LINE_WARM = new Map();
function warmLines(ep) {  // every line of a live episode is its own small file: preload them all so jumping around is instant
  (ep && ep.lines || []).forEach((l) => {
    if (!l.url || LINE_WARM.has(l.url)) return;
    if (blobable(l.url)) { fetchBlob(l.url); LINE_WARM.set(l.url, null); return; }
    try { const a = new Audio(); a.preload = 'auto'; a.muted = true; a.src = absUrl(l.url); a.load(); LINE_WARM.set(l.url, a); } catch (e) { /* ignore */ }
  });
  while (LINE_WARM.size > 40) { const k = LINE_WARM.keys().next().value; LINE_WARM.delete(k); }
}

function openPlayer() {
  if (playerOpen) return;
  if (location.hash !== '#/player') { playerPushed = true; location.hash = '#/player'; }
  else showPlayerUI();
}
function closePlayer() {
  if (playerPushed) { playerPushed = false; history.back(); }
  else { location.hash = baseHash || '#/home'; }
}
function showPlayerUI() {
  if (!P.id) { location.replace('#/home'); return; }
  playerOpen = true;
  { const pid = P.id; setTimeout(() => { if (playerOpen && P.id === pid) { warmRings(); prepareCall(pid); } }, 8000); }
  renderPlayer();
  const el = $('#player');
  el.classList.add('on'); el.setAttribute('aria-hidden', 'false');
  $('#mini').style.visibility = 'hidden';
  updatePlayerUI(true);
}
function hidePlayerUI() {
  playerOpen = false;
  const el = $('#player');
  el.classList.remove('on'); el.setAttribute('aria-hidden', 'true');
  $('#mini').style.visibility = '';
  renderMini();
  if (isDetailOpen()) renderDetailEpisodes();
}

/* =========================================================================
 * 12. Routing
 * ========================================================================= */
let baseHash = '#/home';
function route() {
  const h = location.hash.replace(/^#\/?/, '') || 'home';
  const [a, b] = h.split('/');
  if (a === 'player') { showPlayerUI(); return; }
  if (playerOpen) { hidePlayerUI(); playerPushed = false; }
  if (sheetStack.length) closeAllSheets();
  baseHash = location.hash || '#/home';
  if (a === 'series' && b) { showDetail(decodeURIComponent(b)); return; }
  hideDetail();
  const tab = TABS.some(([k]) => k === a) ? a : 'home';
  showTab(tab);
}
function showTab(tab) {
  curTab = tab;
  $$('.view').forEach((v) => v.classList.toggle('on', v.id === 'v-' + tab));
  renderTabbar();
  if (tab === 'home') renderHome();
  else if (tab === 'explore') renderExplore();
  else if (tab === 'library') renderLibrary();
  else if (tab === 'rewards') renderRewards();
}
function go(to) {
  if (to === curTab && !isDetailOpen()) { const v = $('#v-' + to); if (v) v.scrollTo({ top: 0, behavior: reduceMotion() ? 'auto' : 'smooth' }); return; }
  location.hash = '#/' + to;
}
let navCount = 0;
window.addEventListener('hashchange', () => { navCount++; route(); });

/* =========================================================================
 * 13. Event delegation
 * ========================================================================= */
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.disabled) return;
  const act = el.dataset.act, id = el.dataset.id;
  switch (act) {
    case 'go': go(el.dataset.to); break;
    case 'open': e.stopPropagation(); location.hash = '#/series/' + encodeURIComponent(id); break;
    case 'back': if (navCount > 0) history.back(); else location.hash = '#/' + curTab; break;
    case 'play-series': e.stopPropagation(); startOrContinue(id); break;
    case 'continue': startOrContinue(id); break;
    case 'restart': closeAllSheets(); newSession(id || P.id); break;
    case 'save': case 'pl-save': {
      const sid = id || P.id; const i = S.saved.indexOf(sid);
      if (i >= 0) { S.saved.splice(i, 1); toast('Removed from Library'); } else { S.saved.unshift(sid); toast(`${ic('check', 'sm')} Added to Library`); }
      save(); if (isDetailOpen()) renderDetail(); updatePlayerUI(); break;
    }
    case 'share': shareSeries(id || P.id); break;
    case 'syn': synOpen = !synOpen; renderDetail(); break;
    case 'dt-tab': detailTab = el.dataset.t; $$('.tabs button').forEach((b) => { b.classList.toggle('on', b.dataset.t === detailTab); b.setAttribute('aria-selected', b.dataset.t === detailTab); }); renderDetailPane(); break;
    case 'ep': onEpisodeTap(id, +el.dataset.n, el.dataset.k); break;
    case 'genre': exGenre = el.dataset.g; exQuery = ''; go('explore'); break;
    case 'ex-genre': exGenre = exGenre === el.dataset.g ? '' : el.dataset.g; renderExplore(); break;
    case 'ex-clear': exGenre = ''; exQuery = ''; renderExplore(); break;
    case 'lib-tab': libTab = el.dataset.t; renderLibrary(); break;
    case 'lib-rm': delete S.progress[el.dataset.k]; save(); renderLibrary(); toast('Removed from Listening'); break;
    case 'unsave': S.saved = S.saved.filter((x) => x !== id); save(); renderLibrary(); break;
    case 'hist-rm': S.hist = S.hist.filter((h) => String(h.at) !== el.dataset.at); save(); renderLibrary(); break;
    case 'hist-play': { const ss = getSess(id); if (ss && ss.eps.some((x) => x.n === +el.dataset.n)) playStored(id, +el.dataset.n); else location.hash = '#/series/' + id; break; }
    case 'checkin': doCheckin(); break;
    case 'claim': claimTask(el.dataset.k); break;
    case 'store': openStore(); break;
    case 'buy': { const p = PACKS[+el.dataset.i]; const bonus = parseInt((p.bonus || '0').replace(/\D/g, ''), 10) || 0; addCoins(p.n + bonus, `Coin pack ${p.n}${bonus ? ' + ' + bonus : ''} (test)`); toast(`${coinIc('sm')} +${p.n + bonus} test coins`); break; }
    case 'vip': S.vip = !S.vip; save(); toast(S.vip ? `${ic('crown', 'sm')} VIP on — every episode free` : 'VIP off'); refreshSheets(); refreshAfterWallet(); break;
    case 'auto-unlock': S.autoUnlock = !S.autoUnlock; save(); refreshSheets(); break;
    case 'profile': openProfile(); break;
    case 'lang': if (el.dataset.l !== LANG) { save(true); location.href = langUrl(el.dataset.l); } break;
    case 'reset': if (window.confirm('Reset all local data (coins, progress, library, name)?')) { ['ua.state', 'ua.sess'].forEach(store.del); clearTimeout(saveT); window.removeEventListener('pagehide', save); S = DEF(); SESS = {}; location.hash = ''; location.reload(); } break;
    case 'scrim': { const t = topSheet(); if (t && !t.sticky) closeSheet(t); break; }
    case 'sheet-close': closeSheet(); break;
    case 'open-player': openPlayer(); break;
    case 'close-player': closePlayer(); break;
    case 'toggle': togglePlay(); renderMini(); break;
    case 'open-choice': if (!playerOpen) openPlayer(); openChoiceSheet(); break;
    case 'back10': skip(-10); break;
    case 'fwd10': skip(10); break;
    case 'prev': prevEpisode(); break;
    case 'next': nextEpisode(); break;
    case 'speed': cycleSpeed(); break;
    case 'sleep-sheet': openSleepSheet(); break;
    case 'sleep': {
      const m = +el.dataset.m;
      S.sleep = m === 0 ? null : m === -1 ? { eoe: true } : { until: Date.now() + m * 60000 };
      save(); closeSheet(); updateSleepTool();
      toast(m === 0 ? 'Sleep timer off' : m === -1 ? `${ic('moon', 'sm')} Stops at end of episode` : `${ic('moon', 'sm')} Pausing in ${m} min`);
      break;
    }
    case 'pl-eps': openEpisodesSheet(); break;
    case 'choose': { const c = (P.ep && P.ep.choices || [])[+el.dataset.i]; if (c) submitChoice(c, 'option'); break; }
    case 'silent': submitChoice('', 'silence'); break;
    case 'mic': toggleMic(el); break;
    case 'mode-sheet': openModeSheet(); break;
    case 'set-mode': setMode(el.dataset.m); break;
    case 'talk': openTalkSheet(); break;
    case 'talk-mic': if (VOICE_OK) { if (talkRec) talkRec.stop(); else talkListen(); } break;
    case 'hf-again': hfListen(); break;
    case 'nr-mic': { const i = $('#nr-in'); if (i) { i.blur(); i.value = ''; } if (VOICE_OK && P.needChoice) { holdForHer(); hfListen(); } break; }
    case 'nr-send': askSend(); break;
    case 'hf-stop': if (HF.rec) HF.rec.stop(); break;
    case 'ch-wait': holdForHer(); break;
    case 'ly-seek': lySeek(+el.dataset.j); break;
    case 'me-chip': { const t = $('#pf-me'); if (t) { t.value = (t.value ? t.value.trim() + ' ' : '') + el.dataset.t; t.focus(); } break; }
    case 'ul-coins': {
      const t = topSheet(); if (!t || t.kind !== 'unlock') break;
      const price = t.price || PRICE;
      if (S.coins < price) { openStore(); break; }
      addCoins(-price, t.call ? `Call ${shortName(callerOf(byId(t.id), t.who))} · ${byId(t.id).title}` : `Unlock Ep ${t.n} · ${byId(t.id).title}`);
      finishUnlock(t, `−${price} coins`);
      break;
    }
    case 'ul-ad': { const t = topSheet(); if (!t || t.kind !== 'unlock') break; playAd(() => { S.ledger.unshift({ t: Date.now(), d: 0, l: t.call ? `Ad call · ${byId(t.id).title}` : `Ad unlock Ep ${t.n} · ${byId(t.id).title}` }); finishUnlock(t, 'thanks for watching'); }); break; }
    case 'vip-from-call': { const t = topSheet(); if (!t) break; S.vip = true; save(); toast(`${ic('crown', 'sm')} VIP on — calls and episodes free`); refreshAfterWallet(); const cb = t.onDone; closeSheet(t); if (cb) cb(); break; }
    case 'call-lead': requestCall(id); break;
    case 'call-who': { const t = topSheet(); const o = (t && t.opts) || {}; closeSheet(); requestCall(id, Object.assign({}, o, { who: el.dataset.who })); break; }
    case 'pl-call': if (P.id) requestCall(P.id, { sid: (getSess(P.id) || {}).sid }); break;
    case 'call-accept': acceptCall(); break;
    case 'call-decline': declineCall(); break;
    case 'call-hangup': hangUp(); break;
    case 'call-choice': { const c = C && C.choices[+el.dataset.i]; if (c) sendCallTurn(c, 'option'); break; }
    case 'call-silent': sendCallTurn('', 'silence'); break;
    case 'call-mute': toggleCallMute(); break;
    case 'open-safari': {
      const u = location.origin + location.pathname + '?k=' + encodeURIComponent(TOKEN) + '&lang=' + LANG + (TTS !== 'v4' ? '&tts=' + TTS : '') + (NARRA ? '&ui=narra' : '');
      const done = () => toast(tz('Link copied — open Safari and paste it', '链接已复制，打开 Safari 粘贴到地址栏'));
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(u).then(done).catch(() => window.prompt(tz('Copy this link into Safari', '复制这个链接到 Safari 打开'), u));
      else window.prompt(tz('Copy this link into Safari', '复制这个链接到 Safari 打开'), u);
      break;
    }
    case 'call-speaker': toggleCallSpeaker(); break;
    case 'call-speed': cycleCallSpeed(); break;
    case 'call-resume': if (C) { C.blocked = false; callAudio.play().catch(() => {}); renderCallUI(true); } break;
    case 'call-close': closeCallScreen(); break;
    case 'call-again': { const c0 = C; closeCallScreen(); if (c0) requestCall(c0.id, { who: c0.who, sid: c0.sid }); break; }
    case 'call-tr': openTranscriptView(el.dataset.rid); break;
    case 'call-live-tr': if (C && C.rec) openTranscriptView(C.rec.rid); break;
    case 'go-calls': {
      closeCallScreen(); closeAllSheets(); libTab = 'calls';
      const toLib = () => { if (location.hash === '#/library') { hideDetail(); showTab('library'); } else location.hash = '#/library'; };
      if (playerOpen) { closePlayer(); setTimeout(toLib, 380); } else toLib();
      break;
    }
    case 'series-calls': openSeriesCalls(id); break;
    case 'call-del': deleteCallRec(el.dataset.rid); break;
    case 'calls-clear': clearAllCalls(); break;
    case 'confirm-ok': { const t = topSheet(); if (t && t.kind === 'confirm') { const f = t.onOk; closeSheet(t); if (f) f(); } break; }
    case 'tr-close': closeTranscriptView(); break;
    case 'tr-line': trToggleLine(el.dataset.k); break;
    case 'tr-whole': trToggleWhole(); break;
    case 'tr-speed': cycleTrSpeed(); break;
    case 'tr-del': if (TR) { TR.confirmDel = true; renderTranscriptView(); } break;
    case 'tr-del-cancel': if (TR) { TR.confirmDel = false; renderTranscriptView(); } break;
    case 'tr-del-ok': if (TR) deleteCallRec(TR.rid); break;
    case 'call-back': closeAllSheets(); if (TR) closeTranscriptView(); if (C && !callActive()) closeCallScreen(); requestCall(id, { who: el.dataset.who }); break;
    case 'upnext-now': if (P.upNext) { const e2 = P.upNext.ep; cancelUpNext(); playEpisode(P.id, e2); } break;
    case 'upnext-cancel': cancelUpNext(); updatePlayerUI(); break;
    case 'ob-next': obNext(el.dataset.skip === '1'); break;
    case 'ob-genre': { const g = el.dataset.g; const i = obGenres.indexOf(g); if (i >= 0) obGenres.splice(i, 1); else obGenres.push(g); el.classList.toggle('on'); break; }
    default: break;
  }
});
document.addEventListener('keydown', (e) => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.hero-slide')) { e.preventDefault(); e.target.click(); }
  if (e.key === 'Escape' && sheetStack.length) closeSheet();
  else if (e.key === 'Escape' && TR) closeTranscriptView();
});
document.addEventListener('submit', (e) => {
  const f = e.target.closest('[data-form]'); if (!f) return;
  e.preventDefault();
  if (f.dataset.form === 'name') {
    const v = ($('#pf-name').value || '').trim().slice(0, 24);
    S.name = v; save(); toast(v ? `They'll call you ${esc(v)}` : 'Name cleared');
    refreshSheets(); if (curTab === 'home') renderHome();
  } else if (f.dataset.form === 'search') {
    const q = $('#ex-q'); if (q) q.blur();
  } else if (f.dataset.form === 'call') {
    const t = (($('#cl-text') || {}).value || '').trim(); if (t) sendCallTurn(t, 'free');
  } else if (f.dataset.form === 'me') {
    S.me = ((($('#pf-me') || {}).value) || '').trim().slice(0, 400); save();
    toast(S.me ? `${ic('spark', 'sm')} Your next episodes and calls will be written around you` : 'Cleared');
  } else if (f.dataset.form === 'wish') {
    const t = ((($('#tk-text') || {}).value) || '').trim(); if (t) sendWish(t);
  } else if (f.dataset.form === 'ob-name') {
    obNext();
  }
});

function onEpisodeTap(id, n, kind) {
  const ss = getSess(id);
  if (kind === 'stored') {
    if (P.id === id && P.ep && P.ep.n === n && !P.needChoice) { closeAllSheets(); togglePlay(); openPlayer(); renderDetailEpisodes(); return; }
    closeAllSheets();
    playStored(id, n);
    return;
  }
  if (kind === 'start') { closeAllSheets(); newSession(id); return; }
  if (kind === 'next') {
    if (!ss) { closeAllSheets(); toast(`Play Ep 1 first — Ep ${n} is written from your choice`); newSession(id); return; }
    if (P.id === id && P.gen) { closeAllSheets(); openPlayer(); return; }
    closeAllSheets();
    startOrContinue(id);
    if (!(S.progress[skey(id)] || {}).needChoice) toast(`Finish Ep ${n - 1} and make your choice to write Ep ${n}`);
    return;
  }
  toast(`Ep ${n} is written live after your earlier choices`);
}

async function shareSeries(id) {
  const s = byId(id); if (!s) return;
  const q = new URLSearchParams(); q.set('lang', LANG); if (MOCK) q.set('mock', '1'); if (NARRA) q.set('ui', 'narra'); if (REAL_ONLY) q.set('real', '1');
  const url = `${location.origin}${location.pathname}?${q}#/series/${encodeURIComponent(id)}`;
  let ok = false;
  try {
    if (navigator.share) { await navigator.share({ title: s.title, text: s.hook, url }); ok = true; }
    else if (navigator.clipboard) { await navigator.clipboard.writeText(url); ok = true; toast(`${ic('check', 'sm')} Link copied`); }
  } catch (e) { ok = e && e.name !== 'AbortError' ? false : false; }
  if (!ok && !navigator.share) toast('Share link ready: ' + esc(url.slice(0, 40)) + '…');
  ensureToday(); S.tasks.share = 1; save();
  if (curTab === 'rewards') renderRewards();
}

function doCheckin() {
  const ci = checkinInfo(); if (ci.today) return;
  const reward = CHECKIN[ci.streak];
  S.checkin = { last: dayStr(), streak: ci.streak + 1 };
  addCoins(reward, `Daily check-in · Day ${ci.streak + 1}`);
  toast(`${coinIc('sm')} +${reward} coins · Day ${ci.streak + 1}`);
  renderRewards();
}
function claimTask(k) {
  ensureToday();
  const t = TASKS.find((x) => x.k === k); if (!t || S.tasks.claimed[k] || (S.tasks[k] || 0) < t.goal) return;
  S.tasks.claimed[k] = true;
  addCoins(t.reward, `Task · ${t.label}`);
  toast(`${coinIc('sm')} +${t.reward} coins`);
  renderRewards();
}
function refreshAfterWallet() {
  if (curTab === 'rewards') renderRewards();
  if (isDetailOpen()) renderDetail();
  refreshCoins();
}

/* =========================================================================
 * 14. Onboarding
 * ========================================================================= */
let obStep = 0, obGenres = [];
function renderOnboard() {
  const el = $('#onboard');
  el.hidden = false;
  const pick = (NARRA ? ['magnus', 'rian', 'rafael'] : ['magnus', 'reborn', 'rian']).map(byId).filter(Boolean);
  const steps = `<div class="ob-steps">${[0, 1, 2].map((i) => `<i class="${i <= obStep ? 'on' : ''}"></i>`).join('')}</div>`;
  let body = '';
  if (obStep === 0) {
    body = `
      <div class="ob-body">
        <div class="logo" style="justify-content:center;margin-top:8px">${LOGO}<span class="logo-word">${NARRA ? 'narra' : 'unscripted'}<em>.</em></span></div>
        <div class="ob-collage">${pick.map((s) => `<img src="${esc(coverOf(s))}" alt="">`).join('')}</div>
        <h1 class="ob-title">Stories that <em>listen back.</em></h1>
        <p class="ob-sub">Audio series where every episode ends with your choice — and the next one is written and voiced live, just for you.</p>
      </div>
      <div class="ob-foot"><button class="btn btn-grad btn-block" data-act="ob-next">Get started</button></div>`;
  } else if (obStep === 1) {
    const m = byId('rian') || SERIES[0];
    body = `
      <form class="ob-body" data-form="ob-name" autocomplete="off">
        <p class="ob-step-l">Step 2 of 3</p>
        <h1 class="ob-title">What should they call you?</h1>
        <p class="ob-sub">Characters will say your name in the story.</p>
        <div class="ob-name"><input id="ob-name" maxlength="24" placeholder="Your name" value="${esc(S.name)}" autocomplete="given-name" enterkeyhint="next" aria-label="Your name"></div>
        <div class="ob-bubble"><img src="${esc(avatarOf(m))}" alt=""><p id="ob-preview" translate="no">${LANG === 'zh' ? `“别松开我的手。从现在起，你是我未来的新娘，<b>${esc(S.name || '…')}</b>。”` : `“Don't let go of my hand. As of now, you're my future bride, <b>${esc(S.name || '…')}</b>.”`}</p></div>
      </form>
      <div class="ob-foot"><button class="btn btn-grad btn-block" data-act="ob-next">Continue</button><button class="link-btn" data-act="ob-next" data-skip="1">Skip for now</button></div>`;
  } else {
    body = `
      <div class="ob-body">
        <p class="ob-step-l">Step 3 of 3</p>
        <h1 class="ob-title">Pick what you love</h1>
        <p class="ob-sub">We'll tune your home shelves. Choose as many as you like.</p>
        <div class="ob-genres">${GENRES.map((g) => `<button class="chip ${obGenres.indexOf(g) >= 0 ? 'on' : ''}" data-act="ob-genre" data-g="${esc(g)}">${esc(g)}</button>`).join('')}</div>
      </div>
      <div class="ob-foot"><button class="btn btn-grad btn-block" data-act="ob-next">Start listening</button></div>`;
  }
  el.innerHTML = steps + body;
  const inp = $('#ob-name');
  if (inp) {
    inp.addEventListener('input', () => { const p = $('#ob-preview b'); if (p) p.textContent = inp.value.trim() || '…'; });
    setTimeout(() => { try { inp.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }, 250);
  }
}
/* new listeners start with WELCOME (100) coins (11-10; was 30). Listeners who already got the old 30 are topped up once. Returns coins added. */
function grantWelcome() {
  if ((S.welcome || 0) >= WELCOME) return 0;
  const had = S.welcome || (S.ledger.some((l) => /Welcome/.test(l.l)) ? 30 : 0);
  S.welcome = WELCOME;
  if (WELCOME <= had) { save(); return 0; }
  addCoins(WELCOME - had, 'Welcome bonus');
  return WELCOME - had;
}
function obNext(skip) {
  if (obStep === 1 && !skip) { const inp = $('#ob-name'); if (inp) S.name = inp.value.trim().slice(0, 24); }
  if (obStep < 2) { obStep += 1; save(); renderOnboard(); return; }
  S.genres = obGenres.slice();
  S.onboarded = true;
  const got = grantWelcome();
  save(true);
  const el = $('#onboard'); el.hidden = true; el.innerHTML = '';
  primeMic();  // the last onboarding tap: ask for the mic now (Hands-free is the default), not at the first choice point
  toast(`${coinIc('sm')} Welcome${S.name ? ', ' + esc(S.name) : ''}! +${got || WELCOME} coins`);
  route();
}

/* =========================================================================
 * 15. Boot
 * ========================================================================= */
async function boot() {
  renderTabbar();
  ensureToday();
  if (S.sleep && S.sleep.until && S.sleep.until < Date.now()) S.sleep = null;
  setAudioRate();
  try {
    if (MOCK) throw new Error('mock');
    const ck = 'ua.series.' + LANG, cachedList = store.get(ck, null), lastRelay = store.get('ua.relay', '');
    // Seen this app before on this phone: open from the cached list + last relay address at once, check relay.json in the background
    if (Array.isArray(cachedList) && cachedList.length && lastRelay) { API_BASE = lastRelay; loadRelay().then((ok) => { if (!ok) API_BASE = lastRelay; pickFastBase(); }); }
    else { await loadRelay(); pickFastBase(); }
    const fresh = RealAPI.series().then((list) => {
      if (!Array.isArray(list) || !list.length) throw new Error('empty');
      store.set(ck, list);
      setTimeout(prefetchScripts, 600);
      return list;
    });
    if (Array.isArray(cachedList) && cachedList.length) {
      // Open instantly from the last series list on this device; refresh in the background (the tunnel can take seconds)
      SERIES = shelfSort(cachedList); API = RealAPI;
      fresh.then((list) => {
        const byIdNew = Object.fromEntries(list.map((x) => [x.id, x]));
        SERIES.forEach((x) => { if (byIdNew[x.id]) Object.assign(x, byIdNew[x.id]); });
        list.forEach((x) => { if (!SERIES.some((y) => y.id === x.id)) SERIES.push(x); });
        SERIES = shelfSort(SERIES);
        if (curTab === 'home' && !isDetailOpen() && location.hash !== '#/player') renderHome();
      }).catch(() => toast('Server is reconnecting…'));
    } else {
      SERIES = shelfSort(await fresh);
      API = RealAPI;
    }
  } catch (e) {
    const wasExplicit = MOCK;
    MOCK = true; API = MockAPI;
    SERIES = shelfSort(await MockAPI.series());
    if (!wasExplicit) setTimeout(() => toast('Server offline — demo mode'), 600);
  }
  // drop live sessions with a different language/mode? keys already include both.
  if (location.hash === '#/player') history.replaceState(null, '', location.pathname + location.search + '#/home');
  setTimeout(() => { if (!slowNet()) warmRings(); }, 2500);
  setTimeout(prefetchScripts, 1800);
  if (!S.onboarded) { renderOnboard(); showTab('home'); }
  else { const top = grantWelcome(); if (top) setTimeout(() => toast(`${coinIc('sm')} +${top} coins · Welcome bonus`), 900); route(); primeMicOnEntry(); if (modeOf() === 'voice') fetchLocalBlob(`ack.${LANG}.mp3`); }
  if (TTS !== 'v4') setTimeout(() => toast(LANG === 'zh' ? `配音测试：${TTS === 'turbo' ? 'Eleven v4 Turbo（低延迟）' : 'Eleven Turbo v2.5（实时）'} · 第 2 集起生效` : `Voice test: ${TTS === 'turbo' ? 'Eleven v4 Turbo (low latency)' : 'Eleven Turbo v2.5 (realtime)'} · from Episode 2`), 900);
  renderMini();
}
boot();
})();
