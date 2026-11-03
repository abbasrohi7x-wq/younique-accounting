/** UNIQUE Fin module — use full file from release zip if this is placeholder */
'use strict';
function createFin(db, h, core) {
  throw new Error('Incomplete fin.js — upload full file from release');
}
if (typeof module !== 'undefined' && module.exports) module.exports = { createFin };
else window.UniqueFin = { createFin };
