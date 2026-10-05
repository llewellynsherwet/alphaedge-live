"""Client-side HTML widgets for app.py.

Streamlit re-creates an iframe whenever its HTML changes, which wipes a TradingView
chart (and every drawing on it). So the main chart is ONE component whose HTML never
changes (`persistent_chart_html`). Inside it we keep one TradingView Advanced Chart per
visited symbol and only show/hide them, so drawings stay put when you switch pairs
and come back. The sidebar selection reaches the chart through a tiny "bridge" iframe
(`chart_bridge_html`) that re-renders on every symbol change and calls into the chart
frame (same origin) plus writes sessionStorage as a fallback.

`station_html` is radio-first (HTML5 audio with multi-source fallback). Optional YouTube
links open on youtube.com — we never scrape YouTube for music. Live Financial TV uses
`TV_CHANNELS` + same-origin `static/tv.html` (YouTube live_stream embed with radio / Twitch /
HLS fallbacks). Prefer `st.iframe(tv_static_url(...))` so the player has a real origin
(srcdoc YouTube iframes hit Error 153).
"""
from __future__ import annotations

import html as _html_mod
import json

TV_AFF = "163585"


def _esc(s: str) -> str:
    return _html_mod.escape(s, quote=True)

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


# ── Live Financial TV (channel picker + in-page playable embeds) ──────────────

# Channel id → YouTube live_stream (+ optional radio / Twitch / HLS fallbacks).
# Use tv_static_url() → /app/static/tv.html so video plays in-page (not Open-on-YouTube only).
TV_CHANNELS = {
    "Bloomberg Markets": {
        "youtube_channel": "UCIALMKvObZNtJ6AmdCLP7Lg",
        "streams_url": "https://www.youtube.com/@markets/streams",
        "blurb": "Bloomberg Markets live on YouTube · Bloomberg Radio fallback",
        "audio": {
            "title": "Bloomberg Radio (WBBR)",
            "urls": [
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC48.aac",
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC.aac",
            ],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "CNBC Live": {
        "youtube_channel": "UCvJJ_dzjViJCoLf5uKUTwoA",
        "streams_url": "https://www.youtube.com/@CNBC/streams",
        "blurb": "CNBC live on YouTube · radio/Twitch fallbacks",
        "audio": {
            "title": "News / markets radio fallback",
            "urls": [
                "https://npr-ice.streamguys1.com/live.mp3",
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC48.aac",
            ],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "Reuters TV": {
        "youtube_channel": "UChqUTb7kYRX8-EiaN3XFrSQ",
        "streams_url": "https://www.youtube.com/@Reuters/streams",
        "blurb": "Reuters live on YouTube",
        "audio": {
            "title": "World news radio fallback",
            "urls": [
                "https://npr-ice.streamguys1.com/live.mp3",
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC48.aac",
            ],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "Yahoo Finance": {
        "youtube_channel": "UCEAZeUIeJs0IjQiqTCdVSIg",
        "streams_url": "https://www.youtube.com/@YahooFinance/streams",
        "blurb": "Yahoo Finance live on YouTube",
        "audio": {
            "title": "Markets radio fallback",
            "urls": [
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC48.aac",
                "https://npr-ice.streamguys1.com/live.mp3",
            ],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "Sky News": {
        "youtube_channel": "UCoMdktPbSTixAyNGwb-UYkQ",
        "streams_url": "https://www.youtube.com/@SkyNews/streams",
        "blurb": "Sky News live on YouTube",
        "audio": {
            "title": "News radio fallback",
            "urls": ["https://npr-ice.streamguys1.com/live.mp3"],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "DW News": {
        "youtube_channel": "UCknLrEdhRCp1aegoMqRaCZg",
        "streams_url": "https://www.youtube.com/@DWNews/streams",
        "blurb": "Deutsche Welle News live on YouTube",
        "audio": {
            "title": "News radio fallback",
            "urls": ["https://npr-ice.streamguys1.com/live.mp3"],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "France 24": {
        "youtube_channel": "UCCCPCZNChQdGa9EkATeye4g",
        "streams_url": "https://www.youtube.com/@FRANCE24/streams",
        "blurb": "France 24 English live on YouTube",
        "audio": {
            "title": "News radio fallback",
            "urls": ["https://npr-ice.streamguys1.com/live.mp3"],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
    "Bloomberg Radio": {
        "youtube_channel": "UCIALMKvObZNtJ6AmdCLP7Lg",
        "streams_url": "https://www.youtube.com/@markets/streams",
        "blurb": "Bloomberg Radio audio-first · TV still available",
        "default_mode": "radio",
        "audio": {
            "title": "Bloomberg Radio (WBBR)",
            "urls": [
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC48.aac",
                "https://playerservices.streamtheworld.com/api/livestream-redirect/WBBRAMAAC.aac",
            ],
        },
        "alt": "stocktwits",
        "alt_kind": "twitch",
    },
}


def tv_youtube_embed_url(channel: str) -> str:
    """Direct YouTube live_stream embed URL (use with st.iframe, not srcdoc)."""
    ch = TV_CHANNELS.get(channel) or TV_CHANNELS["Bloomberg Markets"]
    cid = ch.get("youtube_channel") or ""
    vid = ch.get("fallback_video") or ""
    if vid:
        return f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&playsinline=1&rel=0"
    return (
        f"https://www.youtube.com/embed/live_stream?channel={cid}"
        f"&autoplay=1&mute=1&playsinline=1&rel=0"
    )


def tv_static_url(channel: str) -> str:
    """Same-origin Live TV player (YouTube + radio + alt). Requires static serving."""
    from urllib.parse import urlencode
    ch = TV_CHANNELS.get(channel) or TV_CHANNELS["Bloomberg Markets"]
    q = {
        "title": channel,
        "ch": ch.get("youtube_channel") or "",
        "streams": ch.get("streams_url") or "",
    }
    if ch.get("fallback_video"):
        q["vid"] = ch["fallback_video"]
    audio = ch.get("audio") or {}
    urls = []
    if audio.get("url"):
        urls.append(str(audio["url"]))
    for u in (audio.get("urls") or []) + (audio.get("fallback") or []):
        if u and str(u) not in urls:
            urls.append(str(u))
    if urls:
        q["audio"] = ",".join(urls)
        q["audio_title"] = audio.get("title") or "Finance radio"
    if ch.get("alt"):
        q["alt"] = ch["alt"]
        q["alt_kind"] = ch.get("alt_kind") or "iframe"
    if ch.get("default_mode"):
        q["mode"] = ch["default_mode"]
    return "/app/static/tv.html?" + urlencode(q)


def tv_desk_html(channel: str, height: int = 450) -> str:
    """Deprecated TradingView desk — kept so old imports don't crash; prefer tv_static_url."""
    title = _esc(channel)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#050505;color:#888;font:12px sans-serif;padding:16px}}</style>
</head><body>
<div style="color:#D4AF37;font-weight:700;margin-bottom:8px">📺 {title}</div>
<p>TradingView desk widgets were removed from Live Financial TV (they duplicate other tabs).
Use the channel picker with in-page YouTube / radio playback instead.</p>
</body></html>"""


# Back-compat alias so stale references don't break imports.
TV_DESKS = {k: {"blurb": v.get("blurb", "")} for k, v in TV_CHANNELS.items()}


def tv_channel_card_html(name: str, streams_url: str, blurb: str = "") -> str:
    """Optional external channel link card — not the primary player."""
    n = _esc(name)
    u = _esc(streams_url)
    b = _esc(blurb or (
        "Optional external channel link. Primary playback is the in-page Live TV player."
    ))
    return f"""
<div style="background:#0b0b0b;border:1px solid #333;border-radius:8px;padding:14px 14px 12px;margin:4px 0 10px 0;">
  <div style="color:#D4AF37;font-weight:700;font-size:14px;letter-spacing:.5px;margin-bottom:6px;">📺 {n}</div>
  <div style="color:#888;font-size:12px;line-height:1.5;margin-bottom:12px;">{b}</div>
  <a href="{u}" target="_blank" rel="noopener"
     style="display:inline-block;background:#D4AF37;color:#000;font-weight:700;text-decoration:none;
            padding:10px 14px;border-radius:5px;font-size:13px;">Open channel ↗</a>
</div>
"""



def station_html(radio_or_videos=None, audio: dict | None = None, height: int = 200,
                 youtube_url: str | None = None, *, videos: list | None = None,
                 radio: dict | None = None) -> str:
    """Radio-first Trading Station player with multi-URL fallback (no YouTube embed).

    New: station_html({"url","title", "fallback":[...]}, youtube_url="https://...")
         station_html(radio={...}, youtube_url=...)
    Legacy: station_html([{id,title},...], audio={url,title})
    """
    if radio is not None:
        radio_or_videos = radio
    if isinstance(radio_or_videos, list):
        videos = videos or radio_or_videos
        radio_d = audio
    elif isinstance(radio_or_videos, dict):
        radio_d = radio_or_videos
    else:
        radio_d = audio
    if not radio_d or not (radio_d.get("url") or radio_d.get("urls")):
        return ('<!doctype html><html><body style="background:#000;color:#888;font:12px sans-serif;padding:16px">'
                'No radio stream configured.</body></html>')
    if not youtube_url and videos:
        vid = videos[0] if isinstance(videos[0], dict) else None
        if vid and vid.get("id"):
            youtube_url = f"https://www.youtube.com/watch?v={vid['id']}"
    title = _esc(str(radio_d.get("title") or "Radio"))
    urls: list[str] = []
    if radio_d.get("url"):
        urls.append(str(radio_d["url"]))
    for u in radio_d.get("urls") or []:
        if u and str(u) not in urls:
            urls.append(str(u))
    for u in radio_d.get("fallback") or []:
        if u and str(u) not in urls:
            urls.append(str(u))
    yt = _esc(str(youtube_url)) if youtube_url else ""
    yt_btn = (
        f'<a class="btn gold" href="{yt}" target="_blank" rel="noopener">Open on YouTube ↗</a>'
        if yt else ""
    )
    title_js = json.dumps(str(radio_d.get("title") or "Radio"))
    urls_js = json.dumps(urls)
    primary = _esc(urls[0])
    h = int(height)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{{margin:0;background:#050505;color:#ccc;font:12px -apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}}
.wrap{{padding:12px 10px;box-sizing:border-box;height:{h}px}}
.title{{color:#D4AF37;font-weight:700;font-size:12px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.meta{{color:#666;font-size:10px;margin-bottom:8px}}
audio{{width:100%;height:36px}}
.row{{display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap}}
.btn{{background:#1c1c1c;color:#D4AF37;border:1px solid #333;border-radius:3px;padding:4px 8px;text-decoration:none;font-size:10px;cursor:pointer;font-family:inherit}}
.btn.gold{{background:#D4AF37;color:#000;border-color:#D4AF37;font-weight:700}}
#st{{color:#888;font-size:10px;margin-top:6px;min-height:14px}}
</style></head><body>
<div class="wrap">
  <div class="title">♪ {title}</div>
  <div class="meta">In-page radio · auto-fallback streams · press ▶ if blocked</div>
  <audio id="au" controls preload="auto" playsinline src="{primary}"></audio>
  <div class="row">
    <button class="btn" id="play" type="button">▶ Play</button>
    <button class="btn" id="next" type="button">Next stream</button>
    {yt_btn}
  </div>
  <div id="st">Ready</div>
</div>
<script>
(function(){{
  var urls = {urls_js};
  var idx = 0;
  var au = document.getElementById('au'), st = document.getElementById('st');
  function set(t, ok){{ st.textContent = t; st.style.color = ok===1 ? '#00ff88' : (ok===0 ? '#ff6b6b' : '#888'); }}
  function load(i, autoplay){{
    if (!urls.length) {{ set('No streams configured', 0); return; }}
    idx = ((i % urls.length) + urls.length) % urls.length;
    au.src = urls[idx];
    au.load();
    set('Stream ' + (idx+1) + '/' + urls.length + ' — loading…', 2);
    if (autoplay) {{
      au.play().then(function(){{ set('Playing · stream ' + (idx+1) + '/' + urls.length, 1); }})
        .catch(function(){{ set('Ready — press ▶ to start (stream ' + (idx+1) + ')', 2); }});
    }}
  }}
  document.getElementById('play').onclick = function(){{
    au.play().then(function(){{ set('Playing · stream ' + (idx+1) + '/' + urls.length, 1); }})
      .catch(function(){{ set('Press play on the audio bar if blocked', 0); }});
  }};
  document.getElementById('next').onclick = function(){{ load(idx + 1, true); }};
  au.addEventListener('playing', function(){{ set('Playing · stream ' + (idx+1) + '/' + urls.length, 1); }});
  au.addEventListener('error', function(){{
    if (idx + 1 < urls.length) {{
      set('Stream failed — trying next…', 0);
      setTimeout(function(){{ load(idx + 1, true); }}, 400);
    }} else {{
      set('All streams failed — try Next stream or another station', 0);
    }}
  }});
  // Attempt autoplay; browsers may require a click.
  load(0, true);
  window.AE_STATION = {{get: function(){{ return {{mode:'radio', title: {title_js}, url: urls[idx], urls: urls}}; }}}};
}})();
</script></body></html>"""


def station_static_url(radio: dict, youtube_url: str | None = None) -> str:
    """Same-origin static station page URL (requires server.enableStaticServing)."""
    from urllib.parse import urlencode
    url = radio.get("url") or (radio.get("urls") or [""])[0]
    q = {"url": url, "title": radio.get("title") or "Radio"}
    if youtube_url:
        q["yt"] = youtube_url
    # Pass fallbacks as comma-separated extras when present
    extras = []
    for u in (radio.get("urls") or []) + (radio.get("fallback") or []):
        if u and u != url and u not in extras:
            extras.append(u)
    if extras:
        q["alts"] = ",".join(extras)
    return "/app/static/station.html?" + urlencode(q)
