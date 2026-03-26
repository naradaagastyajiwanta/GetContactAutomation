const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  console.log('=== LOADING PAGE ===');
  await page.goto('http://103.253.145.84:3200/university-groups');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: 'C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png' });
  const dims = await page.evaluate(() => ({ docH: document.body.scrollHeight, viewH: window.innerHeight, docW: document.body.scrollWidth, viewW: window.innerWidth }));
  console.log('Page: doc=' + dims.docW + 'x' + dims.docH + ' viewport=' + dims.viewW + 'x' + dims.viewH);
  const sidebarItems = await page.evaluate(() => {
    const nav = document.querySelector('nav');
    if (!nav) return [];
    const results = [];
    nav.querySelectorAll('button, a, [role], li').forEach(el => {
      const rect = el.getBoundingClientRect();
      const text = el.textContent.trim();
      if (rect.width > 100 && rect.height > 15 && rect.height < 80 && rect.y > 50) {
        results.push({ tag: el.tagName, text: text.substring(0, 60), x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) });
      }
    });
    return results;
  });
  console.log('Sidebar items: ' + sidebarItems.length);
  sidebarItems.forEach((s, i) => {
    const isUni = s.text.includes('Universitas') || s.text.includes('Institut') || s.text.includes('PTN');
    console.log('  ' + (i+1) + '. <' + s.tag + '> ' + s.text.substring(0,40) + (isUni ? ' [UNIV]' : '') + ' at ' + s.x + ',' + s.y);
  });
  let clicked = false;
  for (const item of sidebarItems) {
    if (item.text.includes('Universitas') || item.text.includes('Institut') || item.text.includes('PTN')) {
      console.log('Clicking: ' + item.text);
      await page.mouse.click(item.x + item.w/2, item.y + item.h/2);
      clicked = true;
      break;
    }
  }
  if (!clicked && sidebarItems.length > 0) {
    console.log('Clicking first sidebar item: ' + sidebarItems[0].text.substring(0,40));
    await page.mouse.click(sidebarItems[0].x + sidebarItems[0].w/2, sidebarItems[0].y + sidebarItems[0].h/2);
    clicked = true;
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png' });
  const mainArea = await page.evaluate(() => {
    const main = document.querySelector('main');
    if (!main) return null;
    const rect = main.getBoundingClientRect();
    const style = window.getComputedStyle(main);
    return { tag: main.tagName, x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height), overflowY: style.overflowY, scrollH: main.scrollHeight, clientH: main.clientHeight, scrollable: main.scrollHeight > main.clientHeight };
  });
  console.log('MAIN: ' + (mainArea ? mainArea.w + 'x' + mainArea.h + ' at ' + mainArea.x + ',' + mainArea.y + ' overflowY=' + mainArea.overflowY + ' scroll=' + mainArea.scrollH + '/' + mainArea.clientH : 'not found'));
  console.log('=== WHEEL SCROLL TEST ===');
  if (mainArea) {
    const cx = mainArea.x + mainArea.w/2, cy = mainArea.y + mainArea.h/2;
    await page.mouse.move(cx, cy);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    console.log('Wheel at main center (' + cx + ',' + cy + '): window.scrollY ' + before + ' -> ' + after);
    console.log((after !== before ? 'BAD: Window scrolled' : 'GOOD: No window scroll'));
    if (after === before) {
      const mainTop = await page.evaluate(() => { const m = document.querySelector('main'); return m ? m.scrollTop : 0; });
      console.log('main.scrollTop: ' + mainTop);
    }
  }
  await page.evaluate(() => { const m = document.querySelector('main'); if(m) m.scrollTop = m.scrollHeight; });
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'C:/Users/narad/Programming/GetContactAI/_playwright_test/03_scrolled_down.png' });
  const allScroll = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('*').forEach(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 100 && rect.height > 100 && rect.y >= 0 && el.scrollHeight > el.clientHeight + 10) {
        results.push({ tag: el.tagName, cls: el.className ? el.className.substring(0, 100) : '', x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height), overflowY: style.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight });
      }
    });
    return results;
  });
  console.log('All scrollable: ' + allScroll.length);
  allScroll.forEach((s, i) => { console.log('  ' + (i+1) + '. <' + s.tag + '> ' + s.w + 'x' + s.h + ' at ' + s.x + ',' + s.y + ' overflowY=' + s.overflowY + ' scroll=' + s.scrollH + '/' + s.clientH + ' | ' + s.cls.substring(0,80)); });
  console.log('=== DIAGNOSIS ===');
  const mainScrollOK = mainArea && (mainArea.overflowY === 'auto' || mainArea.overflowY === 'scroll');
  const sidebarScrollOK = allScroll.some(s => s.tag === 'NAV' && (s.overflowY === 'auto' || s.overflowY === 'scroll'));
  console.log('Sidebar: ' + (sidebarScrollOK ? 'INTERNAL SCROLL OK' : 'NO'));
  console.log('Main: ' + (mainScrollOK ? 'INTERNAL SCROLL OK (' + mainArea.overflowY + ' scroll=' + mainArea.scrollH + '/' + mainArea.clientH + ')' : 'NO'));
  if (sidebarScrollOK && mainScrollOK) console.log('RESULT: CORRECT - both scroll internally');
  await page.screenshot({ path: 'C:/Users/narad/Programming/GetContactAI/_playwright_test/04_final.png' });
  await browser.close();
  console.log('Done');
})().catch(err => { console.error('ERROR:', err.message); process.exit(1); });
