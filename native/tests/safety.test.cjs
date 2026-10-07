const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const path = require('node:path');

function load(source, overrides = {}) {
  const exports = {};
  const context = { exports, require: id => overrides[id] || (id === './serverUrl' ? load('serverUrl.ts') : id === 'expo/fetch' ? { fetch: overrides.fetch } : require(id)), process: { env: {} }, URL, AbortController, setTimeout: overrides.setTimeout || setTimeout, clearTimeout, fetch: overrides.fetch, console };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', source), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, context);
  return exports;
}
function storageHarness() {
  const stored = new Map();
  const enrollments = [];
  let counter = 0;
  const paired = new Set();
  const api = load('api.ts', {
    'expo-secure-store': { getItemAsync: async key => stored.get(key) || null, setItemAsync: async (key, value) => { stored.set(key, value); }, deleteItemAsync: async key => { stored.delete(key); }, WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'locked' },
    'expo-crypto': { getRandomBytesAsync: async length => new Uint8Array(length).fill(++counter) },
    '@noble/curves/ed25519.js': { ed25519: { getPublicKey: seed => seed, sign: () => new Uint8Array(64) } },
    '@noble/hashes/sha2.js': { sha256: () => new Uint8Array(32) },
    '@noble/hashes/utils.js': { bytesToHex: bytes => Buffer.from(bytes).toString('hex'), hexToBytes: value => Uint8Array.from(Buffer.from(value, 'hex')), utf8ToBytes: value => Buffer.from(value) },
    fetch: async (url, options) => {
      if (url.endsWith('/enroll')) return new Promise(resolve => enrollments.push({ body: JSON.parse(options.body), resolve: () => { paired.add(JSON.parse(options.body).device_id); resolve({ ok: true, status: 200, json: async () => ({}) }); } }));
      if (url.endsWith('/api/me') && !paired.has(options.headers['X-Device-Id'])) return { ok: false, status: 401, json: async () => ({ detail: 'Device is not paired' }) };
      return { ok: true, status: 200, json: async () => ({ demo: false }) };
    },
  });
  return { api, enrollments };
}
async function until(check) { for (let i = 0; i < 100 && !check(); i++) await new Promise(resolve => setImmediate(resolve)); assert.ok(check(), 'operation reached enrollment'); }

test('approval slider accepts only deliberate horizontal single-finger releases', () => {
  const { completesApprovalDrag } = load('approvalGesture.ts');
  assert.equal(completesApprovalDrag(300, 240, 0, 1, 500), true);
  for (const gesture of [[0, 240, 0, 1, 500], [300, 180, 0, 1, 500], [300, 240, 40, 1, 500], [300, 240, 0, 2, 500], [300, 240, 0, 1, 50], [300, -240, 0, 1, 500]]) assert.equal(completesApprovalDrag(...gesture), false);
});
test('concurrent enrollments preserve both device keys even with reversed responses', async () => {
  const { api, enrollments } = storageHarness();
  const first = api.pair('a'.repeat(32), { service: 'first', label: 'First' });
  const second = api.pair('b'.repeat(32), { service: 'second', label: 'Second' });
  await until(() => enrollments.length === 2);
  assert.equal((await api.getConnections()).length, 2);
  enrollments[1].resolve(); await second;
  enrollments[0].resolve(); await first;
  const connections = await api.getConnections();
  assert.equal(connections.length, 2);
  assert.ok(connections.every(connection => !connection.pending));
});
test('late enrollment response cannot restore a device removed during enrollment', async () => {
  const { api, enrollments } = storageHarness();
  const pairing = api.pair('a'.repeat(32), { service: 'service', label: 'Service' });
  await until(() => enrollments.length === 1);
  await api.unlink(enrollments[0].body.device_id);
  enrollments[0].resolve(); await pairing;
  assert.equal((await api.getConnections()).length, 0);
});
test('pairing tokens reject foreign deep-link authorities and malformed values', () => {
  const { api } = storageHarness();
  const token = 'a'.repeat(32);
  assert.equal(api.pairingToken(`hooapprove://pair?token=${token}`), token);
  for (const value of ['hooapprove://other?token=' + token, 'short', 'https://other/?token=' + token]) assert.throws(() => api.pairingToken(value));
});

test('server origins exclude credentials, unexpected protocols and URL suffixes', () => {
  const { serverOrigin } = load('serverUrl.ts');
  assert.equal(serverOrigin('https://approve.example/'), 'https://approve.example');
  assert.equal(serverOrigin('http://127.0.0.1:8097'), 'http://127.0.0.1:8097');
  for (const url of ['https://user:password@approve.example', 'https://approve.example/api', 'https://approve.example?target=evil', 'https://approve.example#target', 'http://approve.example', 'file:///tmp/example']) assert.throws(() => serverOrigin(url));
});

test('pairing requests reject redirects and keep timeout active while reading the response body', async () => {
  let options;
  const api = load('api.ts', {
    './serverUrl': load('serverUrl.ts'),
    'expo-secure-store': {}, 'expo-crypto': {},
    '@noble/curves/ed25519.js': {}, '@noble/hashes/sha2.js': {}, '@noble/hashes/utils.js': {},
    setTimeout: callback => setTimeout(callback, 10),
    fetch: async (_, init) => {
      options = init;
      return { ok: true, status: 200, json: () => new Promise((resolve, reject) => { init.signal.addEventListener('abort', () => reject(new Error('aborted'))); }) };
    },
  });
  await assert.rejects(api.previewPairing('a'.repeat(32)), /aborted/);
  assert.equal(options.redirect, 'error');
  assert.equal(options.credentials, 'omit');
});

test('local recovery can remove pending keys but never forget a confirmed connection', async () => {
  const { api, enrollments } = storageHarness();
  const pairing = api.pair('a'.repeat(32), { service: 'service', label: 'Service' });
  await until(() => enrollments.length === 1);
  const id = enrollments[0].body.device_id;
  await api.forgetPending(id);
  assert.equal((await api.getConnections()).length, 0);
  enrollments[0].resolve(); await pairing;
  const next = api.pair('b'.repeat(32), { service: 'service', label: 'Service' });
  await until(() => enrollments.length === 2);
  enrollments[1].resolve(); await next;
  await assert.rejects(api.forgetPending(enrollments[1].body.device_id), /connection_is_paired/);
  assert.equal((await api.getConnections()).length, 1);
});
