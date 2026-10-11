import { readFileSync } from 'node:fs';
import { arch, platform } from 'node:os';

export function browserPlatformOverride(osName, architecture, release, configured) {
  if (configured || osName !== 'linux' || !['x64', 'arm64'].includes(architecture)) return configured;
  const id = release.match(/^ID=["']?([^\n"']+)/m)?.[1];
  const version = release.match(/^VERSION_ID=["']?([^\n"']+)/m)?.[1];
  // Playwright 1.56 has binaries for Ubuntu 24.04, but no Ubuntu 26.04 entry.
  if (id === 'ubuntu' && Number.parseInt(version, 10) >= 26) return `ubuntu24.04-${architecture}`;
  return undefined;
}
let release = '';
if (platform() === 'linux') {
  try { release = readFileSync('/etc/os-release', 'utf8'); } catch {}
}
const configured = process.env.PLAYWRIGHT_HOST_PLATFORM_OVERRIDE;
const override = browserPlatformOverride(platform(), arch(), release, configured);
if (override && !configured) {
  process.env.PLAYWRIGHT_HOST_PLATFORM_OVERRIDE = override;
  console.log(`Browser compatibility fallback: using Playwright's ${override} build on this Ubuntu release.`);
}
