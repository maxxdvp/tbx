from log import mplog
from log.debug_print import print_object  #dbg
import logging

import threading
import multiprocessing as mp
import asyncio

import keyring
import yaml

import numpy as np
from decimal import Decimal

import zmq
import time

from constants import msg_queue
from proto.tgbot_pb2 import TGBotMsg, TxNotice, AgentError

from connectors.enums import ConnMode, Provider, MarketType, TxStatus
from connectors.objects import Asset, Tx
from connectors.helpers import opposite_sign

from agent.shmem import ShMemOHLCV
from agent.money_guard import MoneyGuard
from agent.tx_log import TxLog
from agent.agent_base import AssetDataPlan, AgentBase, AccountItemType, QMsgType


class AgentService:

    class ConsolidatedDataPlan:
        assets: {int, Asset} = {}  # asset_id 2 asset
        timeframes: {int: [int]} = {}  # asset_id to [timeframes]
        min_timeframes: {int: int} = {}  # asset_id to minimal timeframe

        def add_plan(self, dp: AssetDataPlan):
            for aid, a in dp.assets.items():
                if aid not in self.assets.keys():
                    self.assets[aid] = a[0]
                    self.timeframes[aid] = a[1]
                    self.timeframes[aid].sort()
                    self.min_timeframes[aid] = min(a[1])
                else:
                    items = set(a[1]) - set(self.assets[aid].timeframes)
                    if len(items) > 0:
                        self.timeframes[aid].extend(items)
                        self.timeframes[aid].sort()
                        if self.min_timeframes[aid] > min(items):
                            self.min_timeframes[aid] = min(items)

        def __getitem__(self, asset_id: int) -> str:
            return self.assets[asset_id]

    def __init__(self, agent: AgentBase):
        self.log = mplog.get_logger("AgentService")
        self._running = False
        self._stop_lock = threading.Lock()

        self.log.info("▶ Agent service is being initialized...")

        with open("./params.yml", "r+") as f:
            params = yaml.safe_load(f)
            f.close()
        keyring_service = params["keyring_service"]
        self.conn_mode = ConnMode.DEMO if bool(params["demo_acc"]) else (ConnMode.TESTNET if bool(params["test_mode"]) else ConnMode.NORMAL)

        # connect to provider(s)
        self.api_key = keyring.get_password(keyring_service, "API_KEY")
        self.api_secret = keyring.get_password(keyring_service, "API_SECRET")

        self.agent = agent
        self.data_plan = AgentService.ConsolidatedDataPlan()  # rearranged data plan of the agent
        self.market_queue = asyncio.Queue()  # for market data warmup input for the agent
        self.shmem = self.create_shmem()  # for agent market data input feed
        # objects for processing of agent output transactions
        self.tx_rq_queue = mp.Queue()
        self.tx_rpt_queue = asyncio.Queue()

        self.conn_ts = self._import_connector_class("state", "TradingState")(self.api_key, self.api_secret, self.conn_mode)
        self.conn_to = self._import_connector_class("operation", "TradingOperation")(self.api_key, self.api_secret, self.conn_mode)
        self.conn_fm = None

        # for tx reports
        self.base_ticker = None
        self.equity_base = Decimal(0)
        self.equity = Decimal(0)

        self.tx_log = TxLog("./tx_log.sqlite")
        self.tx_log_last_ts = self.tx_log.get_last_record_ts()
        self.money_guard = MoneyGuard(params, self.tx_log)

        # objects for services
        self.stop_event = asyncio.Event()
        self.service_tasks = []
        self.market_q = asyncio.Queue()
        self.tx_result_q = asyncio.Queue()

        self.zmq_context = zmq.Context()
        self.tgbot_socket = self.zmq_context.socket(zmq.PUSH)
        self.tgbot_socket.setsockopt(zmq.SNDHWM, 1000)
        self.tgbot_socket.connect(msg_queue.TGBOT_SOCKET)
        time.sleep(0.1)
        self.log.info(f"🗹 TG-bot connection has been set.")

    def _import_connector_class(self, package: str, class_: str):
        provider = self.agent.common_params.provider.name.lower()
        try:
            module = __import__(f"connectors.{provider}.{package}", fromlist=[class_])
            return getattr(module, class_)
        except (ImportError, AttributeError) as e:
            self.log.critical(f"Failed to import {class_} from connectors.{provider}.{package}: {e}")
            return None

    def create_shmem(self) -> ShMemOHLCV | None:
        try:
            self.log.info("Shared memory is being created...")
            agent_data_plan = self.agent.get_data_plan()
            self.data_plan.add_plan(agent_data_plan)
            new_size = []
            for aid, asset in self.data_plan.assets.items():
                for tf in self.data_plan.timeframes[aid]:
                    v = (aid, tf)
                    if v not in new_size:
                        new_size.append(v)
            new_size = len(new_size)
            shmem = ShMemOHLCV(self.agent.agent_id, size=new_size)
            if shmem.size < new_size:
                self.log.info(f"Shared memory {shmem.name} of size {shmem.size} already exists, but needed size {new_size} is bigger. The shared memory will be recreated.")
                shmem.cleanup()
                shmem = ShMemOHLCV(self.agent.agent_id, size=new_size)
            self.log.info(f"🗹 Shared memory {shmem.name} has been created.")
            return shmem
        except Exception as e:
            self.log.error(e, exc_info=True)
        return None

    def warmup_agent(self):
        async def start_agent_impl():
            async def feed_asset_info(provider_id: Provider, market_id: MarketType, asset: str):
                log = mplog.get_logger(f"Asset info feed for provider {provider_id}, marker {market_id}, asset {asset}")
                log.info(f"🗘 starting...")
                try:
                    asset_info = await self.conn_ts.get_asset_info(market_id, asset)
                    if asset_info:
                        await self.agent.push_data(asset_info)
                        self.base_ticker = asset_info.base_ticker
                        self.log.debug(f"base_ticker: {self.base_ticker}")
                except Exception as e:
                    log.error(e, exc_info=True)
                finally:
                    await self.agent.push_data(None)  # signal end of feeding
                    log.info(f"🗙 finished")

            async def feed_account_state(provider_id: Provider, market_id: MarketType, asset: str):
                log = mplog.get_logger(f"Account state feed for provider {provider_id}, marker {market_id}, asset {asset}")
                log.info(f"🗘 starting...")
                try:
                    assets = await self.conn_ts.get_assets()
                    if len(assets) != 0:
                        await self.agent.push_data((AccountItemType.ASSET, assets))
                        for ast in assets:
                            if ast.ticker == self.base_ticker:
                                self.equity_base = ast.value
                                self.log.debug(f"base equity: {self.equity_base}")

                    funds = await self.conn_ts.get_funds()
                    if len(funds) != 0:
                        await self.agent.push_data((AccountItemType.FUNDING, funds))

                    if market_id in (MarketType.FUTURE, MarketType.FUTUREINV):
                        positions = await self.conn_ts.get_positions(market_id, asset)
                        if len(positions) != 0:
                            await self.agent.push_data((AccountItemType.FUTURE, positions))
                            for pos in positions:
                                self.equity += pos.value_base
                            self.log.debug(f"equity: {self.equity}")
                    elif market_id == MarketType.OPTION:
                        positions = await self.conn_ts.get_options()
                        if len(positions) != 0:
                            await self.agent.push_data((AccountItemType.OPTION, positions))

                    orders: dict = await self.conn_ts.get_orders(market_id, asset)
                    if len(orders) != 0:
                        await self.agent.push_data((AccountItemType.ORDER, orders))
                except Exception as e:
                    log.error(e, exc_info=True)
                finally:
                    await self.agent.push_data(None)  # signal end of feeding
                    log.info(f"🗙 finished")

            async def feed_hist_data(tf, period):
                async def fetch_hist_data(provider_id: Provider, market_id: MarketType, asset: str, timeframe: int, period: int):
                    try:
                        return self.conn_ts.get_price_history(market_id, asset, timeframe, period)
                    except Exception as e:
                        log.error(e, exc_info=True)
                    return None

                log = mplog.get_logger(f"History market data feed for tf {tf}, period {period}")
                log.info(f"🗘 starting...")
                try:
                    async for data_row in await fetch_hist_data(self.agent.common_params.provider, self.agent.common_params.market, self.agent.common_params.asset, tf, period):
                        if data_row is not None:
                            await self.agent.push_data((tf, data_row))
                except Exception as e:
                    log.error(e, exc_info=True)
                finally:
                    await self.agent.push_data(None)  # signal end of feeding
                    log.info(f"🗙 finished")

            await self.agent.init_data_feed()
            # update agent with traded asset detals
            await feed_asset_info(self.agent.common_params.provider, self.agent.common_params.market, self.agent.common_params.asset)
            # update agent with account state
            await feed_account_state(self.agent.common_params.provider, self.agent.common_params.market, self.agent.common_params.asset)
            # warmup agent with historical market data
            wa_periods = self.agent.get_warmup_periods()
            tasks = [asyncio.create_task(feed_hist_data(tf, period)) for tf, period in wa_periods]
            await asyncio.gather(*tasks)  # wait for the completion of all tasks (sending all data)

        try:
            asyncio.run(start_agent_impl())
            self.log.info("Agent completed its initialization.")
        except Exception as e:
            self.log.error(e, exc_info=True)

    async def market_data_feed(self, q: asyncio.Queue):
        log = mplog.get_logger("Market data feed")
        try:
            log.info("🗘 starting...")
            self.conn_fm = self._import_connector_class("feeding", "FeedingMarket")(self.agent.common_params.market, q, self.conn_mode)

            assets = self.data_plan.assets.items()  # todo: traverse along all assets
            asset = list(assets)[0]
            tf = self.data_plan.min_timeframes[asset[0]]
            self.conn_fm.start_feed(asset[1], tf)
            log.info("🗘 started")
        except Exception as e:
            self.log.error(e, exc_info=True)

    # updates ohlcv of highest tf from ohlcv of lowest tf
    @staticmethod
    def update_ohlcv(ohlcv_h: np.ndarray, ohlcv_l: list[float]):
        if ohlcv_h[0] == 0:  # open
            ohlcv_h[0] = ohlcv_l[0]
        if ohlcv_h[1] < ohlcv_l[1]:  # high
            ohlcv_h[1] = ohlcv_l[1]
        if ohlcv_h[2] == 0. or ohlcv_h[2] > ohlcv_l[2]:  # low
            ohlcv_h[2] = ohlcv_l[2]
        ohlcv_h[3] = ohlcv_l[3]  # close
        ohlcv_h[4] += ohlcv_l[4]  # volume

    # market data handler
    async def market_data_handler(self, q: asyncio.Queue):
        log = mplog.get_logger("Market data handler")
        log.info("🗘 starting...")
        try:
            while True:
                # retrieve data
                data = await q.get()
                ohlcv = [float(data["open"]), float(data["high"]), float(data["low"]), float(data["close"]), float(data["volume"])]
                ts_min = int(data["timestamp"]) // 60000  # ms -> mins
                # update shmem buffer for strategy
                for aid, timeframes in self.data_plan.timeframes.items():
                    for tf in timeframes:
                        if tf == self.data_plan.min_timeframes[aid]:
                            self.shmem.store(tf, aid, np.array(ohlcv))
                        else:
                            ohlcv_tf = self.shmem.read(tf, aid)
                            AgentService.update_ohlcv(ohlcv_tf, ohlcv)
                            self.shmem.store(tf, aid, ohlcv_tf)
                        if ts_min % tf == 0:  # notify agent when the candle finished
                            await self.agent.push_data((QMsgType.QMSG_OHLCV, tf), wait_ack=False)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(e, exc_info=True)
        finally:
            log.info("🗙 shut down")

    # processes tx requests from the agent
    async def tx_rq_poller(self, tx_queue: mp.Queue):
        async def tx_handler() -> str | None:
            match tx.market:
                case MarketType.SPOT:
                    return await self.conn_to.place_spot_order(market=True, asset=tx.ticker, value=tx.operation.value, price=tx.operation.price, slippage_pct=tx.operation.slippage, tp=tx.operation.tp, sl=tx.operation.sl)  # todo: tp, sl, to_limit, sl_limit
                case MarketType.FUTURE | MarketType.FUTUREINV:
                    return await self.conn_to.place_future_order(market=True, asset=tx.ticker, value=tx.operation.value, price=tx.operation.price, slippage_pct=tx.operation.slippage, close=False, linear_future=tx.market == MarketType.FUTURE, tp=tx.operation.tp, sl=tx.operation.sl)  # link_id=str(self.agent.agent_id),  #todo: tp, sl, to_limit, sl_limit
                case MarketType.OPTION:
                    return await self.conn_to.place_option_order(market=True, asset=tx.ticker, value=tx.operation.value, price=tx.operation.price, slippage_pct=tx.operation.slippage, close=False)  # link_id=self.agent.agent_id,
            return None

        log = mplog.get_logger("Tx handler")
        log.info("🗘 starting...")
        try:
            while True:
                tx = await asyncio.to_thread(tx_queue.get)
                print_object(tx, title="Tx poller received request:")  #dbg
                if await self.money_guard.trade_allowed():
                    log.debug("trade allowed by risk manager")
                    try:
                        order_id = await tx_handler()
                        if order_id:
                            log.debug(f"order sent: order id = {order_id}")
                    except Exception as e:
                        log.error(e, exc_info=True)  # await asyncio.sleep(0.05)  # yield execution for efficiency
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(e, exc_info=True)
        finally:
            log.info("🗙 shut down")

    # tx notifier for tg-bot
    async def _tg_notify_on_tx(self, tx: Tx, pnl: Decimal, status: str):
        try:
            notice = TxNotice(provider=self.agent.common_params.provider.value, market=tx.market.value, ticker="BTCUSDT", op_side=tx.op_side.value, op_type=tx.op_type.value, value=str(tx.value), value_base=str(tx.value_base), price=str(tx.price), fee=str(tx.fee), pnl=str(pnl), status=status, ts_ms=tx.ts_ms)
            msg = TGBotMsg(rid=1, tx_notice=notice)  # rid?
            self.tgbot_socket.send(msg.SerializeToString(), zmq.DONTWAIT)
        except zmq.Again:
            # todo: handle full buffer: log, drop, save to disk
            self.log.warning("Tx notice message not delivered to TG-bot")

    # trade disallowance notifier for tg-bot
    async def _tg_notify_on_trade_disallowance(self):
        try:
            if msg := await self.money_guard.trade_disallowance_reason():
                notice = AgentError(ts_ms=int(time.time() * 1000), level=logging.WARNING, source="Money Guard", message=msg)
                msg = TGBotMsg(rid=0, agent_error=notice)  # rid?
                self.tgbot_socket.send(msg.SerializeToString(), zmq.DONTWAIT)
        except zmq.Again:
            # todo: handle full buffer: log, drop, save to disk
            self.log.warning("Tx notice message not delivered to TG-bot")

    async def tx_rpt_poller(self, market: MarketType, ticker: str, tx_result_queue: asyncio.Queue):
        log = mplog.get_logger("Tx report poller")
        log.info("🗘 starting...")
        try:
            while True:
                try:
                    self.tx_log_last_ts = await self.conn_to.fetch_orders_result(market, ticker, self.tx_log_last_ts, tx_result_queue)
                except Exception as e:
                    log.error(e)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(e, exc_info=True)
        finally:
            log.info("🗙 shut down")

    # reads posted orders from the queue, fetches the execution results and handles them
    async def tx_rpt_handler(self, tx_result_queue: asyncio.Queue):
        async def handler(tx: Tx):
            if tx:
                if tx.price and tx.value != 0:
                    if tx.status == TxStatus.REJECTED:
                        #todo: tell to the strategy?
                        await self._tg_notify_on_tx(tx, Decimal(0), f"tx rejected ({tx.reason})")
                        return
                    elif tx.status == TxStatus.CANCELLED:
                        await self._tg_notify_on_tx(tx, Decimal(0), f"tx cancelled ({tx.reason})")
                        return

                    await self.agent.push_data((QMsgType.QMSG_TX, tx), wait_ack=False)

                    pnl = -tx.fee
                    equity = Decimal(0)
                    if self.agent.common_params.market == MarketType.FUTURE:
                        if opposite_sign(self.equity, tx.value_base):
                            for i in range(5):
                                try:
                                    ret = await self.conn_to.get_last_closed_pnl(tx.market, tx.ticker)
                                    if ret is not None and ret[0] == tx.order_id:
                                        pnl = ret[1]
                                        break
                                except Exception as e:
                                    log.error(e)
                                await asyncio.sleep(0.2)
                        self.equity += tx.value_base
                        self.equity_base += pnl
                        equity = self.equity_base
                    elif self.agent.common_params.market == MarketType.SPOT:
                        equity1 = self.equity_base + abs(self.equity)
                        if opposite_sign(self.equity, tx.value_base):
                            if abs(self.equity) > abs(tx.value_base):
                                self.equity_base += abs(tx.value_base)
                            else:
                                self.equity_base += abs(self.equity)
                        else:
                            self.equity_base -= abs(tx.value_base)
                        self.equity += tx.value_base
                        self.equity_base += pnl
                        equity = self.equity_base + abs(self.equity)
                        pnl = equity - equity1

                    self.tx_log.add_operation(tx.ts_ms, self.agent.common_params.provider, tx.market, tx.ticker, tx.value, tx.price, tx.op_side, tx.op_type, tx.fee)
                    trade_allowed = self.money_guard.update_agent_allowance()

                    await self._tg_notify_on_tx(tx, pnl, f"eq {equity}")

                    if not trade_allowed:
                        await self._tg_notify_on_trade_disallowance()

        log = mplog.get_logger("Tx report handler")
        log.info("🗘 starting...")
        try:
            while True:
                tx = await tx_result_queue.get()
                asyncio.create_task(handler(tx))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(e, exc_info=True)
        finally:
            log.info("🗙 shut down")

    def start_services(self):
        async def start_services_impl():
            await self.agent.init_data_feed()
            self.service_tasks = [asyncio.create_task(self.market_data_handler(self.market_q)), asyncio.create_task(self.market_data_feed(self.market_q)),
                asyncio.create_task(self.tx_rpt_handler(self.tx_rpt_queue)),
                asyncio.create_task(self.tx_rpt_poller(self.agent.common_params.market, self.agent.common_params.asset, self.tx_rpt_queue)),
                asyncio.create_task(self.tx_rq_poller(self.tx_rq_queue))
            ]
            await self.stop_event.wait()

        try:
            self.log.info("starting agent services...")
            asyncio.run(start_services_impl())
        except Exception as e:
            self.log.error(e, exc_info=True)

    def run(self):
        with self._stop_lock:
            if self._running:
                return
            self._running = True
        try:
            self.agent.start(self.tx_rq_queue)
            self.log.info("🗘 Agent started.")
            self.warmup_agent()
            self.start_services()
        except Exception as e:
            self.log.error(e, exc_info=True)
        finally:
            self.cleanup()

    def stop(self):
        self.cleanup()

    def cleanup(self):
        with self._stop_lock:
            if not self._running:
                return
            self._running = False

            assert self.stop_event is not None, "Agent services are not run."
            if self.conn_fm:
                self.conn_fm.cleanup()
                self.log.info("🗙 Market data feeder was shut down.")
            for task in self.service_tasks:
                task.cancel()
            self.stop_event.set()
            asyncio.gather(*self.service_tasks, return_exceptions=True)
            self.log.info("🗙 Agent services have been stopped.")

            assert self.agent is not None, "Agent service: agent has not been initialized."
            self.agent.stop()
            if self.shmem is not None:
                self.shmem.cleanup()
                self.log.info(f"🗆 Shared memory {self.shmem.name} was cleaned up.")

            if self.tgbot_socket:
                self.tgbot_socket.disconnect(msg_queue.TGBOT_SOCKET)
                self.tgbot_socket.close()
            if self.zmq_context:
                self.zmq_context.term()
            self.log.info(f"🗆 TG-bot connection was closed.")

            self.log.info("■ The bot was fully stopped.\n🕇🕇🕇")
