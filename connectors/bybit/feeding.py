'''
ByBit API wrapper for agent feeding with market data.
'''

import time
import asyncio
import threading as th

from pybit.unified_trading import WebSocket

from log import mplog

from connectors.objects import MarketType
from connectors.bybit.common import _market_type2str, LOG_PREFIX, ConnMode


# https://bybit-exchange.github.io/docs/v5/ws/connect

class FeedingMarket:
    def __init__(self, asset_type: MarketType, out_queue: asyncio.Queue, mode: ConnMode):
        self.asset_type = asset_type
        self.out_queue = out_queue
        self.mode = mode

        self.ws: WebSocket | None = None
        self._stop_event = th.Event()
        self.loop = None
        self.feed_thread: th.Thread | None = None
        self.last_msg_time = time.time()
        self.lock = th.Lock()

    def cleanup(self):
        self._stop_event.set()
        if self.ws:
            self.ws.exit()
        if self.feed_thread:
            self.feed_thread.join(timeout=1)

    @staticmethod
    def validate_timeframe(timeframe_min: int):
        if timeframe_min not in [1, 3, 5, 15, 30, 60, 120, 240, 360, 720, 1440, 10080, 40320]:
            raise ValueError(f"{LOG_PREFIX}timeframe {timeframe_min} not supported")

    # https://bybit-exchange.github.io/docs/v5/websocket/public/kline

    def msg_handler(self, msg):
        with self.lock:
            self.last_msg_time = time.time()
        data = msg["data"][0]
        if int(data["timestamp"]) >= int(data["end"]):  # do not send incomplete candles
            asyncio.run_coroutine_threadsafe(self.out_queue.put(data), self.loop)

    # interval (min) = 1 3 5 15 30 60 120 240 360 720, 1440 (day), 10080 (week), 40320 (month)
    def start_feed(self, asset: str, timeframe_min: int):
        log = mplog.get_logger("ByBit feed (prices)")

        def start_feed_impl(asset: str, timeframe_min: int):
            FeedingMarket.validate_timeframe(timeframe_min)

            while not self._stop_event.is_set():
                try:
                    # ByBit Demo WebSockets only supports the private streams, so for demo mode regular mainnet used (demo=False always)
                    # callback_function ws_name tld domain rsa_authentication ping_interval ping_timeout trace_logging private_auth_expire
                    self.ws = WebSocket(channel_type=_market_type2str(self.asset_type), testnet=self.mode == ConnMode.TESTNET, restart_on_error=False, retries=0)

                    # with self.lock:
                    self.last_msg_time = time.time()

                    self.ws.kline_stream(interval=timeframe_min, symbol=asset, callback=self.msg_handler)

                    # watchdog loop - check for stall every second
                    while not self._stop_event.is_set():
                        time.sleep(1)
                        with self.lock:
                            delta = time.time() - self.last_msg_time
                        if delta > 15:  #todo: move to settings?
                            log.warning(f"WebSocket feed stalled for {delta:.1f}s, restarting...")
                            break
                except Exception as e:
                    log.critical(e, exc_info=True)
                    if self.ws:
                        self.ws.exit()
                    time.sleep(3)  # optional backoff

        self.loop = asyncio.get_running_loop()
        self.feed_thread = th.Thread(target=start_feed_impl, args=(asset, timeframe_min))
        self.feed_thread.start()

    # others:
    # https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook
    # https://bybit-exchange.github.io/docs/v5/websocket/public/trade
    # https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
    # https://bybit-exchange.github.io/docs/v5/websocket/public/liquidation
    # https://bybit-exchange.github.io/docs/v5/websocket/public/etp-kline
    # https://bybit-exchange.github.io/docs/v5/websocket/public/etp-ticker
    # https://bybit-exchange.github.io/docs/v5/websocket/public/etp-nav
