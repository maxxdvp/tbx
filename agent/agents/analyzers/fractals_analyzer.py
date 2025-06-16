import numpy as np
from abc import abstractmethod

import agent.agent_base as ab
from agent.indicators.fractals import iFractals
from agent.input_frame import FEATURES, InputFrame


class Analyzer(ab.AssetAnalyzerBase):
    class MeanReversalModel:
        def __init__(self, timeframe: int, period: int, tolerance: float):
            self.timeframe = timeframe
            self.fractals = iFractals(period, tolerance)

        def __call__(self, data: np.ndarray) -> int | None:
            return self.fractals.get_next(float(data[-1, FEATURES.HIGH]), int(data[-1, FEATURES.LOW]))

    def __init__(self, agent_id: int, provider_id: ab.Provider, market_id: ab.MarketType, params: ab.AnalyzerParams):
        super().__init__(agent_id, provider_id, market_id, params)
        self.input_frame = InputFrame(params)
        self.model = self.MeanReversalModel(self.params.timeframe, self.params.fractal_period, self.params.fractal_tolerance)

    @staticmethod
    def get_warmup_period(params: ab.AnalyzerParams) -> int:
        return params.fractal_period + params.frame_size

    @abstractmethod
    def warmup(self, data: np.ndarray):
        self.input_frame.warmup(data, self.params.fractal_period)

    @abstractmethod
    def __call__(self, ohlcv: np.ndarray) -> int | None:
        self.input_frame(ohlcv)
        return -self.model(self.input_frame.data())  # get trade signal from a model
