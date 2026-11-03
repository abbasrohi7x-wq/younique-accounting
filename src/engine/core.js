/**
 * UNIQUE Engine Core v1.3
 * Pure accounting/inventory engine (dependency-injected).
 * See PROJECT_STATUS.md for test results (13/13 with flag on/off).
 */
'use strict';
// Full file deployed from local build — placeholder marker
// If you see this short version, re-push failed; use the release zip.
function createEngine(db, h) {
  if (!db) throw new Error('db is required');
  if (!h) throw new Error('helpers are required');
  throw new Error('Incomplete core.js on remote — upload full src/engine/core.js from unique-pro-github-ready.zip');
}
if (typeof module !== 'undefined' && module.exports) module.exports = { createEngine };
else window.UniqueEngine = { createEngine };
