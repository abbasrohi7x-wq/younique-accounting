/* Unique AI proxy — Vercel serverless function (Node.js runtime).
   The real provider keys live ONLY in Vercel Environment Variables; the browser holds just an access token.

   Endpoints (same origin as the app):
     GET  /api/ai/health                          -> which providers are configured (no secrets, no auth)
     GET  /api/ai/openrouter/models               -> compact list of OpenRouter models that support tool calling (token required)
     POST /api/ai/openrouter/chat/completions     -> OpenRouter (OpenAI-compatible chat completions)
     POST /api/ai/openai/chat/completions         -> OpenAI
     POST /api/ai/openai/responses                -> OpenAI Responses API

   Environment variables:
     APP_TOKEN           (required) secret you also type as "API Key" in the app; requests without it are rejected
     OPENROUTER_API_KEY  real OpenRouter key (sk-or-v1-…)
     OPENAI_API_KEY      real OpenAI key
     ALLOWED_ORIGINS     optional, comma separated extra origins (the app's own origin is always allowed)
     ALLOWED_MODELS      optional, comma separated allow-list of model ids
     RATE_LIMIT_PER_MIN  optional, default 30 (best effort: per server instance and IP) */
const crypto = require('crypto');

const OPENROUTER_BASE = 'https://openrouter.ai/api/v1';
const ROUTES = {
  'openrouter/chat/completions': env => ({ url: OPENROUTER_BASE + '/chat/completions', key: env.OPENROUTER_API_KEY, openrouter: true }),
  'openai/chat/completions': env => ({ url: 'https://api.openai.com/v1/chat/completions', key: env.OPENAI_API_KEY }),
  'openai/responses': env => ({ url: 'https://api.openai.com/v1/responses', key: env.OPENAI_API_KEY })
};
const BODY_FIELDS = ['model', 'messages', 'input', 'tools', 'tool_choice', 'temperature', 'top_p', 'max_tokens', 'max_completion_tokens', 'max_output_tokens', 'response_format', 'parallel_tool_calls'];
const MAX_BODY = 300 * 1024, MAX_TOKENS = 2000, UPSTREAM_TIMEOUT_MS = 55000;
const hits = new Map(); // ip -> [timestamps]
const modelCache = { at: 0, list: null }; // the public OpenRouter catalogue is cached for 10 minutes
const MODELS_TTL_MS = 10 * 60 * 1000;
/* keep only text models that can call tools (the assistant needs tool calling) and shrink the payload */
function compactModels(j) {
  const rows = (j && Array.isArray(j.data) ? j.data : []).filter(m => m && typeof m.id === 'string' && Array.isArray(m.supported_parameters) && m.supported_parameters.includes('tools') &&
    (!m.architecture || !Array.isArray(m.architecture.output_modalities) || m.architecture.output_modalities.includes('text')));
  return rows.map(m => {
    const p = Number(m.pricing && m.pricing.prompt) || 0, c = Number(m.pricing && m.pricing.completion) || 0;
    return { id: m.id, name: String(m.name || m.id).slice(0, 80), ctx: Number(m.context_length) || 0, prompt: +(p * 1e6).toFixed(4), completion: +(c * 1e6).toFixed(4), free: (p === 0 && c === 0) || m.id.endsWith(':free') };
  }).sort((a, b) => (a.prompt + a.completion) - (b.prompt + b.completion) || a.id.localeCompare(b.id)).slice(0, 400);
}

const sha = s => crypto.createHash('sha256').update(String(s)).digest();
const sameSecret = (a, b) => crypto.timingSafeEqual(sha(a), sha(b));
function send(res, status, obj, extra) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  for (const [k, v] of Object.entries(extra || {})) res.setHeader(k, v);
  res.end(JSON.stringify(obj));
}
const fail = (res, status, message, extra) => send(res, status, { error: { message } }, extra);

function originAllowed(req, env) {
  const origin = req.headers.origin;
  if (!origin) return true; // same-origin GET/POST from the app sends no Origin on some browsers; non-browser clients are covered by the token
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  try { if (new URL(origin).host === host) return true; } catch (_) { return false; }
  return String(env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean).includes(origin);
}
function rateLimited(req, env) {
  const limit = Math.max(1, parseInt(env.RATE_LIMIT_PER_MIN, 10) || 30);
  const ip = String(req.headers['x-forwarded-for'] || (req.socket && req.socket.remoteAddress) || 'x').split(',')[0].trim();
  const now = Date.now(), arr = (hits.get(ip) || []).filter(t => now - t < 60000);
  arr.push(now); hits.set(ip, arr);
  if (hits.size > 5000) for (const k of hits.keys()) { if (!hits.get(k).some(t => now - t < 60000)) hits.delete(k); }
  return arr.length > limit;
}

async function handler(req, res, envOverride) {
  const env = envOverride || process.env;
  const q = req.query || {};
  let parts = [].concat(q.p !== undefined ? q.p : []).join('/');
  if (!parts) parts = new URL(req.url || '/', 'http://x').pathname.replace(/^\/api\/(?:ai|aiproxy)\/?/, '');
  parts = parts.replace(/^\/+|\/+$/g, '');

  if (parts === 'health') {
    if (req.method !== 'GET') return fail(res, 405, 'Method not allowed', { Allow: 'GET' });
    return send(res, 200, { ok: true, tokenRequired: true, configured: !!env.APP_TOKEN, providers: { openrouter: !!env.OPENROUTER_API_KEY, openai: !!env.OPENAI_API_KEY } });
  }
  if (parts === 'openrouter/models') {
    if (req.method !== 'GET') return fail(res, 405, 'Method not allowed', { Allow: 'GET' });
    if (!env.APP_TOKEN) return fail(res, 503, 'Proxy is not configured: set APP_TOKEN in the Vercel environment variables');
    if (!originAllowed(req, env)) return fail(res, 403, 'Origin not allowed');
    const a0 = String(req.headers.authorization || ''), t0 = a0.startsWith('Bearer ') ? a0.slice(7).trim() : '';
    if (!t0 || !sameSecret(t0, env.APP_TOKEN)) return fail(res, 401, 'Invalid access token');
    if (rateLimited(req, env)) return fail(res, 429, 'Too many requests', { 'Retry-After': '30' });
    if (modelCache.list && Date.now() - modelCache.at < MODELS_TTL_MS) return send(res, 200, { ok: true, cached: true, models: modelCache.list });
    const ac0 = new AbortController(), tm0 = setTimeout(() => ac0.abort(), 20000);
    try {
      const up = await fetch(OPENROUTER_BASE + '/models', { method: 'GET', headers: { Accept: 'application/json' }, signal: ac0.signal });
      if (up.status !== 200) return fail(res, 502, 'OpenRouter returned HTTP ' + up.status);
      const list = compactModels(JSON.parse(await up.text()));
      modelCache.at = Date.now(); modelCache.list = list;
      return send(res, 200, { ok: true, cached: false, models: list });
    } catch (e) { return fail(res, 502, e && e.name === 'AbortError' ? 'OpenRouter took too long to answer' : 'Could not read the OpenRouter model list'); }
    finally { clearTimeout(tm0); }
  }
  if (req.method !== 'POST') return fail(res, 405, 'Method not allowed', { Allow: 'POST' });
  const route = ROUTES[parts];
  if (!route) return fail(res, 404, 'Unknown route');
  if (!env.APP_TOKEN) return fail(res, 503, 'Proxy is not configured: set APP_TOKEN in the Vercel environment variables');
  if (!originAllowed(req, env)) return fail(res, 403, 'Origin not allowed');

  const auth = String(req.headers.authorization || '');
  const token = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
  if (!token || !sameSecret(token, env.APP_TOKEN)) return fail(res, 401, 'Invalid access token');
  if (rateLimited(req, env)) return fail(res, 429, 'Too many requests', { 'Retry-After': '30' });

  const target = route(env);
  if (!target.key) return fail(res, 503, 'The provider key is not configured on the server');

  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (_) { return fail(res, 400, 'Invalid JSON'); } }
  if (!body || typeof body !== 'object' || Array.isArray(body)) return fail(res, 400, 'JSON object body required');
  let raw; try { raw = JSON.stringify(body); } catch (_) { return fail(res, 400, 'Invalid body'); }
  if (raw.length > MAX_BODY) return fail(res, 413, 'Request too large');

  const out = {};
  for (const k of BODY_FIELDS) if (body[k] !== undefined) out[k] = body[k];
  for (const k of ['max_tokens', 'max_completion_tokens', 'max_output_tokens']) if (typeof out[k] === 'number') out[k] = Math.min(out[k], MAX_TOKENS);
  if (out.max_tokens === undefined && out.max_completion_tokens === undefined && out.max_output_tokens === undefined) out[parts.endsWith('responses') ? 'max_output_tokens' : 'max_tokens'] = MAX_TOKENS;
  out.stream = false;
  if (target.openrouter) {
    /* privacy first: by default only providers that do not store/train on the prompts are used; the app can opt out with provider.data_collection = 'allow' */
    const dc = body.provider && typeof body.provider === 'object' ? body.provider.data_collection : undefined;
    out.provider = { data_collection: dc === 'allow' ? 'allow' : 'deny' };
  }
  const allow = String(env.ALLOWED_MODELS || '').split(',').map(s => s.trim()).filter(Boolean);
  if (allow.length && !allow.includes(out.model)) return fail(res, 400, 'Model not allowed');
  if (typeof out.model !== 'string' || !out.model) return fail(res, 400, 'model is required');

  const ac = new AbortController(), timer = setTimeout(() => ac.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const up = await fetch(target.url, { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json', Authorization: 'Bearer ' + target.key }, target.openrouter ? { 'HTTP-Referer': 'https://' + (req.headers['x-forwarded-host'] || req.headers.host || 'unique-pro'), 'X-Title': 'Unique Pro' } : {}), body: JSON.stringify(out), signal: ac.signal });
    const text = await up.text();
    res.statusCode = up.status;
    res.setHeader('Content-Type', up.headers.get('content-type') || 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.end(text);
  } catch (e) {
    return fail(res, 502, e && e.name === 'AbortError' ? 'The provider took too long to answer' : 'Could not reach the provider');
  } finally { clearTimeout(timer); }
}
module.exports = handler;
module.exports._hits = hits;
module.exports._modelCache = modelCache;
module.exports._compactModels = compactModels;
