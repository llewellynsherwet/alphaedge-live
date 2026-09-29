"""Client-side HTML widgets for app.py.

Streamlit re-creates an iframe whenever its HTML changes, which wipes a TradingView
chart (and every drawing on it). So the main chart is ONE component whose HTML never
changes (`persistent_chart_html`). Inside it we keep one TradingView Advanced Chart per
visited symbol and only show/hide them, so drawings stay put when you switch pairs
and come back. The sidebar selection reaches the chart through a tiny "bridge" iframe
(`chart_bridge_html`) that re-renders on every symbol change and calls into the chart
frame (same origin) plus writes sessionStorage as a fallback.

`station_html` is a YouTube player with an ordered list of fallback video IDs plus a
final plain-audio stream, so a live stream that ends doesn't leave "Video unavailable".
"""
from __future__ import annotations

import json

TV_AFF = "163585"

CHART_OPTIONS = {
    "autosize": True,
    "interval": "60",
    "timezone": "Etc/UTC",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "toolbar_bg": "#131722",
    "enable_publishing": False,
    "allow_symbol_change": True,
    "hide_top_toolbar": False,
    "hide_side_toolbar": False,
    "hide_legend": False,
    "withdateranges": True,
    "details": True,
    "hotlist": True,
    "calendar": True,
    "save_image": True,
    "show_popup_button": True,
    "popup_width": "1400",
    "popup_height": "900",
    "studies": ["STD;EMA"],
}


def tv_chart_url(tv_symbol: str) -> str:
    from urllib.parse import quote
    return f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol, safe='')}&aff_id={TV_AFF}"


def persistent_chart_html(default_symbol: str = "FX:EURUSD", max_charts: int = 10) -> str:
    """Constant HTML (do NOT interpolate the current symbol here, or the iframe reloads)."""
    opts = json.dumps(CHART_OPTIONS)
    return """<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;background:#0b0e14;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
#bar{height:40px;box-sizing:border-box;display:flex;align-items:center;gap:8px;padding:0 10px;background:#131722;border-bottom:1px solid #2a2e39;color:#d1d4dc;font-size:12px;white-space:nowrap}
#sym{font-weight:700;color:#D4AF37;font-size:14px;letter-spacing:.5px}
#info{color:#787b86;overflow:hidden;text-overflow:ellipsis;flex:1}
.btn{background:#2a2e39;color:#d1d4dc;border:1px solid #363a45;border-radius:4px;padding:5px 10px;cursor:pointer;font-size:12px;text-decoration:none;font-family:inherit}
.btn:hover{background:#363a45;color:#fff}
.btn.gold{background:#D4AF37;color:#000;border-color:#D4AF37;font-weight:700}
#stack{position:relative;height:calc(100% - 40px)}
.pane{position:absolute;inset:0;visibility:hidden;z-index:0}
.pane.active{visibility:visible;z-index:1}
</style>
<script src="https://s3.tradingview.com/tv.js"></script>
</head><body>
<div id="bar">
  <span id="sym">—</span>
  <span id="info">Drawings are kept per pair while this page stays open</span>
  <a id="open" class="btn" href="https://www.tradingview.com/chart/?aff_id=""" + TV_AFF + """" target="_blank" rel="noopener" title="Opens the full TradingView platform. Drawings made there save to your TradingView account.">Open full chart on TradingView ↗</a>
  <button id="fs" class="btn gold" title="Fullscreen (Esc to exit)">⛶ Fullscreen</button>
</div>
<div id="stack"></div>
<script>
(function(){
  var OPTS = """ + opts + """;
  var MAX = """ + str(int(max_charts)) + """;
  var DEFAULT = """ + json.dumps(default_symbol) + """;
  var KEY = 'ae_chart_symbol';
  var stack = document.getElementById('stack');
  var panes = {}, order = [], current = null, created = 0;

  function paneId(s){ return 'tv_' + s.replace(/[^A-Za-z0-9]/g, '_'); }
  function evict(){
    while (order.length >= MAX) {
      var victim = null;
      for (var i = 0; i < order.length; i++) { if (order[i] !== current) { victim = order[i]; break; } }
      if (!victim) return;
      var p = panes[victim]; if (p && p.el.parentNode) p.el.parentNode.removeChild(p.el);
      delete panes[victim]; order.splice(order.indexOf(victim), 1);
    }
  }
  function ensure(s){
    if (panes[s]) return panes[s];
    evict();
    var el = document.createElement('div'); el.className = 'pane'; el.id = paneId(s);
    stack.appendChild(el);
    var o = {}; for (var k in OPTS) o[k] = OPTS[k];
    o.symbol = s; o.container_id = el.id;
    try { new TradingView.widget(o); } catch (e) { el.innerHTML = '<p style="color:#f66;padding:20px">Chart failed to load: ' + e + '</p>'; }
    created++;
    panes[s] = {el: el}; return panes[s];
  }
  function touch(s){ var i = order.indexOf(s); if (i >= 0) order.splice(i, 1); order.push(s); }
  function show(s){
    if (!s || s === current) return;
    var p = ensure(s);
    for (var k in panes) panes[k].el.classList.remove('active');
    p.el.classList.add('active'); current = s; touch(s);
    document.getElementById('sym').textContent = s;
    document.getElementById('info').textContent = order.length + ' chart' + (order.length > 1 ? 's' : '') +
      ' open · drawings kept per pair while this page stays open (lost on refresh)';
    document.getElementById('open').href = 'https://www.tradingview.com/chart/?symbol=' + encodeURIComponent(s) + '&aff_id=""" + TV_AFF + """';
    try { sessionStorage.setItem('ae_chart_current', s); } catch (e) {}
  }
  window.AE_CHART = {show: show, panes: panes, order: order, stats: function(){ return {current: current, open: order.slice(), created: created}; }};

  var init = null; try { init = sessionStorage.getItem(KEY); } catch (e) {}
  show(init || DEFAULT);
  setInterval(function(){ var s = null; try { s = sessionStorage.getItem(KEY); } catch (e) {} if (s && s !== current) show(s); }, 700);

  // Fullscreen: fullscreen the Streamlit iframe itself; CSS overlay fallback.
  var fe = null; try { fe = window.frameElement; } catch (e) {}
  var btn = document.getElementById('fs'), overlay = false, saved = '';
  function setOverlay(on){
    if (!fe) return; overlay = on;
    if (on) { saved = fe.getAttribute('style') || ''; fe.setAttribute('style', saved + ';position:fixed;inset:0;width:100vw;height:100vh;z-index:1000000;background:#0b0e14'); }
    else { fe.setAttribute('style', saved); }
    btn.textContent = on ? '✕ Exit fullscreen' : '⛶ Fullscreen';
  }
  function fsDoc(){ try { return fe ? fe.ownerDocument : document; } catch (e) { return document; } }
  btn.addEventListener('click', function(){
    var d = fsDoc();
    if (overlay) { setOverlay(false); return; }
    if (d.fullscreenElement) { d.exitFullscreen(); return; }
    var target = fe || document.documentElement;
    var req = target.requestFullscreen || target.webkitRequestFullscreen;
    if (!req) { setOverlay(true); return; }
    try { var pr = req.call(target); if (pr && pr.catch) pr.catch(function(){ setOverlay(true); }); } catch (e) { setOverlay(true); }
  });
  try { fsDoc().addEventListener('fullscreenchange', function(){ btn.textContent = fsDoc().fullscreenElement ? '✕ Exit fullscreen' : '⛶ Fullscreen'; }); } catch (e) {}
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && overlay) setOverlay(false); });
})();
</script>
</body></html>"""


def chart_bridge_html(tv_symbol: str) -> str:
    """Tiny, invisible iframe that re-renders on each selection and tells the chart."""
    s = json.dumps(tv_symbol)
    return ("<script>(function(){var s=" + s + ";"
            "try{sessionStorage.setItem('ae_chart_symbol',s)}catch(e){}"
            "try{var fr=window.parent.frames;for(var i=0;i<fr.length;i++){try{if(fr[i].AE_CHART)fr[i].AE_CHART.show(s)}catch(e){}}}catch(e){}"
            "})();</script><!-- ae-chart-bridge -->")


def popup_chart_html(tv_symbol: str, height: int = 640) -> str:
    o = dict(CHART_OPTIONS, symbol=tv_symbol, container_id="tv_chart_popup")
    return (f'<div id="tv_chart_popup" style="height:{height}px;"></div>'
            '<script src="https://s3.tradingview.com/tv.js"></script>'
            f'<script>new TradingView.widget({json.dumps(o)});</script>')


def station_html(videos: list[dict], audio: dict | None = None, height: int = 170) -> str:
    """YouTube player trying `videos` in order (onError / not playing → next), then `audio`.

    videos: [{"id": "rFZHOHl-L8A", "title": "..."}], audio: {"url": ..., "title": ...}
    """
    cfg = json.dumps({"videos": videos, "audio": audio})
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="strict-origin-when-cross-origin">
<style>html,body{margin:0;background:#000;color:#aaa;font:11px -apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
#p{width:100%;height:""" + str(height - 22) + """px;background:#000}#p iframe{width:100%;height:100%;border:0}
#st{height:22px;line-height:22px;padding:0 4px;display:flex;gap:6px;align-items:center;white-space:nowrap;overflow:hidden}
#st span{flex:1;overflow:hidden;text-overflow:ellipsis}
button{background:#1c1c1c;color:#D4AF37;border:1px solid #333;border-radius:3px;font-size:10px;padding:1px 6px;cursor:pointer}
audio{width:100%;height:40px}</style>
</head><body><div id="p"><div id="yt"></div></div><div id="st"><span id="msg">Loading…</span><button id="nx" title="Try the next source">Next ▶</button></div>
<script>
var CFG = """ + cfg + """, idx = -1, player = null, watchdog = null, state = 'init', LOG = [];
window.AE_STATION = {get: function(){ return {idx: idx, state: state, id: (CFG.videos[idx] || {}).id || null, log: LOG.slice(-12)}; }};
function log(e, d){ LOG.push([idx, e, d]); }
function msg(t){ document.getElementById('msg').textContent = t; }
function playAudio(){
  log('audio', null); state = 'audio'; clearTimeout(watchdog);
  var a = CFG.audio; var box = document.getElementById('p');
  if (!a) { msg('No source available right now'); return; }
  box.innerHTML = '<div style="padding:18px 8px 0"><div style="color:#D4AF37;font-weight:bold;font-size:12px;margin-bottom:10px">♪ ' + a.title +
    '</div><audio id="au" controls autoplay preload="none" src="' + a.url + '"></audio>' +
    '<div style="color:#666;margin-top:8px">YouTube stream unavailable here, playing radio instead. Press ▶ if it does not start.</div></div>';
  msg('Radio fallback · Next ▶ retries YouTube');
}
function next(){
  idx++; clearTimeout(watchdog);
  if (idx >= CFG.videos.length) { playAudio(); return; }
  var v = CFG.videos[idx]; state = 'loading'; msg('▶ ' + v.title);
  if (!player) {
    player = new YT.Player('yt', {videoId: v.id, host: 'https://www.youtube.com',
      playerVars: {autoplay: 1, mute: 1, playsinline: 1, rel: 0, modestbranding: 1, origin: location.origin && location.origin !== 'null' ? location.origin : undefined},
      events: {onReady: function(e){ try { e.target.mute(); e.target.playVideo(); } catch (x) {} },
               onError: function(e){ log('error', e.data); msg('Source ' + (idx + 1) + ' unavailable (' + e.data + '), trying next…'); setTimeout(next, 600); },
               onStateChange: function(e){ log('state', e.data); if (e.data === 1) { state = 'playing'; clearTimeout(watchdog); msg('▶ ' + CFG.videos[idx].title + ' · muted, tap 🔊 to listen'); } }}});
  } else {
    try { player.loadVideoById(v.id); } catch (x) { setTimeout(next, 300); return; }
  }
  // Live stream offline / stuck without an error event → move on, but only while the
  // player is actually visible (browsers may hold back autoplay for hidden iframes).
  armWatchdog();
}
var visible = true;
try { new IntersectionObserver(function(es){ visible = es[0].isIntersecting; }).observe(document.getElementById('p')); } catch (x) {}
function armWatchdog(){
  clearTimeout(watchdog);
  watchdog = setTimeout(function(){
    if (state === 'playing' || state === 'audio') return;
    var ps = -1; try { ps = player.getPlayerState(); } catch (x) {}
    log('watchdog', ps + '/' + document.visibilityState + '/' + visible);
    if (document.visibilityState === 'visible' && visible && (ps === -1 || ps === 5)) next(); else armWatchdog();
  }, 25000);
}
document.getElementById('nx').onclick = function(){ if (state === 'audio') { idx = -1; player = null; document.getElementById('p').innerHTML = '<div id="yt"></div>'; } next(); };
window.onYouTubeIframeAPIReady = function(){ next(); };
var s = document.createElement('script'); s.src = 'https://www.youtube.com/iframe_api';
s.onerror = function(){ playAudio(); }; document.head.appendChild(s);
setTimeout(function(){ if (idx < 0) playAudio(); }, 15000);
</script></body></html>"""
