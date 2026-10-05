"""The persistent chart only survives Streamlit reruns if its HTML never changes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_widgets as u  # noqa: E402


def test_chart_html_is_constant_and_symbol_free():
    a, b = u.persistent_chart_html("FX:EURUSD"), u.persistent_chart_html("FX:EURUSD")
    assert a == b
    assert "OANDA:US30USD" not in a          # current selection must not be baked in
    for opt in ('"allow_symbol_change": true', '"hide_side_toolbar": false', '"withdateranges": true',
                '"details": true', '"calendar": true', '"save_image": true', '"theme": "dark"'):
        assert opt in a, opt


def test_bridge_carries_symbol_and_marker():
    h = u.chart_bridge_html("OANDA:US30USD")
    assert '"OANDA:US30USD"' in h and "ae-chart-bridge" in h and "AE_CHART" in h


def test_tv_chart_url_encodes_symbol():
    assert u.tv_chart_url("OANDA:US30USD").startswith("https://www.tradingview.com/chart/?symbol=OANDA%3AUS30USD")


def test_station_is_radio_first_no_youtube_embed():
    h = u.station_html({"url": "https://lofi.stream.laut.fm/lofi", "title": "laut.fm lofi",
                        "fallback": ["https://ice1.somafm.com/dronezone-128-mp3"]},
                       youtube_url="https://www.youtube.com/@LofiGirl")
    assert "lofi.stream.laut.fm/lofi" in h
    assert "Open on YouTube" in h
    assert "iframe_api" not in h
    assert "youtube.com/embed" not in h
    assert "Next stream" in h
    assert "dronezone" in h
    assert "mode:'radio'" in h or 'mode:"radio"' in h or "mode:'radio'" in h.replace('"', "'")


def test_station_legacy_videos_audio_shape():
    h = u.station_html([{"id": "rFZHOHl-L8A", "title": "a"}],
                       {"url": "https://stream.laut.fm/lofi", "title": "r"})
    assert "stream.laut.fm/lofi" in h
    assert "iframe_api" not in h


def test_tv_channels_include_bloomberg_and_playable_fallbacks():
    assert "Bloomberg Markets" in u.TV_CHANNELS
    assert "CNBC Live" in u.TV_CHANNELS
    assert "Reuters TV" in u.TV_CHANNELS
    bb = u.TV_CHANNELS["Bloomberg Markets"]
    assert bb["youtube_channel"].startswith("UC")
    assert bb["audio"]["urls"]
    url = u.tv_static_url("Bloomberg Markets")
    assert url.startswith("/app/static/tv.html?")
    assert "UCIALMKvObZNtJ6AmdCLP7Lg" in url
    assert "WBBRAMAAC48" in url
    assert "stocktwits" in url
    embed = u.tv_youtube_embed_url("Bloomberg Markets")
    assert "embed/live_stream" in embed
    assert "UCIALMKvObZNtJ6AmdCLP7Lg" in embed


def test_tv_channel_card_is_optional_external_link():
    h = u.tv_channel_card_html("Bloomberg Markets", "https://www.youtube.com/@markets/streams")
    assert "Open channel" in h
    assert "@markets/streams" in h


def test_app_uses_channel_picker_not_tradingview_desk():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"), encoding="utf8").read()
    assert "TV_CHANNELS" in src
    assert "tv_static_url" in src
    assert "embed/live_stream" in src or "tv_youtube_embed_url" in src
    assert "STATIONS_YT" not in src
    # TradingView desk clutter must not drive the Live TV sidebar
    assert "tv_desk_html(" not in src
    assert "Market Overview" not in src.split("LIVE FINANCIAL TV", 1)[-1].split("TRADING STATION", 1)[0]
