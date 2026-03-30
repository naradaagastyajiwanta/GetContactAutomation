const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  
  console.log("=== Testing URL: http://103.253.145.84:3000/university-groups ===");
  await page.goto("http://103.253.145.84:3000/university-groups");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  
  console.log("Page title: " + await page.title());
  console.log("Page URL: " + page.url());
  
  // Get page HTML
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log("Body text: " + bodyText);
  
  // Get the HTML content
  const html = await page.content();
  console.log("HTML length: " + html.length);
  if (html.includes("university-groups") || html.includes("UniversityGroups")) {
    console.log("Found university-groups references in HTML");
  }
  
  // Check for 404 or error text
  if (bodyText.includes("404") || bodyText.includes("Not Found") || bodyText.includes("Cannot") || bodyText.includes("error")) {
    console.log("ERROR page detected in text content!");
  }
  
  await page.screenshot({ path: "C:/Users/narad/Programming/GetContactAI/_playwright_test/01_initial.png" });
  console.log("Screenshot saved: 01_initial.png");
  
  await browser.close();
  console.log("Done");
})().catch(err => {
  console.error("ERROR:", err.message);
  process.exit(1);
});
