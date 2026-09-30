import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { openSession } from './session.mjs';

const evidence = resolve(process.argv[2] ?? '.visual-evidence/stagehand-browser');
await mkdir(evidence, { recursive: true });
const saves = [];
const html = `<!doctype html><meta charset="utf-8"><title>Stagehand integration</title>
<style>body{font:20px system-ui;max-width:680px;margin:60px auto;color:#17232e}label{display:block;margin:20px 0}input,select,button{font:inherit;padding:10px}output{display:block;margin-top:24px;color:#146b38}</style>
<h1>Browser integration check</h1><form><label>Name <input id="name" required></label>
<label>Plan <select id="plan"><option>Basic</option><option>Pro</option></select></label>
<button id="save">Save</button></form><output></output>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();
const name=document.querySelector('#name').value,plan=document.querySelector('#plan').value;
const response=await fetch('/save',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name,plan})});
if(response.ok){const output=document.querySelector('output');output.textContent='Saved: '+name+' / '+plan;output.dataset.saved='true'}};</script>`;
const server = createServer(async (request, response) => {
  if (request.url === '/save' && request.method === 'POST') {
    let body = '';
    for await (const chunk of request) body += chunk;
    saves.push(JSON.parse(body));
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end('{"saved":true}');
    return;
  }
  response.writeHead(200, { 'content-type': 'text/html' });
  response.end(html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}`;
let session;
const profile = await mkdtemp(join(tmpdir(), 'kit-stagehand-profile-'));
try {
  session = await openSession({ executablePath: process.env.STAGEHAND_CHROME_PATH });
  const { page } = session;
  const response = await page.goto(url, { waitUntil: 'load', timeout: 15000 });
  assert.equal(response.status(), 200);
  assert.equal(await page.waitForSelector('#name', { state: 'visible', timeout: 5000 }), true);
  await page.locator('#name').fill('Stagehand test');
  await page.locator('#plan').selectOption('Pro');
  await page.locator('#save').click();
  assert.equal(await page.waitForSelector('[data-saved="true"]', { timeout: 5000 }), true);
  assert.equal(await page.locator('output').innerText(), 'Saved: Stagehand test / Pro');
  assert.deepEqual(saves, [{ name: 'Stagehand test', plan: 'Pro' }]);
  const extracted = await page.evaluate(() => ({ name: document.querySelector('#name').value, plan: document.querySelector('#plan').value }));
  assert.deepEqual(extracted, saves[0]);
  await assert.rejects(page.waitForSelector('#not-present', { timeout: 100 }), /Timeout/);
  await assert.rejects(page.locator('#not-present').click());
  const snapshot = await page.snapshot();
  assert.match(snapshot.formattedTree, /Saved: Stagehand test/);
  await page.setViewportSize(1366, 768);
  const png = await page.screenshot({ path: resolve(evidence, 'saved.png'), type: 'png', scale: 'css' });
  assert.equal(Buffer.from(png).readUInt32BE(16), 1366);
  assert.equal(Buffer.from(png).readUInt32BE(20), 768);
  await session.close();
  session = undefined;

  session = await openSession({ userDataDir: profile });
  await session.page.goto(url);
  await session.page.evaluate(() => {
    document.cookie = 'synthetic-session=retained; path=/; max-age=3600';
    localStorage.setItem('synthetic-login', 'retained');
  });
  await session.close();
  session = await openSession({ userDataDir: profile });
  await session.page.goto(url);
  assert.equal(await session.page.evaluate(() => document.cookie), 'synthetic-session=retained');
  assert.equal(await session.page.evaluate(() => localStorage.getItem('synthetic-login')), 'retained');
  await session.close();
  session = undefined;
  const result = {
    sdk: '@browserbasehq/stagehand@4.1.0', browser: 'local Chrome',
    navigation: true, interaction: true, extraction: true, serverSideSave: true,
    missingSelectorFails: true, borrowedCdpAttachment: 'disabled: upstream close terminates host browser',
    retainedSyntheticCookie: true, retainedLocalStorage: true, separateModelRequests: 0,
    screenshot: 'saved.png', screenshotSha256: createHash('sha256').update(png).digest('hex'),
    viewport: { width: 1366, height: 768 },
    visualInspection: 'pending', windows: 'unverified', webkit: 'unsupported', firefox: 'unsupported',
  };
  await writeFile(resolve(evidence, 'result.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally {
  try { await session?.close(); }
  finally {
    await rm(profile, { recursive: true, force: true });
    await new Promise(resolve => server.close(resolve));
  }
}
