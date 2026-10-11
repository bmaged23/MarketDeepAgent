const test = require('node:test');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');

test('Ubuntu fallback applies to 26.04 on install and recording, preserving user overrides', async () => {
  const {browserPlatformOverride} = await import(pathToFileURL(path.resolve(__dirname,'../../docs/browser-platform.mjs')).href);
  const ubuntu='ID=ubuntu\nVERSION_ID="26.04"\n';
  assert.equal(browserPlatformOverride('linux','x64',ubuntu), 'ubuntu24.04-x64');
  assert.equal(browserPlatformOverride('linux','arm64',ubuntu), 'ubuntu24.04-arm64');
  assert.equal(browserPlatformOverride('linux','x64',ubuntu,'debian13-x64'), 'debian13-x64');
  assert.equal(browserPlatformOverride('linux','x64','ID=ubuntu\nVERSION_ID="24.04"'),undefined);
  assert.equal(browserPlatformOverride('linux','x64','ID=debian\nVERSION_ID="13"'),undefined);
  assert.equal(browserPlatformOverride('win32','x64',ubuntu),undefined);
});
