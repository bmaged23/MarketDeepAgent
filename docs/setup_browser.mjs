import './browser-platform.mjs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const cli = fileURLToPath(new URL('node_modules/playwright/cli.js', import.meta.url));
const result = spawnSync(process.execPath, [cli, 'install', 'chromium', ...process.argv.slice(2)], {
  stdio: 'inherit', env: process.env
});
if (result.error) console.error(`Browser installer could not start: ${result.error.message}`);
process.exit(result.status ?? 1);
