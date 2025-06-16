'''
Support and Resistance Levels indicator

Computation:
1. run fractals indicator on the data window
2. add previous levels to given points
3. sort the points
4. clusterize the points
5. return centroids of clusters as found levels
'''

import numpy as np
# from line_profiler import profile

from .fractals import iFractals


class iLevels:
    # @profile
    def calc(self):
        pts = []
        for v in self.wnd[-self.fractals_period:]:  # check for new reversal point
            fr = self.ifr.get_next(v[0], v[1]) != 0
            if fr == 1:
                pts.append([v[0], 1])
            elif fr == -1:
                pts.append([v[1], 1])
        if len(pts) == 0:
            return
        pts += self.levels
        pts = sorted(pts)  # sorting by axis 0
        clusters = []
        pt1 = pts[0]
        curr_cluster = [pt1]
        for pt in pts[1:]:
            if pt[0] / pt1[0] <= self.keps:
                curr_cluster.append(pt)
            else:
                clusters.append(curr_cluster)
                curr_cluster = [pt]
            pt1 = pt
        clusters.append(curr_cluster)
        levels = []
        for clr in clusters:
            vsum = sum(pt[0]*pt[1] for pt in clr)
            nsum = sum(pt[1] for pt in clr)
            if nsum > self.points_thres:
                levels.append([vsum / nsum, nsum])  # save centroid and points count
        self.levels = levels

    '''
    initial_value = [[high, low]]
    period = len(initial_values)
    fractals_period
    fractals_tolerance
    eps = radius to clusterize fractal points
    '''
    def __init__(self, initial_values: np.array, fractals_period: int, fractals_tolerance: float, level_eps: float, level_points_thres: int):
        self.wnd = np.copy(initial_values)
        self.fractals_period = fractals_period
        self.ifr = iFractals(fractals_period, fractals_tolerance)
        self.keps = 1.0 + level_eps
        self.points_thres = level_points_thres
        self.levels = []

    def get_next(self, high: float, low: float) -> np.ndarray:
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1, 0] = high
        self.wnd[-1, 1] = low
        self.calc()
        return np.array(self.levels, dtype=np.float32)
