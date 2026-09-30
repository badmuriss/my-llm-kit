import { mkdir, readFile, realpath, stat, symlink, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { spawnSync } from 'node:child_process';

const { values } = parseArgs({ options: {
  home: { type: 'string', default: homedir() },
  'dry-run': { type: 'boolean', default: false },
} });
const tools = dirname(fileURLToPath(import.meta.url));
const skill = dirname(tools);
const canonical = join(values.home, '.agents', 'skills', 'stagehand-browser');
const ompAgent = join(values.home, '.omp', 'agent');
const extension = join(ompAgent, 'extensions', 'stagehand-browser.mjs');
const loader = `export { default } from ${JSON.stringify(pathToFileURL(join(tools, 'omp-extension.mjs')).href)};\n`;

async function existing(path) {
  try { return await readFile(path, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return undefined; throw error; }
}

try {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 22 || (major === 22 && minor < 18)) throw new Error('Stagehand requires Node >=22.18.0.');
  try {
    if (await realpath(canonical) !== await realpath(skill)) throw new Error('User-owned stagehand-browser skill exists; left unchanged.');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const withOmp = await stat(ompAgent).then(info => info.isDirectory()).catch(error => {
    if (error.code === 'ENOENT') return false;
    throw error;
  });
  const previous = withOmp ? await existing(extension) : undefined;
  if (previous !== undefined && previous !== loader) throw new Error('User-owned Stagehand extension exists; left unchanged.');
  if (values['dry-run']) {
    console.log(`Stagehand: npm ci in installed skill, skill link${withOmp ? ', OMP extension' : ''}; no model/MCP/auth changes.`);
  } else {
    const installed = spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm',
      ['ci', '--ignore-scripts', '--no-audit', '--no-fund'],
      { cwd: tools, stdio: 'inherit', shell: process.platform === 'win32' });
    if (installed.error || installed.status !== 0) throw new Error('Stagehand dependency installation failed.');
    await mkdir(dirname(canonical), { recursive: true });
    try { await symlink(skill, canonical, process.platform === 'win32' ? 'junction' : 'dir'); }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
    if (withOmp) {
      await mkdir(dirname(extension), { recursive: true });
      if (previous === undefined) await writeFile(extension, loader, { flag: 'wx', mode: 0o600 });
    }
    console.log(`Stagehand scripts installed. ${withOmp ? 'Reload OMP extensions or start a new session. ' : ''}Chrome must already be installed.`);
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
