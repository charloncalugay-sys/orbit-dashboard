/* ════════════════════════════════════════════════════════════════════════
   ORBIT auth service — PostgREST RPC client for Supabase-backed sign-in.

   Mirrors the TEMPUS supabase-shim model:
     - Publishable key authenticates the APP to PostgREST.
     - A bearer token (orbit_sessions) authenticates the USER to the RPC.
     - RLS denies all direct table access; only safe RPCs are granted.

   Loaded after supabase-config.js, before orbit-app.js.
   Exposes window.ORBIT_SVC — the AUTH module in orbit-app.js is the only
   consumer; nothing else should call this directly.
   ════════════════════════════════════════════════════════════════════════ */
(() => {
'use strict';

/* Route through the same-origin Vercel rewrite (/sb/* → supabase.co/rest/v1/*)
   when the config points at supabase.co — corporate DNS does not resolve
   *.supabase.co on this network, but *.vercel.app is reachable. Outside
   Vercel (e.g. local file:// or a host without the rewrite), fall back to
   the direct Supabase URL. */
const REST = (() => {
  const isVercel = /\.vercel\.app$/.test(location.hostname);
  const isSbco   = /supabase\.co$/.test(SUPA.URL.replace(/\/$/, '').split('//')[1] || '');
  return isVercel && isSbco ? '/sb' : SUPA.URL.replace(/\/$/, '') + '/rest/v1';
})();
const TOK_KEY  = 'orbit.sb_token';

const getTok = () => { try { return localStorage.getItem(TOK_KEY) || ''; } catch { return ''; } };
const setTok = (t) => { try { t ? localStorage.setItem(TOK_KEY, t) : localStorage.removeItem(TOK_KEY); } catch {} };

async function rpc(fn, args = {}) {
  let res;
  try {
    res = await fetch(`${REST}/rpc/${fn}`, {
      method: 'POST',
      headers: { apikey: SUPA.KEY, 'Content-Type': 'application/json' },
      body: JSON.stringify(args),
    });
  } catch {
    return { ok: false, error: 'Unable to reach the ORBIT sign-in service. Check your network.' };
  }
  const body = await res.json().catch(() => null);
  if (body && body.ok === false) return body;                       // RPC-level error contract
  if (!res.ok) {
    const msg = body?.message || '';
    if (msg.includes('session_expired') || (body && body.code === 'expired')) {
      return { ok: false, code: 'expired', error: 'Session expired.' };
    }
    return { ok: false, error: msg || `Sign-in request failed (${res.status}).` };
  }
  return body || { ok: true };
}

/* Sign in with Domain ID + personal password.
   Resolves to the raw RPC payload:
     { ok:true, token, profile } | { ok:false, code, error, needSetup?, needPasscode? } */
async function signIn(domain, password) {
  return rpc('orbit_login', { p_domain: domain, p_passcode: password || null });
}

/* First-time setup: team passcode + personal password → session. */
async function setupPassword(domain, bootstrap, newPassword) {
  return rpc('orbit_setup_password', {
    p_domain: domain, p_bootstrap: bootstrap, p_new_password: newPassword });
}

/* Validate stored token → profile or expired. */
async function session() {
  const t = getTok();
  if (!t) return { ok: false, code: 'expired' };
  return rpc('orbit_session', { p_token: t });
}

async function logout() {
  const t = getTok();
  setTok('');
  if (!t) return { ok: true };
  return rpc('orbit_logout', { p_token: t });
}

async function changePassword(current, next) {
  return rpc('orbit_change_password', { p_token: getTok(), p_current: current, p_new: next });
}

window.ORBIT_SVC = { signIn, setupPassword, session, logout, changePassword, getTok, setTok };
})();
