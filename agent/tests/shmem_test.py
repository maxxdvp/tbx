import multiprocessing
import numpy as np

from connectors.enums import Provider, MarketType
from connectors.helpers import gen_agent_id, gen_asset_id
from agent.shmem import ShMemOHLCV


# Shared memory name
AGENT_ID = gen_agent_id("Test_Agent")
SOLUSDT_ID = gen_asset_id(Provider.BYBIT, MarketType.FUTURE, "SOLUSDT")
BTCUSDT_ID = gen_asset_id(Provider.BYBIT, MarketType.SPOT, "BTCUSDT")

if __name__ == "__main__":
    hash_table = ShMemOHLCV(AGENT_ID, 3)
    print("Storing data...")
    hash_table.store(5, SOLUSDT_ID, np.array([1.23, 4.56, 7.89, 0.12, 3.45]))
    hash_table.store(15, BTCUSDT_ID, np.array([2.34, 5.67, 8.90, 1.23, 4.56]))
    hash_table.store(60, BTCUSDT_ID, np.array([7.89, 0.12, 3.45, 6.78, 9.01]))
    print("Data stored")

    hash_table = ShMemOHLCV(AGENT_ID)
    result = hash_table.read(5, SOLUSDT_ID)
    print(f"Read SOLUSDT 5m: {result}")
    result = hash_table.read(15, BTCUSDT_ID)
    print(f"Read BTCUSDT 15m: {result}")
    result = hash_table.read(60, BTCUSDT_ID)
    print(f"Read BTCUSDT 60m: {result}")

    hash_table.cleanup()
    print("Cleanup done")
    exit(0)

# Writer process
def writer():
    shmem = ShMemOHLCV(AGENT_ID, 3)
    print("[Writer] Storing data...")
    shmem.store(5, 1, np.array([1.23, 4.56, 7.89, 0.12, 3.45]))
    shmem.store(15, 2, np.array([2.34, 5.67, 8.90, 1.23, 4.56]))
    shmem.store(60, 2, np.array([7.89, 0.12, 3.45, 6.78, 9.01]))
    print("[Writer] Data stored.")
    time.sleep(5)
    shmem.cleanup()
    print("[Writer] Cleanup done.")

# Reader process
def reader(timeframe):
    shmem = ShMemOHLCV(AGENT_ID)
    result = shmem.read(timeframe, SOLUSDT_ID)
    print(f"[Reader {multiprocessing.current_process().name}] Read {timeframe}: {result}")

if __name__ == "__main__":
    writer_process = multiprocessing.Process(target=writer)
    writer_process.start()
    writer_process.join()

    reader_processes = [multiprocessing.Process(target=reader, args=(5,)) for _ in range(3)]

    for p in reader_processes:
        p.start()

    for p in reader_processes:
        p.join()


# Benchmarking multiprocessing.shared_memory.SharedMemory Attach Time
#--------------------------------------------------------------------

import time
import multiprocessing.shared_memory as shm

SHARED_MEMORY_NAME = "benchmark_test"

shape = (1024, 5)
size = np.prod(shape) * np.dtype(np.float64).itemsize

shared_mem = shm.SharedMemory(name=SHARED_MEMORY_NAME, create=True, size=size)
shared_mem.close()

start = time.perf_counter()
for _ in range(1000):  # Attach 1000 times
    shared_mem = shm.SharedMemory(name=SHARED_MEMORY_NAME)
    table = np.ndarray(shape, dtype=np.float64, buffer=shared_mem.buf)
    shared_mem.close()
end = time.perf_counter()

print(f"Average attach time: {(end - start) / 1000:.6f} seconds ({(end - start) * 1e6 / 1000:.2f} µs per attach)")
shared_mem.unlink()


# Benchmarking ShMemOHLCV Attach Time
#------------------------------------

shared_mem = ShMemOHLCV(1, 1)

start = time.perf_counter()
for _ in range(1000):  # Attach 1000 times
    sm = ShMemOHLCV(1, 1)
    sm.cleanup()
end = time.perf_counter()

print(f"Average attach time: {(end - start) / 1000:.6f} seconds ({(end - start) * 1e6 / 1000:.2f} µs per attach)")
shared_mem.cleanup()
