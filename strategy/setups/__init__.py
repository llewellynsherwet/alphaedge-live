from .smc_sweep import evaluate as smc_sweep
from .orb_open import evaluate as orb_open
from .vwap_pullback import evaluate as vwap_pullback

REGISTRY = {
    "smc_sweep": smc_sweep,
    "orb_open": orb_open,
    "vwap_pullback": vwap_pullback,
}
