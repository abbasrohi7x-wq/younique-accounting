/* Unique Pro — local Persian speech recognition (Vosk/WASM).
 * Audio stays on-device. Model download is explicit and cached locally.
 */
(function () {
  'use strict';
  var MODEL_URL = './vendor/vosk/model.tar.gz';
  var CACHE_NAME = 'unique-voice-v1';
  var model = null, recognizer = null, stream = null, audioContext = null;
  var source = null, processor = null, muted = null, active = false, finalText = '', pendingStop = null, captureWatchdog = null;
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
        if (window.Vosk && (typeof window.Vosk.Model === 'function' || typeof window.Vosk.createModel === 'function')) resolve(window.Vosk);
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
  function createModelWithDiagnostics(Vosk) {
    var timeoutMs = 240000;
    return new Promise(function (resolve, reject) {
      var candidate = null, settled = false;
      var timer = setTimeout(function () {
        finish(new Error('بارگذاری مدل گفتار بیش از چهار دقیقه طول کشید؛ فضای ذخیره‌سازی و حافظه دستگاه را بررسی کنید.'));
      }, timeoutMs);
      function finish(error, value) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) {
          if (candidate && typeof candidate.terminate === 'function') {
            try { candidate.terminate(); } catch (_) {}
          }
          reject(error);
        } else resolve(value);
      }
      try {
        if (typeof Vosk.Model === 'function') {
          candidate = new Vosk.Model(MODEL_URL);
          candidate.on('load', function (message) {
            if (message && message.result && candidate.ready) finish(null, candidate);
            else finish(new Error('موتور Vosk نتوانست مدل فارسی را آماده کند.'));
          });
          candidate.on('error', function (message) {
            finish(new Error('خطای موتور Vosk: ' + (message && (message.error || message.message) || 'بارگذاری مدل ناموفق بود')));
          });
          /* vosk-browser 0.0.8 does not forward Worker startup errors through Model events. */
          if (candidate.worker && typeof candidate.worker.addEventListener === 'function') {
            candidate.worker.addEventListener('error', function (event) {
              finish(new Error('خطای اجرای Worker گفتار: ' + (event && event.message || 'فایل‌های موتور بارگذاری نشدند')));
            });
            candidate.worker.addEventListener('messageerror', function () {
              finish(new Error('ارتباط Worker گفتار با برنامه ناموفق بود.'));
            });
          }
        } else if (typeof Vosk.createModel === 'function') {
          Vosk.createModel(MODEL_URL).then(function (loaded) {
            finish(null, loaded);
          }).catch(function (error) {
            finish(error instanceof Error ? error : new Error(String(error)));
          });
        } else {
          finish(new Error('API بارگذاری مدل در کتابخانه Vosk موجود نیست.'));
        }
      } catch (error) {
        finish(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }
  function ensureModel() {
    if (model && model.ready) return Promise.resolve(model);
    status('در حال آماده‌سازی موتور محلی…');
    return loadLibrary().then(function (Vosk) {
      return downloadModel().then(function () { return createModelWithDiagnostics(Vosk); });
    }).then(function (loaded) {
      model = loaded;
      status('موتور گفتار فارسی آماده است. برای شروع ضبط، دکمهٔ میکروفون را بزنید.');
      return model;
    });
  }
  function stopCapture(releaseModel, finalize) {
    if (pendingStop) return releaseModel ? pendingStop.then(function () { return stopCapture(true, false); }) : pendingStop;
    active = false;
    var voiceApi = window.UAI && window.UAI.Voice;
    if (voiceApi) {
      voiceApi.listening = false;
      if (typeof voiceApi.setBtn === 'function') voiceApi.setBtn(false);
    }
    if (captureWatchdog) { clearTimeout(captureWatchdog); captureWatchdog = null; }
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
      return Promise.reject(new Error('این مرورگر دسترسی مستقیم به میکروفون را پشتیبانی نمی‌کند؛ برنامه را در Chrome و از نشانی HTTPS باز کنید.'));
    }
    var sessionNode = byId('yqVStatus');
    status('در حال فعال‌کردن پردازش صوت و درخواست اجازهٔ میکروفون…');
    /* Create and resume AudioContext synchronously inside the real button gesture.
       Creating it only after the model download can lose Chrome's user activation
       and leave the context suspended forever on Android. */
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return Promise.reject(new Error('مرورگر موتور پردازش صوت را پشتیبانی نمی‌کند.'));
    var resumePromise;
    try {
      try { audioContext = new AudioCtx({ sampleRate: 16000 }); }
      catch (_) { audioContext = new AudioCtx(); }
      resumePromise = audioContext.state === 'suspended' ? audioContext.resume() : Promise.resolve();
    } catch (audioError) {
      stopCapture(false);
      return Promise.reject(new Error('فعال‌سازی پردازش صوت ناموفق بود: ' + (audioError.message || audioError)));
    }
    /* Request the microphone directly from the button action, before model download. */
    return navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      video: false
    }).then(function (media) {
      if (!sessionNode || byId('yqVStatus') !== sessionNode) {
        media.getTracks().forEach(function (track) { track.stop(); });
        throw new Error('پنجرهٔ گفتار بسته شد؛ ضبط شروع نشد.');
      }
      stream = media;
      var tracks = media.getAudioTracks();
      if (!tracks.length || tracks[0].readyState !== 'live') {
        throw new Error('جریان ورودی میکروفون فعال نشد. مجوز میکروفون و تنظیمات سایت را بررسی کنید.');
      }
      status('میکروفون مجاز شد؛ در حال آماده‌سازی موتور تشخیص فارسی…');
      return ensureModel();
    }).then(function (loaded) {
      if (!sessionNode || byId('yqVStatus') !== sessionNode) {
        stopCapture(false);
        throw new Error('پنجرهٔ گفتار بسته شد؛ ضبط شروع نشد.');
      }
      return resumePromise.then(function () {
        if (!audioContext || audioContext.state !== 'running') throw new Error('پردازش صوت مرورگر فعال نشد؛ مجوز پخش/میکروفون را بررسی و صفحه را تازه‌سازی کنید.');
        /* vosk-browser 0.0.8 requires the recognizer sample rate; omitting it can fail inside WASM with an undefined-to-float error. Match the actual AudioContext rate because acceptWaveform receives AudioBuffer objects at this rate. */
        recognizer = new loaded.KaldiRecognizer(audioContext.sampleRate);
        var frames = 0, signalFrames = 0, lastStatus = 0;
        recognizer.on('result', function (message) {
          var text = message && message.result && message.result.text || '';
          if (text.trim()) {
            finalText = (finalText + ' ' + text).trim();
            transcript(finalText);
            status('گفتار تشخیص داده شد؛ می‌توانید ادامه دهید یا توقف ضبط را بزنید.');
          }
        });
        recognizer.on('partialresult', function (message) {
          var partial = message && message.result && message.result.partial || '';
          status(partial ? 'در حال تشخیص: ' + partial : 'میکروفون فعال است؛ صحبت کنید…');
        });
        if (typeof recognizer.on === 'function') {
          recognizer.on('error', function (message) {
            var detail = message && (message.error || message.message) || 'خطای ناشناخته';
            status('خطای موتور تشخیص گفتار: ' + detail);
          });
        }
        source = audioContext.createMediaStreamSource(stream);
        processor = audioContext.createScriptProcessor(4096, 1, 1);
        muted = audioContext.createGain();
        muted.gain.value = 0;
        processor.onaudioprocess = function (event) {
          if (!active || !recognizer) return;
          frames++;
          if (frames === 1 && captureWatchdog) { clearTimeout(captureWatchdog); captureWatchdog = null; }
          try {
            var data = event.inputBuffer.getChannelData(0), sum = 0;
            for (var i = 0; i < data.length; i += 8) sum += data[i] * data[i];
            if (sum > 0.000001) signalFrames++;
            recognizer.acceptWaveform(event.inputBuffer);
            if (frames >= 12 && Date.now() - lastStatus > 1800) {
              lastStatus = Date.now();
              status(signalFrames ? 'میکروفون صدا دریافت می‌کند؛ صحبت کنید…' : 'میکروفون فعال است اما هنوز صدای قابل‌تشخیصی دریافت نشده؛ نزدیک‌تر صحبت کنید و مجوز/ورودی میکروفون را بررسی کنید.');
            }
          } catch (error) {
            status('خطا در پردازش صوت محلی: ' + (error.message || error));
          }
        };
        active = true;
        var voiceApi = window.UAI && window.UAI.Voice;
        if (voiceApi) {
          voiceApi.listening = true;
          if (typeof voiceApi.setBtn === 'function') voiceApi.setBtn(true);
        }
        source.connect(processor);
        processor.connect(muted);
        muted.connect(audioContext.destination);
        captureWatchdog = setTimeout(function () {
          captureWatchdog = null;
          if (active && frames === 0) {
            status('میکروفون مجاز شده اما مرورگر هیچ فریم صوتی به برنامه نداد. ورودی میکروفون را بررسی کنید، دسترسی سایت را دوباره بدهید و صفحه را تازه‌سازی کنید.');
            stopCapture(false);
          }
        }, 5000);
        status('ضبط فعال شد؛ اکنون صحبت کنید. برای پایان، «توقف ضبط» را بزنید.');
      });
    }).catch(function (error) {
      stopCapture(false);
      var name = error && error.name || '';
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        throw new Error('مجوز میکروفون رد شده است. در تنظیمات سایت، Microphone را روی Allow بگذارید و صفحه را دوباره باز کنید.');
      }
      if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        throw new Error('هیچ میکروفون فعالی پیدا نشد. اتصال یا ورودی میکروفون گوشی را بررسی کنید.');
      }
      throw error;
    });
  }
  function applyTranscript(value, context) {
    value = String(value || '').trim();
    if (!value) { if (typeof toast === 'function') toast('متنی برای ارسال وجود ندارد', true); return; }
    if (context === 'sale' && typeof window.yqApplyVoiceDraft === 'function') {
      window.yqApplyVoiceDraft(value);
      return;
    }
    var assistantUI = window.UAI && window.UAI.ui;
    if (assistantUI && typeof assistantUI.submit === 'function') {
      assistantUI.submit(value, 'voice');
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
      '<div class="toolbar"><button class="btn" id="yqVInstall" type="button">دریافت / آماده‌سازی مدل فارسی</button><button class="btn primary" id="yqVStart" type="button">اجازه میکروفون و شروع ضبط</button><button class="btn" id="yqVStop" type="button">توقف ضبط</button></div>' +
      '<textarea id="yqVTranscript" rows="4" placeholder="متن تشخیص‌داده‌شده اینجا نمایش داده می‌شود؛ قبل از استفاده آن را بررسی کنید."></textarea>' +
      '<div class="modal-actions"><button class="btn" id="yqVText" type="button">ورود متن</button><button class="btn primary" id="yqVApply" type="button">تأیید و افزودن به پیش‌نویس</button></div>'
    );
    byId('yqVInstall').onclick = function () {
      byId('yqVInstall').disabled = true;
      ensureModel().then(function () { status('مدل آماده است. حالا «اجازه میکروفون و شروع ضبط» را بزنید.'); })
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
      stopCapture(false, true).then(function () {
        status(finalText ? 'ضبط متوقف شد؛ متن تشخیص‌داده‌شده را بررسی کنید.' : 'ضبط متوقف شد اما متنی تشخیص داده نشد. دوباره شروع کنید و نزدیک میکروفون واضح صحبت کنید.');
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
  window.yqVoiceDraft = function (context) {
    if (!window.isSecureContext && location.hostname !== 'localhost') {
      modal('<div class="modalhead"><h2>دستیار گفتاری</h2><button class="close" data-close>×</button></div><p>برای دسترسی به میکروفون، برنامه باید از HTTPS باز شود.</p>');
      return;
    }
    showDialog(context === 'sale' ? 'sale' : 'assistant');
  };
  window.voiceRecord = function () {
    var voiceApi = window.UAI && window.UAI.Voice;
    if (active || (voiceApi && voiceApi.listening)) {
      return stopCapture(false, true).then(function () {
        status(finalText ? 'ضبط متوقف شد؛ متن را بررسی کنید.' : 'ضبط متوقف شد.');
      });
    }
    window.yqVoiceDraft('assistant');
    return true;
  };
  var voiceApi = window.UAI && window.UAI.Voice;
  if (voiceApi) {
    voiceApi.stop = function () {
      return stopCapture(false, true).then(function () {
        status(finalText ? 'ضبط متوقف شد؛ متن را بررسی کنید.' : 'ضبط متوقف شد.');
      });
    };
  }
  window.addEventListener('pagehide', function () { stopCapture(true); });
})();