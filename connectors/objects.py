from decimal import Decimal, ROUND_DOWN

from connectors.enums import Provider, MarketType, OpSide, OpType, TxStatus


class AssetPosition:
    #todo: provider: Provider
    #todo: market: MarketType
    ticker: str
    value: Decimal
    value_locked: Decimal

    def __init__(self, ticker: str, value: Decimal, value_locked: Decimal):
        self.ticker = ticker
        self.value = value
        self.value_locked = value_locked


class FundingPosition:
    ticker: str
    balance: Decimal
    available_balance: Decimal


class Asset:
    provider: Provider                # index of provider from enums.Providers
    market: MarketType                # optional index of market from enums.Providers
    symbol: str
    ticker: str
    base_ticker: str
    trading: bool
    min_order_amount: Decimal
    max_order_amount: Decimal
    tick_size: Decimal
    value_step: Decimal
    value_base_step: Decimal
    price_step: Decimal

    def __init__(self, provider: Provider, market: MarketType, symbol: str, ticker: str, base_ticker: str, trading: bool,
                 min_order_amount: Decimal, max_order_amount: Decimal, value_step: Decimal, value_base_step: Decimal, price_step: Decimal):
        self.provider = provider
        self.market = market
        self.symbol = symbol
        self.ticker = ticker
        self.base_ticker = base_ticker
        self.trading = trading
        self.min_order_amount = min_order_amount
        self.max_order_amount = max_order_amount
        self.value_step = value_step
        self.value_base_step = value_base_step
        self.price_step = price_step


class Position:
    class Option:
        pass

    #todo: provider: Provider
    market: MarketType
    ticker: str
    value: Decimal  # > 0 => long, < 0 => short
    value_base: Decimal
    open_price: Decimal
    leverage: int
    realized_pnl: Decimal
    created_ts_ms: int
    option: Option | None = None

    def __init__(self, market: MarketType, ticker: str, value: Decimal, value_base: Decimal, open_price: Decimal, leverage: int,
                 realized_pnl: Decimal, created_ts_ms: int, option: Option | None = None):
        self.market = market
        self.ticker = ticker
        self.value = value
        self.value_base = value_base
        self.open_price = open_price
        self.leverage = leverage
        self.realized_pnl = realized_pnl
        self.created_ts_ms = created_ts_ms
        self.option = option


class Tx:
    order_id: str
    #todo: provider: Provider
    market: MarketType
    ticker: str
    op_side: OpSide
    op_type: OpType
    value: Decimal  # > 0 => long, < 0 => short
    value_base: Decimal
    price: Decimal
    fee: Decimal
    ts_ms: int
    status: TxStatus
    reason: str

    def __init__(self, order_id: str, market: MarketType, ticker: str, op_side: OpSide, op_type: OpType,
                 value: Decimal, value_base: Decimal, price: Decimal, fee: Decimal,
                 ts_ms: int, status: TxStatus, reason: str):
        self.order_id = order_id
        self.market = market
        self.ticker = ticker
        self.op_side = op_side
        self.op_type = op_type
        self.value = value
        self.value_base = value_base
        self.price = price
        self.fee = fee
        self.ts_ms = ts_ms
        self.status = status
        self.reason = reason


class Trade:
    #todo: provider: Provider
    market: MarketType
    ticker: str
    open_op_side: OpSide    # position open side
    close_op_type: OpType   # position close type
    value: Decimal          # > 0 => long, < 0 => short
    avg_open_price: Decimal
    avg_open_value_base: Decimal
    open_ts_ms: int         #todo: first/last open tx?
    avg_close_price: Decimal
    avg_close_value_base: Decimal
    close_ts_ms: int        #todo: first/last close tx?
    s_fee: Decimal            # cumulative fee
    s_pnl: Decimal            # cumulative P&L, includes cumulative fee

    def __init__(self, market: MarketType, ticker: str, open_op_side: OpSide, close_op_type: OpType, value: Decimal,
                 avg_open_price: Decimal, avg_open_value_base: Decimal, open_ts_ms: int,
                 avg_close_price: Decimal, avg_close_value_base: Decimal, close_ts_ms: int,
                 s_fee: Decimal, s_pnl: Decimal):
        self.market = market
        self.ticker = ticker
        self.op_side = open_op_side
        self.op_type = close_op_type
        self.value = value
        self.avg_open_price = avg_open_price
        self.avg_open_value_base = avg_open_value_base
        self.open_ts_ms = open_ts_ms
        self.avg_close_price = avg_close_price
        self.avg_close_value_base = avg_close_value_base
        self.close_ts_ms = close_ts_ms
        self.s_fee = s_fee
        self.s_pnl = s_pnl


class Order:
    #todo: provider: Provider
    #todo: market: MarketType
    id: str
    ticker: str
    base_ticker: str
    value: Decimal            # in target asset, > 0 => buy, < 0 => sell
    exec_value: Decimal       # in target asset, > 0 => buy, < 0 => sell
    open_price: Decimal
    avg_exec_price: Decimal
    exec_fee: Decimal
    stop_loss: Decimal
    take_profit: Decimal

    @staticmethod
    def parse(data: {}) -> list['Order']: #todo: move to connector
        '''
        "status": order["orderStatus"], "cancel_type": order["cancelType"], "reject_reason": order["rejectReason"],

        "link_id": order["orderLinkId"], "block_trade_id": order["blockTradeId"],

        "trigger_price": _s2f(order["triggerPrice"]), "trigger_direction": int(order["triggerDirection"]),  # trigger direction. 1: rise, 2: fall
        "trigger_by": order["triggerBy"],  # the price type to trigger
        "tp_limit": _s2f(order["tpLimitPrice"]), "sl_limit": _s2f(order["slLimitPrice"]),
        "tp_trigger_by": order["tpTriggerBy"], "sl_trigger_by": order["slTriggerBy"],  # the price type to trigger
        "type": order["orderType"],  # Market,Limit. For TP/SL order, it means the order type after triggered
        "stop_type": order["stopOrderType"], "base_asset": order["marketUnit"],  # the unit for qty (baseCoin | quoteCoin)

        "exec_value": _s2f(order["cumExecValue"]),
        "left_amount": _s2f(order["leavesQty"]), "left_value": _s2f(order["leavesValue"]), "lifetime": order["timeInForce"],
        "leveraged": bool(order["isLeverage"]),
        "position_index": int(order["positionIdx"]),
        "created_ts_ms": int(order["createdTime"]), "updated_ts_ms": int(order["updatedTime"])
        if cat != "spot":
            orders[order["orderId"]]["tpsl_mode"] = order["tpslMode"]  # Full = entire position for TP/SL; Partial = partial position tp/sl. Option returns always ""
            orders[order["orderId"]]["price_on_creation"] = _s2f(order["lastPriceOnCreated"])  # last price when place the order
            orders[order["orderId"]]["oco_trigger_by"] = order["ocoTriggerBy"]  # OcoTriggerByUnknown | OcoTriggerByTp | OcoTriggerByBySl - the trigger type of Spot OCO order
        else:
            orders[order["orderId"]]["price_on_creation"] = _s2f(order["basePrice"])  # Last price when place the order
        if account["category"] == "linear":
            orders[order["orderId"]]["create_type"] = order["createType"]
        if account["category"] == "option":
            orders[order["orderId"]]["place_type"] = order["placeType"]  # iv | price
            orders[order["orderId"]]["implied_volatility"] = _s2f(order["orderIv"])
        #todo: inverse
        # orders[order["orderId"]]["reduce_only"] = bool(order["reduceOnly"])
        # orders[order["orderId"]]["close_on_trigger"] = bool(order["closeOnTrigger"])
        # orders[order["orderId"]]["smp_type"] = bool(order["smpType"])  # None (default) | CancelMaker | CancelTaker | CancelBoth
        # orders[order["orderId"]]["smp_group_id"] = bool(order["smpGroup"])  # Smp group ID. If the UID has no group, it is 0 by default
        # orders[order["orderId"]]["smp_order_id"] = bool(order["smpOrderId"])  # The counterparty's orderID which triggers this SMP execution
        '''
        orders = []
        for k, v in data.items():
            order = Order()
            order.id = k
            order.ticker = v["asset"]
            side = 1 if v["side"] == "Buy" else -1
            order.value = side * v["amount"]
            order.exec_value = side * v["exec_amount"]
            order.open_price = v["price"]
            order.avg_exec_price = v["avg_price"]
            order.exec_fee = v["exec_fee"]
            order.stop_loss = v["sl"]
            order.take_profit = v["tp"]
            orders.append(order)
        #todo
        return orders
