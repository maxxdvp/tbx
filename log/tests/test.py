import time
import asyncio
import threading as th
import multiprocessing as mp

import logging
from log import mplog


def thread_task():
    log = mplog.get_logger("ThreadWorker")
    for i in range(3):
        log.info(f"Thread log #{i}")
        time.sleep(0.5)

def process_task():
    log = mplog.get_logger("ProcessWorker")
    for i in range(3):
        log.info(f"Process log #{i}")
        time.sleep(0.5)

async def async_task():
    log = mplog.get_logger("AsyncWorker")
    for i in range(3):
        log.info(f"Async log #{i}")
        await asyncio.sleep(0.5)

def main():
    mplog.setup_listener(log_file="test.log", log_to_stdout=True)

    log = mplog.get_logger("Main")
    log.info("Starting logging demo")

    threads = [th.Thread(target=thread_task) for _ in range(2)]
    for t in threads:
        t.start()

    procs = [mp.Process(target=process_task) for _ in range(2)]
    for p in procs:
        p.start()

    asyncio.run(async_task())

    for t in threads:
        t.join()
    for p in procs:
        p.join()

    mplog.set_log_level(logging.WARNING)
    log.info("This will NOT show (level raised to WARNING)")
    log.warning("This will show (WARNING)")
    mplog.set_log_level(logging.INFO)

    log.info("All workers complete")
    mplog.stop_listener()


if __name__ == "__main__":
    # mp.set_start_method("spawn", force=True)
    main()
