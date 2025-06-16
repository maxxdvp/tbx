from connectors.enums import ConnMode, MarketType

LOG_PREFIX = "ByBit API Error:"


BaseUrls = {ConnMode.NORMAL: "https://api.bybit.com", ConnMode.DEMO: "https://api-demo.bybit.com", ConnMode.TESTNET: "https://api-testnet.bybit.com"}

MarketTypes = {"spot": MarketType.SPOT, "linear": MarketType.FUTURE, "inverse": MarketType.FUTUREINV, "option": MarketType.OPTION}
ReverseMarketTypes = {v: k for k, v in MarketTypes.items()}


def _market_type2str(market: MarketType) -> str:
    try:
        return ReverseMarketTypes[market]
    except KeyError:
        raise TypeError(f"Unknown market type {market}")


def _str2market_type(market: str) -> MarketType:
    try:
        return MarketTypes[market]
    except KeyError:
        raise TypeError(f"Unknown market type '{market}'")
