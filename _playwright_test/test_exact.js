const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  
  // Track network requests
  let responses = [];
  page.on("response", resp => {
    if (resp.status() >= 400) {
      responses.push({ url: resp.url().substring(0, 100), status: resp.status() });
    }
  });
  
  console.log("=== Navigate to EXACT URL: http://103.253.145.84/university-groups ===");
  try {
    await page.goto("http://103.253.145.84/university-groups", { timeout: 15000 });
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);
  } catch (e) {
    console.log("Navigation error:", e.message);
  }
  
  console.log("Page title: " + await page.title());
  console.log("Page URL: " + page.url());
  
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log("Body text: " + bodyText);
  
  if (responses.length > 0) {
    console.log("Failed responses:");
    responses.forEach(r => console.log("  " + r.status + ": " + r.url));
  }
  
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  console.log("Screenshot saved");
  
  await browser.close();
})().catch(err => {
  console.error("ERROR:", err.message);
  process.exit(1);
});
