import { createRequire } from 'module'; import fs from 'fs';
export async function boot(nodeMods, url, out) {
  const require = createRequire(nodeMods); const { chromium } = require('playwright');
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, permissions: ['microphone'], locale: 'en-US' });
  const page = await ctx.newPage(); const errs = [];
  page.on('pageerror', (e) => errs.push(String(e).slice(0, 160)));
  const snap = async (name) => {
    await page.evaluate(() => document.querySelectorAll('.toast, #toast').forEach((t) => { t.style.visibility = 'hidden'; }));
    await page.screenshot({ path: `${out}/${name}.png` });
    const els = await page.evaluate(() => { const vis = (e) => { const r = e.getBoundingClientRect(); if (r.width < 6 || r.height < 6 || r.bottom < 4 || r.top > innerHeight - 4 || r.right < 4 || r.left > innerWidth - 4) return null; return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };
      return [...document.querySelectorAll('[data-act],h1,h2,h3,input,.hero,.shelf,.wallet4,.w4-tags,.me4-top,.me4-tabs,.lib-grid,.rw-task,.rw-tabs,.rw-card,.sheet.on,.ob4-m,.ob4-turn,.ob4-bar,.ob4-head,.ob4-ways,.ob-steps,.ob-collage,.ob-title,.ob-sub,.cl-list,.promo,.mode-opt,.ul-price,.wait-free,.vip-card,.packs,.segc,.toggle-row,.field-l,.pf-who,.hist-row,.panel')]
        .map((e) => { const r = vis(e); return r ? { k: (e.dataset.act ? 'act:' + e.dataset.act + (e.dataset.t ? '/' + e.dataset.t : '') + (e.dataset.i ? '/' + e.dataset.i : '') : e.tagName.toLowerCase() + '.' + String(e.className).split(' ').slice(0, 2).join('.')), t: (e.value || e.placeholder || e.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 26), r } : null; }).filter(Boolean); });
    fs.writeFileSync(`${out}/${name}.json`, JSON.stringify(els)); console.log('shot', name);
  };
  const closeSheet = async () => { const c = page.locator('.sheet.on [data-act="sheet-close"]:visible').last(); if (await c.count()) await c.click().catch(() => {}); else await page.keyboard.press('Escape'); await page.waitForTimeout(500); };
  return { browser, page, snap, closeSheet, errs };
}
