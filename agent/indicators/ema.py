'''
Exponential Moving Average indicator

Computation:
EMAt = v(t) * a + [ EMA(t-1) * (1-a) ]
where:
• EMA(t) is the EMA for the current time t
• v(t) is the value for the current time t
• α (alpha) is the smoothing factor, calculated as α = 2 / (N+1)
• N is the period of the EMA
• EMA(t−1) is the EMA for the previous time t−1
'''

import numpy as np


'''
period = len(initial_values) // 2
'''
class iEMA:
    def calc(self, v: float):
        self.wnd[-1] = (v - self.wnd[-2]) * self.a + self.wnd[-2]

    def __init__(self, initial_values: np.array):
        n = len(initial_values) // 2
        self.a = 2 / (n+1)
        self.wnd = np.zeros(n, dtype=float)
        self.wnd[-1] = np.mean(initial_values[:n])
        for v in initial_values[n:n*2]:
            self.wnd = np.roll(self.wnd, -1, axis=0)
            self.calc(v)

    def get_next(self, v):
        # roll the window
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        # calculate the indicator
        self.calc(v)
        return self.wnd[-1]
