const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const script = path.resolve(__dirname, '../tools/push-live.sh');
function publish(t, failures) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'publish-retry-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.writeFileSync(path.join(dir, 'git'), `#!/usr/bin/env node
const fs = require('node:fs');
const file = process.env.PUSH_CALLS;
fs.appendFileSync(file, JSON.stringify(process.argv.slice(2)) + '\\n');
const count = fs.readFileSync(file, 'utf8').trim().split('\\n').length;
const message = JSON.parse(process.env.PUSH_FAILURES)[count - 1];
if (message) { console.error(message); process.exit(1); }
`, { mode: 0o755 });
  fs.writeFileSync(path.join(dir, 'sleep'), '#!/bin/sh\nprintf "%s\\n" "$1" >> "$PUSH_DELAYS"\n', { mode: 0o755 });
  const calls = path.join(dir, 'calls'), delays = path.join(dir, 'delays');
  const result = spawnSync('bash', [script, 'publish'], {
    encoding: 'utf8',
    env: { ...process.env, PATH: `${dir}:${process.env.PATH}`, PUSH_CALLS: calls,
      PUSH_DELAYS: delays, PUSH_FAILURES: JSON.stringify(failures) },
  });
  assert.ifError(result.error);
  return { ...result, calls: fs.readFileSync(calls, 'utf8').trim().split('\n').map(JSON.parse),
    delays: fs.existsSync(delays) ? fs.readFileSync(delays, 'utf8').trim().split('\n') : [] };
}

test('successful publication pushes only the live-data ref without sleeping', t => {
  const r = publish(t, []);
  assert.equal(r.status, 0);
  assert.deepEqual(r.calls, [['push', '-q', '-f', 'publish', 'HEAD:refs/heads/live-data']]);
  assert.deepEqual(r.delays, []);
});
test('temporary server errors back off and recover on the third attempt', t => {
  const r = publish(t, ['remote: Internal Server Error', 'fatal: HTTP 503']);
  assert.equal(r.status, 0);
  assert.equal(r.calls.length, 3);
  assert.deepEqual(r.delays, ['10', '20']);
});
test('exhausted temporary failures remain a failed publication', t => {
  const r = publish(t, Array(3).fill('fatal: Connection reset by peer'));
  assert.equal(r.status, 1);
  assert.equal(r.calls.length, 3);
  assert.deepEqual(r.delays, ['10', '20']);
  assert.match(r.stdout, /::error::/);
});
for (const message of ['fatal: Authentication failed', 'remote: GH006: Protected branch update failed', 'fatal: unknown error']) {
  test(`permanent failure stops immediately: ${message}`, t => {
    const r = publish(t, [message]);
    assert.equal(r.status, 1);
    assert.equal(r.calls.length, 1);
    assert.deepEqual(r.delays, []);
  });
}
