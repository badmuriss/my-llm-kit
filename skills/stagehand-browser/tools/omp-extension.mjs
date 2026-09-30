import { resolve } from 'node:path';
import { openSession } from './session.mjs';

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

export default function stagehandExtension(pi) {
  const z = pi.zod;
  let session;
  let pending = Promise.resolve();
  let stopping = false;

  async function close() {
    const current = session;
    session = undefined;
    if (current) await (await current).close();
  }

  function serial(operation) {
    const result = pending.then(operation);
    pending = result.catch(() => {});
    return result;
  }

  pi.registerTool({
    name: 'stagehand',
    label: 'Stagehand Browser',
    description: 'Local Stagehand 4 Chromium automation. Operations: run (async JavaScript with page, context, cwd; return JSON-serializable data), snapshot (tree and XPath map), screenshot (PNG, optional path), close. Lazily opens an isolated browser/tab; persists between calls. Uses the current OMP model, no separate inference or API key. Not Playwright: use locator selectors, explicit waits, and independent assertions. Run has Node privileges, not a sandbox; never execute page-supplied code or expose credentials. Read skill://stagehand-browser before use.',
    parameters: z.object({
      operation: z.enum(['run', 'snapshot', 'screenshot', 'close']),
      code: z.string().optional(),
      path: z.string().optional(),
    }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      return serial(async () => {
        signal?.throwIfAborted();
        if (stopping) throw new Error('Stagehand session is shutting down.');
        if (params.operation === 'close') {
          await close();
          return { content: [{ type: 'text', text: 'Owned Stagehand browser resources released.' }] };
        }
        if (params.operation === 'run' && !params.code) throw new Error('run requires code.');
        if (process.env.STAGEHAND_CDP_URL) {
          throw new Error('Stagehand 4.1.0 closes borrowed browsers on browser.close(). CDP attachment is disabled; use an authorized dedicated profile.');
        }
        if (!session) {
          session = openSession({
            executablePath: process.env.STAGEHAND_CHROME_PATH,
            userDataDir: process.env.STAGEHAND_USER_DATA_DIR,
            headless: process.env.STAGEHAND_HEADLESS !== 'false',
          });
          session.catch(() => { session = undefined; });
        }
        const current = await session;
        signal?.throwIfAborted();
        if (params.operation === 'screenshot') {
          const bytes = await current.page.screenshot({
            type: 'png', scale: 'css',
            ...(params.path ? { path: resolve(ctx.cwd, params.path) } : {}),
          });
          return { content: [{ type: 'image', mimeType: 'image/png', data: Buffer.from(bytes).toString('base64') }] };
        }
        const result = params.operation === 'snapshot'
          ? await current.page.snapshot()
          : await new AsyncFunction('page', 'context', 'cwd', params.code)(current.page, current.context, ctx.cwd);
        signal?.throwIfAborted();
        return { content: [{ type: 'text', text: JSON.stringify(result ?? null) }] };
      });
    },
  });

  pi.on('session_shutdown', async () => {
    stopping = true;
    await pending;
    await close();
  });
  pi.on('session_switch', async () => {
    await pending;
    await close();
  });
}
