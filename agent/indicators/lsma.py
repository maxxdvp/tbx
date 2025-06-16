'''
Least Squares Moving Average indicator

Computation:
1. Define a period n.
2. For each data point x from 1 to n, compute its linear regression line value.
3. The equation for the line is given by y = mx + c, where m is the slope and c is the y-intercept.
4. The LSMA is essentially the computed y values for each x.
The slope m is given by:
    m = [ n∑xy-∑x∑y ] / [ n∑x²-(∑x)² ]
and the y-intercept c is:
    c = [ ∑y-m∑x ] / n
where:
    • Σ(xy) is the sum of the product of each x value and its corresponding y value (price).
    • ∑x is the sum of x values.
    • ∑y is the sum of y values (prices).
    • ∑x² is the sum of the squares of x values.
'''

import numpy as np

class iLSMA:

    def calc(self):
        m = (self.n * np.sum(self.x * self.wnd) - self.x_sum * np.sum(self.wnd)) / (self.n * self.x2_sum - self.x_sum2)
        c = (np.sum(self.wnd) - m * self.x_sum) / self.n
        return m * self.n + c  # The projected value at the end of the period

    '''
    period = len(initial_values)
    '''
    def __init__(self, initial_values: np.array):
        self.n = len(initial_values)
        self.x = np.array(range(1, self.n+1)).astype(float)
        self.x_sum = np.sum(self.x)
        self.x_sum2 = self.x_sum ** 2
        self.x2_sum = np.sum(self.x ** 2)
        self.wnd = np.copy(initial_values)

    def get_next(self, v):
        self.wnd = np.roll(self.wnd, -1, axis=0)
        self.wnd[-1] = v
        return self.calc()
