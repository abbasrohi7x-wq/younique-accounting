/**
 * Unique Pro — Supabase snapshot sync (Free tier friendly)
 * Uses PostgREST; no supabase-js dependency.
 */
(function (global) {
  'use strict';

  function cfgFrom(db) {
    const s = (db && db.settings && db.settings.supabase) || {};
    return {
      url: String(s.url || '').replace(/\/$/, ''),
      anonKey: String(s.anonKey || ''),
      workspaceId: String(s.workspaceId || ''),
      accessKey: String(s.accessKey || ''),
      lastRevision: Number(s.lastRevision || 0) || 0,
      lastPullAt: s.lastPullAt || null,
      lastPushAt: s.lastPushAt || null,
      enabled: !!s.enabled
    };
  }

  function saveCfg(db, patch) {
    db.settings = db.settings || {};
    db.settings.supabase = Object.assign({}, db.settings.supabase || {}, patch);
  }

  function headers(cfg) {
    return {
      apikey: cfg.anonKey,
      Authorization: 'Bearer ' + cfg.anonKey,
      'Content-Type': 'application/json',
      Prefer: 'return=representation'
    };
  }

  async function rest(cfg, path, options) {
    if (!cfg.url || !cfg.anonKey) throw new Error('آدرس پروژه و کلید anon را وارد کنید');
    const res = await fetch(cfg.url + path, options);
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch (_) { body = text; }
    if (!res.ok) {
      const msg = (body && (body.message || body.error_description || body.error)) || res.statusText || 'خطای شبکه';
      throw new Error(msg);
    }
    return body;
  }

  async function pull(cfg) {
    if (!cfg.workspaceId) throw new Error('شناسه فضای کاری خالی است');
    const q = '/rest/v1/unique_snapshots?workspace_id=eq.' + encodeURIComponent(cfg.workspaceId) + '&select=*';
    const rows = await rest(cfg, q, { method: 'GET', headers: headers(cfg) });
    if (!rows || !rows.length) return { empty: true, row: null };
    const row = rows[0];
    if (row.access_key && cfg.accessKey && row.access_key !== cfg.accessKey) {
      throw new Error('کلید دسترسی نادرست است');
    }
    return { empty: false, row };
  }

  async function push(cfg, payload, meta) {
    if (!cfg.workspaceId) throw new Error('شناسه فضای کاری خالی است');
    if (!cfg.accessKey) throw new Error('کلید دسترسی را تنظیم کنید');
    const existing = await pull(cfg);
    const nextRev = existing.empty ? 1 : (Number(existing.row.revision) || 0) + 1;
    const body = {
      workspace_id: cfg.workspaceId,
      access_key: cfg.accessKey,
      payload: payload,
      device_id: meta.deviceId || null,
      revision: nextRev,
      checksum: meta.checksum || null,
      updated_at: new Date().toISOString()
    };
    if (existing.empty) {
      await rest(cfg, '/rest/v1/unique_snapshots', {
        method: 'POST',
        headers: headers(cfg),
        body: JSON.stringify(body)
      });
    } else {
      // Optimistic: require same revision we saw
      const rev = Number(existing.row.revision) || 0;
      await rest(
        cfg,
        '/rest/v1/unique_snapshots?workspace_id=eq.' + encodeURIComponent(cfg.workspaceId) + '&revision=eq.' + rev,
        {
          method: 'PATCH',
          headers: Object.assign({}, headers(cfg), { Prefer: 'return=minimal' }),
          body: JSON.stringify({
            access_key: cfg.accessKey,
            payload: payload,
            device_id: meta.deviceId || null,
            revision: nextRev,
            checksum: meta.checksum || null,
            updated_at: body.updated_at
          })
        }
      );
    }
    return { revision: nextRev };
  }

  function randomId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'ws-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function randomKey() {
    const a = new Uint8Array(24);
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(a);
    else for (let i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256);
    return Array.from(a).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  global.UniqueSupabaseSync = {
    cfgFrom,
    saveCfg,
    pull,
    push,
    randomId,
    randomKey,
    version: '1.0.0-supabase-sync'
  };
})(typeof window !== 'undefined' ? window : global);
