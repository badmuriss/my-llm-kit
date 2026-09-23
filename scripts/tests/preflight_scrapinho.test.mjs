import { createServer } from 'node:http';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { preflight } from '../../skills/research/scripts/preflight_scrapinho_mcp.mjs';

async function fixture(run, { missingTool = false, unavailable = false, redirect = false } = {}) {
  const calls = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    calls.push({ path: request.url, authorization: request.headers.authorization });
    if (redirect) {
      response.writeHead(302, { location: '/credential-trap' }).end();
      return;
    }
    if (request.headers.authorization !== 'Bearer fixture-key') {
      response.writeHead(401).end('private error details');
      return;
    }
    const message = JSON.parse(Buffer.concat(chunks).toString());
    calls.at(-1).method = message.method;
    let result;
    if (message.method === 'initialize') result = { protocolVersion: '2025-11-25' };
    if (message.method === 'tools/list') result = { tools: (missingTool ? ['scraper_submit'] : ['scraper_capabilities', 'scraper_usage', 'scraper_submit', 'scraper_get', 'scraper_cancel', 'scraper_read_source']).map(name => ({ name })) };
    if (message.method === 'tools/call') {
      assert.equal(message.params.name, 'scraper_capabilities');
      result = { structuredContent: { operations: [{ operation: 'fetch.page', available: !unavailable, target_policy: 'public_hosts', modes: ['static', 'browser'] }] } };
    }
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify({ jsonrpc: '2.0', id: message.id, result }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try { await run({ baseUrl: `http://127.0.0.1:${server.address().port}`, apiKey: 'fixture-key' }, calls); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

test('verifies authenticated page capability without submitting an acquisition', async () => {
  await fixture(async (options, calls) => {
    const result = await preflight(options);
    assert.equal(result.scope, 'fetch.page');
    assert.deepEqual(calls.map(call => call.method), ['initialize', 'tools/list', 'tools/call']);
  });
});

test('rejects failed auth without exposing the service body', async () => {
  await fixture(async options => {
    await assert.rejects(preflight({ ...options, apiKey: 'wrong' }), { message: 'service_http_401' });
  });
});

test('rejects a catalog that cannot support the migrated workflow', async () => {
  await fixture(async options => {
    await assert.rejects(preflight(options), { message: 'missing_required_tools' });
  }, { missingTool: true });
  await fixture(async options => {
    await assert.rejects(preflight(options), { message: 'public_page_acquisition_unavailable' });
  }, { unavailable: true });
});

test('refuses redirects without forwarding bearer credentials', async () => {
  await fixture(async (options, calls) => {
    await assert.rejects(preflight(options), { message: 'service_connection_failed' });
    assert.deepEqual(calls.map(call => call.path), ['/mcp']);
  }, { redirect: true });
});
