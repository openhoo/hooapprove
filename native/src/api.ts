import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import * as WebBrowser from 'expo-web-browser';

export const SERVER_URL = (process.env.EXPO_PUBLIC_HOOAPPROVE_URL || 'https://approve.openhoo.dev').replace(/\/$/, '');
const tokenKey = 'hooapprove.session';
export async function getToken(): Promise<string | null> { return SecureStore.getItemAsync(tokenKey); }
export async function setToken(token: string | null) {
  if (token) await SecureStore.setItemAsync(tokenKey, token, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  else await SecureStore.deleteItemAsync(tokenKey);
}
export async function api(path: string, body?: unknown, method = 'POST') {
  const token = await getToken();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(SERVER_URL + path, {
      method: body === undefined ? 'GET' : method,
      headers: { Authorization: 'Bearer ' + (token || ''), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
    });
    if (response.status === 401) throw new Error('session_expired');
    if (response.status === 409) throw new Error('conflict');
    if (!response.ok) throw new Error('request_failed');
    return response.json();
  } finally { clearTimeout(timeout); }
}
export async function login(): Promise<boolean> {
  // PKCE protects the handoff if another app claims our custom URI scheme.
  const verifier = Array.from(Crypto.getRandomBytes(32), b => b.toString(16).padStart(2, '0')).join('');
  const challenge = (await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier,
    { encoding: Crypto.CryptoEncoding.BASE64 })).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const result = await WebBrowser.openAuthSessionAsync(
    SERVER_URL + '/auth/login?mobile_challenge=' + challenge, 'hooapprove://callback',
  );
  if (result.type !== 'success') return false;
  const callback = new URL(result.url);
  if (callback.protocol !== 'hooapprove:' || callback.hostname !== 'callback') throw new Error('invalid_callback');
  const ticket = callback.searchParams.get('ticket');
  if (!ticket) throw new Error('missing_ticket');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(SERVER_URL + '/api/mobile/session', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticket, verifier }), signal: controller.signal,
    });
    if (!response.ok) throw new Error('login_failed');
    const session = await response.json(); await setToken(session.token); return true;
  } finally { clearTimeout(timeout); }
}
