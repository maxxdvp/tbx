'''
Shared memory with single writer and multiple readers for market data feed
'''

import numpy as np
import multiprocessing.shared_memory as shm

class ShMemOHLCV:
    DATA_ITEM_SIZE = 5  # OHLCV values as float64
    MIN_SIZE = 16

    # specified size also means taking ownership
    def __init__(self, agent_id: int, size: int = None):
        self.name = f"TB{agent_id}"
        self.lock_name = f"TBLOCK{agent_id}"
        self.dtype = np.float64
        self.is_owner = size is not None

        try:
            # try to attach to existing shared memory
            self.shm = shm.SharedMemory(name=self.name)
            self.lock_shm = shm.SharedMemory(name=self.lock_name)
            self.size = self.shm.size // np.dtype(self.dtype).itemsize // self.DATA_ITEM_SIZE
        except FileNotFoundError:
            assert size is not None, f"Shared memory {self.name} was not found, and size for creation is not specified."
            self.size = max(size, self.MIN_SIZE)  # to prevent hashed index collisions
            # create new shared memory and lock
            self.shm = shm.SharedMemory(name=self.name, create=True, size=self.size * self.DATA_ITEM_SIZE * np.dtype(self.dtype).itemsize)
            self.lock_shm = shm.SharedMemory(name=self.lock_name, create=True, size=8)  # 8-byte lock flag
            np.ndarray((self.size, self.DATA_ITEM_SIZE), dtype=self.dtype, buffer=self.shm.buf)[:] = 0.  # zero out memory for new instance
            np.ndarray((1,), dtype=np.int64, buffer=self.lock_shm.buf)[0] = 0  # reset lock

        # shared memory-backed arrays
        self.table = np.ndarray((self.size, self.DATA_ITEM_SIZE), dtype=self.dtype, buffer=self.shm.buf)
        self.lock_flag = np.ndarray((1,), dtype=np.int64, buffer=self.lock_shm.buf)

    def _hash(self, timeframe: int, asset_id: int) -> int:
        return ((timeframe * 31) ^ (asset_id * 17)) % self.size

    def _acquire_lock(self):
        while self.lock_flag[0] == 1:
            pass
        self.lock_flag[0] = 1

    def _release_lock(self):
        self.lock_flag[0] = 0

    def store(self, timeframe: int, asset_id: int, ohlcv: np.ndarray):
        self._acquire_lock()
        try:
            index = self._hash(timeframe, asset_id)
            self.table[index] = ohlcv
        finally:
            self._release_lock()

    def read(self, timeframe: int, asset_id: int) -> np.ndarray:
        index = self._hash(timeframe, asset_id)
        return self.table[index]

    def clear(self, timeframe: int, asset_id: int):
        self._acquire_lock()
        try:
            index = self._hash(timeframe, asset_id)
            self.table[index] = 0.
        finally:
            self._release_lock()

    def cleanup(self):
        self.shm.close()
        self.lock_shm.close()
        if self.is_owner:
            try:
                self.shm.unlink()
                self.lock_shm.unlink()
            except FileNotFoundError:
                pass  # another process may have already unlinked it
