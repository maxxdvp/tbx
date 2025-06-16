'''
Composite indicator of 3 any MA
'''

import numpy as np
def x3ma(prev: int, eps: np.float32, slow: np.float32, medium: np.float32, fast: np.float32) -> (int, np.float32):
    signal = prev
    match prev:
        case 1:
            if medium + eps < slow < fast - eps:
                signal = 2
        case 2:
            if slow + eps < medium < fast - eps:
                signal = 3
        case 3:
            if medium - eps > fast > slow + eps:
                signal = -1
        case -1:
            if medium - eps > slow > fast + eps:
                signal = -2
        case -2:
            if slow - eps > medium > fast + eps:
                signal = -3
        case -3:
            if medium + eps < fast < slow - eps:
                signal = 1
    ## return signal, signal_factor * signal * np.exp(fast / slow - 1.)
    # return signal, signal / 3. * (1. + np.log(1. + 10. * (fast / slow - 1.)))
    # print(signal, signal * (1. + 10. * (fast - slow)))
    return signal, signal * (1. + 10. * (fast - slow))
