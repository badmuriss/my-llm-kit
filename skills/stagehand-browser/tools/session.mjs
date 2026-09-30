import { localBrowser, Stagehand } from '@browserbasehq/stagehand';
import { setTimeout as delay } from 'node:timers/promises';

async function closeChromeGracefully(cdpUrl) {
  const pid = await new Promise((resolve, reject) => {
    const socket = new WebSocket(cdpUrl);
    let browserPid;
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error('Owned Chrome did not finish its graceful shutdown.'));
    }, 5000);
    socket.onopen = () => {
      socket.send(JSON.stringify({ id: 1, method: 'SystemInfo.getProcessInfo' }));
    };
    socket.onmessage = ({ data }) => {
      const response = JSON.parse(data);
      if (response.id !== 1) return;
      browserPid = response.result?.processInfo?.find(info => info.type === 'browser')?.id;
      if (!Number.isSafeInteger(browserPid) || browserPid <= 0) {
        clearTimeout(timer);
        socket.close();
        reject(new Error('Could not identify owned Chrome for graceful shutdown.'));
        return;
      }
      socket.send(JSON.stringify({ id: 2, method: 'Browser.close' }));
    };
    socket.onerror = () => {
      clearTimeout(timer);
      socket.close();
      reject(new Error('Could not gracefully close owned Chrome.'));
    };
    socket.onclose = () => {
      clearTimeout(timer);
      if (browserPid) resolve(browserPid);
      else reject(new Error('Owned Chrome connection closed before shutdown.'));
    };
  });
  // CDP disconnects before Chrome flushes its profile and exits.
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    try { process.kill(pid, 0); }
    catch (error) { if (error.code === 'ESRCH') return; throw error; }
    await delay(50);
  }
  throw new Error('Owned Chrome remained alive after Browser.close.');
}

/** Owns Chrome; its private CDP endpoint may be shared only with authorized tools. */
export async function openSession({ executablePath, userDataDir, headless = true, port } = {}) {
  const browser = await localBrowser.launch({ headless, executablePath, userDataDir, port });
  let stagehand;
  let page;
  try {
    stagehand = await Stagehand.create({
      browser,
      logging: { level: 'off' },
      // v4.1 has no telemetry-off flag. Keep traces off external services.
      telemetry: { traces: { endpoint: 'http://127.0.0.1:9/v1/traces' } },
    });
    page = await browser.context.newPage();
  } catch (error) {
    try { await stagehand?.close(); } finally { await browser.close(); }
    throw error;
  }
  const cdpUrl = stagehand.rpcClient.browserWebSocketDebuggerUrl;
  let closing;
  return {
    page,
    context: browser.context,
    cdpUrl,
    async close() {
      closing ??= (async () => {
        try { await stagehand.close(); }
        finally {
          // SDK process termination alone can lose newly written cookies.
          try { await closeChromeGracefully(cdpUrl); }
          finally { await browser.close(); }
        }
      })();
      return closing;
    },
  };
}
