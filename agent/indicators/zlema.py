'''
Zero Lag Moving Average indicator

Computation:
N is the ZLEMA period
1. Lag = N / 2
2. Create a new series of adjusted values, by subtracting the lag-day EMA from the value:
XAi = X(i) − X(i-Lag)
3. ZLEMA = EMA(XA).
'''

import numpy as np
from .ema import iEMA


class iZLEMA:
    '''
    period = len(initial_values) // 2
    '''
    def __init__(self, init_values: np.array):
        ni = len(init_values)
        self.n = ni // 2
        self.lag = self.n // 2
        self.wnd = np.copy(init_values[:self.lag])
        iva = np.zeros(ni, dtype=float)
        iva[self.lag:] = init_values[0]
        iva = [2 * init_values[i] - init_values[i - self.lag] for i in range(self.lag, ni)]
        self.iema = iEMA(iva)

    def get_next(self, v):
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        return self.iema.get_next(2 * v - self.wnd[0])
