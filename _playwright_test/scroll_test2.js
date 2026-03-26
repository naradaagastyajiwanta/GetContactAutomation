const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  console.log("=== STEP 1 ===");
  await page.goto("http://103.253.145.84:3200/university-groups");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  console.log("Title: " + await page.title());
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  console.log("Doc height: " + await page.evaluate(() => document.body.scrollHeight));
  console.log("Viewport: " + await page.evaluate(() => window.innerHeight));
  console.log("window.scrollY: " + await page.evaluate(() => window.scrollY));

  // Find university group divs in sidebar
  const allDivs = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("div").forEach(el => {
      const rect = el.getBoundingClientRect();
      const text = el.textContent.trim();
      if (rect.x > 0 && rect.x < 280 && rect.y > 60 && rect.height > 20 && rect.height < 80 && rect.width > 100) {
        if (text.includes("Universitas") || text.includes("Institut") || text.includes("PTN") || text.includes("Sekolah")) {
          results.push({ text: text.substring(0, 60), x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) });
        }
      }
    });
    return results;
  });
  console.log("University groups in sidebar: " + allDivs.length);
  allDivs.slice(0, 5).forEach((d, i) => { console.log("  " + (i+1) + ". " + d.text + " at " + d.x + "," + d.y); });
  
  if (allDivs.length > 0) {
    const first = allDivs[0];
    console.log("Clicking: " + first.text);
    await page.mouse.click(first.x + first.w/2, first.y + first.h/2);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png" });
    console.log("window.scrollY after click: " + await page.evaluate(() => window.scrollY));
  }
  
  // Full scroll analysis
  const structure = await page.evaluate(() => {
    const sc = [];
    document.querySelectorAll("*").forEach(el => {
      if (el.scrollHeight > el.clientHeight + 5) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (rect.width > 100 && rect.height > 100) {
          sc.push({
            tag: el.tagName, classes: el.className ? el.className.substring(0, 150) : "",
            overflowY: style.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight,
            x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)
          });
        }
      }
    });
    return sc;
  });
  console.log("Scrollable containers: " + structure.length);
  structure.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " at " + s.x + "," + s.y + " overflowY:" + s.overflowY + " scroll:" + s.scrollH + "/" + s.clientH);
    console.log("     " + s.classes.substring(0, 120));
  });
  
  // Test wheel scroll on each container
  console.log("");
  console.log("=== SCROLL BEHAVIOR TESTS ===");
  for (const s of structure) {
    const centerX = s.x + s.w / 2;
    const centerY = s.y + s.h / 2;
    console.log("Test: Wheel over <" + s.tag + "> at (" + centerX + "," + centerY + ") w=" + s.w + " h=" + s.h + " overflowY=" + s.overflowY);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);
    await page.mouse.move(centerX, centerY);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 150);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    if (after !== before) {
      console.log("  RESULT: UNWANTED - window scrolled from " + before + " to " + after + " (overflowY=" + s.overflowY + ")");
    } else {
      console.log("  RESULT: GOOD - window did not scroll");
    }
  }
  
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/03_final.png" });
  
  console.log("");
  console.log("=== DIAGNOSIS ===");
  const sidebarScroll = structure.find(s => s.classes.includes("space-y-3") || s.classes.includes("overflow-y-auto"));
  const mainScroll = structure.find(s => s.x > 300 && s.w > 500 && (s.overflowY === "auto" || s.overflowY === "scroll"));
  const windowOnlyScroll = structure.filter(s => s.w > 800 || (s.x === 0 && s.y === 0)).length;
  console.log("Sidebar has internal scroll: " + (sidebarScroll ? "YES (overflowY=" + sidebarScroll.overflowY + ")" : "NO"));
  console.log("Main content has internal scroll: " + (mainScroll ? "YES" : "NO - entire page may scroll"));
  if (!mainScroll && structure.length > 0) {
    console.log("");
    console.log("FINDING: The main university list/table does NOT have internal scrolling.");
    console.log("The entire page scrolls when interacting with the list area.");
    console.log("This is UNWANTED scroll behavior.");
  }
  
  await browser.close();
  console.log("Done.");
})().catch(err => { console.error("ERROR:", err.message); process.exit(1); });
