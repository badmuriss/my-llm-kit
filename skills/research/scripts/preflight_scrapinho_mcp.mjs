import { pathToFileURL } from 'node:url';
import { realpathSync } from 'node:fs';

const REQUIRED_TOOLS = ['scraper_capabilities', 'scraper_usage', 'scraper_submit', 'scraper_get', 'scraper_cancel', 'scraper_read_source'];
const CALLER_FIELDS = new Set(['input', 'project_scope', 'client_request_id']);

function requiredDefaults(schema) {
  if (!schema || schema.type !== 'object' || !Array.isArray(schema.required) || !schema.properties) throw new Error('fetch_page_defaults_unavailable');
  const defaults = {};
  for (const name of schema.required) {
    if (CALLER_FIELDS.has(name)) continue;
    const property = schema.properties[name];
    if (!property) throw new Error('fetch_page_defaults_unavailable');
    if (Object.hasOwn(property, 'default')) {
      defaults[name] = property.default;
      continue;
    }
    if (Object.hasOwn(property, 'const')) {
      defaults[name] = property.const;
      continue;
    }
    if (property.type === 'object') {
      defaults[name] = requiredDefaults(property);
      continue;
    }
    throw new Error('fetch_page_defaults_unavailable');
  }
  return defaults;
}

function findFetchPageSchema(tool) {
  for (const branch of tool.inputSchema?.anyOf ?? []) {
    for (const request of branch.properties?.request?.oneOf ?? []) {
      if (request.properties?.operation?.const === 'fetch.page') return request;
    }
  }
  throw new Error('fetch_page_defaults_unavailable');
}

export async function preflight({ baseUrl = 'https://scrapinho.dev', apiKey }) {
  if (!apiKey) throw new Error('SCRAPINHO_API_KEY missing');
  const url = new URL(baseUrl);
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(loopback && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash) {
    throw new Error('invalid_service_url');
  }
  const signal = AbortSignal.timeout(30_000);
  let id = 0;
  async function rpc(method, params) {
    const requestId = ++id;
    let response;
    try {
      response = await fetch(baseUrl.replace(/\/$/, '') + '/mcp', {
        method: 'POST', redirect: 'error', signal,
        headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id: requestId, method, params }),
      });
    } catch { throw new Error('service_connection_failed'); }
    if (!response.ok) {
      await response.body?.cancel();
      throw new Error(`service_http_${response.status}`);
    }
    let message;
    try { message = await response.json(); } catch { throw new Error('invalid_rpc_response'); }
    if (message.id !== requestId || message.jsonrpc !== '2.0' || message.error || !message.result) throw new Error('invalid_rpc_response');
    return message.result;
  }
  const initialized = await rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'my-llm-kit-preflight', version: '1.0.0' } });
  if (initialized.protocolVersion !== '2025-11-25') throw new Error('unsupported_protocol');
  const listed = await rpc('tools/list', {});
  if (!Array.isArray(listed.tools) || REQUIRED_TOOLS.some(name => !listed.tools.some(tool => tool.name === name))) throw new Error('missing_required_tools');
  const submitTool = listed.tools.find(tool => tool.name === 'scraper_submit');
  const pageSchema = findFetchPageSchema(submitTool);
  const requestDefaults = requiredDefaults(pageSchema);
  const result = await rpc('tools/call', { name: 'scraper_capabilities', arguments: {} });
  const page = result.structuredContent?.operations?.find(operation => operation.operation === 'fetch.page');
  if (result.isError || !page?.available || page.target_policy !== 'public_hosts' || !['static', 'browser'].every(mode => page.modes?.includes(mode))) throw new Error('public_page_acquisition_unavailable');
  return { scope: 'fetch.page', authenticated: true, modes: ['static', 'browser'], requestDefaults, acquisitions: 0 };
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  try {
    console.log(JSON.stringify(await preflight({ baseUrl: process.env.SCRAPINHO_BASE_URL, apiKey: process.env.SCRAPINHO_API_KEY })));
  } catch (error) {
    console.error(error instanceof Error ? error.message : 'preflight_failed');
    process.exitCode = 1;
  }
}
