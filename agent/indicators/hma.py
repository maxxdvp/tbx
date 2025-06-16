'''
Hull Moving Average indicator

Computation:
n = period
WMA = P1*n/W + P2*(n-1)/W + ... + Pn/W; W = n*(n+1)/2
HMA = WMA(2*WMA(n/2) − WMA(n)),sqrt(n))
'''

import numpy as np

class iHMA:
    def __init__(self, period: int, initial_values: np.array):
        self.m = 2 / (period + 1)
        self.wnd = np.zeros(period, dtype=float)
        self.wnd[-1] = np.mean(initial_values[:period])
        for v in initial_values[period:period*2]:
            self.wnd = np.roll(self.wnd, -1, axis=0)
            self.wnd[-1] = (v - self.wnd[-2]) * self.m + self.wnd[-2]

    def get_next(self, v):
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        self.wnd[-1] = (v - self.wnd[-2]) * self.m + self.wnd[-2]
        return self.wnd[-1]
