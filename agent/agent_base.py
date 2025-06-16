'''
Base class for agents.
'''

import sys
import decimal
from abc import abstractmethod
from copy import deepcopy
from decimal import Decimal
from enum import Enum

import multiprocessing as mp
import multiprocessing.connection as mpc

from agent.shmem import ShMemOHLCV
import asyncio

import numpy as np
import os
import torch
import random

from log import mplog
import yaml

from connectors.enums import Provider, ProviderType, MarketType
from connectors.objects import Asset, AssetPosition, FundingPosition, Position, Tx, Order
from connectors.helpers import gen_asset_id, opposite_sign, gen_agent_id


class AssetDataPlan:
    def __init__(self, provider_id: Provider, market_id: MarketType, assets_timeframes: list[tuple[str, int]]):
        self.provider_id = provider_id
        self.market_id = market_id
        self.assets = {}  # {int, (Asset, [int])}    # asset ids to assets and timeframes lists used by analyzers

        for ticker, tf in assets_timeframes:
            asset_id = gen_asset_id(provider_id, market_id, ticker)
            if asset_id in self.assets:
                if tf not in self.assets[asset_id][1]:
                    self.assets[asset_id][1].append(tf)
                    self.assets[asset_id][1].sort()
            else:
                self.assets[asset_id] = (ticker, [tf])

    def __getitem__(self, asset_id: int) -> (str, []):
        return self.assets[asset_id]

#todo:
# class OnChainDataPlan:
#     provider_id: int
#     market_id: int
#     chain_id: int
#     history_depth: int           # in timeframes
#     timeframe: int               # one set of timeframes for all assets, in minutes

#todo:
# class NewsSubscription:
#     asset_tickers: [str]


class AccountItemType(Enum):
    ASSET = 1
    FUTURE = 2
    OPTION = 3
    ORDER = 4
    FUNDING = 5

class QMsgType(Enum):
    QMSG_OHLCV = 1
    QMSG_TX = 2

class OHLCV:
    open: decimal
    high: decimal
    low: decimal
    close: decimal
    volume: decimal

# operation details of transaction request
class TxRqOp:
    value: Decimal  # > 0 => buy, < 0 => sell
    price: Decimal | None
    slippage: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    ts_profit: Decimal | None
    ts: Decimal | None
    lifetime_min: int  # in minutes

    def __init__(self, value: Decimal, price: Decimal | None = None, slippage: Decimal | None = None,
                 sl: Decimal | None = None, tp: Decimal | None = None, ts_profit: Decimal | None = None, ts: Decimal | None = None,
                 lifetime_min: int = 0):
        self.value = value
        self.price = price
        self.slippage = slippage
        self.sl = sl
        self.tp = tp
        self.ts_profit = ts_profit
        self.ts = ts
        self.lifetime_min = lifetime_min

# transaction request
class TxRq:
    provider: Provider
    market: MarketType
    ticker: str
    operation: TxRqOp

    def __init__(self, provider: Provider, market: MarketType, ticker: str, operation: TxRqOp):
        self.provider = provider
        self.market = market
        self.ticker = ticker
        self.operation = operation


class TorchSettings:
    def __init__(self, use_gpu: bool, use_mixed_precision: bool):
        # https://pytorch.org/docs/stable/backends.html
        self.use_mixed_precision = use_mixed_precision
        torch.set_default_dtype(torch.float16 if use_mixed_precision else torch.float32)
        if use_gpu and torch.cuda.is_available():
            # device and tensor type setup
            self.device = torch.device('cuda')
            torch.set_default_device('cuda')
            # self.TFloatTensor = torch.cuda.FloatTensor
            # torch.set_default_tensor_type(torch.cuda.FloatTensor)
            torch.cuda.empty_cache()

            # Mixed Precision support

            # CuDNN settings
            if torch.backends.cudnn.is_available():
                torch.backends.cudnn.enabled = True
                torch.backends.cudnn.allow_tf32 = not use_mixed_precision  # use TensorFloat-32 tensor cores in cuDNN convolutions on Ampere or newer GPUs
                # torch.backends.cudnn.deterministic = True  # cuDNN to benchmark multiple convolution algorithms and select the fastest
                torch.backends.cudnn.benchmark = True  # enable the inbuilt cudnn auto-tuner to find the best algorithm

            # CUDA environment variables
            os.environ['CUDA_LAUNCH_BLOCKING'] = '0'  #1 = cpu synchronized to gpu
            os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':128:128'  #:16:8 :initial:growth in Mb
            # os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'garbage_collection_threshold:0.5,max_split_size_mb:32' #,roundup_power2_divisions'
            os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'backend:cudaMallocAsync'

            # CUDA Tensor Cores settings
            torch.backends.cuda.matmul.allow_tf32 = not use_mixed_precision  # use TensorFloat-32 tensor cores in matrix multiplications on Ampere or newer GPUs
            # torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = use_mixed_precision  # allow reduced precision reductions (e.g., with fp16 accumulation type) with fp16 GEMMs
            torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = use_mixed_precision  # allow reduced precision reductions with bf16 GEMMs
        else:
            self.device = torch.device('cpu')
            torch.set_default_device('cpu')
            # self.TFloatTensor = torch.FloatTensor
            # torch.set_default_tensor_type(torch.FloatTensor)
        # torch.set_num_threads(1)


class AgentParams:
    def __init__(self, params: dict):
        self.provider = Provider.get_id(params['provider'])
        self.market = MarketType.get_id(params['market'])
        self.asset = str(params['asset'])


class AnalyzerParams:
    @staticmethod
    def parse_values(params: dict) -> 'AnalyzerParams':
        obj = AnalyzerParams()
        assert "timeframe" in params, "AssetAnalyzer params should have timeframe"
        assert "asset" in params, "AssetAnalyzer params should have asset"
        for key in params:
            dtype = int if str(params[key]).isnumeric() else float
            try:
                setattr(obj, key, dtype(params[key]))
            except ValueError:
                setattr(obj, key, str(params[key]))
        return obj


# market info analyzer
class AssetAnalyzerBase:
    model = None
    # timeframe: int = 0

    def __init__(self, agent_id: int, provider_id: Provider, market_id: MarketType, params: AnalyzerParams):
        self.agent_id = agent_id
        self.provider_id = provider_id
        self.market_id = market_id
        self.params = params

        self.asset_id = gen_asset_id(provider_id, market_id, params.asset)
        self.torch_settings = TorchSettings(bool(params.use_gpu), bool(params.use_mixed_precision)) if hasattr(params, "use_gpu") and hasattr(params, "use_mixed_precision") else None
        self._set_rnd_seed()

    def _set_rnd_seed(self):
        if hasattr(self.params, "random_seed"):
            seed = self.params.random_seed
            if self.torch_settings:
                torch.manual_seed(seed)
                if self.torch_settings.device.type == 'cuda':
                    torch.cuda.manual_seed(seed)
            np.random.seed(seed)
            random.seed(seed)

    # full length of initialization warmup data needed before start to operate.
    @staticmethod
    def get_warmup_period(self) -> int: ...

    # initialize with warmup data.
    @abstractmethod
    def warmup(self, data: np.ndarray): ...

    @abstractmethod
    def __call__(self, ohlcv: np.ndarray) -> TxRq | None: ...


# trading strategy & money manager
class StrategyBase:
    provider: ProviderType = None
    market: MarketType = None
    asset: Asset = None

    assets: list[AssetPosition] = []
    fundings: list[FundingPosition] = []
    positions: list[Position] = []
    orders: list[Order] = []

    def __init__(self):
        pass

    # money management
    @abstractmethod
    def __call__(self, timeframe: int, signal: int | None, price: float) -> TxRqOp | None: ...

    def _debug_print_positions(self, tx: Tx | None = None):
        print(f"positions {"before" if tx else "after"} tx")
        for _pos in self.positions:
            print(f"\tprice {_pos.open_price} | pnl {_pos.realized_pnl} | value {_pos.value} | base value {_pos.value_base}")
        if tx:
            print("tx:")
            print(f"\tprice {tx.price} | pnl {tx.pnl} | fee {tx.fee} | value {tx.value} | base value {tx.value_base}")

    def trade_update(self, tx: Tx) -> None:
        self._debug_print_positions(tx)  #dbg

        new_value = tx.value
        new_value_base = tx.value_base
        pnl = -tx.fee
        # search for matched position
        for _pos in self.positions:
            if _pos.market == tx.market and _pos.ticker == tx.ticker:
                # calc new values of the matched position
                new_value += _pos.value
                new_value_base += _pos.value_base
                if opposite_sign(tx.value, _pos.value):
                    # the tx fully/partially closes the position
                    pnl += tx.value * (tx.price - _pos.open_price)
                if opposite_sign(new_value, _pos.value):
                    # new_value is 0 or on counterside to the existing position, the transaction fully overlaps the current position
                    self.positions.remove(_pos)
                else:
                    # the position is decreased/increased and should be updated
                    _pos.value = new_value
                    _pos.value_base = new_value_base
                    _pos.realized_pnl += pnl
                    new_value = 0
                break
        if new_value != 0:
            # todo: opt = Option()
            pos = Position(market=tx.market, ticker=tx.ticker, value=new_value, value_base=new_value_base, open_price=tx.price,
                           leverage=1,  # todo: tx.leverage
                           realized_pnl=pnl, created_ts_ms=tx.ts_ms)
            self.positions.append(pos)

        self._debug_print_positions()  # dbg


class AgentBase:
    shmem: ShMemOHLCV = None
    proc: mp.Process

    def __init__(self, name: str):
        self.name = name
        self.agent_id = gen_agent_id(name)

        self.log = mplog.get_logger("AgentBase")

        derived_module = self.__class__.__module__
        module_file = sys.modules[derived_module].__file__
        module_dir = os.path.dirname(module_file)

        with open(f"{module_dir}/params.yml", "r+") as f:
            p = yaml.safe_load(f)
            f.close()
        self.strategy_params = p["strategy"]
        self.common_params = AgentParams(self.strategy_params)
        self.analyzers_params = []
        for ps in p["analyzers"].values():
            self.analyzers_params.append(AnalyzerParams.parse_values(ps))
        # compose merged data plan
        self.data_plan = AssetDataPlan(self.common_params.provider, self.common_params.market, [(ap.asset, ap.timeframe) for ap in self.analyzers_params])

        self.pipe_cli = self.pipe_srv = self.lock = None

    def __del__(self):
        if self.shmem is not None:
            self.shmem.cleanup()
        self.stop()

    def get_name(self) -> str:
        return self.name

    def get_data_plan(self) -> AssetDataPlan:
        return self.data_plan

    # returns analyzer class
    @abstractmethod
    def get_analyzer_cls(self) -> type: ...

    # returns strategy class and args for its creation
    @abstractmethod
    def get_strategy_cls(self) -> type: ...

    # returns tuples (timeframe, warmup period) for all analyzers
    def get_warmup_periods(self) -> [(int, int)]:
        ret = []
        analyzer_cls = self.get_analyzer_cls()
        for ap in self.analyzers_params:
            ret.append((ap.timeframe, analyzer_cls.get_warmup_period(ap)))
        return ret

    def create_analyzer(self, params: AnalyzerParams) -> (int, AssetAnalyzerBase):
        analyzer_cls = self.get_analyzer_cls()
        analyzer = analyzer_cls(self.agent_id, self.common_params.provider, self.common_params.market, params)
        return params.timeframe, analyzer

    def start(self, tx_queue: mp.Queue) -> None:
        self.pipe_cli, self.pipe_srv = mp.Pipe()
        strategy_cls = self.get_strategy_cls()  #todo: get type directly, or use the base class
        self.proc = mp.Process(target=self.operate, args=(strategy_cls, self.strategy_params, len(self.analyzers_params), tx_queue, self.pipe_srv))
        self.proc.start()

    def stop(self) -> None:
        assert self.proc is not None, "Agent has not been started."
        if self.proc.is_alive():
            try:
                # graceful shutdown signal (None sentinel)
                for i in range(4):
                    self.pipe_cli.send(None)
                # wait for process to exit

                self.proc.join(timeout=1.0)
                # force kill if still running
                if self.proc.is_alive():
                    self.proc.terminate()
                    self.proc.join(timeout=1.0)
                self.log.info("🗙 the agent has not been normally shut down and was terminated")
            finally:
                self.pipe_cli.close()
                self.log.info("🗙 the agent was shut down")

    # to call at the beginning of each async loop if it calls push_data
    async def init_data_feed(self):
        self.lock = asyncio.Lock()

    # call init_data_feed in the same async loop before the first use
    async def push_data(self, data, wait_ack = True):
        async with self.lock:
            # send data for warmup
            await asyncio.to_thread(self.pipe_cli.send, data)
            if data is None or not wait_ack:
                return  # do not wait acknowledgement after final sending of None
            # non-blocking read of acknowledgment
            while True:
                if await asyncio.to_thread(lambda: mpc.wait([self.pipe_cli], timeout=1)):
                    try:
                        ack = await asyncio.to_thread(self.pipe_cli.recv)
                        if ack == "ACK":
                            break
                        # else:
                        #     self.log.error("Failed ACK.")
                    except EOFError:
                        pass  # no answer yet
                await asyncio.sleep(0.001)  # small delay to avoid busy-waiting

    def operate(self, strategy_cls: type, strategy_params: dict, n_analyzers: int, tx_queue: mp.Queue, pipe: mp.Pipe):
        # create analyzers
        analyzers: {int, AssetAnalyzerBase} = {}  # table of {timeframe, analyzer}
        for ap in self.analyzers_params:
            tf, a = self.create_analyzer(ap)
            analyzers[tf] = a
            self.log.info(f"analyzer for {ap.asset}/{tf}min@{self.common_params.provider}:{self.common_params.market} added")
        # sort analyzers by timeframe in descending order for warmup data requests
        analyzers = dict(sorted(analyzers.items()))

        strategy: StrategyBase = strategy_cls(strategy_params, n_analyzers)

        shmem = None
        try:
            # receive asset info
            while True:
                try:
                    data = pipe.recv()  # blocking receiving from the pipe
                    if data is None:  # end of data
                        break
                    strategy.asset = data
                    pipe.send("ACK")
                except EOFError:
                    break  # sender had closed the connection
            self.log.info("traded asset info update finished")
            # receive account data
            while True:
                try:
                    data = pipe.recv()  # blocking receiving from the pipe
                    if data is None:  # end of data
                        break
                    dtype, data = data
                    match dtype:
                        case AccountItemType.ASSET:
                            strategy.assets = data
                        case AccountItemType.FUTURE | AccountItemType.OPTION:
                            assert len(strategy.positions) == 0, "Strategy positions list is already set"
                            strategy.positions = data
                        case AccountItemType.ORDER:
                            strategy.orders = Order.parse(data)
                        case AccountItemType.FUNDING:
                            strategy.fundings = data
                    pipe.send("ACK")
                except EOFError:
                    break  # sender had closed the connection
            self.log.info("account data update finished")
            # receive warmup data
            feed_cout = len(analyzers)
            while True:
                try:
                    data = pipe.recv()  # blocking receiving from the pipe
                    if data is None:  # end of data
                        feed_cout -= 1
                        if feed_cout == 0:
                            break
                        continue
                    tf, data = data
                    analyzers[tf].warmup(data)
                    pipe.send("ACK")
                except EOFError:
                    break  # sender had closed the connection
            self.log.info("🗘 warmup finished, ready for trading")
            # get to the main work
            shmem = ShMemOHLCV(self.agent_id)
            while True:
                try:
                    data = pipe.recv()  # blocking receiving from the pipe
                    if data is None:  # end of data
                        break
                    msg_type, data = data
                    if msg_type == QMsgType.QMSG_OHLCV:  # read new market data from the shmem and process it
                        tf = int(data)
                        if tf in analyzers.keys():
                            ohlcv = deepcopy(shmem.read(tf, analyzers[tf].asset_id))
                            shmem.clear(tf, analyzers[tf].asset_id)  # clean used cell for proper accumulation of next values
                            signal = analyzers[tf](ohlcv)
                            tx_rq_op = strategy(tf, signal, float(ohlcv[3])) #todo: rm convertion
                            if tx_rq_op is not None:
                                tx_rq = TxRq(self.common_params.provider, self.common_params.market, self.common_params.asset, tx_rq_op)
                                tx_queue.put(tx_rq)
                    elif msg_type == QMsgType.QMSG_TX:
                        strategy.trade_update(data)
                except EOFError:
                    break  # sender had closed the connection
        except Exception as e:
            self.log.error(e, exc_info=True)
        finally:
            if shmem is not None:
                shmem.cleanup()
            self.log.info("🗙 process stopped and shared memory unlinked")
