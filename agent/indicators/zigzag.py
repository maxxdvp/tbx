'''
ZigZag indicator
'''

import numpy as np


PEAK = 1
VALLEY = -1

class iZigZag:
    def identify_initial_pivot(self, X: np.ndarray) -> int:
        x_0 = X[0]
        max_x, min_x = x_0, x_0
        max_t, min_t = 0, 0

        for t in range(1, len(X)):
            x_t = X[t]
            if x_t / min_x >= self.up_thresh:
                return VALLEY if min_t == 0 else PEAK
            if x_t / max_x <= self.down_thresh:
                return PEAK if max_t == 0 else VALLEY
            if x_t > max_x:
                max_x = x_t
                max_t = t
            if x_t < min_x:
                min_x = x_t
                min_t = t

        t_n = len(X)-1
        return VALLEY if x_0 < X[t_n] else PEAK

    def __init__(self, up_thresh: float, down_thresh: float, initial_values: np.array):
        '''
        :param up_thresh: minimum relative change necessary to define a peak
        :param down_thesh: minimum relative change necessary to define a valley
        '''
        if down_thresh > 0:
            raise ValueError('The down_thresh must be negative.')
        self.up_thresh = up_thresh + 1.
        self.down_thresh = down_thresh + 1.

        initial_pivot = self.identify_initial_pivot(initial_values)
        self.trend = -initial_pivot
        self.last_pivot_x = initial_values[0]

    def get_next(self, x: float):
        r = x / self.last_pivot_x
        pivot = 0

        if self.trend == -1:
            if r >= self.up_thresh:
                pivot = self.trend
                self.trend = PEAK
                self.last_pivot_x = x
            elif x < self.last_pivot_x:
                self.last_pivot_x = x
        else:
            if r <= self.down_thresh:
                pivot = self.trend
                self.trend = VALLEY
                self.last_pivot_x = x
            elif x > self.last_pivot_x:
                self.last_pivot_x = x

        return pivot
