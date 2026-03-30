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
  let initialScrollY = await page.evaluate(() => window.scrollY);
  console.log("window.scrollY: " + initialScrollY);
  console.log("=== STEP 2 ===");
  const allClickable = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll("[role=button], [role=listitem], div[tabindex], button").forEach(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width > 50 && rect.height > 20 && rect.height < 300 && rect.width < 1300 && rect.y >= 0) {
        results.push({
          tag: el.tagName,
          classes: el.className ? el.className.substring(0, 100) : "",
          text: el.textContent.substring(0, 80).replace(/\s+/g, " "),
          x: Math.round(rect.x), y: Math.round(rect.y),
          w: Math.round(rect.width), h: Math.round(rect.height),
          cursor: style.cursor
        });
      }
    });
    return results;
  });
  console.log("Found " + allClickable.length + " clickable elements");
  allClickable.slice(0, 10).forEach((c, i) => {
    console.log("  " + (i+1) + ". <" + c.tag + "> " + c.classes.substring(0, 80) + " | " + c.text + " | " + c.w + "x" + c.h);
  });
  let clicked = false;
  for (const el of allClickable) {
    if (el.text.includes("Universitas") || el.text.includes("Institut") || el.text.includes("Sekolah") || el.text.includes("PTN")) {
      console.log("Clicking: " + el.text);
      await page.mouse.click(el.x + el.w/2, el.y + el.h/2);
      clicked = true;
      break;
    }
  }
  if (!clicked && allClickable.length > 0) {
    const first = allClickable[0];
    console.log("Clicking first: " + first.text);
    await page.mouse.click(first.x + first.w/2, first.y + first.h/2);
    clicked = true;
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/02_after_click.png" });
  let scrollAfterClick = await page.evaluate(() => window.scrollY);
  console.log("window.scrollY after click: " + scrollAfterClick);
  console.log("=== STEP 3 ===");
  const structure = await page.evaluate(() => {
    const scrollContainers = [];
    document.querySelectorAll("*").forEach(el => {
      if (el.scrollHeight > el.clientHeight + 5) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 50 && rect.height < 2000) {
          scrollContainers.push({
            tag: el.tagName,
            classes: el.className ? el.className.substring(0, 150) : "",
            overflow: style.overflow, overflowY: style.overflowY,
            scrollH: el.scrollHeight, clientH: el.clientHeight,
            x: Math.round(rect.x), y: Math.round(rect.y),
            w: Math.round(rect.width), h: Math.round(rect.height)
          });
        }
      }
    });
    return scrollContainers;
  });
  console.log("Scrollable containers: " + structure.length);
  structure.forEach((s, i) => {
    console.log("  " + (i+1) + ". <" + s.tag + "> " + s.w + "x" + s.h + " scroll:" + s.scrollH + "/" + s.clientH + " overflowY:" + s.overflowY);
    console.log("     classes: " + s.classes.substring(0, 100));
  });
  console.log("=== STEP 4 ===");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  let listContainer = null;
  let maxArea = 0;
  for (const s of structure) {
    const area = s.w * s.h;
    if (area > maxArea && s.w < 1000) { maxArea = area; listContainer = s; }
  }
  if (listContainer) {
    console.log("List container: <" + listContainer.tag + "> " + listContainer.w + "x" + listContainer.h + " overflowY:" + listContainer.overflowY);
    const centerX = listContainer.x + listContainer.w / 2;
    const centerY = listContainer.y + listContainer.h / 2;
    console.log("Test 1: Wheel over LIST at (" + centerX + ", " + centerY + ")");
    await page.mouse.move(centerX, centerY);
    let wsBefore = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 150);
    await page.waitForTimeout(500);
    let wsAfter = await page.evaluate(() => window.scrollY);
    console.log("  Window before: " + wsBefore + " after: " + wsAfter);
    console.log("  " + (wsAfter !== wsBefore ? "BAD: Window scrolled (page scroll triggered by list wheel)" : "GOOD: No window scroll"));
    console.log("Test 2: Wheel over BACKGROUND (50, 750)");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await page.mouse.move(50, 750);
    wsBefore = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 150);
    await page.waitForTimeout(500);
    wsAfter = await page.evaluate(() => window.scrollY);
    console.log("  Window before: " + wsBefore + " after: " + wsAfter);
  } else {
    console.log("NO distinct list container - entire page is the scrollable area!");
    console.log("This is UNWANTED: List does not scroll internally.");
    let wsBefore = await page.evaluate(() => window.scrollY);
    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, 150);
    await page.waitForTimeout(500);
    let wsAfter = await page.evaluate(() => window.scrollY);
    console.log("  Window scrolled from " + wsBefore + " to " + wsAfter);
  }
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/03_final.png" });
  await page.waitForTimeout(1000);
  console.log("=== DIAGNOSIS ===");
  if (!listContainer) {
    console.log("UNWANTED SCROLL BEHAVIOR: No internal list scrolling. Entire page scrolls.");
    console.log("FIX: Add fixed height + overflow-y:auto to list container.");
  } else {
    console.log("Scroll behavior OK: List container has internal scrolling.");
  }
  await browser.close();
  console.log("Done. Screenshots: 01_initial, 02_after_click, 03_final");
})().catch(err => { console.error("ERROR:", err.message); process.exit(1); });
