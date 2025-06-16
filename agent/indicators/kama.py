'''
Adaptive Moving Average (AMA or KAMA) indicator

Computation:
ER = abs(v(i) - v(i - N)) / Σ(j=1,n:abs(v(j)-v(j-1))
SC = (ER(fastSC-slowSC) + slowSC)²
KAMA(i) = KAMA(i-1) + SC(v(i) - KAMA(i-1))
where:
• ER is the Efficiency Ratio, change divided by volatility.
• SC is the Smoothing Constant.
• The fastest SC and the slowest SC are typically set at 2/(2+1) and 2/(30+1) respectively.
'''

import numpy as np


class iKAMA:
    def calc(self):
        ER = np.abs(self.wnd[-1]-self.wnd[0]) / np.sum(np.abs(np.diff(self.wnd)))  #todo: optimize for speed
        SC = (ER * self.fSC_sSC + self.sSC) ** 2
        return self.KAMAprev + SC * (self.wnd[-1] - self.KAMAprev)

    '''
    fastest_SC = 2 / (2 + 1)
    slowest_SC = 2 / (30 + 1)
    period = len(initial_values)
    '''
    def __init__(self, fastSC: float, slowSC: float, initial_values: np.array):
        self.sSC = slowSC
        self.fSC_sSC = fastSC - slowSC
        self.wnd = np.copy(initial_values)
        self.KAMAprev = 0.
        self.KAMAprev = self.calc()

    def get_next(self, v):
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        self.KAMAprev = self.calc()
        return self.KAMAprev
