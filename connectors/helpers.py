from decimal import Decimal, ROUND_05UP
import hashlib
import struct

from connectors.enums import Provider, MarketType


def _s2i(v: str) -> int | None:
    return int(v) if v else None

def _s2f(v) -> float | None:
    return (float(v) if type(v) == str else v) if v else None

def _s2dec(v) -> Decimal | None:
    return (Decimal(v) if type(v) == str else Decimal(str(v))) if v else None

def _normdec(v: Decimal, step: Decimal) -> Decimal:
    return (v / step).to_integral_value(rounding=ROUND_05UP) * step  # .normalize() ##ROUND_HALF_EVEN

# if one of the arguments is 0, the result is true
def opposite_sign(a: Decimal, b: Decimal) -> bool:
    return (a > 0) != (b > 0)

# ----- id generators -----

# hashlib is used because of the result of hash() changes every time Python restarted
# (because Python introduces hash randomization for security)

def gen_asset_id(provider_id: Provider, market_id: MarketType, ticker: str) -> int:
    data = struct.pack("qq", provider_id.value, market_id.value) + ticker.encode()
    return int(hashlib.sha256(data).hexdigest(), 16) & ((1 << 64) - 1)

def gen_agent_id(agent_name: str):
    return int(hashlib.sha256(agent_name.encode()).hexdigest(), 16) & ((1 << 64) - 1)
