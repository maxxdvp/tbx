'''
ByBit API wrapper for trading results feeding.
'''

from log import mplog
import time

import threading as th
import asyncio

import hmac

from pybit.unified_trading import WebSocket
import socket

from connectors.enums import OpSide, OpType, TxStatus
from connectors.objects import Position, Tx
from connectors.helpers import _s2dec
from connectors.bybit.common import _str2market_type, ConnMode


class FeedingAccount:
    def __init__(self, out_queue: asyncio.Queue, api_key: str, api_secret: str, mode: ConnMode):
        self.out_queue = out_queue
        self.conn_mode = mode
        self.api_key = api_key
        self.api_secret = api_secret

        self._stop_event = th.Event()
        self.feed_tx_loop = None
        self.feed_tx_thread: th.Thread | None = None
        self.feed_ord_loop = None
        self.feed_ord_thread: th.Thread | None = None
        self.feed_pos_loop = None
        self.feed_pos_thread: th.Thread | None = None

    def cleanup(self):
        self._stop_event.set()
        if self.feed_tx_thread:
            self.feed_tx_thread.join(timeout=1)
        if self.feed_ord_thread:
            self.feed_ord_thread.join(timeout=1)
        if self.feed_pos_thread:
            self.feed_pos_thread.join(timeout=1)

    def msg_handler_tx(self, msg):
        #todo: there may be multiple executions for one order in a single message.
        data = msg["data"][0]

        order_id = data["orderId"]
        size = _s2dec(data["execQty"])  # orderQty, leavesQty
        side = 1 if data["side"] == "Buy" else -1  #todo: rm?
        op_side = OpSide.BUY if side > 0 else OpSide.SELL
        value = _s2dec(data["execValue"])
        price = _s2dec(data["execPrice"])  # orderPrice, markPrice, indexPrice
        fee = _s2dec(data["execFee"])  # feeRate
        # pnl = _s2dec(data["execPnl"]) $todo: ?

        op_type = OpType.NON_AUTO  # UNKNOWN
        match data["stopOrderType"]:
            case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                op_type = OpType.TAKE_PROFIT
            case "StopLoss" | "PartialStopLoss":
                op_type = OpType.STOP_LOSS
            case "Stop":  # triggered a market order
                op_type = OpType.STOP_LIMIT
            case "tpslOrder" | "BidirectionalTpslOrder":
                op_type = OpType.STOP_LIMIT  #todo: determine tp|sl
            # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)

        exec_ts_ms = int(data["execTime"])
        # execType: Trade | Funding (Funding fee) | AdlTrade (Auto-Deleveraging) | BustTrade (Takeover liquidation)
        #     Delivery (USDC futures delivery; Position closed by contract delisted) | Settle (Inverse futures settlement; Position closed due to delisting)
        #     BlockTrade | MovePosition | FutureSpread (Spread leg execution) | UNKNOWN (May be returned by a classic account)
        # orderType: Market | Limit | UNKNOWN (Funding etc)
        # createType: CreateByUser | CreateByStopLoss/CreateByPartialStopLoss | CreateByTakeProfit/CreateByPartialTakeProfit | CreateByStopOrder | CreateByTrailingStop
        #     CreateByFutureSpread (Spread order) | CreateByAdminClosing | CreateBySettle (USDC Futures delivery) | CreateByLiq (Laddered liquidation to reduce the required maintenance margin)
        #     CreateByTakeOver_PassThrough (If the position is still subject to liquidation) | CreateByAdl_PassThrough (Auto-Deleveraging(ADL)) | CreateByBlock_PassThrough (Order placed via Paradigm) | CreateByBlockTradeMovePosition_PassThrough (Order created by move position)
        #     CreateByClosing | CreateByFGridBot | CloseByFGridBot | CreateByTWAP | CreateByTVSignal | CreateByMartingaleBot/CloseByMartingaleBot | CreateByIceBerg | CreateByArbitrage | CreateByDdh | CreateByMmRateClose - external apps

        # orderLinkId, execId, blockTradeId, seq, isLeverage, isMaker, closedSize, tradeIv, markIv, underlyingPrice, marketUnit
        trade = Tx(order_id, _str2market_type(data["category"]), data["symbol"], op_side, op_type, side * size, side * value, price, fee, exec_ts_ms, TxStatus.FILLED, "")
        self.feed_tx_loop.call_soon_threadsafe(self.out_queue.put_nowait, trade)

    def start_feed_tx(self):
        def start_feed_tx_impl():
            # https://bybit-exchange.github.io/docs/v5/ws/connect
            # https://bybit-exchange.github.io/docs/v5/websocket/private/execution
            log = mplog.get_logger("ByBit feed (transactions)")
            try:
                ws: WebSocket | None = None
                while not self._stop_event.is_set():
                    # callback_function ws_name tld="" domain="" rsa_authentication=False ping_interval=20 ping_timeout=10 trace_logging=False private_auth_expire=1
                    ws = WebSocket(channel_type="private", testnet=self.conn_mode == ConnMode.TESTNET, demo=self.conn_mode == ConnMode.DEMO,
                                   api_key=self.api_key, api_secret=self.api_secret, restart_on_error=False, retries=0)
                    try:
                        ws.execution_stream(callback=self.msg_handler_tx)
                        while not self._stop_event.is_set():
                            time.sleep(0.1)
                    except (ConnectionResetError, socket.error, Exception) as e:
                        log.error(f"{e} Restarting tx feed after short delay.")
                        try:
                            ws.exit()
                        except:
                            pass
                        time.sleep(5)  # cooldown before reconnecting
                if ws:
                    ws.exit()
            except Exception as e:
                log.critical(e, exc_info=True)

        self.feed_tx_loop = asyncio.get_running_loop()
        self.feed_tx_thread = th.Thread(target=start_feed_tx_impl)
        self.feed_tx_thread.start()

    def msg_handler_ord(self, msg):
        data = msg["data"][0]

        order_id = data["orderId"]
        status = data["orderStatus"]
        reason = ""
        match status:
            case "Cancelled":  # not supported for spot; for derivatives, orders with this status may have an executed qty
                status = TxStatus.CANCELLED
                reason = data["cancelType"]
            case "Rejected":
                status = TxStatus.REJECTED
                reason = data["rejectReason"]
            case "Filled":
                status = TxStatus.FILLED
            case "PartiallyFilled" | "PartiallyFilledCanceled":  # PFC supported only for spot
                status = TxStatus.PARTIALLY_FILLED
            case _:  # New | Untriggered | Triggered | Deactivated - non-executions
                return

        size = _s2dec(data["cumExecQty"])  # qty, leavesQty, marketUnit(spot)=baseCoin|quoteCoin
        side = 1 if data["side"] == "Buy" else -1  #todo: rm?
        op_side = OpSide.BUY if side > 0 else OpSide.SELL
        value = _s2dec(data["cumExecValue"])  # leavesValue
        price = _s2dec(data["avgPrice"])  # price, lastPriceOnCreated
        fee = _s2dec(data["cumExecFee"])  # feeCurrency(spot)
        # pnl = _s2dec(data["closedPnl"]) #todo ?

        op_type = OpType.NON_AUTO
        match data["stopOrderType"]:
            case "TakeProfit" | "PartialTakeProfit" | "TrailingStop":
                op_type = OpType.TAKE_PROFIT
            case "StopLoss" | "PartialStopLoss":
                op_type = OpType.STOP_LOSS
            case "Stop":  # triggered a market order
                op_type = OpType.STOP_LIMIT
            case "tpslOrder" | "BidirectionalTpslOrder":
                op_type = OpType.STOP_LIMIT  #todo: determine tp|sl
            # OcoOrder (spot Oco order) | MmRateClose (On web or app can set MMR to close position)

        exec_ts_ms = int(data["updatedTime"])  # createdTime
        # orderLinkId, blockTradeId, positionIdx
        # orderType: Market|Limit|UNKNOWN (usually when execType=Funding), createType: CreateByClosing
        # isLeverage: 0|1 (spot only), slippageTolerance, slippageToleranceType(spot|futures)=TickSize|Percent|UNKNOWN
        # reduceOnly, timeInForce = GTC(GoodTillCancel)|IOC(ImmediateOrCancel)|FOK(FillOrKill)|PostOnly|RPI
        # tpslMode, triggerBy, triggerPrice, triggerDirection, closeOnTrigger, takeProfit, stopLoss, tpTriggerBy, slTriggerBy, tpLimitPrice, slLimitPrice, ocoTriggerBy
        # smpType, smpGroup, smpOrderId (Self Match Prevention)
        # if data["category"] == "option":
        #     orderIv, placeType

        trade = Tx(order_id, _str2market_type(data["category"]), data["symbol"], op_side, op_type, side * size, side * value, price, fee, exec_ts_ms, status, reason)
        self.feed_ord_loop.call_soon_threadsafe(self.out_queue.put_nowait, trade)

    def start_feed_ord(self):
        def start_feed_ord_impl():
            # https://bybit-exchange.github.io/docs/v5/ws/connect
            # https://bybit-exchange.github.io/docs/v5/websocket/private/order
            log = mplog.get_logger("ByBit feed (orders)")
            try:
                ws: WebSocket | None = None
                while not self._stop_event.is_set():
                    # callback_function ws_name tld="" domain="" rsa_authentication=False ping_interval=20 ping_timeout=10 trace_logging=False private_auth_expire=1
                    ws = WebSocket(channel_type="private", testnet=self.conn_mode == ConnMode.TESTNET, demo=self.conn_mode == ConnMode.DEMO,
                                   api_key=self.api_key, api_secret=self.api_secret, restart_on_error=False, retries=0)
                    try:
                        ws.order_stream(callback=self.msg_handler_ord)
                        while not self._stop_event.is_set():
                            time.sleep(1)
                    except (ConnectionResetError, socket.error, Exception) as e:
                        log.error(f"{e} Restarting order feed after short delay.")
                        try:
                            ws.exit()
                        except:
                            pass
                        time.sleep(5)  # cooldown before reconnecting
                if ws:
                    ws.exit()
            except Exception as e:
                log.critical(e, exc_info=True)

        self.feed_ord_loop = asyncio.get_running_loop()
        self.feed_ord_thread = th.Thread(target=start_feed_ord_impl)
        self.feed_ord_thread.start()

    def msg_handler_pos(self, msg):
        data = msg["data"][0]

        size = data["size"]
        if size == "0":
            return
        side = data["side"]
        if side == "":
            return
        value = data["positionValue"]
        if value == "":
            return
        open_price = data["entryPrice"]
        if open_price == "0":
            return
        side = 1 if side == "Buy" else -1
        pos = Position(_str2market_type(data["category"]), data["symbol"], side * _s2dec(size), side * _s2dec(value), _s2dec(open_price),
                       int(data["leverage"]), _s2dec(data["curRealisedPnl"]), int(data["createdTime"]))
        #todo:
        # pos.option = Option()
        # pos.option... = ...
        self.feed_pos_loop.call_soon_threadsafe(self.out_queue.put_nowait, pos)

    def start_feed_pos(self):
        def start_feed_pos_impl():
            # https://bybit-exchange.github.io/docs/v5/ws/connect
            # https://bybit-exchange.github.io/docs/v5/websocket/private/position
            log = mplog.get_logger("ByBit feed (positions)")
            try:
                ws: WebSocket | None = None
                while not self._stop_event.is_set():
                    # callback_function ws_name tld="" domain="" rsa_authentication=False ping_interval=20 ping_timeout=10 trace_logging=False private_auth_expire=1
                    ws = WebSocket(channel_type="private", testnet=self.conn_mode == ConnMode.TESTNET, demo=self.conn_mode == ConnMode.DEMO,
                                   api_key=self.api_key, api_secret=self.api_secret, restart_on_error=False, retries=0)
                    try:
                        ws.position_stream(callback=self.msg_handler_pos)
                        while not self._stop_event.is_set():
                            time.sleep(1)
                    except (ConnectionResetError, socket.error, Exception) as e:
                        log.error(f"{e} Restarting positions feed after short delay.")
                        try:
                            ws.exit()
                        except:
                            pass
                        time.sleep(5)  # cooldown before reconnecting
                if ws:
                    ws.exit()
            except Exception as e:
                log.critical(e, exc_info=True)

        self.feed_pos_loop = asyncio.get_running_loop()
        self.feed_pos_thread = th.Thread(target=start_feed_pos_impl)
        self.feed_pos_thread.start()

    #todo:
    # https://bybit-exchange.github.io/docs/v5/websocket/private/order
    # https://bybit-exchange.github.io/docs/v5/websocket/private/wallet
    # https://bybit-exchange.github.io/docs/v5/websocket/private/greek
    # https://bybit-exchange.github.io/docs/v5/websocket/private/dcp
