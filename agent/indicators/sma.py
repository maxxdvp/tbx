'''
Simple Moving Average indicator
'''

import numpy as np


class iSMA:
    def __init__(self, period: int):
        self.wnd = np.zeros(period, dtype=float)
        self.SMA = 0.0

    def get_next(self, v):
        # change mean sum
        self.SMA -= self.wnd[0] / self.wnd.size
        self.SMA += v / self.wnd.size
        # roll the window
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        return self.SMA
