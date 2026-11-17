// 11-16 v109 精简版重截：引导（新小戏）、首页、解锁、收听方式、我的、设置、登录、福利、商店。不花额度：写下一集 / 通话 / 提问的接口全拦掉，/api/play 带 prewarm。
import { boot } from './lib24.mjs';
const [, , mods, url, out] = process.argv;
const { browser, page, snap, closeSheet, errs } = await boot(mods, url, out);
await page.route(/\/api\/(next|spec|call|cue|wish)/, (r) => r.abort());
await page.route(/\/api\/play/, async (r) => { let b = {}; try { b = JSON.parse(r.request().postData() || '{}'); } catch (e) {} b.prewarm = true; await r.continue({ postData: JSON.stringify(b) }); });
const W = (ms) => page.waitForTimeout(ms); const ua = (f, a) => page.evaluate(f, a);
const click = (sel) => page.locator(sel).first().click({ timeout: 5000 }).catch((e) => console.log('click fail', sel, String(e).slice(0, 80)));
const imgs = async () => { for (let i = 0; i < 30; i++) { const ok = await ua(() => [...document.querySelectorAll('img')].filter((e) => { const r = e.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0 && r.width > 4 && r.left < innerWidth && r.right > 0; }).every((e) => e.complete && e.naturalWidth > 0)); if (ok) break; await W(300); } };
const S = async (n) => { await imgs(); await snap(n); };
// 引导
await page.goto(url, { waitUntil: 'load' }); await W(3500); await S('01-onboard-welcome');
await click('#onboard [data-act="ob-next"]'); await W(8500); await S('02-ob-name');
await page.fill('#ob4-t', 'Vicky'); await click('.ob4-send'); await W(9500); await S('03-ob-turn');
await click('.ob4-opt[data-i="0"]'); await W(5200); await S('04-ob-end');
await click('[data-act="ob4-skip"]'); await W(2500);
// 我的：没登录 → 登录 → 用原名或改名
await ua(() => { location.hash = '#/me'; }); await W(1500);
await click('.me4-top [data-act="signin"]'); await W(1000); await S('66-signin');
await click('.sheet.on [data-act="signin-go"][data-via="apple"]'); await W(1200); await S('67-signed-in');
await page.fill('#pf-name', 'Vicky'); await click('.sheet.on form[data-form="name"] button'); await W(1000);
// 首页（新用户）
await ua(() => { location.hash = '#/home'; }); await W(2500); await ua(() => document.querySelector('#v-home').scrollTo({ top: 0 })); await W(800); await S('04-home');
await ua(() => document.querySelector('#v-home').scrollTo({ top: 560 })); await W(900); await S('05-home-shelves');
await ua(() => { const v = document.querySelector('#v-home'); const g = [...v.querySelectorAll('.shelf-h h3')].find((h) => /Browse/.test(h.textContent)); v.scrollTo({ top: g.closest('.shelf').offsetTop - 66 }); }); await W(900); await S('06-home-more');
await ua(() => { const v = document.querySelector('#v-home'); v.scrollTo({ top: v.scrollHeight }); }); await W(900); await S('53-home-end');
await ua(() => document.querySelector('#v-home').scrollTo({ top: 0 })); await W(400);
// 播放器里的弹层
await ua(() => { location.hash = '#/series/rowan'; }); await W(4000);
await page.locator('#detail [data-act="play-series"]').first().click({ force: true, timeout: 4000 }).catch(() => {}); await W(7000);
await click('#player [data-act="mode-sheet"]'); await W(1200); await S('24-listening-mode'); await closeSheet();
await ua(() => { const S = window.__ua.S; S._f = S.freeSec; S.freeSec = 1800; window.__ua.openUnlockSheet('rowan', 4); }); await W(1200); await S('42-unlock-sheet'); await closeSheet(); await W(400);
await ua(() => { const S = window.__ua.S; S._c = S.coins; S.coins = 0; window.__ua.openUnlockSheet('rowan', 4); }); await W(1200); await S('43-unlock-no-coins'); await closeSheet();
await ua(() => { const S = window.__ua.S; S.coins = S._c; S.freeSec = S._f; });
await click('#player [data-act="close-player"]'); await W(1200); await ua(() => { try { window.__ua.audio.pause(); } catch (e) {} });
// 老用户示例数据
await ua(() => {
  const st = JSON.parse(localStorage.getItem('ua.state')); const ss = JSON.parse(localStorage.getItem('ua.sess') || '{}'); const now = Date.now();
  [['rowan', 1, .46, false, 'The Stranger Who Caught the Sign'], ['magnus', 3, .29, false, 'She Goes Upstairs Anyway'], ['rian', 1, .6, false, 'My Future Bride'], ['reborn', 2, 1, true, 'The Dragon King Lands'], ['lena', 6, .44, false, 'Episode 6'], ['hellqueen', 1, .57, false, 'The Queen and the Microwave']]
    .forEach(([id, ep, pct, need, title], i) => { const k = `r:${id}:en`; ss[k] = { sid: 'x' + i, eps: [] }; st.progress[k] = { id, ep, title, pct, t: 0, line: 0, at: now - (i + 1) * 3600e3 * 5, needChoice: need, rem: null }; });
  st.saved = ['island', 'rafael', 'mii', 'kael']; st.played = ['rowan', 'magnus', 'rian', 'reborn', 'lena', 'hellqueen']; st.freeSec = 420; st.coins = 185;
  st.ledger = [[15, 'Daily check-in · Day 2', 1], [10, 'New listener reward · Make your first choice', 1], [20, 'New listener reward · Finish your first episode', 1], [10, 'New listener reward · Save a series to your Library', 2], [5, 'Task · Share a series', 5], [10, 'Daily check-in · Day 1', 26], [-10, 'Auto-unlock Ep 4 · Four Liars, One Island', 90], [25, 'Daily check-in · Day 4', 96], [100, 'Welcome bonus', 200]].map(([d, l, h]) => ({ t: now - h * 3600e3, d, l }));
  localStorage.setItem('ua.state', JSON.stringify(st)); localStorage.setItem('ua.sess', JSON.stringify(ss)); Storage.prototype.setItem = () => {};
});
await page.goto(url.replace(/#.*$/, '') + '#/home', { waitUntil: 'load' }); await W(800); await page.reload({ waitUntil: 'load' }); await W(4000);
await ua(() => { const v = document.querySelector('#v-home'); const h = [...v.querySelectorAll('.shelf-h h3')].find((x) => /Continue/.test(x.textContent)); v.scrollTo({ top: h.closest('.shelf').offsetTop - 250 }); }); await W(900); await S('26-mini-player');
await ua(() => { location.hash = '#/me'; }); await W(1800); await S('60-me');
await click('[data-act="lib-edit"]'); await W(500); await S('61-me-edit'); await click('[data-act="lib-edit"]'); await W(300);
await click('[data-act="lib-tab"][data-t="saved"]'); await W(900); await S('62-me-saved');
await click('.me4-set'); await W(1000); await S('63-settings'); await closeSheet();
await ua(() => { location.hash = '#/rewards'; }); await W(1500); await S('11-rewards');
await ua(() => { const v = document.querySelector('#v-rewards'); v.scrollTo({ top: document.querySelector('.rw-tasks').offsetTop - 66 }); }); await W(700); await S('12-rewards-daily');
await click('[data-act="rw-tab"][data-t="new"]'); await W(700); await S('51-rewards-new');
await click('[data-act="rw-tab"][data-t="daily"]'); await W(400); await click('.ledger-more'); await W(500);
await ua(() => { const v = document.querySelector('#v-rewards'); v.scrollTo({ top: v.scrollHeight }); }); await W(600); await S('65-coin-history');
await ua(() => document.querySelector('#v-rewards').scrollTo({ top: 0 })); await W(300); await click('#v-rewards .coin-pill'); await W(1200); await S('13-coin-store');
console.log('errs', JSON.stringify(errs)); await browser.close();
