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


def test_station_has_fallbacks():
    h = u.station_html([{"id": "rFZHOHl-L8A", "title": "a"}, {"id": "JD-kMIpDfnY", "title": "b"}],
                       {"url": "https://stream.laut.fm/lofi", "title": "r"})
    assert "rFZHOHl-L8A" in h and "JD-kMIpDfnY" in h and "stream.laut.fm/lofi" in h
    assert "onError" in h and "iframe_api" in h


def test_app_uses_verified_lofi_ids():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"), encoding="utf8").read()
    assert "jfKfPfyJRdk" not in src           # ended stream (YouTube error 150)
    assert "rFZHOHl-L8A" in src
