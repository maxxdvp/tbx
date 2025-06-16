import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from decimal import Decimal

import yaml
import keyring

import zmq
import zmq.asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message

from log import mplog
import logging

from constants import msg_queue
from proto.tgbot_pb2 import TGBotMsg
from google.protobuf.message import DecodeError
from connectors.enums import Provider, MarketType, OpSide, OpType


USERS_FILE = "users.txt"
SUBSCRIBERS_FILE = "subscribers.json"


def ts_ms2str(ts_ms: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000.0)
        return dt.strftime('%Y.%m.%d %H:%M:%S.%f')[:-3]
    except Exception as e:
        raise ValueError(f"Failed to convert ts_ms={ts_ms} to string") from e


def load_users():
    log = mplog.get_logger("Load Users")
    if not os.path.exists(USERS_FILE):
        log.info(f"No {USERS_FILE} found; no users allowed.")
        return set()
    try:
        with open(USERS_FILE, "r") as f:
            return set(int(line.strip()) for line in f if line.strip().isdigit())
    except Exception as e:
        log.error(f"{e}; no users allowed", exc_info=True)
        return set()


def load_subscribers():
    log = mplog.get_logger("Load Subscribers")
    if not os.path.exists(SUBSCRIBERS_FILE):
        log.info(f"No {SUBSCRIBERS_FILE} found; no subscribers.")
        return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return set(json.load(f))
    except Exception as e:
        log.error(f"No {e} found; no subscribers.", exc_info=True)
        return set()


def save_subscribers():
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subscribers), f)
    log.info(f"{SUBSCRIBERS_FILE} updated.")


async def q_listener():
    log = mplog.get_logger("Queue Listener")

    ctx = None
    in_socket = None

    try:
        log.info("starting...")

        ctx = zmq.asyncio.Context()
        in_socket = ctx.socket(zmq.PULL)
        in_socket.setsockopt(zmq.SNDHWM, 1000)
        try:
            in_socket.bind(msg_queue.TGBOT_SOCKET)
        except zmq.ZMQError as e:
            log.error(f"Socket bind failed: {e}")
            return

        log.info(f"awaiting for queue messages on: {msg_queue.TGBOT_SOCKET}")

        # create a poller to monitor the socket
        poller = zmq.Poller()
        poller.register(in_socket, zmq.POLLIN)

        data = b""
        while True:
            try:
                events = dict(poller.poll(timeout=1000))  # in ms
                if in_socket in events and events[in_socket] == zmq.POLLIN:
                    try:
                        data = await in_socket.recv(zmq.NOBLOCK)
                    except zmq.Again:
                        continue  # no message to read, continue polling
                    except Exception as e:
                        log.error(e, exc_info=True)
                else:
                    continue  #todo: idle handling, heartbeat, etc.

                log.debug(f"Message received from the queue: {data}")
                msg = TGBotMsg()
                msg.ParseFromString(data)

                text = ""
                if msg.HasField("tx_notice"):
                    tx = msg.tx_notice
                    bullet = ""
                    fee = Decimal(tx.fee)
                    pnl = Decimal(tx.pnl)
                    if pnl != -fee:
                        if pnl > 0:
                            bullet = "🙂"  # "▲"
                        elif pnl < 0:
                            bullet = "🫥"  # "▼"
                    text = (f"{bullet} <b>Tx:</b> {ts_ms2str(tx.ts_ms)}<code>"
                            f"\n{Provider(tx.provider).name}/{MarketType(tx.market).name}"
                            f"\n{tx.ticker} {OpSide(tx.op_side).name} {OpType(tx.op_type).name}"
                            f"\n{Decimal(tx.value)}/{Decimal(tx.value_base)} @ {Decimal(tx.price)}"
                            f"\nfee {fee} : {f"pnl {pnl} : " if pnl else ""}{tx.status}</code>")
                elif msg.HasField("agent_error"):
                    err = msg.agent_error
                    bullet = ""
                    match err.level:
                        case logging.INFO:
                            bullet = "ℹ️"
                        case logging.DEBUG:
                            bullet = "⚙️"
                        case logging.WARNING:
                            bullet = "⚠️"
                        case logging.ERROR:
                            bullet = "🚫"
                        case logging.CRITICAL:
                            bullet = "☠️"
                    # text = (f"{bullet} <b>({msg.rid}):</b> {ts_ms2str(err.ts_ms)}"
                    text = (f"{bullet}: {ts_ms2str(err.ts_ms)}"
                            f"\n{err.source}"
                            f"\n{err.message}{"\n<code>" + err.details + "</code>" if err.details else ""}")

                for user_id in list(subscribers):
                    try:
                        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
                    except Exception as e:
                        log.error(f"Error sending to {user_id}: {e}", exc_info=True)
            except DecodeError as e:
                log.warning(f"Failed to decode incoming message: {e}, raw data: {data[:20]!r}")
                continue
            except Exception as e:
                log.warning(e, exc_info=True)
                continue

            await asyncio.sleep(0.1)

    except Exception as e:
        log.error(e, exc_info=True)
    finally:
        in_socket.disconnect(msg_queue.TGBOT_SOCKET)
        in_socket.close()
        ctx.term()
        log.info("stopped")


async def main():
    global allowed_users, subscribers
    allowed_users = load_users()
    subscribers = load_subscribers()

    await asyncio.gather(dp.start_polling(bot), q_listener(),)


if __name__ == "__main__":
    mplog.setup_listener(log_file="tgbot.log", log_to_stdout=True)
    log = mplog.get_logger("Main")

    with open("./params.yml", "r+") as f:
        params = yaml.safe_load(f)
        f.close()
    keyring_service = params["keyring_service"]
    debug_level = params["debug_level"]
    mplog.set_log_level(getattr(logging, debug_level))

    bot_token = keyring.get_password(keyring_service, "BOT_TOKEN")

    bot = Bot(token=bot_token)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def handle_start(msg: Message):
        chat_id = msg.chat.id  # msg.from_user.id
        if chat_id not in allowed_users:
            await msg.answer(f"🚫 You're not authorized to use this bot. id:{chat_id}")
            return

        if chat_id not in subscribers:
            subscribers.add(chat_id)
            save_subscribers()
            await msg.answer("✅ Subscribed to agent trade notifications!")
        else:
            await msg.answer("📡 You're already subscribed.")

    @dp.message(Command("stop"))
    async def handle_stop(msg: Message):
        chat_id = msg.chat.id
        if chat_id not in allowed_users:
            await msg.answer("🚫 You're not authorized to use this bot.")
            return

        if chat_id in subscribers:
            subscribers.remove(chat_id)
            save_subscribers()
            await msg.answer("❌ Unsubscribed from notifications.")
        else:
            await msg.answer("ℹ️ You're not currently subscribed.")

    def cleanup_and_exit(signum=None, frame_t=None):
        log.info(f"Caught termination signal {signum}")
        mplog.stop_listener()
        sys.exit(0)

    # register termination signal handlers
    # signal.signal(signal.SIGKILL, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    signal.signal(signal.SIGINT, cleanup_and_exit)
    # signal.signal(signal.SIGHUP, cleanup_and_exit)
    # signal.signal(signal.SIGQUIT, cleanup_and_exit)

    try:
        allowed_users = set()
        subscribers = set()

        asyncio.run(main())
    except Exception as e:
        log.error(e, exc_info=True)
    finally:
        cleanup_and_exit()
