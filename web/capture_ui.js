const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

async function capture() {
  const screenshotsDir = path.resolve('..', 'screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  console.log('Launching headless Chrome...');
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,1050'],
    defaultViewport: { width: 1440, height: 1050, deviceScaleFactor: 1.5 },
  });

  const page = await browser.newPage();

  // 1. Audit Run with GPT-4o (rl_key_2828a6c8c1f2428c)
  console.log('Capturing Audit with GPT-4o model...');
  await page.goto('http://localhost:3000/raglens?key=rl_key_2828a6c8c1f2428c', {
    waitUntil: 'domcontentloaded',
    timeout: 15000,
  });
  await new Promise((r) => setTimeout(r, 2500));

  await page.screenshot({
    path: path.join(screenshotsDir, '01_lighthouse_audit_gpt4o.png'),
    fullPage: true,
  });
  console.log('Saved: 01_lighthouse_audit_gpt4o.png');

  // 2. Audit Run with Gemini 1.5 Pro (rl_key_10471fa03d0241e0)
  console.log('Capturing Audit with Gemini 1.5 Pro model...');
  await page.goto('http://localhost:3000/raglens?key=rl_key_10471fa03d0241e0', {
    waitUntil: 'domcontentloaded',
    timeout: 15000,
  });
  await new Promise((r) => setTimeout(r, 2500));

  await page.screenshot({
    path: path.join(screenshotsDir, '02_lighthouse_audit_gemini.png'),
    fullPage: true,
  });
  console.log('Saved: 02_lighthouse_audit_gemini.png');

  // 3. Expand Opportunity Code Blueprint
  console.log('Capturing Opportunity Code Blueprint...');
  try {
    const viewFixBtn = await page.evaluateHandle(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.find((b) => b.textContent && b.textContent.includes('View Fix'));
    });
    if (viewFixBtn && viewFixBtn.asElement()) {
      await viewFixBtn.asElement().click();
      await new Promise((r) => setTimeout(r, 600));
    }
  } catch (e) {
    console.warn('Could not click View Fix button:', e.message);
  }

  await page.screenshot({
    path: path.join(screenshotsDir, '03_opportunities_expanded.png'),
    fullPage: true,
  });
  console.log('Saved: 03_opportunities_expanded.png');

  // 4. Open PostgreSQL History Drawer
  console.log('Capturing PostgreSQL History Drawer...');
  try {
    const historyBtn = await page.evaluateHandle(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.find((b) => b.textContent && b.textContent.includes('Audit History'));
    });
    if (historyBtn && historyBtn.asElement()) {
      await historyBtn.asElement().click();
      await new Promise((r) => setTimeout(r, 800));
    }
  } catch (e) {
    console.warn('Could not click Audit History button:', e.message);
  }

  await page.screenshot({
    path: path.join(screenshotsDir, '04_postgresql_history_drawer.png'),
    fullPage: false,
  });
  console.log('Saved: 04_postgresql_history_drawer.png');

  // 5. Offline HTML Report Screenshot
  console.log('Capturing Offline HTML Report...');
  const offlineHtmlPath = 'file:///' + path.resolve('..', 'artifacts', 'reports', 'raglens_latest.html').replace(/\\/g, '/');
  await page.goto(offlineHtmlPath, { waitUntil: 'domcontentloaded', timeout: 10000 });
  await new Promise((r) => setTimeout(r, 1500));

  await page.screenshot({
    path: path.join(screenshotsDir, '05_offline_lighthouse_html_report.png'),
    fullPage: true,
  });
  console.log('Saved: 05_offline_lighthouse_html_report.png');

  await browser.close();
  console.log('All screenshots successfully captured into screenshots/ folder!');
}

capture().catch((err) => {
  console.error('Failed to capture screenshots:', err);
  process.exit(1);
});
