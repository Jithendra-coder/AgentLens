const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function capture() {
  const screenshotsDir = path.resolve(__dirname, '..', 'screenshots');
  fs.mkdirSync(screenshotsDir, { recursive: true });

  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,1050'],
  });

  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
      deviceScaleFactor: 1.5,
    });

    const captures = [
      [process.env.RAGLENS_GPT4O_KEY, '01_lighthouse_audit_gpt4o.png'],
      [process.env.RAGLENS_GEMINI_KEY, '02_lighthouse_audit_gemini.png'],
    ];
    for (const [key, filename] of captures) {
      if (!key) throw new Error(`Set the key used for ${filename} in the environment.`);
      const url = `http://localhost:3000/raglens?key=${encodeURIComponent(key)}`;
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForTimeout(2500);
      await page.screenshot({ path: path.join(screenshotsDir, filename), fullPage: true });
      console.log(`Saved: ${filename}`);
    }

    for (const [label, filename, fullPage] of [
      ['View Fix', '03_opportunities_expanded.png', true],
      ['Audit History', '04_postgresql_history_drawer.png', false],
    ]) {
      try {
        await page.getByRole('button', { name: new RegExp(label) }).first().click({ timeout: 1500 });
        await page.waitForTimeout(600);
      } catch (error) {
        console.warn(`Could not open ${label}: ${error.message}`);
      }
      await page.screenshot({ path: path.join(screenshotsDir, filename), fullPage });
      console.log(`Saved: ${filename}`);
    }

    const reportPath = path.resolve(__dirname, '..', 'artifacts', 'reports', 'raglens_latest.html');
    await page.goto(pathToFileURL(reportPath).href, { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(1500);
    const filename = '05_offline_lighthouse_html_report.png';
    await page.screenshot({ path: path.join(screenshotsDir, filename), fullPage: true });
    console.log(`Saved: ${filename}`);
  } finally {
    await browser.close();
  }
}

capture().catch((error) => {
  console.error('Failed to capture screenshots:', error);
  process.exitCode = 1;
});
