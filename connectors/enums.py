from enum import Enum
from typing import TypeVar, Type, Optional


T = TypeVar("T", bound="BaseEnum")  # type variable to ensure the method returns the correct Enum subtype
class BaseEnum(Enum):
    @classmethod
    def get_id(cls: Type[T], name: str) -> Optional[T]:
        """Returns the enum member instead of its integer value, or None if not present."""
        return cls.__members__.get(name.upper())


class ConnMode(Enum):
    NORMAL = 0
    DEMO = 1
    TESTNET = 2


class Provider(BaseEnum):
    BYBIT = 1
    BINANCE = 2
    ONEINCH = 3
    JUPITER = 4


class ProviderType(Enum):
    EX = 1
    CEX = 2
    DEX = 3


class MarketType(BaseEnum):
    SPOT = 1
    FUTURE = 2
    FUTUREINV = 3
    OPTION = 4


class Network(BaseEnum):
    ETHEREUM = 1
    SOLANA = 2
    POLYGON = 3


class Connector:
    provider: Provider
    type: ProviderType
    markets: [MarketType]
    networks: [Network]


class OpSide(Enum):
    BUY = 1
    SELL = 2
    FUND = 3
    UNFUND = 4

class OpType(Enum):
    NON_AUTO = 0
    TAKE_PROFIT = 1
    STOP_LOSS = 2
    STOP_LIMIT = 3
    FUND_FEE = 4

class TxStatus(Enum):
    CANCELLED = 0
    REJECTED = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
