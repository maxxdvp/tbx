'''
Average True Range (ATR) indicator

Computation:
TRᵢ = max((Hᵢ-Lᵢ),abs(Hᵢ-Cᵢ₋₁),abs(Lᵢ-Cᵢ₋₁))
ATR = 1/N ∑ᵢᴺ TRᵢ
N = period
'''

import numpy as np


class iATR:
    def __init__(self, period: int):
        self.wnd = np.zeros(shape=[period], dtype=float)
        self.pclose = .0

    def get_next(self, high: float, low: float, close: float) -> float:
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = max(high - low, abs(high - self.pclose), abs(low - self.pclose))
        self.pclose = close
        return self.wnd.sum() / self.wnd.size
