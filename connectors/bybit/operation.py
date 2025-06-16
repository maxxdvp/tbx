'''
ByBit API wrapper for agent transactions.
'''

from log import mplog

from decimal import Decimal
from datetime import datetime, UTC

import asyncio

import hmac
import hashlib
import urllib.parse
import aiohttp
import json

from connectors.enums import OpSide, OpType, TxStatus
from connectors.objects import MarketType, Tx
from connectors.helpers import _s2dec
from connectors.bybit.common import _market_type2str, _str2market_type, LOG_PREFIX, ConnMode, BaseUrls


base_urls = {ConnMode.NORMAL: "https://api.bybit.com", ConnMode.DEMO: "https://api-demo.bybit.com", ConnMode.TESTNET: "https://api-testnet.bybit.com"}

class TradingOperation:

    def __init__(self, api_key: str, api_secret: str, mode: ConnMode, rcv_wnd: int = 5000):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BaseUrls[mode]
        self.rcv_wnd = str(rcv_wnd)
        self.log = mplog.get_logger("ByBitTradingOperation")

    # generates HMAC SHA256 signature
    def _generate_signature(self, timestamp: str, params: dict, encode_params: bool) -> str:
        # https://bybit-exchange.github.io/docs/v5/guide#parameters-for-authenticated-endpoints

        param_str = timestamp + self.api_key + self.rcv_wnd + (urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus) if encode_params else json.dumps(params))
        hmac_hash = hmac.new(bytes(self.api_secret, "utf-8"), param_str.encode("utf-8"), hashlib.sha256)
        return hmac_hash.hexdigest()

    # sends a GET request to ByBit API with authentication
    async def _send_request(self, endpoint: str, params: dict, post: bool = False) -> dict:
        # UTC timestamp in milliseconds
        # should adhere to the following rule: server_time - recv_window <= timestamp < server_time + 1000
        # server_time stands for Bybit server time, which can be queried via the Server Time endpoint https://bybit-exchange.github.io/docs/v5/market/time
        # timestamp = str(int(time.time() * 1000))
        timestamp = str(int(datetime.now(tz=UTC).timestamp() * 1000))
        # params.update({...})
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.rcv_wnd,
            "X-BAPI-SIGN": self._generate_signature(timestamp, params, not post),
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            if post:
                response = await session.post(url, headers=headers, data=json.dumps(params))
            else:
                response = await session.get(url, params=params, headers=headers, data={})

            if response.status != 200:
                raise Exception(f"{LOG_PREFIX}{response.reason}")
            json_data = await response.json()
            if json_data["retCode"] != 0:
                raise Exception(f"{LOG_PREFIX}{json_data['retMsg']}")

        return json_data

    async def get_market_prices(self, market: MarketType, assets: list[str], base_asset: str | None = None) -> dict:
        # https://bybit-exchange.github.io/docs/v5/market/tickers
        # https://bybit-exchange.github.io/docs/api-explorer/v5/market/tickers

        endpoint = "/v5/market/tickers"
        cat = _market_type2str(market)
        params = {"category": cat}
        match market:
            case MarketType.SPOT:
                if len(assets) > 0:
                    params["symbol"] = assets[0]
            case MarketType.FUTURE:
                params["symbol"] = assets[0]
            case MarketType.FUTUREINV:
                params["symbol"] = assets[0]
            case MarketType.OPTION:
                params["symbol"] = assets[0]  #format: SOL-30MAY25-220-C
                params["baseCoin"] = base_asset
                params["expDate"] = "25DEC22"

        data = await self._send_request(endpoint, params)

        prices = {}
        result = data.get("result", {})
        if result["category"] == cat:
            for asset in result.get("list", []):
                # "prevPrice24h": "20393.48",
                # "price24hPcnt": "0.0068",
                # "highPrice24h": "21128.12",
                # "lowPrice24h": "20318.89",
                # "turnover24h": "243765620.65899866",
                # "usdIndexPrice": "20784.12009279"
                prices[asset["symbol"]] = {
                    "bid1": _s2dec(asset["bid1Price"]), "bid1_size": _s2dec(asset["bid1Size"]),
                    "ask1": _s2dec(asset["ask1Price"]), "ask1_size": _s2dec(asset["ask1Size"]),
                    "last_price": _s2dec(asset["lastPrice"]), "volume_24h": _s2dec(asset["volume24h"])
                }

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return prices

    #todo
    async def get_order_book(self, asset: str):
        # https://bybit-exchange.github.io/docs/v5/market/orderbook
        # https://bybit-exchange.github.io/docs/api-explorer/v5/market/orderbook

        raise NotImplementedError(f"{LOG_PREFIX}not implemented")

    #todo
    async def get_long_short_ratio(self, asset: str):
        # https://bybit-exchange.github.io/docs/v5/market/long-short-ratio
        # https://bybit-exchange.github.io/docs/api-explorer/v5/market/long-short-ratio

        raise NotImplementedError(f"{LOG_PREFIX}not implemented")

    '''
    Open orders up limit:
        Perps & Futures:
            a) Each account can hold a maximum of 500 active orders simultaneously per symbol.
            b) conditional orders: each account can hold a maximum of 10 active orders simultaneously per symbol.
        Spot: 500 orders in total, including a maximum of 30 open TP/SL orders, a maximum of 30 open conditional orders for each symbol per account
        Option: a maximum of 50 open orders per account
        
    Rate limit:
        Please refer to rate limit table: https://bybit-exchange.github.io/docs/v5/rate-limit#trade.
        
    Risk control limit notice:
        Bybit will monitor on your API requests. When the total number of orders of a single user (aggregated the number of orders across main account and sub-accounts)
        within a day (UTC 0 - UTC 24) exceeds a certain upper limit, the platform will reserve the right to remind, warn, and impose necessary restrictions.
        Customers who use API default to acceptance of these terms and have the obligation to cooperate with adjustments.
    '''

    # value - in final asset, sign indicates the side (positive = buy, negative = sell)
    # slippage_pct - slippage in percents, [0.05, 1], up to 2 decimals
    # link_id - user customised order ID, a max of 36 characters (numbers, letters upper and lower cases, dashes, and underscores); is linked to the order ID in the system
    def _set_order_main_params(self, params: dict, asset_type: str, market: bool, asset: str, value: Decimal,
                               price: Decimal | None = None, slippage_pct: Decimal | None = None, link_id: str | None = None) -> dict:
        params["category"] = asset_type
        if market:
            params["orderType"] = "Market"
            if slippage_pct:
                params["slippageToleranceType"] = "Percent"         # | TickSize: highest buy = ask1 + slippageTolerance x tickSize, lowest sell = bid1 - slippageTolerance x tickSize
                                                                    # slippageTolerance in range [5, 2000], integer only
                params["slippageTolerance"] = str(slippage_pct)
        else:
            params["orderType"] = "Limit"
            # params["timeInForce"] = "PostOnly"  # maker order (cancel if can be executed immedialely)
            # IOC = Immediate-Or-Cancel (default for market order), GTC = GoodTillCancel (default for all the rest market & limit orders)
            # other options: FOK = Fill-Or-Kill; PostOnly = test; RPI = Retail-Price-Improvement (PostOnly, non-API matching, low priority)
            if price:
                params["price"] = str(price)
        params["symbol"] = asset
        params["side"] = "Buy" if value > 0 else "Sell"
        params["qty"] = str(abs(value))
        params["marketUnit"] = "baseCoin"      # quoteCoin = qty in base_asset (by value) | baseCoin = qty in asset; Perps, Futures & Option: always order by qty
        if link_id:
            params["orderLinkId"] = link_id
        return params

    # tp/sl - trigger price, order executed immediately if tp_limit/sl_limit is(are) not set
    # tp_limit/sl_limit - price for limit order to be placed when tp/sl is triggered
    def _set_order_tp_params(self, params: {}, spot: bool, tp: Decimal, sl: Decimal, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None) -> dict:
        params["takeProfit"] = str(tp)              # take profit trigger price
        if tp_limit:
            params["tpOrderType"] = "Limit"         # limit order will be created when take profit is triggered
            params["tpLimitPrice"] = str(tp_limit)  # limit order price
        else:
            params["tpOrderType"] = "Market"        # market order on the trigger price

        params["stopLoss"] = str(sl)                # stop loss trigger price
        if sl_limit:
            params["slOrderType"] = "Limit"         # limit order will be created when stop loss is triggered
            params["slLimitPrice"] = str(sl_limit)  # limit order price
        else:
            params["slOrderType"] = "Market"    # market order on the trigger price

        if not spot:
            if tp_limit or sl_limit:
                params["tpslMode"] = "Partial"  # partial position tp/sl (with the qty size)
            else:
                params["tpslMode"] = "Full"  # entire position for TP/SL

        return params

    async def _send_order(self, params: dict, order_id: str | None = None, order_link_id: str | None = None) -> str:
        # https://bybit-exchange.github.io/docs/v5/order/create-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/create-order
        # https://bybit-exchange.github.io/docs/v5/order/amend-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/amend-order

        amend = False
        if order_id:
            params["orderId"] = order_id
            amend = True
        if order_link_id:
            params["orderLinkId"] = order_link_id
            amend = True
        data = await self._send_request("/v5/order/amend" if amend else "/v5/order/create", params, True)
        # print(data)

        result = data.get("result", {})
        order_id = result["orderId"]
        # order_link_id = result["orderLinkId"]
        # 'retExtInfo': {}
        # 'time': 1739794348815

        return order_id

    # value - in final asset
    # slippage_pct - slippage in percents, [0.05, 1], up to 2 decimals
    # can throw exception
    async def place_spot_order(self, market: bool, asset: str, value: Decimal, price: Decimal | None = None, slippage_pct: Decimal | None = None,
                               tp: Decimal | None = None, sl: Decimal | None = None, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None) -> str:
        params = {
            "isLeverage": 0  # whether to borrow: 0(default) = false, spot trading; 1 = true, margin trading
            # make sure margin trading is turned on, and the relevant currency is set as collateral
            # "orderFilter": "Order"  # default
        }
        if tp or sl:
            #todo:
            # if sl_limit and ((side_buy and sl_limit < sl) or (not side_buy and sl_limit > sl)):
            #     raise ValueError(f"Spot order error: SL Limit {sl_limit} is worse than SL {sl} for the Future {params['side']}. SL Limit may never be executed")
            params = self._set_order_tp_params(params, True, tp, sl, tp_limit, sl_limit)
        params = self._set_order_main_params(params, "spot", market, asset, value, price, slippage_pct)
        return await self._send_order(params)

    # value - in final asset
    # can throw exception
    async def replace_spot_order(self, asset: str, value: Decimal | None = None, price: Decimal | None = None,
                                 tp: Decimal | None = None, sl: Decimal | None = None, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None,
                                 order_id: str | None = None, order_link_id: str | None = None) -> str:
        params = {"category": "spot", "symbol": asset}
        if price:
            params["price"] = str(price)
        if value:
            params["qty"] = str(value)
        if tp or sl:
            #todo:
            # if sl_limit and ((side_buy and sl_limit < sl) or (not side_buy and sl_limit > sl)):
            #     raise ValueError(f"Spot order error: SL Limit {sl_limit} is worse than SL {sl} for the Future {params['side']}. SL Limit may never be executed")
            params = self._set_order_tp_params(params, True, tp, sl, tp_limit, sl_limit)
        return await self._send_order(params, order_id, order_link_id)

    # value - in final asset
    # always sell side because leveraging is not used
    # slippage setting for take profit, stoploss, conditional orders is not supported
    # can throw exception
    async def place_spot_tpsl(self, asset: str, value: Decimal, trigger_price: Decimal, limit_price: Decimal | None = None,
                              slippage_pct: Decimal | None = None, link_id: str | None = None) -> str:
        params = {
            "isLeverage": 0,    # whether to borrow: 0(default) = false, spot trading; 1 = true, margin trading
                                # make sure margin trading is turned on, and the relevant currency is set as collateral
            "triggerPrice": str(trigger_price),     # TP/SL and Conditional order trigger price. If set, the order will be automatically converted into a conditional order.
                                                    # The conditional order does not occupy the margin.
                                                    # If the margin is insufficient after the conditional order is triggered, the order will be cancelled.
            "orderFilter": "StopOrder" if limit_price else "tpslOrder"
            # tpslOrder = Spot TP/SL order, the assets are occupied even before the order is triggered
            # StopOrder = Spot conditional order, the assets will not be occupied until the price of the underlying asset reaches the trigger price,
            #             and the required assets will be occupied after the Conditional order is triggered
        }
        params = self._set_order_main_params(params, "spot", not limit_price, asset, value, limit_price, slippage_pct, link_id)
        return await self._send_order(params)

    # value - in final asset
    # link_id - user customised order ID, a max of 36 characters (numbers, letters upper and lower cases, dashes, and underscores); is linked to the order ID in the system
    # always sell side because leveraging is not used
    # slippage setting for take profit, stoploss, conditional orders is not supported
    # can throw exception
    async def replace_spot_tpsl(self, asset: str, value: Decimal | None = None, trigger_price: Decimal | None = None, limit_price: float | None = None,
                                order_id: str | None = None, order_link_id: str | None = None) -> str:
        params = {"category": "spot", "symbol": asset}
        if value:
            params["qty"] = str(value)
        if trigger_price:
            params["triggerPrice"] = str(trigger_price)  # TP/SL and Conditional order trigger price. If set, the order will be automatically converted into a conditional order.
                                                         # The conditional order does not occupy the margin.
                                                         # If the margin is insufficient after the conditional order is triggered, the order will be cancelled.
        return await self._send_order(params, order_id, order_link_id)

    # value - in final asset
    # slippage_pct - slippage in percents, [0.05, 1], up to 2 decimals
    # link_id - user customised order ID, a max of 36 characters (numbers, letters upper and lower cases, dashes, and underscores); is linked to the order ID in the system
    # can throw exception
    async def place_future_order(self, market: bool, asset: str, value: Decimal, price: Decimal | None = None, slippage_pct: Decimal | None = None,
                                 link_id: str | None = None, close: bool = False, linear_future: bool = True,
                                 tp: Decimal | None = None, sl: Decimal | None = None, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None) -> str:
        params = self._set_order_main_params({}, "linear" if linear_future else "inverse", market, asset, value, price, slippage_pct, link_id)
        if close:
            params["reduceOnly"] = "true"       # take profit/stop loss cannot be set when position is being closing
            params["closeOnTrigger"] = "true"   # For a closing order. It can only reduce position, not increase it.
                                                # If the account has insufficient available balance when the closing order is triggered, then other active orders of similar contracts will be cancelled or reduced.
                                                # It can be used to ensure stop loss reduces position regardless of current available margin.
                                                # https://www.bybit.com/en/help-center/article/Close-On-Trigger-Order
        else:
            params["reduceOnly"] = "false"
            if tp or sl:
                #todo:
                # if sl_limit and ((side_buy and sl_limit < sl) or (not side_buy and sl_limit > sl)):
                #     raise ValueError(f"Spot order error: SL Limit {sl_limit} is worse than SL {sl} for the Future {params['side']}. SL Limit may never be executed")
                params = self._set_order_tp_params(params, False, tp, sl, tp_limit, sl_limit)
            if tp:
                params["tpTriggerBy"] = "LastPrice"   # The price type to trigger take profit. LastPrice (default) | MarkPrice | IndexPrice
            if sl:
                params["slTriggerBy"] = "LastPrice"   # The price type to trigger stop loss. LastPrice (default) | MarkPrice | IndexPrice

        #todo: for Conditional (for Stop Orders, Take Profit (TP), Stop Loss (SL)), and Trailing Stop orders:
        # params["triggerPrice"] = 0      # Conditional order trigger price. If set, the order will be automatically converted into a conditional order.
        #                                 # The conditional order does not occupy the margin. If the margin is insufficient after the conditional order is triggered, the order will be cancelled.
        #                                 # If the price is expected to rise to trigger conditional order: triggerPrice > market price. Else: triggerPrice < market price
        # params["triggerBy"] = 0         # Trigger price type, Conditional order param for Perps & Futures.
        #                                 #     LastPrice | IndexPrice | MarkPrice
        # params["triggerDirection"] = 0  # Conditional order param. Used to identify the expected direction of the conditional order.
        #                                 #   1 = triggered when market price rises to triggerPrice
        #                                 #   2 = triggered when market price falls to triggerPrice

        #todo: hedging
        # params["positionIdx"] = 0     # Used to identify positions in different position modes. Required under hedge-mode.
                                        # 0 = one-way mode | 1 = hedge-mode Buy | 2 = hedge-mode Sell

        return await self._send_order(params)

    # value - in final asset
    # link_id - user customised order ID, a max of 36 characters (numbers, letters upper and lower cases, dashes, and underscores); is linked to the order ID in the system
    # can throw exception
    async def replace_future_order(self, asset: str, value: Decimal, price: Decimal | None = None, linear_future: bool = True,
                                   tp: Decimal | None = None, sl: Decimal | None = None, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None,
                                   order_id: str | None = None, order_link_id: str | None = None) -> str:
        params = {"category": "linear" if linear_future else "inverse", "symbol": asset}
        if value:
            params["qty"] = str(value)
        if price:
            params["price"] = str(price)
        if tp or sl:
            #todo:
            # if sl_limit and ((side_buy and sl_limit < sl) or (not side_buy and sl_limit > sl)):
            #     raise ValueError(f"Spot order error: SL Limit {sl_limit} is worse than SL {sl} for the Future {params['side']}. SL Limit may never be executed")
            params = self._set_order_tp_params(params, False, tp, sl, tp_limit, sl_limit)
        if tp:
            params["tpTriggerBy"] = "LastPrice"  # The price type to trigger take profit. LastPrice (default) | MarkPrice | IndexPrice
        if sl:
            params["slTriggerBy"] = "LastPrice"  # The price type to trigger stop loss. LastPrice (default) | MarkPrice | IndexPrice

        #todo: for Conditional (for Stop Orders, Take Profit (TP), Stop Loss (SL)), and Trailing Stop orders:
        # if trigger_price:
        #     params["triggerPrice"] = str(trigger_price)  # TP/SL and Conditional order trigger price. If set, the order will be automatically converted into a conditional order.
        #                                                  # The conditional order does not occupy the margin.
        #                                                  # If the margin is insufficient after the conditional order is triggered, the order will be cancelled.
        # if trigger_by:
        #     params["triggerBy"] = str(trigger_by)        # Conditional order param. Used to identify the expected direction of the conditional order.
        #                                                  #   1 = triggered when market price rises to triggerPrice
        #                                                  #   2 = triggered when market price falls to triggerPrice

        return await self._send_order(params, order_id, order_link_id)

    # for futures (linear, reverse)
    # can throw exception
    async def reset_future_tpsl(self, asset: str, linear_future: bool = True,
                                tp: Decimal | None = None, sl: Decimal | None = None, tp_limit: Decimal | None = None, sl_limit: Decimal | None = None,
                                tp_qty: Decimal | None = None, sl_qty: Decimal | None = None,
                                trailing_stop_trigger_price: float | None = None, trailing_stop: Decimal | None = None,
                                order_id: str | None = None, order_link_id: str | None = None) -> None:
        # https://bybit-exchange.github.io/docs/v5/position/trading-stop
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/trading-stop

        params = {"category": "linear" if linear_future else "inverse", "symbol": asset}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id

        if tp or sl:
            #todo:
            # if sl_limit and ((side_buy and sl_limit < sl) or (not side_buy and sl_limit > sl)):
            #     raise ValueError(f"Spot order error: SL Limit {sl_limit} is worse than SL {sl} for the Future {params['side']}. SL Limit may never be executed")
            params = self._set_order_tp_params(params, False, tp, sl, tp_limit, sl_limit)
        if tp:
            params["tpTriggerBy"] = "LastPrice"  # The price type to trigger take profit. LastPrice (default) | MarkPrice | IndexPrice
        if sl:
            params["slTriggerBy"] = "LastPrice"  # The price type to trigger stop loss. LastPrice (default) | MarkPrice | IndexPrice

        if trailing_stop and trailing_stop_trigger_price:
            params["activePrice"] = str(trailing_stop_trigger_price)
            params["trailingStop"] = str(trailing_stop)

        #todo: hedging
        # params["positionIdx"] = 0     # Used to identify positions in different position modes. Required under hedge-mode.
                                        # 0 = one-way mode | 1 = hedge-mode Buy | 2 = hedge-mode Sell

        data = await self._send_request("/v5/position/trading-stop", params, True)

    # can throw exception
    async def reset_futures_leverage(self, asset: str, buy_leverage: int, sell_leverage: int, linear_future: bool = True) -> None:
        # https://bybit-exchange.github.io/docs/v5/position/leverage
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/leverage

        params = {"category": "linear" if linear_future else "inverse", "symbol": asset,
                  "buyLeverage": str(buy_leverage), "sellLeverage": str(sell_leverage)}

        data = await self._send_request("/v5/position/trading-stop", params, True)
        # print(data) #dbg

    #todo:
    # https://bybit-exchange.github.io/docs/v5/position/cross-isolate
    # https://bybit-exchange.github.io/docs/api-explorer/v5/position/cross-isolate
    # https://bybit-exchange.github.io/docs/v5/position/position-mode
    # https://bybit-exchange.github.io/docs/api-explorer/v5/position/position-mode
    #todo:
    # https://bybit-exchange.github.io/docs/v5/position/auto-add-margin
    # https://bybit-exchange.github.io/docs/api-explorer/v5/position/auto-add-margin
    # https://bybit-exchange.github.io/docs/v5/position/manual-add-margin
    # https://bybit-exchange.github.io/docs/api-explorer/v5/position/manual-add-margin

    # can throw exception
    async def place_option_order(self, market: bool, asset: str, value: Decimal, price: Decimal, slippage_pct: Decimal | None = None,
                           link_id: str | None = None, close: bool = False) -> str:
        params = self._set_order_main_params({}, "option", market, asset, value, price, slippage_pct, link_id)
        if close:
            params["reduceOnly"] = "true"       # take profit/stop loss cannot be set when position is being closing
            # params["closeOnTrigger"] = false  # For a closing order. It can only reduce position, not increase it.
                                                # If the account has insufficient available balance when the closing order is triggered, then other active orders of similar contracts will be cancelled or reduced.
                                                # It can be used to ensure stop loss reduces position regardless of current available margin.
                                                # https://www.bybit.com/en/help-center/article/Close-On-Trigger-Order
        else:
            params["reduceOnly"] = "false"

        #todo
        # params["orderIv"] = 0                 # Implied volatility. option only. Pass the real value, e.g for 10%, 0.1 should be passed. orderIv has a higher priority when price is passed as well
        # params["smpType"] = ""                # Self Match Prevention. https://bybit-exchange.github.io/docs/v5/smp
        # params["mmp"] = 0                     # Market maker protection. true = set the order as a market maker protection order. https://bybit-exchange.github.io/docs/v5/account/set-mmp

        return await self._send_order(params)

    #todo
    # can throw exception
    async def replace_option_order(self, asset: str, amount: Decimal, price: Decimal, order_id: str | None = None, order_link_id: str | None = None) -> str:
        raise NotImplementedError(f"{LOG_PREFIX}not implemented")

    # if both order_id and order_link_id are entered in the parameter input, Bybit will prioritize the orderId to process the corresponding order
    # can throw exception
    async def cancel_order(self, asset_class: MarketType, asset: str, order_id: str | None = None, order_link_id: str | None = None) -> bool:
        # https://bybit-exchange.github.io/docs/v5/order/cancel-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/cancel-order

        cat = _market_type2str(asset_class)
        params = {"category": cat, "symbol": asset}
        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id

        data = await self._send_request("/v5/order/cancel", params, True)
        result = data.get("result", {})
        if result["orderId"] == order_id or result["orderLinkId"] == order_link_id:
            return True
        # 'retExtInfo': {}
        # 'time': 1739794348815
        return False

    #todo:
    # https://bybit-exchange.github.io/docs/v5/order/batch-place
    # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/batch-place

    #todo
    # https://bybit-exchange.github.io/docs/v5/order/batch-amend
    # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/batch-amend

    #todo
    # https://bybit-exchange.github.io/docs/v5/order/batch-cancel
    # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/batch-cancel

    #todo
    # https://bybit-exchange.github.io/docs/v5/order/cancel-all
    # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/cancel-all

    #todo
    # fund/unfund from/to unified account
    # can throw exception
    def do_funding(self, fund: bool, asset: str, amount: float):
        raise NotImplementedError(f"{LOG_PREFIX}not implemented")

    # can throw exception
    async def fetch_order_result(self, market: MarketType, ticker: str, order_id: str, order_link_id: str = None, trials: int = 10) -> Tx:
        # https://bybit-exchange.github.io/docs/v5/order/open-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/open-order

        endpoint = "/v5/order/realtime"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": ticker, "orderId": order_id}
        if order_link_id:
            params["orderLinkId"] = order_link_id

        for _ in range(trials):
            data = await self._send_request(endpoint, params)
            '''
            cancelType, ,
            blockTradeId, isLeverage, positionIdx,
            timeInForce, orderType, placeType,
            orderIv,
            triggerPrice, takeProfit, stopLoss, tpTriggerBy, slTriggerBy, triggerDirection, triggerBy, tpslMode, tpLimitPrice, slLimitPrice,
            reduceOnly, closeOnTrigger,
            smpType, smpGroup, smpOrderId,
            '''
            lst = data["result"]["list"]
            if lst:
                it = lst[0]

                status = it["orderStatus"]
                reason = ""
                match status:
                    case "Cancelled":  # not supported for spot; for derivatives, orders with this status may have an executed qty
                        status = TxStatus.CANCELLED
                        reason = it["cancelType"]
                    case "Rejected":
                        status = TxStatus.REJECTED
                        reason = it["rejectReason"]
                    case "Filled":
                        status = TxStatus.FILLED
                    case "PartiallyFilled" | "PartiallyFilledCanceled":  # PFC supported only for spot
                        status = TxStatus.PARTIALLY_FILLED
                    case _:  # New | Untriggered | Triggered | Deactivated - non-executions
                        continue

                # if status in ("Filled", "PartiallyFilled", "PartiallyFilledCanceled"):  # PFC - Only spot has this order status
                size = _s2dec(it["cumExecQty"])  # qty, leavesQty, marketUnit(spot)=baseCoin|quoteCoin
                side = 1 if it["side"] == "Buy" else -1  # todo: rm?
                op_side = OpSide.BUY if side > 0 else OpSide.SELL
                value = _s2dec(it["cumExecValue"])  # leavesValue
                price = _s2dec(it["avgPrice"])  # price, lastPriceOnCreated
                fee = _s2dec(it["cumExecFee"])
                op_type = OpType.NON_AUTO
                match it["stopOrderType"]:
                    case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                        op_type = OpType.TAKE_PROFIT
                    case "StopLoss" | "PartialStopLoss":
                        op_type = OpType.STOP_LOSS
                    case "Stop":  # triggered a market order
                        op_type = OpType.STOP_LIMIT
                    case "tpslOrder" | "BidirectionalTpslOrder":
                        op_type = OpType.STOP_LIMIT  # todo: determine tp|sl  # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)
                exec_ts_ms = int(it["updatedTime"])  # createdTime

                return Tx(order_id, _str2market_type(cat), ticker, op_side, op_type, side * size, side * value, price, fee, exec_ts_ms, status, reason)

            # await asyncio.sleep(1.0)

        raise TimeoutError("Order status polling timed out")

    # returns last record timestamp
    # can throw exception
    async def fetch_orders_result(self, market: MarketType, ticker: str, last_ts: int, out_queue: asyncio.Queue) -> int:
        # https://bybit-exchange.github.io/docs/v5/order/open-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/open-order

        endpoint = "/v5/order/realtime"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": ticker}
        if market not in [MarketType.SPOT, MarketType.FUTUREINV]:
            params["openOnly"] = "1"

        data = await self._send_request(endpoint, params)
        lst = data["result"]["list"]
        if not lst:
            return last_ts

        max_ts = last_ts
        for it in lst:
            exec_ts_ms = int(it["updatedTime"])  # createdTime
            if exec_ts_ms <= last_ts:
                continue
            if exec_ts_ms > max_ts:
                max_ts = exec_ts_ms

            order_id = it["orderId"]
            status = it["orderStatus"]
            reason = ""
            match status:
                case "Cancelled":  # not supported for spot; for derivatives, orders with this status may have an executed qty
                    status = TxStatus.CANCELLED
                    reason = it["cancelType"]
                case "Rejected":
                    status = TxStatus.REJECTED
                    reason = it["rejectReason"]
                case "Filled":
                    status = TxStatus.FILLED
                case "PartiallyFilled" | "PartiallyFilledCanceled":  # PFC supported only for spot
                    status = TxStatus.PARTIALLY_FILLED
                case _:  # New | Untriggered | Triggered | Deactivated - non-executions
                    continue

            op_type = OpType.NON_AUTO
            match it["stopOrderType"]:
                case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                    op_type = OpType.TAKE_PROFIT
                case "StopLoss" | "PartialStopLoss":
                    op_type = OpType.STOP_LOSS
                case "Stop":  # triggered a market order
                    op_type = OpType.STOP_LIMIT
                case "tpslOrder" | "BidirectionalTpslOrder":
                    op_type = OpType.STOP_LIMIT  # todo: determine tp|sl  # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)

            side = 1 if it["side"] == "Buy" else -1
            op_side = OpSide.BUY if side > 0 else OpSide.SELL  #todo: redundant parameter with signed value
            value = side * _s2dec(it["cumExecQty"])  # qty, leavesQty, marketUnit(spot)=baseCoin|quoteCoin
            value_base = side * _s2dec(it["cumExecValue"])  # leavesValue
            price = _s2dec(it["avgPrice"])  # price, lastPriceOnCreated
            fee = _s2dec(it["cumExecFee"])

            # orderLinkId, blockTradeId, isLeverage, positionIdx,
            # timeInForce, orderType, placeType,
            # orderIv,
            # triggerPrice, takeProfit, stopLoss, tpTriggerBy, slTriggerBy, triggerDirection, triggerBy, tpslMode, tpLimitPrice, slLimitPrice,
            # reduceOnly, closeOnTrigger,
            # smpType, smpGroup, smpOrderId,

            tx = Tx(order_id, _str2market_type(cat), ticker, op_side, op_type, value, value_base, price, fee, exec_ts_ms, status, reason)
            out_queue.put_nowait(tx)

        return max_ts

    # can throw exception
    async def fetch_orders_history(self, market: MarketType, ticker: str, out_queue: asyncio.Queue):
        # https://bybit-exchange.github.io/docs/v5/order/order-list
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/order-list

        endpoint = "/v5/order/history"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": ticker}
        cursor = None

        while True:
            data = await self._send_request(endpoint, params)
            result = data["result"]
            lst = result["list"]
            cursor = result["nextPageCursor"]
            if lst:
                for it in lst:
                    order_id = it["orderId"]
                    size = _s2dec(it["execQty"])  # leavesQty, orderQty
                    side = 1 if it["side"] == "Buy" else -1  # todo: rm?
                    op_side = OpSide.BUY if side > 0 else OpSide.SELL
                    value = _s2dec(it["execValue"])
                    price = _s2dec(it["execPrice"])  # markPrice, orderPrice, indexPrice
                    fee = _s2dec(it["execFee"])  # feeRate, feeCurrency
                    op_type = OpType.NON_AUTO
                    match it["stopOrderType"]:
                        case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                            op_type = OpType.TAKE_PROFIT
                        case "StopLoss" | "PartialStopLoss":
                            op_type = OpType.STOP_LOSS
                        case "Stop":  # triggered a market order
                            op_type = OpType.STOP_LIMIT
                        case "tpslOrder" | "BidirectionalTpslOrder":
                            op_type = OpType.STOP_LIMIT  # todo: determine tp|sl  # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)
                    exec_ts_ms = int(it["execTime"])
                    # orderType, execType, orderLinkId, execId, blockTradeId, seq, underlyingPrice, tradeIv, markIv, isMaker, closedSize

                    tx = Tx(order_id, _str2market_type(cat), ticker, op_side, op_type, side * size, side * value, price, fee, exec_ts_ms, TxStatus.FILLED, "")
                    out_queue.put_nowait(tx)
            if not cursor:
                break
            params["cursor"] = cursor

    # can throw exception
    async def fetch_orders_executions(self, market: MarketType, ticker: str, out_queue: asyncio.Queue):
        # https://bybit-exchange.github.io/docs/v5/order/execution
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/execution

        endpoint = "/v5/execution/list"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": ticker}
        cursor = None

        while True:
            data = await self._send_request(endpoint, params)
            result = data["result"]
            lst = result["list"]
            cursor = result["nextPageCursor"]
            if lst:
                for it in lst:
                    order_id = it["orderId"]
                    size = _s2dec(it["execQty"])  # leavesQty, orderQty
                    side = 1 if it["side"] == "Buy" else -1  # todo: rm?
                    op_side = OpSide.BUY if side > 0 else OpSide.SELL
                    value = _s2dec(it["execValue"])
                    price = _s2dec(it["execPrice"])  # markPrice, orderPrice, indexPrice
                    fee = _s2dec(it["execFee"])  # feeRate, feeCurrency
                    op_type = OpType.NON_AUTO
                    match it["stopOrderType"]:
                        case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                            op_type = OpType.TAKE_PROFIT
                        case "StopLoss" | "PartialStopLoss":
                            op_type = OpType.STOP_LOSS
                        case "Stop":  # triggered a market order
                            op_type = OpType.STOP_LIMIT
                        case "tpslOrder" | "BidirectionalTpslOrder":
                            op_type = OpType.STOP_LIMIT  # todo: determine tp|sl  # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)
                    exec_ts_ms = int(it["execTime"])
                    # orderType, execType, orderLinkId, execId, blockTradeId, seq, underlyingPrice, tradeIv, markIv, isMaker, closedSize

                    tx = Tx(order_id, _str2market_type(cat), ticker, op_side, op_type, side * size, side * value, price, fee, exec_ts_ms, TxStatus.FILLED, "")
                    out_queue.put_nowait(tx)
            if not cursor:
                break
            params["cursor"] = cursor

    # returns id, p&l and executions count for last filled order
    # can throw exception
    async def get_last_closed_pnl(self, market: MarketType, ticker: str) -> tuple[str, Decimal, int] | None:
        # https://bybit-exchange.github.io/docs/v5/position/close-pnl
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/close-pnl
        endpoint = "/v5/position/closed-pnl"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": ticker, "limit": 1}

        data = await self._send_request(endpoint, params)
        lst = data["result"]["list"]
        if not lst:
            return None

        it = lst[0]
        order_id = it["orderId"]
        pnl = Decimal(it["closedPnl"])
        execs = int(it["fillCount"])
        # symbol, orderType, leverage, updatedTime, side, execType,
        # qty, avgEntryPrice, cumEntryValue, createdTime, orderPrice, closedSize, avgExitPrice, cumExitValue

        return order_id, pnl, execs
