const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("http://103.253.145.84:3200/university-groups");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  
  // Click a university group from the sidebar  
  const clicked = await page.evaluate(async () => {
    const allDivs = document.querySelectorAll("div");
    for (const el of allDivs) {
      const text = el.textContent.trim();
      const rect = el.getBoundingClientRect();
      if ((text.includes("Universitas") || text.includes("Institut") || text.includes("PTN")) && rect.height > 15 && rect.height < 80 && rect.width > 150) {
        el.click();
        return { text: text.substring(0, 50), x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) };
      }
    }
    return null;
  });
  if (clicked) {
    console.log("Clicked: " + clicked.text + " at " + clicked.x + "," + clicked.y);
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png" });
  
  // Now check ALL elements in the right half of the page
  const rightSide = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("*").forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.x > 250 && rect.width > 300 && rect.height > 50) {
        const style = window.getComputedStyle(el);
        const tag = el.tagName;
        const cls = el.className ? el.className.substring(0, 120) : "";
        results.push({
          tag, cls,
          x: Math.round(rect.x), y: Math.round(rect.y),
          w: Math.round(rect.width), h: Math.round(rect.height),
          overflow: style.overflow, overflowY: style.overflowY,
          scrollH: el.scrollHeight, clientH: el.clientHeight,
          hasScroll: el.scrollHeight > el.clientHeight + 5
        });
      }
    });
    return results.sort((a,b) => b.w * b.h - a.w * a.h);
  });
  
  console.log("Top 15 largest elements on RIGHT side (x>250, w>300):");
  rightSide.slice(0, 15).forEach((el, i) => {
    console.log("  " + (i+1) + ". <" + el.tag + "> " + el.w + "x" + el.h + " at " + el.x + "," + el.y);
    console.log("     scroll: " + el.scrollH + "/" + el.clientH + " overflowY: " + el.overflowY + " hasScroll: " + el.hasScroll);
    console.log("     " + el.cls.substring(0, 100));
  });
  
  // Check the full page structure
  const allScrollable = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("*").forEach(el => {
      if (el.scrollHeight > el.clientHeight + 5) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        results.push({
          tag: el.tagName,
          cls: el.className ? el.className.substring(0, 120) : "",
          overflowY: style.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight,
          x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)
        });
      }
    });
    return results;
  });
  
  console.log("");
  console.log("All scrollable elements (" + allScrollable.length + "):");
  allScrollable.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " at " + s.x + "," + s.y + " scroll:" + s.scrollH + "/" + s.clientH + " overflowY:" + s.overflowY);
    console.log("     " + s.cls.substring(0, 100));
  });
  
  // Page scroll test
  console.log("");
  console.log("=== PAGE SCROLL TEST ===");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
  const docH = await page.evaluate(() => document.body.scrollHeight);
  const viewH = await page.evaluate(() => window.innerHeight);
  console.log("Doc height: " + docH + ", Viewport: " + viewH + ", Scrollable: " + (docH > viewH));
  
  // Try scrolling the window
  if (docH > viewH) {
    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, 200);
    await page.waitForTimeout(500);
    const scrolled = await page.evaluate(() => window.scrollY);
    console.log("After wheel scroll at center, window.scrollY = " + scrolled);
  }
  
  // Try scrolling each scrollable element
  console.log("");
  console.log("=== INTERNAL SCROLL TESTS ===");
  for (const s of allScrollable) {
    if (s.w < 100) continue;
    const cx = s.x + s.w/2, cy = s.y + s.h/2;
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);
    await page.mouse.move(cx, cy);
    const before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 200);
    await page.waitForTimeout(500);
    const after = await page.evaluate(() => window.scrollY);
    if (after !== before) {
      console.log("UNWANTED: <" + s.tag + "> " + s.w + "x" + s.h + " at (" + s.x + "," + s.y + ") overflowY=" + s.overflowY + " -> window scrolled " + before + " to " + after);
    } else {
      console.log("OK: <" + s.tag + "> " + s.w + "x" + s.h + " at (" + s.x + "," + s.y + ") overflowY=" + s.overflowY + " -> window did not scroll");
    }
  }
  
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/03_final.png" });
  await browser.close();
})().catch(err => { console.error("ERROR:", err.message); process.exit(1); });
