from .smc_sweep import evaluate as smc_sweep
from .orb_open import evaluate as orb_open
from .vwap_pullback import evaluate as vwap_pullback
from .ema_vwap_kz import evaluate as ema_vwap_kz
from .pip_builder import evaluate as pip_builder

REGISTRY = {
    "smc_sweep": smc_sweep,
    "orb_open": orb_open,
    "vwap_pullback": vwap_pullback,
    "ema_vwap_kz": ema_vwap_kz,
    "pip_builder": pip_builder,
}
