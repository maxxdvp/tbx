from datetime import datetime as dt
from log import mplog
import logging

import numpy as np
import copy

import agent.agent_base as ab
from agent.indicators.lsma import iLSMA
from agent.rms import RMS


# features indices
class FEATURES:
    OPEN = 0  # log[orig. open]
    HIGH = 1  # log[orig. high]
    LOW = 2  # log[orig. low]
    CLOSE = 3  # log[orig. close]
    VOLUME = 4  # log[orig. volume]
    NUM = 5


class InputFrame:
    def __init__(self, params: ab.AnalyzerParams):
        self.params = params

        self.orig_ohlcv = self.prev_orig_ohlcv = None
        #todo:rm self.start_close_price_updated = self.start_close_price = None
        self.input_frame = np.zeros((params.frame_size, FEATURES.NUM), dtype=np.float32)

        self.norm_eps = 1.0e-10

        if self.params.smooth_period > 1:  # warmup smoothing MAs
            self.OMA = self.HMA = self.LMA = self.CMA = self.VMA = None

        # input normalization
        if params.norm_input:
            self.norm_clip = 0.999999999999  # todo: add param
            self.norm_features_begin = FEATURES.OPEN
            self.norm_features_end = FEATURES.VOLUME + 1
            self.input_rms = RMS(epsilon=self.norm_eps, shape=(self.norm_features_end - self.norm_features_begin,))

        # input differencing
        # if self.params.diff_input:

    def warmup(self, data: np.ndarray, wu_size: int):
        self.wu_buff = np.zeros((wu_size, 5), dtype=np.float32)
        self.wu_pt = 0
        if self.wu_pt < wu_size:  # accumulate buffer for indicators warmup
            self.wu_buff[self.wu_pt] = data[1:-1]  # todo: use all elements?
            self.wu_pt += 1
            if self.wu_pt == wu_size:  # warmup indicators
                if self.params.log_input:
                    self.wu_buff = np.sign(self.wu_buff) * np.log(np.abs(self.wu_buff) + 1.0)
                if self.params.smooth_period > 1:  # warmup smoothing MAs
                    self.wu_buff = self.wu_buff[-self.params.smooth_period:]
                    self.OMA = iLSMA(self.wu_buff[:, FEATURES.OPEN])
                    self.HMA = iLSMA(self.wu_buff[:, FEATURES.HIGH])
                    self.LMA = iLSMA(self.wu_buff[:, FEATURES.LOW])
                    self.CMA = iLSMA(self.wu_buff[:, FEATURES.CLOSE])
                    self.VMA = iLSMA(self.wu_buff[:, FEATURES.VOLUME])
                del self.wu_buff
        else:  # fill input frame
            self(data[1:-1])
            self.wu_pt += 1

    def __call__(self, ohlcv: np.ndarray):
        # shift input frame to the left
        self.input_frame = np.roll(self.input_frame, -1, axis=0)
        # store original ohlcv for last timeframe
        self.prev_orig_ohlcv = self.orig_ohlcv
        self.orig_ohlcv = copy.deepcopy(ohlcv)

        # logarithmize ohlcv if specified
        if self.params.log_input:
            ohlcv = np.sign(self.orig_ohlcv) * np.log(np.abs(self.orig_ohlcv) + 1.0)

        # smooth prices and volumes if specified
        if self.params.smooth_period > 1:
            self.input_frame[-1, FEATURES.OPEN] = self.OMA.get_next(ohlcv[FEATURES.OPEN])
            self.input_frame[-1, FEATURES.HIGH] = self.HMA.get_next(ohlcv[FEATURES.HIGH])
            self.input_frame[-1, FEATURES.LOW] = self.LMA.get_next(ohlcv[FEATURES.LOW])
            self.input_frame[-1, FEATURES.CLOSE] = self.CMA.get_next(ohlcv[FEATURES.CLOSE])
            self.input_frame[-1, FEATURES.VOLUME] = self.VMA.get_next(ohlcv[FEATURES.VOLUME])
        else:
            self.input_frame[-1, :FEATURES.VOLUME + 1] = ohlcv

        # normalize if specified
        if self.params.norm_input:
            iframe_ohlcv = self.input_frame[-1, self.norm_features_begin:self.norm_features_end]
            self.input_rms.update_from_moments(iframe_ohlcv, 0., 1)
            self.input_frame[-1, self.norm_features_begin:self.norm_features_end] =\
                np.clip((iframe_ohlcv - self.input_rms.mean) / np.sqrt(self.input_rms.var + self.norm_eps), -self.norm_clip, self.norm_clip)

        # differentiate if specified
        if self.params.diff_input:
            # assert data[-1, FEATURES.OPEN] != .0, f'data[-1]: {str(data[-1])}'
            self.input_frame[-1, FEATURES.HIGH] = self.input_frame[-1, FEATURES.HIGH] / self.input_frame[-1, FEATURES.OPEN] - 1.0
            self.input_frame[-1, FEATURES.LOW] = self.input_frame[-1, FEATURES.LOW] / self.input_frame[-1, FEATURES.OPEN] - 1.0
            self.input_frame[-1, FEATURES.CLOSE] = self.input_frame[-1, FEATURES.CLOSE] / self.input_frame[-1, FEATURES.OPEN] - 1.0
            if self.prev_orig_ohlcv is not None:
                self.input_frame[-1, FEATURES.OPEN] = self.input_frame[-1, FEATURES.OPEN] / self.prev_orig_ohlcv[
                    FEATURES.CLOSE] - 1.0
                self.input_frame[-1, FEATURES.VOLUME] = self.input_frame[-1, FEATURES.VOLUME] / self.prev_orig_ohlcv[
                    FEATURES.VOLUME] - 1.0 if self.prev_orig_ohlcv[FEATURES.VOLUME] > .0 else 1.
            else:  # do this only on init
                self.input_frame[-1, FEATURES.OPEN] = .0
                self.input_frame[-1, FEATURES.VOLUME] = .0

    def data(self) -> np.ndarray:
        return self.input_frame

    def __del__(self):
        if self.input_frame is not None:
            del self.input_frame