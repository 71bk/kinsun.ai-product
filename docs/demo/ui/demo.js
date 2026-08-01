/* ==========================================================================
   kinsun.ai UI Demo — 共用 harness
   1) 注入 SVG icon sprite（無 emoji，全部向量）
   2) 畫面切換
   3) Viewport 切換 + 自動縮放，用於檢視 RWD
   ========================================================================== */

(function () {
  'use strict';

  /* ---------- 1. Icon sprite ---------- */
  var ICONS = {
    mic: '<path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4"/>',
    'mic-slash': '<path d="M9 5a3 3 0 0 1 6 0v5.5"/><path d="M9 9.5V11a3 3 0 0 0 4.6 2.5"/><path d="M19 10v1a7 7 0 0 1-10.6 6"/><path d="M5 10v1a7 7 0 0 0 2 4.9"/><path d="M12 18v4"/><path d="M3 3l18 18"/>',
    'wifi-slash': '<path d="M3 3l18 18"/><path d="M2 8.8A16 16 0 0 1 8.2 5.4"/><path d="M13.5 5.2A16 16 0 0 1 22 8.8"/><path d="M5.2 12.6a11 11 0 0 1 3.6-2.3"/><path d="M18.8 12.6a11 11 0 0 0-3-2"/><path d="M8.6 16.3a6 6 0 0 1 6.2-.6"/><path d="M12 20v.01"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="M8.2 12.3l2.6 2.6 4.8-5.3"/>',
    dashed: '<circle cx="12" cy="12" r="9" stroke-dasharray="3.2 3.2"/>',
    warn: '<path d="M12 4L2.8 19.5h18.4z"/><path d="M12 10v4"/><path d="M12 16.9v.01"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    minus: '<path d="M5 12h14"/>',
    send: '<path d="M21 3L10.5 13.5"/><path d="M21 3l-6.6 18-3.9-8-8-3.9z"/>',
    play: '<path d="M8 5.2l11 6.8-11 6.8z"/>',
    pause: '<path d="M9 5v14M15 5v14"/>',
    speaker: '<path d="M4 9.5v5h3.5L13 19V5L7.5 9.5H4z"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 6.8a7.5 7.5 0 0 1 0 10.4"/>',
    repeat: '<path d="M4 9a5 5 0 0 1 5-5h11"/><path d="M17 1l3 3-3 3"/><path d="M20 15a5 5 0 0 1-5 5H4"/><path d="M7 23l-3-3 3-3"/>',
    back: '<path d="M20 12H5"/><path d="M11 6l-6 6 6 6"/>',
    next: '<path d="M9 5l7 7-7 7"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.6v2.2M12 19.2v2.2M4.4 4.4l1.6 1.6M18 18l1.6 1.6M2.6 12h2.2M19.2 12h2.2M4.4 19.6L6 18M18 6l1.6-1.6"/>',
    user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.6 20.2a7.4 7.4 0 0 1 14.8 0"/>',
    users: '<circle cx="9" cy="8" r="3.2"/><path d="M2.6 20a6.4 6.4 0 0 1 12.8 0"/><path d="M16.2 5.3a3.2 3.2 0 0 1 0 5.8"/><path d="M17.6 14.3A6.4 6.4 0 0 1 21.4 20"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6.8v5.4l3.4 2"/>',
    note: '<path d="M6 3h8.5L19 7.5V21H6z"/><path d="M14.2 3v4.6H19"/><path d="M9 12.5h6M9 16.2h4"/>',
    bell: '<path d="M18 9.5a6 6 0 1 0-12 0c0 5-2.2 6.3-2.2 6.3h16.4S18 14.5 18 9.5"/><path d="M10.2 19.6a2.2 2.2 0 0 0 3.6 0"/>',
    house: '<path d="M3.6 11L12 3.8 20.4 11"/><path d="M6 9.7V20.2h12V9.7"/>',
    list: '<path d="M8.5 6h12M8.5 12h12M8.5 18h12M3.6 6h.01M3.6 12h.01M3.6 18h.01"/>',
    shield: '<path d="M12 3.2l8 2.9v6.1c0 4.9-3.4 8.2-8 9.4-4.6-1.2-8-4.5-8-9.4V6.1z"/><path d="M9 12.2l2.2 2.2 4-4.2"/>',
    trash: '<path d="M4 7h16"/><path d="M9.2 7V4h5.6v3"/><path d="M6.2 7l1 13.2h9.6L17.8 7"/>',
    search: '<circle cx="11" cy="11" r="6.6"/><path d="M15.8 15.8l4.6 4.6"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.6 6.6L12 13l8.4-6.4"/>',
    link: '<path d="M10.2 13.4a4.6 4.6 0 0 0 6.6 0l2.4-2.4a4.6 4.6 0 1 0-6.6-6.6l-1.3 1.3"/><path d="M13.8 10.6a4.6 4.6 0 0 0-6.6 0l-2.4 2.4a4.6 4.6 0 1 0 6.6 6.6l1.3-1.3"/>',
    chat: '<path d="M21 11.7a8 8 0 0 1-11.7 7.1L4 20.4l1.6-5.2A8 8 0 1 1 21 11.7z"/>',
    pencil: '<path d="M4 20.2h4.2L19 9.4l-4.2-4.2L4 16z"/><path d="M13.8 6.3l4.2 4.2"/>',
    book: '<path d="M4 5.2A2.2 2.2 0 0 1 6.2 3H19.5v15.5H6.2A2.2 2.2 0 0 0 4 20.7z"/><path d="M4 18.5A2.2 2.2 0 0 1 6.2 21H19.5"/>',
    trophy: '<path d="M7 3.8h10v4.4a5 5 0 0 1-10 0z"/><path d="M7 5.6H4v1.2a3.2 3.2 0 0 0 3.2 3.2M17 5.6h3v1.2a3.2 3.2 0 0 1-3.2 3.2"/><path d="M12 13.2v3.6M9 20.4h6M10.2 16.8h3.6"/>',
    code: '<path d="M9 18.4L3.6 12 9 5.6M15 5.6L20.4 12 15 18.4"/>',
    download: '<path d="M12 3.8v11M8 11l4 4 4-4"/><path d="M4.2 19.6h15.6"/>',
    flag: '<path d="M5.2 21V3.4"/><path d="M5.2 4.6h13.4l-2.6 4.2 2.6 4.2H5.2"/>',
    'eye-slash': '<path d="M3 3l18 18"/><path d="M10.5 6.2A9.4 9.4 0 0 1 12 6.1c5 0 9 5.9 9 5.9a17.4 17.4 0 0 1-2.9 3.4"/><path d="M6.4 8.1A16.9 16.9 0 0 0 3 12s4 5.9 9 5.9a8.7 8.7 0 0 0 3.4-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    filter: '<path d="M3.4 5h17.2l-6.6 7.8V20l-4-2.4v-4.8z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3.2 12h17.6"/><path d="M12 3a14 14 0 0 1 0 18A14 14 0 0 1 12 3z"/>',
    pin: '<path d="M12 21s6.4-5.6 6.4-10.4A6.4 6.4 0 0 0 5.6 10.6C5.6 15.4 12 21 12 21z"/><circle cx="12" cy="10.4" r="2.4"/>'
  };

  function injectSprite() {
    var parts = ['<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">'];
    for (var k in ICONS) {
      parts.push('<symbol id="i-' + k + '" viewBox="0 0 24 24">' + ICONS[k] + '</symbol>');
    }
    parts.push('</svg>');
    var host = document.createElement('div');
    host.innerHTML = parts.join('');
    document.body.insertBefore(host.firstChild, document.body.firstChild);
  }

  /* ---------- 2. Viewport ---------- */
  var VIEWS = {
    tp: { w: 768,  h: 1024, label: '平板直式 768×1024' },
    tl: { w: 1024, h: 768,  label: '平板橫式 1024×768' },
    ph: { w: 390,  h: 844,  label: '手機 390×844' },
    dt: { w: 1280, h: 800,  label: '桌機 1280×800' }
  };

  var state = { view: 'tp', screen: null };

  function applyView() {
    var v = VIEWS[state.view];
    var dev = document.querySelector('.device');
    if (!dev) return;
    dev.style.width = v.w + 'px';
    dev.style.height = v.h + 'px';
    document.querySelectorAll('[data-view]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.view === state.view));
    });
    var lbl = document.querySelector('[data-view-label]');
    if (lbl) lbl.textContent = v.label;
    fit();
  }

  function fit() {
    var stage = document.querySelector('.demo-stage');
    var wrap = document.querySelector('.frame-wrap');
    var v = VIEWS[state.view];
    if (!stage || !wrap) return;
    var pad = 64;
    var s = Math.min(1, (stage.clientWidth - pad) / v.w, (stage.clientHeight - pad) / v.h);
    wrap.style.transform = 'scale(' + (s > 0 ? s : 1) + ')';
    wrap.style.height = (v.h * (s > 0 ? s : 1)) + 'px';
  }

  /* ---------- 3. 畫面切換 ---------- */
  function showScreen(id) {
    state.screen = id;
    document.querySelectorAll('.screen').forEach(function (s) {
      s.dataset.active = String(s.id === id);
    });
    document.querySelectorAll('[data-screen]').forEach(function (b) {
      b.setAttribute('aria-current', String(b.dataset.screen === id));
    });
    var sc = document.getElementById(id);
    var host = document.querySelector('.device');
    if (sc && host && sc.dataset.surface) host.parentElement.dataset.surface = sc.dataset.surface;
    var t = document.querySelector('[data-screen-title]');
    if (sc && t) {
      t.innerHTML = (sc.dataset.title || id) +
        '<small>' + (sc.dataset.note || '') + '</small>';
    }
    var note = document.querySelector('[data-screen-spec]');
    if (note) note.innerHTML = sc && sc.dataset.spec ? sc.dataset.spec : '';
    var pane = document.querySelector('.device');
    if (pane) pane.scrollTop = 0;
  }

  /* ---------- 4. Bind ---------- */
  function init() {
    injectSprite();

    document.querySelectorAll('[data-screen]').forEach(function (b) {
      b.addEventListener('click', function () { showScreen(b.dataset.screen); });
    });
    document.querySelectorAll('[data-view]').forEach(function (b) {
      b.addEventListener('click', function () { state.view = b.dataset.view; applyView(); });
    });

    /* 畫面內的 tab / 狀態切換：data-toggle-group + data-toggle-target */
    document.querySelectorAll('[data-toggle-group]').forEach(function (g) {
      g.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-toggle-target]');
        if (!btn) return;
        var scope = document.getElementById(g.dataset.toggleGroup);
        if (!scope) return;
        g.querySelectorAll('[data-toggle-target]').forEach(function (b) {
          var on = b === btn;
          b.setAttribute('aria-selected', String(on));
          b.setAttribute('aria-pressed', String(on));
        });
        scope.querySelectorAll('[data-toggle-panel]').forEach(function (p) {
          p.hidden = p.dataset.togglePanel !== btn.dataset.toggleTarget;
        });
      });
    });

    /* switch 元件 */
    document.querySelectorAll('.switch').forEach(function (s) {
      s.addEventListener('click', function () {
        s.setAttribute('aria-checked', s.getAttribute('aria-checked') === 'true' ? 'false' : 'true');
      });
    });

    /* 支援 elder.html#e4 這類深連結，讓總覽頁可直接指到單一畫面 */
    var hash = location.hash.slice(1);
    var first = document.querySelector('[data-screen]');
    if (hash && document.getElementById(hash)) { showScreen(hash); }
    else if (first) { showScreen(first.dataset.screen); }
    applyView();
    window.addEventListener('resize', fit);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
