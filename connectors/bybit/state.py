'''
ByBit API wrapper for initial agent state setuip: account items & tx history, market history.

IMPORTANT NOTICE: Supported modern UTA 2.0 account type (partial support for Classic and UTA 1.0).
'''

import hmac
import hashlib
import urllib.parse
from decimal import Decimal
import aiohttp
from datetime import datetime, UTC
import numpy as np

from connectors.enums import Provider, MarketType
from connectors.objects import Asset, AssetPosition, FundingPosition, Position
from connectors.helpers import _s2dec

from connectors.bybit.common import _market_type2str, LOG_PREFIX, ConnMode, BaseUrls


class TradingState:

    def __init__(self, api_key: str, api_secret: str, mode: ConnMode, rcv_wnd: int = 5000):
        self.api_key = api_key
        self.api_secret = api_secret
        self.conn_mode = mode
        self.base_url = BaseUrls[mode]
        self.rcv_wnd = str(rcv_wnd)

    # generates HMAC SHA256 signature
    def _generate_signature(self, timestamp: str, params: dict) -> str:
        request_str = timestamp + self.api_key + self.rcv_wnd + urllib.parse.urlencode(params, quote_via=urllib.parse.quote_plus)
        hmac_hash = hmac.new(bytes(self.api_secret, "utf-8"), request_str.encode("utf-8"), hashlib.sha256)
        return hmac_hash.hexdigest()

    # sends a GET request to ByBit API with authentication
    async def _send_request(self, endpoint: str, params: dict) -> dict:
        # UTC timestamp in milliseconds
        # should adhere to the following rule: server_time - recv_window <= timestamp < server_time + 1000
        # server_time stands for Bybit server time, which can be queried via the Server Time endpoint https://bybit-exchange.github.io/docs/v5/market/time
        # timestamp = str(int(time.time() * 1000))
        timestamp = str(int(datetime.now(tz=UTC).timestamp() * 1000))
        # params.update({})
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.rcv_wnd,
            "X-BAPI-SIGN": self._generate_signature(timestamp, params),
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, data={}) as response:
                if response.status != 200:
                    raise Exception(f"{LOG_PREFIX}{response.reason}")
                json_data = await response.json()
                if json_data["retCode"] != 0:
                    raise Exception(f"{LOG_PREFIX}{json_data['retMsg']}")
                return json_data

    async def get_asset_info(self, market: MarketType, asset: str) -> Asset | None:
        # https://bybit-exchange.github.io/docs/v5/market/instrument
        # https://bybit-exchange.github.io/docs/api-explorer/v5/market/instrument

        endpoint = "/v5/market/instruments-info"
        cat = _market_type2str(market)
        params = {"category": cat, "symbol": asset}

        data = await self._send_request(endpoint, params)
        data = data.get("result", {})
        if data["category"] == cat:
            data = data.get("list", [])[0]
            if data is None:
                return None

            value_step: Decimal | None = None
            value_base_step: Decimal | None = None
            match cat:
                case "spot":
                    value_step = _s2dec(data["lotSizeFilter"]["basePrecision"])
                    value_base_step = _s2dec(data["lotSizeFilter"]["quotePrecision"])
                    # "innovation": "0", "marginTrading": "utaOnly", "stTag": "1",
                    # "lotSizeFilter": { "minOrderAmt": "1", "maxOrderAmt": "100000000" },
                    # "riskParameters": { "priceLimitRatioX": "0.1", "priceLimitRatioY": "0.1" }
                case "linear" | "inverse":
                    value_step = _s2dec(data["lotSizeFilter"]["qtyStep"])
                    # "launchTime": "1634256000000", "deliveryTime": "0", "deliveryFeeRate": "", "priceScale": "3",
                    # "leverageFilter": { "minLeverage": "1", "maxLeverage": "100.00", "leverageStep": "0.01" },
                    # "priceFilter": { "minPrice": "0.010", "maxPrice": "199999.980" },
                    # "lotSizeFilter": { "postOnlyMaxOrderQty": "79770.0", "maxMktOrderQty": "11740.0", "minNotionalValue": "5" },
                    # "unifiedMarginTrade": true, "fundingInterval": 60, "settleCoin": "USDT", "copyTrading": "both", "upperFundingRate": "0.005",
                    # "lowerFundingRate": "-0.005", "isPreListing": false, "preListingInfo": null,
                    # "riskParameters": { "priceLimitRatioX": "0.05", "priceLimitRatioY": "0.1" }, "displayName": ""
                case "option":
                    value_step = _s2dec(data["lotSizeFilter"]["qtyStep"])
                    # "symbol": "ETH-3JAN23-1250-P",
                    # "settleCoin": "USDC", "optionsType": "Put",
                    # "launchTime": "1672560000000", "deliveryTime": "1672732800000", "deliveryFeeRate": "0.00015",
                    # "priceFilter": { "minPrice": "0.1", "maxPrice": "10000000" }

            asset = Asset(Provider.BYBIT, market, asset,
                          data["baseCoin"],
                          data["quoteCoin"], data["status"] == "Trading", _s2dec(data["lotSizeFilter"]["minOrderQty"]), _s2dec(
                    data["lotSizeFilter"]["maxOrderQty"]), value_step, value_base_step, _s2dec(data["priceFilter"]["tickSize"]))

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return asset

    # params:
    #     timeframe_min ∈ [1,3,5,15,30,60,120,240,360,720,D,W,M]
    #     history_depth ∈ [1, 1000]
    #
    # returns:
    #     list of tuples: (
    #         timeframe period start timestamp (ms),
    #         numpy.array (open price, high price, low price, close price,
    #             volume,   # USDT or USDC contract: unit is base coin (e.g., BTC); Inverse contract: unit is quote coin (e.g., USD)
    #             turnover  # USDT or USDC contract: unit is quote coin (e.g., USDT); Inverse contract: unit is base coin (e.g., BTC)
    #         )
    #     )
    async def get_price_history(self, asset_type: MarketType, asset: str, timeframe_min: int, history_depth: int):  # -> np.ndarray:
        # https://bybit-exchange.github.io/docs/v5/market/kline
        # https://bybit-exchange.github.io/docs/api-explorer/v5/market/kline

        assert timeframe_min in [1, 3, 5, 15, 30, 60, 120, 240, 360, 720, 1440, 10080]

        endpoint = "/v5/market/kline"
        cat = _market_type2str(asset_type)
        params = {"category": cat, "symbol": asset}
        if timeframe_min <= 720:
            params["interval"] = str(timeframe_min)
        elif timeframe_min == 1440:
            params["interval"] = "D"
        elif timeframe_min == 10080:
            params["interval"] = "W"
        # "M" - not supported

        limit = history_depth
        max_limit = 1000  # maximum allowed by the API
        while limit > 0:

            if limit > max_limit:
                now = int(datetime.now(tz=UTC).timestamp() * 1000)
                mul = timeframe_min * 60 * 1000
                start_ts_ms = now - limit * mul
                params["start"] = start_ts_ms
                params["end"] = start_ts_ms + 1000 * mul
            params["limit"] = min(limit, 1000)  # history_depth

            data = await self._send_request(endpoint, params)
            data = data.get("result", {})
            if data["category"] == cat and data["symbol"] == asset:
                for tohlcvt in data.get("list", []):
                    # yield np.array([float(x) if x else np.nan for x in tohlcvt], dtype=np.float32)  #todo: ?
                    yield np.array(tohlcvt, dtype=np.float32)
            # 'retExtInfo': {}
            # 'time': 1739794348815

            limit -= max_limit if limit > max_limit else limit

        yield None

    async def get_assets(self) -> list[AssetPosition]:
        """Fetch wallet balances for all assets."""
        # https://bybit-exchange.github.io/docs/v5/account/wallet-balance
        # https://bybit-exchange.github.io/docs/api-explorer/v5/account/wallet

        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}  # legacy types: SPOT, CONTRACT

        data = await self._send_request(endpoint, params)

        balances = []
        for account in data["result"]["list"]:
            if account["accountType"] == "UNIFIED":
                # accountType
                # totalEquity totalAvailableBalance totalWalletBalance
                # accountIMRate totalMarginBalance totalInitialMargin accountMMRate totalMaintenanceMargin
                # totalPerpUPL accountLTV
                for item in account.get("coin", []):
                    asset = AssetPosition(item["coin"], _s2dec(item["equity"]), _s2dec(item["locked"]))
                    # walletBalance availableToBorrow borrowAmount bonus accruedInterest availableToWithdraw unrealisedPnl cumRealisedPnl
                    # totalOrderIM spotHedgingQty collateralSwitch marginCollateral totalPositionMM totalPositionIM
                    balances.append(asset)
                break  # CONTRACT & SPOT account types are legacy

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return balances

    async def get_funds(self) -> list[FundingPosition]:
        """Fetch funded balances for all available assets."""
        # https://bybit-exchange.github.io/docs/v5/asset/balance/all-balance
        # https://bybit-exchange.github.io/docs/api-explorer/v5/asset/all-balance

        if self.conn_mode == ConnMode.DEMO:
            return []  # Demo trading are not supported.

        endpoint = "/v5/asset/transfer/query-account-coins-balance"
        params = {"accountType": "FUND"}  # other types: UNIFIED, OPTION, INVESTMENT; legacy types: SPOT, CONTRACT
        # memberId - for subaccount
        # coin - for specific coins

        data = await self._send_request(endpoint, params)

        balances = []
        account = data.get("result", {})
        # "memberId": "104285860",
        if account["accountType"] == "FUND":
            for item in account.get("balance", []):
                # "bonus": ""
                balance = _s2dec(item["walletBalance"])
                if balance != 0.:
                    fund = FundingPosition()
                    fund.ticker = item["coin"]
                    fund.balance = balance
                    fund.available_balance = _s2dec(item["transferBalance"])
                    balances.append(fund)

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return balances

    async def get_positions(self, market: MarketType, asset: str | None = None, base_asset: str | None = None) -> list[Position]:
        # https://bybit-exchange.github.io/docs/v5/position
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/position-info

        endpoint = "/v5/position/list"
        cat = _market_type2str(market)
        params = {"category": cat}
        if asset:
            params["symbol"] = asset
        elif base_asset:
            if market != MarketType.OPTION:
                params["settleCoin"] = base_asset
            else:
                params["baseCoin"] = base_asset
        else:
            raise ValueError("required one of asset and base_asset")
        params["limit"] = "200"  # 1-200. default 20
        # params["cursor"] = page_num  # todo: for pagination

        data = await self._send_request(endpoint, params)

        positions = []
        account = data["result"]
        if account["category"] == cat:
            for item in account.get("list", []):
                seq = item["seq"]
                if seq == -1:
                    break
                size = item["size"]
                if size == "0":
                    break
                side = item["side"]
                if side == "":
                    break
                side = 1 if side == "Buy" else -1
                value = item["positionValue"]
                if value == "":
                    break
                open_price = item["avgPrice"]
                if open_price == "0":
                    break
                # takeProfit stopLoss trailingStop(The distance from market price) delta gamma vega theta updatedTime isReduceOnly
                pos = Position(market, item["symbol"], side * _s2dec(size), side * _s2dec(value), _s2dec(open_price), int(item["leverage"]), _s2dec(item["curRealisedPnl"]), int(
                    item["createdTime"]))
                positions.append(pos)

        # next_page = account.get("nextPageCursor", {})

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return positions

    #todo
    async def get_options(self) -> list[Position]:
        raise NotImplementedError(f"{LOG_PREFIX}get_options")

    async def get_orders(self, asset_type: MarketType, asset: str | None = None, base_asset: str | None = None) -> {}:  #todo: return list[Order]
        # https://bybit-exchange.github.io/docs/v5/order/open-order
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/open-order

        endpoint = "/v5/order/realtime"
        cat = _market_type2str(asset_type)
        params = {"category": cat}
        if asset:
            params["symbol"] = asset
        elif base_asset:
            if asset_type == MarketType.OPTION:
                # params["baseCoin"] = base_asset
                if base_asset not in ("USDT", "USDC"):
                    raise ValueError(f"{LOG_PREFIX}base_asset for option can only be either USDT or USDC")
            params["settleCoin"] = base_asset
        else:
            if asset_type == MarketType.FUTURE:
                raise ValueError(f"{LOG_PREFIX}required one of asset and base_asset for futures")
        # params["orderId"] = order_id #str
        # params["orderLinkId"] = order_id #string	User customised order ID
        # params["openOnly"] = 0 # 1, 2  # 0 = only get active orders (default); 1 = UTA2.0, UTA1.0(except inverse); 2 =  UTA1.0(inverse), classic account
        # params["orderFilter"] = "Order" # StopOrder | tpslOrder.
        # Order = active order
        # StopOrder = conditional order for Futures and Spot
        # tpslOrder = spot TP/SL order
        # OcoOrder: Spot oco order
        # BidirectionalTpslOrder: Spot bidirectional TPSL order
        # - classic account spot: return Order active order by default
        # - Others: all kinds of orders by default
        params["limit"] = "50"  # 1-50. default 20
        # params["cursor"] = page_num  # todo: for pagination

        data = await self._send_request(endpoint, params)

        orders = {}
        account = data["result"]
        if account["category"] == cat:
            for item in account.get("list", []):
                orders[item["orderId"]] = {
                    "link_id": item["orderLinkId"], "asset": item["symbol"], "block_trade_id": item["blockTradeId"], "price": _s2dec(item["price"]), "amount": _s2dec(
                        item["qty"]), "side": item["side"], "trigger_price": _s2dec(item["triggerPrice"]), "trigger_direction": int(item["triggerDirection"]),
                    # trigger direction. 1: rise, 2: fall
                    "trigger_by": item["triggerBy"],  # the price type to trigger
                    "tp": _s2dec(item["takeProfit"]), "sl": _s2dec(item["stopLoss"]), "tp_limit": _s2dec(item["tpLimitPrice"]), "sl_limit": _s2dec(
                        item["slLimitPrice"]), "tp_trigger_by": item["tpTriggerBy"], "sl_trigger_by": item["slTriggerBy"],  # the price type to trigger
                    "exec_amount": _s2dec(item["cumExecQty"]), "exec_value": _s2dec(item["cumExecValue"]), "avg_price": _s2dec(item["avgPrice"]), "exec_fee": _s2dec(
                        item["cumExecFee"]), "left_amount": _s2dec(item["leavesQty"]), "left_value": _s2dec(item["leavesValue"]), "lifetime": item[
                        "timeInForce"], "leveraged": bool(item["isLeverage"]), "type": item["orderType"],  # Market,Limit. For TP/SL order, it means the order type after triggered
                    "position_index": int(item["positionIdx"]), "status": item["orderStatus"], "cancel_type": item["cancelType"], "reject_reason": item[
                        "rejectReason"], "stop_type": item["stopOrderType"], "base_asset": item["marketUnit"],  # the unit for qty (baseCoin | quoteCoin)
                    "created_ts_ms": int(item["createdTime"]), "updated_ts_ms": int(item["updatedTime"])
                }
                if cat != "spot":
                    orders[item["orderId"]]["tpsl_mode"] = item["tpslMode"]  # Full = entire position for TP/SL; Partial = partial position tp/sl. Option returns always ""
                    orders[item["orderId"]]["price_on_creation"] = _s2dec(item[
                                                                              "lastPriceOnCreated"])  # last price when place the order  # orders[item["orderId"]]["oco_trigger_by"] = item["ocoTriggerBy"]  # OcoTriggerByUnknown | OcoTriggerByTp | OcoTriggerByBySl - the trigger type of Spot OCO order
                else:
                    orders[item["orderId"]]["price_on_creation"] = _s2dec(item["basePrice"])  # Last price when place the order
                if account["category"] == "linear":
                    orders[item["orderId"]]["create_type"] = item["createType"]
                if account["category"] == "option":
                    orders[item["orderId"]]["place_type"] = item["placeType"]  # iv | price
                    orders[item["orderId"]]["implied_volatility"] = _s2dec(item[
                                                                               "orderIv"])  # todo: inverse  # orders[order["orderId"]]["reduce_only"] = bool(order["reduceOnly"])  # orders[order["orderId"]]["close_on_trigger"] = bool(order["closeOnTrigger"])  # orders[order["orderId"]]["smp_type"] = bool(order["smpType"])  # None (default) | CancelMaker | CancelTaker | CancelBoth  # orders[order["orderId"]]["smp_group_id"] = bool(order["smpGroup"])  # Smp group ID. If the UID has no group, it is 0 by default  # orders[order["orderId"]]["smp_order_id"] = bool(order["smpOrderId"])  # The counterparty's orderID which triggers this SMP execution

            # next_page = account.get("nextPageCursor", {})

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return orders

    async def get_tx_history(self, asset_type: MarketType, asset: str | None = None, base_asset: str | None = None,
                             order_id: int | None = None, start_ts_ms: int | None = None) -> {}:
        # https://bybit-exchange.github.io/docs/v5/order/execution
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/execution

        endpoint = "/v5/execution/list"
        cat = _market_type2str(asset_type)
        params = {"category": cat}
        if order_id:
            params["orderId"] = asset  # params["orderLinkId"] = str(asset)
        elif asset:
            params["symbol"] = asset
        elif base_asset:
            params["baseCoin"] = base_asset
        if start_ts_ms:
            params["startTime"] = str(start_ts_ms)
        params["endTime"] = str(int(datetime.now(UTC).timestamp() * 1000))
        # params["execType"] = Trade | AdlTrade | Funding | BustTrade | Settle
        params["limit"] = "100"  # 1-100, default 50
        # params["cursor"] = page_num  # todo: for pagination

        data = await self._send_request(endpoint, params)

        txs = {}
        account = data["result"]
        if account["category"] == cat:
            for item in account["list"]:
                #  "orderLinkId": "", User customized order ID
                #  "stopOrderType": "UNKNOWN", Stop order type. If the order is not stop order, it either returns UNKNOWN or ""
                #  "feeCurrency": "", Spot trading fee currency
                #  "isMaker": false, true => non executed immediately after creation
                #  "tradeIv": "", Implied volatility. Valid for option
                #  "blockTradeId": "", Paradigm block trade ID
                #  "closedSize": "", Closed position size
                #  "seq": 4688002127 Cross sequence, used to associate each fill and each position update
                #                    The seq will be the same when conclude multiple transactions at the same time
                #                    Different symbols may have the same seq, please use seq + symbol to check unique
                # "execType",  Trade, AdlTrade (Auto-Deleveraging), Funding (Funding fee), BustTrade (Takeover liquidation),
                #              Delivery (USDC futures delivery), Settle (Inverse futures settlement), BlockTrade, MovePosition, UNKNOWN
                txs[item["orderId"]] = {
                    "asset": item["symbol"], "side": item["side"],  # Buy,Sell
                    "type": item["orderType"],  # Market,Limit
                    "order_price": _s2dec(item["orderPrice"]), "mark_price": _s2dec(item["markPrice"]), "exec_price": _s2dec(item["execPrice"]), "qty": _s2dec(
                        item["orderQty"]), "exec_qty": _s2dec(item["execQty"]), "left_qty": _s2dec(item["leavesQty"]), "value": _s2dec(item["execValue"]), "fee_rate": _s2dec(
                        item["feeRate"]), "exec_fee": _s2dec(item["execFee"]),
                    # fee asset: feeRate > 0 | !IsMakerOrder => base/quote for Buy/Sell; feeRate <= 0 & IsMakerOrder => quote/base for Buy/Sell
                    "exec_ts_ms": int(item["execTime"]), "exec_id": item["execId"]
                }
                if asset_type == MarketType.OPTION:
                    txs[item["orderId"]]["index_price"] = _s2dec(item["indexPrice"])  # The index price of the symbol when executing
                    txs[item["orderId"]]["underlying_price"] = _s2dec(item["underlyingPrice"])  # The underlying price of the symbol when executing
                    txs[item["orderId"]]["trade_iv"] = _s2dec(item["tradeIv"])  # Implied volatility
                    txs[item["orderId"]]["mark_iv"] = _s2dec(item["markIv"])  # Implied volatility of mark price

        # next_page = account.get("nextPageCursor", {})

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return txs

    async def get_order_history(self, asset_type: MarketType, asset: str | None = None, base_asset: str | None = None,
                                order_id: int | None = None, status: str | None = None, start_ts_ms: int | None = None) -> {}:
        # https://bybit-exchange.github.io/docs/v5/order/order-list
        # https://bybit-exchange.github.io/docs/api-explorer/v5/trade/order-list

        endpoint = "/v5/order/history"
        cat = _market_type2str(asset_type)
        params = {"category": cat}
        if order_id:
            params["orderId"] = asset  # params["orderLinkId"] = str(asset)
        elif asset:
            params["symbol"] = asset
        elif base_asset:
            params["baseCoin"] = base_asset
        if start_ts_ms:
            params["startTime"] = str(start_ts_ms)
        params["endTime"] = str(int(datetime.now(UTC).timestamp() * 1000))
        if status:
            params["orderStatus"] = status
            # Created | New | Rejected | PartiallyFilled | PartillyFilledCancelled | Filled | PendingCancel | Cancelled | Untriggered | Triggered | Deactivated | Active
        # params["orderFilter"] = Order | StopOrder | tpslOrder
        params["limit"] = "50"  # 1-50, default 20
        # params["cursor"] = page_num  # todo: for pagination

        data = await self._send_request(endpoint, params)

        orders = {}
        account = data["result"]
        if account["category"] == cat:
            for item in account.get("list", []):
                # "orderLinkId": "YLxaWKMiHU",
                # "blockTradeId": "",
                # "isLeverage": "",
                # "positionIdx": 1,
                # "cancelType": "UNKNOWN",
                # "rejectReason": "EC_PostOnlyWillTakeLiquidity",
                # "timeInForce": "PostOnly",
                # "orderIv": "", # Implied volatility
                # "lastPriceOnCreated": "0.00",
                # "reduceOnly": false,
                # "closeOnTrigger": false,
                # "smpType": "None", # SMP execution type
                # "smpGroup": 0, # Smp group ID. If the UID has no group, it is 0 by default
                # "smpOrderId": "", # The counterparty's orderID which triggers this SMP execution
                # "placeType": "", # Place type, option used. iv, price
                # "updatedTime": "1684476068372"
                orders[item["orderId"]] = {
                    "asset": item["symbol"], "side": item["side"], "type": item["orderType"], "qty": _s2dec(item["qty"]), "price": _s2dec(item["price"]), "avg_price": _s2dec(
                        item["avgPrice"]), "trigger_price": _s2dec(item["triggerPrice"]), "tp": _s2dec(item["takeProfit"]), "trigger_by_tp": item[
                        "tpTriggerBy"], "tp_limit": _s2dec(item["tpLimitPrice"]), "sl": _s2dec(item["stopLoss"]), "trigger_by_sl": item["slTriggerBy"], "sl_limit": _s2dec(
                        item["slLimitPrice"]), "trigger_dir": int(item["triggerDirection"]), "trigger_by": item["triggerBy"], "stop_type": item[
                        "stopOrderType"], "exec_qty": _s2dec(item["cumExecQty"]), "left_qty": _s2dec(item["leavesQty"]), "value": _s2dec(
                        item["cumExecValue"]), "left_value": _s2dec(item["leavesValue"]), "status": item["orderStatus"], "exec_fee": _s2dec(
                        item["cumExecFee"]), "creation_ts_ms": int(item["createdTime"])
                }
                if asset_type != MarketType.SPOT:
                    orders[item["orderId"]]["tpsl_mode"] = item["tpslMode"]

        # next_page = account.get("nextPageCursor", {})

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return orders

    async def get_futures_pnl_history(self, asset_type: MarketType, asset: str | None = None, start_ts_ms: int | None = None) -> {}:
        # https://bybit-exchange.github.io/docs/v5/position/close-pnl
        # https://bybit-exchange.github.io/docs/api-explorer/v5/position/close-pnl
        #   https://bybit-exchange.github.io/docs/v5/position/move-position-history (deprecated?)

        endpoint = "/v5/position/closed-pnl"
        cat = _market_type2str(asset_type)
        params = {"category": cat}
        if asset_type in (MarketType.SPOT, MarketType.OPTION):
            raise ValueError(f"{LOG_PREFIX}Spot or Option can't be type of position")
        if asset:
            params["symbol"] = asset
        if start_ts_ms:
            params["startTime"] = str(start_ts_ms)
        params["endTime"] = str(int(datetime.now(UTC).timestamp() * 1000))
        params["limit"] = "200"  # 1-200, default 50
        # params["cursor"] = page_num  # todo: for pagination

        data = await self._send_request(endpoint, params)

        pnls = {}
        account = data["result"]
        if account["category"] == cat:
            for item in account["list"]:
                pnls[item["orderId"]] = {
                    "asset": item["symbol"], "side": item["side"], "type": item["orderType"], "qty": _s2dec(item["qty"]), "price": _s2dec(
                        item["orderPrice"]), "avg_entry_price": _s2dec(item["avgEntryPrice"]), "entry_value": _s2dec(item["cumEntryValue"]), "leverage": int(
                        item["leverage"]), "exec_type": item["execType"], "avg_exit_price": _s2dec(item["avgExitPrice"]), "exit_value": _s2dec(item["cumExitValue"]), "pnl": _s2dec(
                        item["closedPnl"]), "closed_size": _s2dec(item["closedSize"]), "fill_count": int(item["fillCount"]), "creation_ts_ms": int(item["createdTime"])
                }  # "updatedTime": "1672214887236"  # pnls[order["orderId"]]["tpsl_mode"] = order["tpslMode"]

        # next_page = account.get("nextPageCursor", {})

        # 'retExtInfo': {}
        # 'time': 1739794348815

        return pnls
