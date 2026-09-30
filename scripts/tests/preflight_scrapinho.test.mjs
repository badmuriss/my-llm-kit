import { mkdtemp, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createServer } from 'node:http';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { preflight } from '../../skills/research/scripts/preflight_scrapinho_mcp.mjs';
const fetchPageSchema = {
  type: 'object',
  properties: {
    schema_version: { type: 'number', const: 1, default: 1 },
    project_scope: { type: 'string' },
    operation: { type: 'string', const: 'fetch.page' },
    input: { type: 'object', required: ['url'] },
    execution: { type: 'string', default: 'static', enum: ['static', 'browser', 'auto'] },
    locale: {
      type: 'object',
      properties: { language: { type: 'string', default: 'pt-BR' }, country: { type: 'string', default: 'BR' } },
      required: ['language', 'country'],
    },
    proxy: {
      type: 'object',
      properties: { country: { type: 'string', default: 'BR' }, mode: { type: 'string', default: 'rotating' } },
      required: ['country', 'mode'],
    },
    limits: {
      type: 'object',
      properties: {
        timeout_ms: { type: 'integer', default: 120000 },
        attempts: { type: 'integer', default: 3 },
        response_bytes: { type: 'integer', default: 2097152 },
        browser_bytes: { type: 'integer', default: 10485760 },
        browser_ms: { type: 'integer', default: 45000 },
      },
      required: ['timeout_ms', 'attempts', 'response_bytes', 'browser_bytes', 'browser_ms'],
    },
    cache: {
      type: 'object',
      properties: { mode: { type: 'string', default: 'default' }, max_age_s: { type: 'integer', default: 900 } },
      required: ['mode', 'max_age_s'],
    },
  },
  required: ['schema_version', 'project_scope', 'operation', 'input', 'execution', 'locale', 'proxy', 'limits', 'cache'],
};

async function fixture(run, { missingTool = false, unavailable = false, redirect = false, missingDefaults = false } = {}) {
  const calls = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    calls.push({ path: request.url, authorization: request.headers.authorization, toolName: undefined });
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
    calls.at(-1).toolName = message.params?.name;
    let result;
    if (message.method === 'initialize') result = { protocolVersion: '2025-11-25' };
    if (message.method === 'tools/list') {
      const schema = structuredClone(fetchPageSchema);
      if (missingDefaults) delete schema.properties.proxy.properties.country.default;
      const tools = (missingTool ? ['scraper_submit'] : ['scraper_capabilities', 'scraper_usage', 'scraper_submit', 'scraper_get', 'scraper_cancel', 'scraper_read_source'])
        .map(name => name === 'scraper_submit' ? { name, inputSchema: { anyOf: [{ properties: { request: { oneOf: [schema] } } }] } } : { name });
      result = { tools };
    }
    if (message.method === 'tools/call') {
      if (message.params.name === 'scraper_submit') {
        const request = message.params.arguments?.request;
        if (request?.proxy?.country !== 'BR') {
          response.writeHead(422).end('capability_unavailable');
          return;
        }
        result = { structuredContent: { accepted: true } };
      } else {
        assert.equal(message.params.name, 'scraper_capabilities');
        result = { structuredContent: { operations: [{ operation: 'fetch.page', available: !unavailable, target_policy: 'public_hosts', modes: ['static', 'browser'] }] } };
      }
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
  await fixture(async (_options, calls) => {
    const result = await preflight(_options);
    assert.equal(result.scope, 'fetch.page');
    assert.equal(calls.some(call => call.toolName === 'scraper_submit'), false);
  });
});
test('accepts schema defaults and rejects an unsupported geographic override', async () => {
  await fixture(async options => {
    const result = await preflight(options);
    const request = { ...result.requestDefaults, project_scope: 'fixture', input: { url: 'https://example.com' } };
    const submit = body => fetch(`${options.baseUrl}/mcp`, {
      method: 'POST',
      headers: { authorization: `Bearer ${options.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 99, method: 'tools/call', params: { name: 'scraper_submit', arguments: { request: body } } }),
    });
    assert.equal((await submit(request)).status, 200);
    assert.equal((await submit({ ...request, proxy: { ...request.proxy, country: 'US' } })).status, 422);
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

test('rejects a fetch workflow when required schema defaults are absent', async () => {
  await fixture(async options => {
    await assert.rejects(preflight(options), { message: 'fetch_page_defaults_unavailable' });
  }, { missingDefaults: true });
});

test('refuses redirects without forwarding bearer credentials', async () => {
  await fixture(async (options, calls) => {
    await assert.rejects(preflight(options), { message: 'service_connection_failed' });
    assert.deepEqual(calls.map(call => call.path), ['/mcp']);
  }, { redirect: true });
});


test('executes the CLI through an installed skill symlink', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'scrapinho-preflight-'));
  const installed = join(directory, 'installed.mjs');
  try {
    await symlink(fileURLToPath(new URL('../../skills/research/scripts/preflight_scrapinho_mcp.mjs', import.meta.url)), installed);
    await fixture(async options => {
      const { stdout } = await promisify(execFile)(process.execPath, [installed], { env: { ...process.env, SCRAPINHO_BASE_URL: options.baseUrl, SCRAPINHO_API_KEY: options.apiKey }, timeout: 5000 });
      assert.equal(JSON.parse(stdout).scope, 'fetch.page');
    });
  } finally { await rm(directory, { recursive: true, force: true }); }
});
