'''
Fractals indicator

Computation:
- example for period=5 (5 previous values)
Hᵢ₋₄ < Hᵢ₋₃ < Hᵢ₋₂ > Hᵢ₋₁ > Hᵢ => bullish fractal (local max)
Lᵢ₋₄ > Lᵢ₋₃ > Lᵢ₋₂ < Lᵢ₋₁ < Lᵢ => bearish fractal (local min)
'''

import numpy as np
# from line_profiler import profile


class iFractals:

    def __init__(self, period: int, tolerance: float = .0):
        """
        period: 2ⁿ+1 = 3,5,7,9,11...
        tolerance: relative part of difference of adjacent values
        """
        # todo: add assert for nonparity of period
        self.wnd = np.zeros(shape=period, dtype=int)
        self.ktlr = tolerance + 1.0
        self.ipvt = period // 2  # center pivot index
        self.prev_high = self.prev_low = 0.

    # @profile
    def calc(self) -> int:
        if np.all(self.wnd[self.ipvt:] == -1):
            if np.all(self.wnd[:self.ipvt] == 1):
                return 1  # local max - bullish fractal (^)
        elif np.all(self.wnd[self.ipvt:] == 1):
            if np.all(self.wnd[:self.ipvt] == -1):
                return -1  # local min - bearish fractal (v)
        return 0

    # @profile
    def get_next(self, high: float, low: float) -> int:
        """
        1 => bullish fractal (local max)
        -1 => bearish fractal (local min)
        """
        self.wnd = np.roll(self.wnd, -1, axis=0)
        if self.prev_high < high / self.ktlr:
            self.wnd[-1] = 1
        elif self.prev_low > low * self.ktlr:
            self.wnd[-1] = -1
        else:
            self.wnd[-1] = 0
        self.prev_high = high
        self.prev_low = low
        return self.calc()
