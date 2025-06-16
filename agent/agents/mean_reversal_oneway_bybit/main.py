from datetime import datetime as dt
import os
from log import mplog
import logging
import sys
from abc import abstractmethod
from decimal import Decimal

import signal
import threading

from connectors.helpers import _s2i, _s2dec, _normdec, opposite_sign

from agent.agent_service import AgentService
import agent.agent_base as ab
from agent.agents.analyzers.fractals_analyzer import Analyzer


class Agent(ab.AgentBase):

    class Strategy(ab.StrategyBase):

        class MoneyRiskMan:
            def __init__(self, params: dict):
                self.trade_size_limit = _s2dec(params["trade_size_limit"])  # maximum sum per 1 trade, in base asset (use whole balance if None)
                self.position_size_limit = _s2dec(params["position_size_limit"])  # maximum sum per 1 position, in base asset by open price (use whole balance if None)
                assert self.trade_size_limit <= self.position_size_limit, "wrong params: trade_size_limit > position_size_limit"
                self.max_order_open_slippage = _s2dec(params["max_order_open_slippage"])  # maximum relative slippage for order open price

                self.sl_pct = _s2dec(params["sl_pct"])  # maximum relative distance from the open price to the estimated SL for a trade
                self.tp_pct = _s2dec(params["tp_pct"])  # estimated profit / risk (SL) for a trade
                self.trailing_stop_profit_pct = _s2dec(params["trailing_stop_profit_pct"])  # profit level to activate trailing stop
                if self.trailing_stop_profit_pct is not None:
                    self.trailing_stop_pct = _s2dec(params["trailing_stop_pct"])  # active trailing stop distance to market price

        signals: {int, int} = {}  # timeframe to signal mapping

        def __init__(self, params: dict, n_analysers: int):
            super().__init__()
            self.log = mplog.get_logger("Strategy")

            self.bidirectional_trading = bool(params["bidirectional_trading"])  # 0 = trade with longs only, 1 = trade with longs and shorts
            self.order_lifetime_min = _s2i(params["order_lifetime_min"])  # order lifetime, minutes

            self.n_analyzers = n_analysers
            self.mr_man = self.MoneyRiskMan(params)
            self.signal = 0
            self.max_signal = 0
            self.signal_thr = int(params["signal_thr"])

        @abstractmethod
        def __call__(self, timeframe: int, signal: int | None, price: float) -> ab.TxRqOp | None:
            self.signals[timeframe] = signal
            price = Decimal(str(price))

            # summarize signals from analyzers of all timeframes
            signal = sum(v*2**i for v, i in zip(self.signals.values(), range(len(self.signals.values()))))
            # update previous values
            prev_signal = self.signal
            self.signal = signal
            if (self.signal > 0) == (self.max_signal > 0):
                if abs(self.signal) > abs(self.max_signal):
                    self.max_signal = self.signal
            else:
                self.max_signal = self.signal
            if signal: #dbg
                print(f"{dt.now().strftime("%Y-%m-%d %H:%M:%S")} : {price} : {timeframe} : {self.signals} >> {signal} ({self.max_signal})") #dbg
            else: #dbg
                return None #dbg
            # do not take action on weak signal and avoid binge-opening position at consequent timeframes
            if abs(signal) < self.signal_thr:
                print(f"--- signal {signal} < thr {self.signal_thr}")  # dbg
                return None

            # get current position
            pos_value, pos_open = next(((pos.value, pos.open_price) for pos in self.positions if pos.ticker == self.asset.symbol), (0, 0))

            # the position on the same side had been already open
            if pos_value != 0 and (signal > 0) == (pos_value > 0):
                if self.mr_man.trade_size_limit == self.mr_man.position_size_limit:  # no complex positions allowed
                    print("--- can't add position: no complex positions allowed") #dbg
                    return None
                if abs(signal) < abs(self.max_signal):  # do not add position on decreasing signal
                    print(f"--- can't add position: signal {signal} < max signal {self.max_signal}") #dbg
                    return None
                if abs((price - pos_open) / price) < 0.01:  # do not add position in the same point  #todo: move to params
                    print("--- can't add position: price change < 1%") #dbg
                    return None

            # money&risk management

            # available and requested amount
            base_balance = next((a.value - a.value_locked for a in self.assets if a.ticker == self.asset.base_ticker), 0)
            value = (base_balance if self.mr_man.trade_size_limit is None else self.mr_man.trade_size_limit.min(base_balance)) / price
            if signal < 0:
                value = -value
            if pos_value != 0 and opposite_sign(pos_value, value):  # close counter-side position
                value -= pos_value
            else:
                if base_balance == 0:
                    print("--- no base asset") #dbg
                    return None  # no base asset #todo: report (once!)
            # normalizing
            value = _normdec(value, self.asset.value_step)  # align the amount to the allowed precision for order of the asset
            if abs(value) < self.asset.min_order_amount:
                print(f"--- value {value} < min order amount {self.asset.min_order_amount}") #dbg
                return None
            if self.mr_man.trade_size_limit != self.mr_man.position_size_limit:  # complex position
                if self.mr_man.position_size_limit < abs(value + pos_value):
                    print(f"--- position size limit {self.mr_man.position_size_limit} < planned value {value + pos_value}") #dbg
                    return None
            # tp/sl
            sl_price = None
            if self.mr_man.sl_pct:
                sl_price = _normdec(price * (1 + (-self.mr_man.sl_pct if value > 0 else self.mr_man.sl_pct)), self.asset.price_step)
            tp_price = None
            if self.mr_man.tp_pct:
                tp_price = _normdec(price * (1 + (self.mr_man.tp_pct if value > 0 else -self.mr_man.tp_pct)), self.asset.price_step)

            # if provider supports trailing stop
            ts_profit_price = None
            ts_price_dist = None
            if self.mr_man.trailing_stop_profit_pct:
                ts_profit_price = _normdec(price * (1 + (self.mr_man.trailing_stop_profit_pct if value > 0 else -self.mr_man.trailing_stop_profit_pct)), self.asset.price_step)
                ts_price_dist = _normdec(price * self.mr_man.trailing_stop_pct, self.asset.price_step)  # if -1, cancel trailing stop

            # compose transaction
            return ab.TxRqOp(value, price=None, slippage=self.mr_man.max_order_open_slippage, sl=sl_price, tp=tp_price, ts_profit=ts_profit_price, ts=ts_price_dist, lifetime_min=self.order_lifetime_min)

    def __init__(self):
        super().__init__("Mean_Reversal_2Way_ByBit")

    def __del__(self):
        pass

    @abstractmethod
    def get_analyzer_cls(self) -> type:
        return Analyzer

    @abstractmethod
    def get_strategy_cls(self) -> type:
        return self.Strategy


if __name__ == "__main__":
    # mp.set_start_method("spawn", force=True)

    agent = None
    service = None
    _cleanup_lock = threading.Lock()
    _cleanup_called = False
    pid = os.getpid()

    mplog.setup_listener(log_file="agent.log", log_to_stdout=True)
    log = mplog.get_logger("Main")
    mplog.set_log_level(logging.DEBUG)

    # SIGTERM/SIGINT termination signals handler to clean up resources properly
    def cleanup_and_exit(signum=None, frame_t=None):
        global log, service, _cleanup_called

        if pid != os.getpid():
            return
        with _cleanup_lock:
            if _cleanup_called:
                return

            log.info(f"Caught termination signal {signum}")
            _cleanup_called = True
            try:
                if service:
                    service.stop()
            except:
                pass
            sys.exit(0)

    # register termination signal handlers
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    signal.signal(signal.SIGINT, cleanup_and_exit)

    try:
        agent = Agent()
        service = AgentService(agent)
        service.run()
    except Exception as e:
        log.error(e, exc_info=True)
