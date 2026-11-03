# Engine Extraction

Phase 1 complete. See `src/engine/core.js` and `src/engine/fin.js`.

Regression: **13/13** with engine flag ON and OFF.

Enable experimental engine:
```js
localStorage.setItem('yq_use_new_engine','1'); location.reload();
```
