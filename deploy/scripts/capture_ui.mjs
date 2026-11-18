import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const base = 'http://127.0.0.1:5173';
const out = 'var/screens';
await mkdir(out, { recursive: true });

const browser = await chromium.launch();
const viewports = [
  { width: 360, height: 800, name: '360' },
  { width: 768, height: 900, name: '768' },
  { width: 1280, height: 900, name: '1280' },
];

for (const viewport of viewports) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.screenshot({ path: `${out}/login-${viewport.name}.png`, fullPage: true });

  if (viewport.name === '1280') {
    await page.keyboard.press('Tab');
    const focus = await page.evaluate(() => {
      const el = document.activeElement;
      const style = el ? getComputedStyle(el) : null;
      return {
        tag: el?.tagName,
        text: (el?.textContent ?? '').trim().slice(0, 30),
        outlineWidth: style?.outlineWidth,
        boxShadow: style?.boxShadow,
      };
    });
    console.log('keyboard focus:', JSON.stringify(focus));
  }

  await page.getByLabel('账号').fill('admin');
  await page.getByLabel('密码').fill('admin123');
  await page.getByRole('button', { name: '安全登录' }).click();
  await page.waitForURL(`${base}/`);
  await page.screenshot({ path: `${out}/home-${viewport.name}.png`, fullPage: true });

  for (const route of ['search', 'documents', 'admin']) {
    await page.goto(`${base}/${route}`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${out}/${route}-${viewport.name}.png`, fullPage: true });
  }
  await context.close();
}

await browser.close();
console.log('screenshots written to var/screens');
