const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto("http://103.253.145.84:3200/university-groups");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  console.log("Initial state captured");

  // Analyze sidebar
  const sidebarInfo = await page.evaluate(() => {
    const nav = document.querySelector("nav");
    if (!nav) return null;
    const rect = nav.getBoundingClientRect();
    const style = window.getComputedStyle(nav);
    return {
      tag: nav.tagName,
      x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height),
      overflowY: style.overflowY,
      scrollH: nav.scrollHeight, clientH: nav.clientHeight,
      scrollable: nav.scrollHeight > nav.clientHeight
    };
  });
  console.log("\n=== SIDEBAR ===");
  console.log(JSON.stringify(sidebarInfo, null, 2));

  // Find university group items in sidebar
  const items = await page.evaluate(() => {
    const nav = document.querySelector("nav");
    if (!nav) return [];
    const results = [];
    nav.querySelectorAll("div").forEach(el => {
      const rect = el.getBoundingClientRect();
      const text = el.textContent.trim();
      if (rect.width > 100 && rect.height > 15 && rect.height < 80 && rect.y > 50) {
        results.push({ text: text.substring(0, 60), x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) });
      }
    });
    return results;
  });
  console.log("\nDivs in sidebar nav: " + items.length);
  items.forEach((item, i) => {
    console.log("  " + (i+1) + ". " + item.text.substring(0,50) + " at " + item.x + "," + item.y + " " + item.w + "x" + item.h);
  });

  // Click first university group
  const target = items.find(i => i.text.includes("Universitas") || i.text.includes("Institut") || i.text.includes("PTN"));
  if (target) {
    console.log("\nClicking: " + target.text);
    await page.mouse.click(target.x + target.w/2, target.y + target.h/2);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png" });
    console.log("After click screenshot captured");
  } else {
    console.log("\nNo university group found to click");
    // Try clicking by position
    await page.mouse.click(110, 150);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png" });
  }

  // Full scroll analysis
  const allScrollable = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("*").forEach(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 100 && rect.height > 100 && rect.y >= 0) {
        if (el.scrollHeight > el.clientHeight + 5 || style.overflowY === "auto" || style.overflowY === "scroll") {
          results.push({
            tag: el.tagName,
            cls: el.className ? el.className.substring(0, 120) : "",
            x: Math.round(rect.x), y: Math.round(rect.y),
            w: Math.round(rect.width), h: Math.round(rect.height),
            overflowY: style.overflowY,
            scrollH: el.scrollHeight, clientH: el.clientHeight,
            hasOverflow: el.scrollHeight > el.clientHeight + 5
          });
        }
      }
    });
    return results;
  });

  console.log("\n=== ALL SCROLLABLE ELEMENTS ===");
  console.log("Total: " + allScrollable.length);
  allScrollable.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " at " + s.x + "," + s.y);
    console.log("     overflowY: " + s.overflowY + ", scroll: " + s.scrollH + "/" + s.clientH);
    console.log("     " + s.cls.substring(0, 100));
  });

  // Find sidebar list
  const sidebarScroll = allScrollable.find(s => s.tag === "NAV" || s.cls.includes("space-y-3"));
  // Find table container
  const tableScroll = allScrollable.find(s => s.x > 250 && s.w > 400 && (s.cls.includes("overflow-y-auto") || s.cls.includes("overflow-y-scroll")));

  console.log("\n=== DIAGNOSIS ===");
  console.log("Sidebar list has internal scroll: " + (sidebarScroll ? "YES (overflowY=" + sidebarScroll.overflowY + ")" : "NO"));
  console.log("Main table has internal scroll: " + (tableScroll ? "YES" : "NO"));

  // Wheel scroll tests
  console.log("\n=== WHEEL SCROLL TESTS ===");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);

  if (sidebarScroll) {
    const cx = sidebarScroll.x + sidebarScroll.w/2, cy = sidebarScroll.y + sidebarScroll.h/2;
    await page.mouse.move(cx, cy);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    console.log("Wheel on sidebar: window.scrollY " + before + " -> " + after + " | " + (after !== before ? "BAD" : "GOOD - internal scroll"));
  }

  if (tableScroll) {
    const cx = tableScroll.x + tableScroll.w/2, cy = tableScroll.y + tableScroll.h/2;
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);
    await page.mouse.move(cx, cy);
    let before = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(500);
    let after = await page.evaluate(() => window.scrollY);
    console.log("Wheel on table: window.scrollY " + before + " -> " + after + " | " + (after !== before ? "BAD - page scrolls" : "GOOD - internal scroll"));
  }

  // Overall page scrollability
  const docH = await page.evaluate(() => document.body.scrollHeight);
  const viewH = await page.evaluate(() => window.innerHeight);
  console.log("\nPage scrollable (doc > viewport): " + docH + " > " + viewH + " = " + (docH > viewH));

  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/03_final.png" });
  await browser.close();
  console.log("\nDone.");
})().catch(err => { console.error("ERROR:", err.message); process.exit(1); });
