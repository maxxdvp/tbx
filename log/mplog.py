import sys
from typing import Optional, List
import multiprocessing

import logging
from logging.handlers import QueueHandler, QueueListener


_log_queue: multiprocessing.Queue = None
_listener: QueueListener = None


def _get_or_create_queue():
    global _log_queue
    if _log_queue is None:
        ctx = multiprocessing.get_context()
        _log_queue = ctx.Queue(-1)
    return _log_queue


def setup_listener(log_file: Optional[str] = None, log_to_stdout: bool = True, extra_handlers: Optional[List[logging.Handler]] = None, level = logging.INFO):
    """
    Set up a logging listener that reads from a multiprocessing queue and writes to configured handlers.
    Should only be called in the main process.
    """
    global _listener
    queue = _get_or_create_queue()

    if _listener is not None:
        return  # Already started

    handlers = []
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s [%(processName)s:%(threadName)s] %(name)s: %(message)s')

    if log_to_stdout:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(level)
        handlers.append(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    if extra_handlers:
        for h in extra_handlers:
            h.setFormatter(formatter)
            h.setLevel(level)
            handlers.append(h)

    _listener = QueueListener(queue, *handlers, respect_handler_level=True)
    _listener.start()


def get_logger(name: str, level=logging.DEBUG) -> logging.Logger:
    """
    Returns a logger that logs via the shared multiprocessing queue.
    Safe to use in subprocesses, threads, and coroutines.
    """
    queue = _get_or_create_queue()

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # prevent duplicate handlers
    if not any(isinstance(h, QueueHandler) for h in logger.handlers):
        logger.handlers.clear()
        qh = QueueHandler(queue)
        qh.setLevel(level)
        logger.addHandler(qh)

    return logger


def stop_listener():
    """
    Stops the background logging listener cleanly.
    """
    global _listener
    if _listener:
        _listener.stop()
        _listener = None


def set_log_level(level: int):
    """
    Dynamically change the logging level of all known loggers and handlers.
    """
    logging.getLogger().setLevel(level)

    # update all known loggers
    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)

    # update listener handlers if present
    if _listener:
        for handler in _listener.handlers:
            handler.setLevel(level)
