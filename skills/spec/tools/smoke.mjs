// Real renderer integration: no model calls or production project state.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer';

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = path.dirname(here);
const output = path.resolve(process.env.VISUAL_OUTPUT || '.visual-evidence/mermaid');
const browserPath = process.env.CHROME_PATH || '/usr/bin/google-chrome';
await mkdir(output, { recursive: true });
const html = path.join(output, 'spec-mermaid.html');
const pdf = path.join(output, 'spec-mermaid.pdf');
const args = [path.join(spec, 'scripts/render_visual_brief.py'), path.join(spec, 'assets/visual-brief-example.md'), '--output', html];
function python(extra = []) {
  const result = spawnSync('python3', [...args, ...extra], { encoding: 'utf8', timeout: 240_000 });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}\n${result.error || ''}`);
}
python(['--mmdc', path.join(here, 'node_modules/.bin/mmdc'), '--browser', browserPath, '--pdf', pdf]);
python(['--check']);
assert.equal((await readFile(pdf)).subarray(0, 5).toString(), '%PDF-');
const document = await readFile(html, 'utf8');
assert.equal(document.includes('<script'), false);
assert.equal(document.includes('src="https:'), false);
const browser = await puppeteer.launch({ executablePath: browserPath, args: ['--disable-background-networking'] });
try {
  const page = await browser.newPage();
  const requests = [];
  await page.setRequestInterception(true);
  page.on('request', request => {
    if (/^https?:/.test(request.url())) {
      requests.push(request.url());
      request.abort();
    } else request.continue();
  });
  await page.setJavaScriptEnabled(false);
  for (const [name, width, height] of [['desktop', 1920, 1080], ['notebook', 1366, 768], ['tablet-chromium', 810, 1080], ['mobile-chromium', 390, 664]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(html).href, { waitUntil: 'networkidle0' });
    const layout = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      images: Array.from(document.querySelectorAll('img')).map(image => image.complete && image.naturalWidth > 0),
    }));
    assert.equal(layout.overflow, false, `${name} has document overflow`);
    assert.deepEqual(layout.images, [true, true], `${name} has missing Mermaid images`);
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  }
  await page.setViewport({ width: 1366, height: 768, deviceScaleFactor: 1 });
  const figures = await page.$$('figure.diagram');
  for (let i = 0; i < figures.length; i++) await figures[i].screenshot({ path: path.join(output, `diagram-${i + 1}.png`) });
  assert.deepEqual(requests, []);
  const details = await page.$('details.diagram-source summary');
  await details.click();
  assert.equal(await page.$eval('details.diagram-source', element => element.open), true);
  await writeFile(path.join(output, 'checks.json'), JSON.stringify({
    status: 'passed', mermaidImages: 2, externalRequests: requests.length,
    browser: await browser.version(), responsiveEngine: 'Chromium',
    webkit: 'unverified', visualInspection: 'required separately',
  }, null, 2));
} finally {
  await browser.close();
}
