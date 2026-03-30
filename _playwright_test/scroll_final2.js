const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("http://103.253.145.84:3200/university-groups");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  console.log("URL: " + page.url());
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  const allScroll = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("*").forEach(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 50 && rect.height > 50 && rect.y >= 0) {
        if (el.scrollHeight > el.clientHeight + 5 || style.overflowY === "auto" || style.overflowY === "scroll") {
          results.push({ tag: el.tagName, cls: el.className ? el.className.substring(0, 120) : "", x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height), overflowY: style.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight });
        }
      }
    });
    return results;
  });
  console.log("Scrollable elements: " + allScroll.length);
  allScroll.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " at " + s.x + "," + s.y + " overflowY=" + s.overflowY + " scroll=" + s.scrollH + "/" + s.clientH);
    console.log("     " + s.cls.substring(0, 100));
  });
  const sidebarNav = allScroll.find(s => s.tag === "NAV" || s.cls.includes("space-y-3"));
  const mainArea = allScroll.find(s => s.tag === "MAIN");
  const tableContainer = allScroll.find(s => s.cls.includes("overflow-y-auto") || s.cls.includes("overflow-y-scroll"));
  console.log("Sidebar nav: " + (sidebarNav ? sidebarNav.w + "x" + sidebarNav.h + " overflowY=" + sidebarNav.overflowY + " scroll=" + sidebarNav.scrollH + "/" + sidebarNav.clientH : "NOT FOUND"));
  console.log("Main: " + (mainArea ? mainArea.w + "x" + mainArea.h + " overflowY=" + mainArea.overflowY + " scroll=" + mainArea.scrollH + "/" + mainArea.clientH : "NOT FOUND"));
  console.log("Table container: " + (tableContainer ? tableContainer.w + "x" + tableContainer.h + " overflowY=" + tableContainer.overflowY + " scroll=" + tableContainer.scrollH + "/" + tableContainer.clientH : "NOT FOUND"));
  console.log("=== WHEEL TESTS ===");
  if (sidebarNav) {
    await page.mouse.move(sidebarNav.x + sidebarNav.w/2, sidebarNav.y + sidebarNav.h/2);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    let navTop = await page.evaluate(() => { const n = document.querySelector("nav"); return n ? n.scrollTop : 0; });
    console.log("Sidebar: window.scrollY " + before + "->" + after + " | nav.scrollTop:" + navTop + " | " + (after !== before ? "BAD" : "GOOD"));
  }
  if (mainArea) {
    await page.mouse.move(mainArea.x + mainArea.w/2, mainArea.y + mainArea.h/2);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    let mainTop = await page.evaluate(() => { const m = document.querySelector("main"); return m ? m.scrollTop : 0; });
    console.log("Main: window.scrollY " + before + "->" + after + " | main.scrollTop:" + mainTop + " | " + (after !== before ? "BAD" : "GOOD"));
  }
  await page.evaluate(() => { const m = document.querySelector("main"); if(m) m.scrollTop = m.scrollHeight; });
  await page.waitForTimeout(500);
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_scrolled_bottom.png" });
  const atBottom = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("*").forEach(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 50 && rect.height > 50 && rect.y >= 0) {
        if (el.scrollHeight > el.clientHeight + 5 || style.overflowY === "auto" || style.overflowY === "scroll") {
          results.push({ tag: el.tagName, cls: el.className ? el.className.substring(0, 120) : "", x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height), overflowY: style.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight });
        }
      }
    });
    return results;
  });
  console.log("Scrollable at bottom: " + atBottom.length);
  atBottom.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " overflowY=" + s.overflowY + " scroll=" + s.scrollH + "/" + s.clientH);
    console.log("     " + s.cls.substring(0, 100));
  });
  const docH = await page.evaluate(() => document.body.scrollHeight);
  const viewH = await page.evaluate(() => window.innerHeight);
  console.log("Page: docH=" + docH + " viewH=" + viewH + " pageScrollable=" + (docH > viewH));
  console.log("=== DIAGNOSIS ===");
  if (sidebarNav && mainArea) {
    console.log("RESULT: GOOD - sidebar nav=" + sidebarNav.overflowY + " main=" + mainArea.overflowY);
  } else {
    console.log("RESULT: CHECK SCROLL BEHAVIOR MANUALLY");
  }
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/03_final.png" });
  await browser.close();
  console.log("Done");
})().catch(err => { console.error("ERROR:", err.message); process.exit(1); });