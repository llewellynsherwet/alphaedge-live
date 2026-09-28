"""Hot-reload strategy_config.yaml. Falls back to the last valid parse on error."""
import os
from copy import deepcopy
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PATH = _ROOT / "strategy_config.yaml"
_cache = {"mtime": None, "cfg": None, "path": None}


def _deep_merge(base, override):
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else _DEFAULT_PATH
    try:
        mtime = p.stat().st_mtime
    except FileNotFoundError:
        if _cache["cfg"] is not None:
            return deepcopy(_cache["cfg"])
        raise

    if _cache["cfg"] is not None and _cache["path"] == str(p) and _cache["mtime"] == mtime:
        return deepcopy(_cache["cfg"])

    try:
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict) or "symbols" not in cfg:
            raise ValueError("strategy_config.yaml missing required 'symbols' key")
        _cache.update(mtime=mtime, cfg=cfg, path=str(p))
        return deepcopy(cfg)
    except Exception as e:
        if _cache["cfg"] is not None:
            print(f"[config] reload failed ({e!r}) — keeping last good config", flush=True)
            return deepcopy(_cache["cfg"])
        raise
