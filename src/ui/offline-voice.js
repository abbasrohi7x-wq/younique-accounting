/* Unique Pro — local Persian speech recognition (Vosk/WASM).
 * Audio stays on-device. Model download is explicit and cached locally.
 */
(function () {
  'use strict';
  var MODEL_URL = './vendor/vosk/model.tar.gz';
  var CACHE_NAME = 'unique-voice-v1';
  var model = null, recognizer = null, stream = null, audioContext = null;
  var source = null, processor = null, muted = null, active = false, finalText = '', pendingStop = null;
  var scriptPromise = null;

  function byId(id) { return document.getElementById(id); }
  function status(message) {
    var el = byId('yqVStatus');
    if (el) el.textContent = message;
  }
  function transcript(value) {
    var el = byId('yqVTranscript');
    if (el) el.value = value;
  }
  function loadLibrary() {
    if (window.Vosk) return Promise.resolve(window.Vosk);
    if (scriptPromise) return scriptPromise;
    scriptPromise = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = './vendor/vosk/vosk.js';
      s.async = true;
      s.onload = function () {
        if (window.Vosk && typeof window.Vosk.createModel === 'function') resolve(window.Vosk);
        else reject(new Error('کتابخانه Vosk بارگذاری شد اما API آن پیدا نشد'));
      };
      s.onerror = function () { scriptPromise = null; reject(new Error('فایل‌های موتور گفتار در دسترس نیستند')); };
      document.head.appendChild(s);
    });
    return scriptPromise;
  }
  function cachedModel() {
    if (!('caches' in window)) return Promise.resolve(false);
    return caches.open(CACHE_NAME).then(function (cache) { return cache.match(MODEL_URL); })
      .then(function (hit) { return !!hit; }).catch(function () { return false; });
  }
  function downloadModel() {
    status('در حال بررسی بستهٔ فارسی…');
    return caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(MODEL_URL).then(function (hit) {
        if (hit) { status('بستهٔ فارسی روی دستگاه موجود است.'); return true; }
        status('در حال دریافت مدل فارسی؛ حجم تقریبی ۵۳ مگابایت…');
        return fetch(MODEL_URL, { cache: 'no-store' }).then(function (response) {
          if (!response.ok) throw new Error('دریافت مدل ناموفق بود: ' + response.status);
          var total = Number(response.headers.get('content-length') || 0), loaded = 0;
          var save = cache.put(MODEL_URL, response.clone());
          if (!response.body || !response.body.getReader) {
            return response.blob().then(function (blob) {
              return cache.put(MODEL_URL, new Response(blob, { headers: { 'content-type': 'application/gzip' } }));
            }).then(function () { status('مدل فارسی ذخیره شد.'); return true; });
          }
          var reader = response.body.getReader();
          function read() {
            return reader.read().then(function (part) {
              if (part.done) return save.then(function () { status('مدل فارسی با موفقیت ذخیره شد.'); return true; });
              loaded += part.value.byteLength;
              var mb = (loaded / 1048576).toFixed(1);
              var suffix = total ? ' از ' + (total / 1048576).toFixed(1) + ' مگابایت' : ' مگابایت';
              status('دریافت مدل فارسی: ' + mb + suffix);
              return read();
            });
          }
          return read();
        });
      });
    });
  }
  function ensureModel() {
    if (model && model.ready) return Promise.resolve(model);
    status('در حال آماده‌سازی موتور محلی…');
    return loadLibrary().then(function (Vosk) {
      return downloadModel().then(function () { return Vosk.createModel(MODEL_URL); });
    }).then(function (loaded) {
      model = loaded;
      status('موتور گفتار فارسی آماده است. برای شروع ضبط، دکمهٔ میکروفون را بزنید.');
      return model;
    });
  }
  function stopCapture(releaseModel, finalize) {
    if (pendingStop) return pendingStop;
    active = false;
    if (processor) { processor.onaudioprocess = null; try { processor.disconnect(); } catch (_) {} processor = null; }
    if (source) { try { source.disconnect(); } catch (_) {} source = null; }
    if (muted) { try { muted.disconnect(); } catch (_) {} muted = null; }
    if (stream) { stream.getTracks().forEach(function (track) { track.stop(); }); stream = null; }
    if (audioContext) { var ctx = audioContext; audioContext = null; try { ctx.close(); } catch (_) {} }
    var current = recognizer;
    recognizer = null;
    function releaseResources() {
      if (current) { try { current.remove(); } catch (_) {} current = null; }
      if (releaseModel && model) { try { model.terminate(); } catch (_) {} model = null; }
    }
    if (current && finalize && typeof current.retrieveFinalResult === 'function') {
      pendingStop = new Promise(function (resolve) {
        var finished = false;
        var timer = setTimeout(finish, 1800);
        function finish() {
          if (finished) return;
          finished = true;
          clearTimeout(timer);
          releaseResources();
          pendingStop = null;
          resolve();
        }
        current.on('result', finish);
        try { current.retrieveFinalResult(); } catch (_) { finish(); }
      });
      return pendingStop;
    }
    releaseResources();
    return Promise.resolve();
  }
  function startCapture() {
    if (active) return Promise.resolve();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('مرورگر دسترسی امن به میکروفون را پشتیبانی نمی‌کند');
    }
    return ensureModel().then(function (loaded) {
      return navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        video: false
      }).then(function (media) {
        stream = media;
        var AudioCtx = window.AudioContext || window.webkitAudioContext;
        audioContext = new AudioCtx({ sampleRate: 16000 });
        if (audioContext.state === 'suspended') return audioContext.resume().then(function () { return media; });
        return media;
      }).then(function () {
        recognizer = new loaded.KaldiRecognizer();
        recognizer.on('result', function (message) {
          var text = message && message.result && message.result.text || '';
          if (text.trim()) {
            finalText = (finalText + ' ' + text).trim();
            transcript(finalText);
          }
        });
        recognizer.on('partialresult', function (message) {
          var partial = message && message.result && message.result.partial || '';
          status(partial ? 'در حال شنیدن: ' + partial : 'در حال شنیدن… برای پایان، دکمهٔ توقف را بزنید.');
        });
        source = audioContext.createMediaStreamSource(stream);
        processor = audioContext.createScriptProcessor(4096, 1, 1);
        muted = audioContext.createGain();
        muted.gain.value = 0;
        processor.onaudioprocess = function (event) {
          if (!active || !recognizer) return;
          try { recognizer.acceptWaveform(event.inputBuffer); }
          catch (error) { status('خطا در پردازش صوت محلی: ' + (error.message || error)); }
        };
        source.connect(processor);
        processor.connect(muted);
        muted.connect(audioContext.destination);
        active = true;
        status('میکروفون فعال است؛ صحبت کنید. صدا فقط روی همین دستگاه پردازش می‌شود.');
      });
    }).catch(function (error) {
      stopCapture(true);
      throw error;
    });
  }
  function applyTranscript(value, context) {
    value = String(value || '').trim();
    if (!value) { if (typeof toast === 'function') toast('متنی برای ارسال وجود ندارد', true); return; }
    var assistantUI = window.UAI && window.UAI.ui;
    if (assistantUI && typeof assistantUI.submit === 'function') {
      assistantUI.submit(value, 'voice');
      return;
    }
    if (window.UI && typeof window.UI.submit === 'function') {
      window.UI.submit(value, 'voice');
      return;
    }
    if (typeof toast === 'function') toast('دستیار محلی در دسترس نیست؛ متن را در صفحهٔ دستیار وارد کنید.', true);
  }
  function showDialog(context) {
    context = context || 'assistant';
    finalText = '';
    modal(
      '<div class="modalhead"><h2>دستیار گفتاری آفلاین فارسی</h2><button class="close" data-close>×</button></div>' +
      '<p class="muted">تشخیص با موتور Vosk و روی همین دستگاه انجام می‌شود. بار اول باید مدل فارسی (حدود ۵۳ مگابایت) دریافت شود؛ بعد از ذخیره می‌توانید اینترنت را قطع کنید.</p>' +
      '<p id="yqVStatus" class="muted">برای آماده‌سازی، دریافت مدل را انتخاب کنید.</p>' +
      '<div class="toolbar"><button class="btn" id="yqVInstall" type="button">دریافت / آماده‌سازی مدل فارسی</button><button class="btn" id="yqVStart" type="button">شروع ضبط</button><button class="btn" id="yqVStop" type="button">توقف ضبط</button></div>' +
      '<textarea id="yqVTranscript" rows="4" placeholder="متن تشخیص‌داده‌شده اینجا نمایش داده می‌شود؛ قبل از استفاده آن را بررسی کنید."></textarea>' +
      '<div class="modal-actions"><button class="btn" id="yqVText" type="button">ورود متن</button><button class="btn primary" id="yqVApply" type="button">تأیید و افزودن به پیش‌نویس</button></div>'
    );
    byId('yqVInstall').onclick = function () {
      byId('yqVInstall').disabled = true;
      ensureModel().then(function () { status('مدل آماده است. برای ضبط، شروع ضبط را بزنید.'); })
        .catch(function (e) { status((e && e.message) || 'آماده‌سازی مدل ناموفق بود.'); })
        .then(function () { if (byId('yqVInstall')) byId('yqVInstall').disabled = false; });
    };
    byId('yqVStart').onclick = function () {
      byId('yqVStart').disabled = true;
      startCapture().catch(function (e) { status((e && e.message) || 'شروع میکروفون ناموفق بود.'); })
        .then(function () { if (byId('yqVStart')) byId('yqVStart').disabled = false; });
    };
    byId('yqVStop').onclick = function () {
      byId('yqVStop').disabled = true;
      stopCapture(true, true).then(function () {
        status('ضبط متوقف شد و متن نهایی آماده است؛ آن را بررسی کنید.');
        if (byId('yqVStop')) byId('yqVStop').disabled = false;
      });
    };
    byId('yqVText').onclick = function () {
      stopCapture(true, active).then(function () {
      var text = byId('yqVTranscript').value;
      closeModal();
      modal(
        '<div class="modalhead"><h2>ورود متن دستیار</h2><button class="close" data-close>×</button></div>' +
        '<textarea id="yqVManual" rows="4" placeholder="جملهٔ فارسی را وارد کنید"></textarea>' +
        '<div class="modal-actions"><button class="btn primary" id="yqVManualApply" type="button">افزودن به پیش‌نویس</button></div>'
      );
      byId('yqVManual').value = text;
      byId('yqVManualApply').onclick = function () {
        var value = byId('yqVManual').value.trim();
        closeModal();
        if (value) applyTranscript(value, context);
      };
      });
    };
    byId('yqVApply').onclick = function () {
      var wasActive = active;
      stopCapture(true, wasActive).then(function () {
        if (wasActive) {
          status('متن نهایی آماده شد؛ دوباره دکمهٔ تأیید را بزنید.');
          return;
        }
        var value = byId('yqVTranscript').value.trim();
        closeModal();
        if (value) applyTranscript(value, context);
        else if (typeof toast === 'function') toast('متنی برای افزودن وجود ندارد', true);
      });
    };
    var overlay = document.getElementById('modal');
    var close = document.querySelector('#modal .close[data-close]');
    if (close) close.addEventListener('click', function () { stopCapture(true); }, { once: true });
    if (overlay) overlay.addEventListener('click', function (event) {
      if (event.target === overlay) stopCapture(true);
    }, { once: true });
    cachedModel().then(function (ready) {
      if (byId('yqVStatus') && ready) status('مدل فارسی قبلاً دریافت شده و برای استفاده آفلاین آماده است.');
    });
  }
  window.yqVoiceDraft = function () {
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      modal('<div class="modalhead"><h2>دستیار گفتاری</h2><button class="close" data-close>×</button></div><p>برای دسترسی به میکروفون، برنامه باید از HTTPS باز شود.</p>');
      return;
    }
    showDialog('assistant');
  };
  window.voiceRecord = function () { showDialog('assistant'); };
  window.addEventListener('pagehide', function () { stopCapture(true); });
})();