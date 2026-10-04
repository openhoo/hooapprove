import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import { ed25519 } from '@noble/curves/ed25519.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

export const SERVER_URL = (process.env.EXPO_PUBLIC_HOOAPPROVE_URL || 'https://approve.openhoo.dev').replace(/\/$/, '');
export type Connection = { device_id: string; seed: string; service: string; label: string; pending?: boolean };
const storageKey = 'hooapprove.connections.v1';
export async function getConnections(): Promise<Connection[]> {
  const ids: string[] = JSON.parse(await SecureStore.getItemAsync(storageKey) || '[]');
  const values = await Promise.all(ids.map(id => SecureStore.getItemAsync('hooapprove.device.' + id)));
  return values.filter((value): value is string => value !== null).map(value => JSON.parse(value));
}
async function saveConnections(values: Connection[]) {
  const previous: string[] = JSON.parse(await SecureStore.getItemAsync(storageKey) || '[]');
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  for (const value of values) await SecureStore.setItemAsync('hooapprove.device.' + value.device_id, JSON.stringify(value), options);
  await SecureStore.setItemAsync(storageKey, JSON.stringify(values.map(c => c.device_id)), options);
  for (const id of previous) if (!values.some(c => c.device_id === id)) await SecureStore.deleteItemAsync('hooapprove.device.' + id);
}
async function request(path: string, body?: unknown, connection?: Connection, method = 'POST') {
  const verb = body === undefined ? 'GET' : method;
  const raw = body === undefined ? '' : JSON.stringify(body);
  const headers: Record<string, string> = body === undefined ? {} : { 'Content-Type': 'application/json' };
  if (connection) {
    const timestamp = String(Math.floor(Date.now() / 1000));
    const nonce = bytesToHex(await Crypto.getRandomBytesAsync(16));
    const digest = bytesToHex(sha256(utf8ToBytes(raw)));
    const message = `hooapprove.device.v1\n${connection.device_id}\n${verb}\n${path}\n${timestamp}\n${nonce}\n${digest}`;
    Object.assign(headers, { 'X-Device-Id': connection.device_id, 'X-Device-Time': timestamp, 'X-Device-Nonce': nonce,
      'X-Device-Signature': bytesToHex(ed25519.sign(utf8ToBytes(message), hexToBytes(connection.seed))) });
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(SERVER_URL + path, { method: verb, headers, body: body === undefined ? undefined : raw, signal: controller.signal });
    if (response.status === 401) throw new Error('device_unavailable');
    if (response.status === 409) throw new Error('conflict');
    if (response.status === 410) throw new Error('pairing_expired');
    if (!response.ok) throw new Error('request_failed');
    return response.json();
  } finally { clearTimeout(timeout); }
}
export async function api(path: string, body?: unknown, method = 'POST', deviceId?: string) {
  const connections = await getConnections();
  const connection = deviceId ? connections.find(c => c.device_id === deviceId) : connections[0];
  if (!connection) throw new Error('device_unavailable');
  return request(path, body, connection, method);
}
export function pairingToken(value: string): string {
  let token = value.trim();
  if (token.startsWith('hooapprove://')) {
    const url = new URL(token);
    if (url.hostname !== 'pair') throw new Error('invalid_pairing');
    token = url.searchParams.get('token') || '';
  }
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new Error('invalid_pairing');
  return token;
}
export async function previewPairing(value: string): Promise<{ service: string; label: string; expires: number }> {
  return request('/api/pairings/preview', { ticket: pairingToken(value) });
}
export async function pair(value: string, preview: { service: string; label: string }) {
  const ticket = pairingToken(value);
  const seed = await Crypto.getRandomBytesAsync(32);
  const device_id = bytesToHex(await Crypto.getRandomBytesAsync(16));
  const public_key = bytesToHex(ed25519.getPublicKey(seed));
  const connection: Connection = { device_id, seed: bytesToHex(seed), ...preview, pending: true };
  // Persist BEFORE enrollment: an interrupted response must not lose the enrolled key.
  const existing = await getConnections();
  await saveConnections([...existing, connection]);
  const digest = bytesToHex(sha256(utf8ToBytes(ticket)));
  const message = `hooapprove.pair.v1\n${digest}\n${device_id}\n${public_key}`;
  try {
    await request('/api/pairings/enroll', { ticket, device_id, public_key, signature: bytesToHex(ed25519.sign(utf8ToBytes(message), seed)) });
  } catch (error) {
    // Reconcile a lost enrollment response with the same persisted key.
    try { await request('/api/me', undefined, connection); }
    catch { throw error; }
  }
  await saveConnections([...existing, { ...connection, pending: false }]);
}
export async function reconcile(connection: Connection) {
  const me = await api('/api/me', undefined, 'GET', connection.device_id);
  if (connection.pending) await saveConnections((await getConnections()).map(c => c.device_id === connection.device_id ? { ...c, pending: false } : c));
  return me;
}
export async function unlink(deviceId: string) {
  await api('/api/device/unlink', {}, 'POST', deviceId);
  await saveConnections((await getConnections()).filter(c => c.device_id !== deviceId));
}
export async function demoTicket() { return request('/api/demo/pairing', {}); }
export const LOCAL_DEMO = /^http:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(SERVER_URL);
