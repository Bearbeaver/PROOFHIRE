const KEY = 'ph_session';
export const session = {
  get() { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } },
  set(s) { localStorage.setItem(KEY, JSON.stringify(s)); },
  clear() { localStorage.removeItem(KEY); },
};
export class ApiError extends Error {
  constructor(status, body) {
    const e = (body && body.error) || {};
    super(e.message || 'Something went wrong. Please try again.');
    this.status = status; this.code = e.code || 'ERROR'; this.details = e.details || null;
  }
}
let onAuthLost = () => {};
export const setAuthLostHandler = (fn) => { onAuthLost = fn; };
const AUTH_CODES = new Set(['UNAUTHENTICATED', 'TOKEN_EXPIRED', 'TOKEN_INVALID', 'ACCOUNT_SUSPENDED', 'ACCOUNT_REMOVED']);

function headers(extra = {}) {
  const s = session.get();
  return s ? { Authorization: 'Bearer ' + s.token, ...extra } : extra;
}
async function handle(res) {
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const err = new ApiError(res.status, body);
    if (AUTH_CODES.has(err.code) && session.get()) onAuthLost(err);
    throw err;
  }
  return body;
}
export async function api(method, path, body) {
  let res;
  try {
    res = await fetch('/api' + path, { method, headers: headers(body !== undefined ? { 'Content-Type': 'application/json' } : {}), body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, { error: { code: 'NETWORK', message: 'Cannot reach the server. Check your connection and try again.' } });
  }
  return handle(res);
}
// multipart with upload progress (XHR: fetch cannot report upload progress)
export function upload(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', '/api' + path);
    const s = session.get();
    if (s) x.setRequestHeader('Authorization', 'Bearer ' + s.token);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
    x.onerror = () => reject(new ApiError(0, { error: { code: 'NETWORK', message: 'Cannot reach the server. Check your connection and try again.' } }));
    x.onload = () => {
      let body = null;
      try { body = JSON.parse(x.responseText); } catch { /* ignore */ }
      if (x.status >= 200 && x.status < 300) return resolve(body);
      const err = new ApiError(x.status, body);
      if (AUTH_CODES.has(err.code) && session.get()) onAuthLost(err);
      reject(err);
    };
    x.send(formData);
  });
}
