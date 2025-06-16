import asyncio
import keyring

from connectors.enums import MarketType
from connectors.bybit.common import ConnMode
from connectors.bybit.feeding import FeedingMarket as BBFM
from connectors.bybit.feeding_acc import FeedingAccount as BBFA

from pprint import pprint


# api_key = keyring.get_password("TB-ByBit-Test", "API_KEY")
# api_secret = keyring.get_password("TB-ByBit-Test", "API_SECRET")
api_key = keyring.get_password("TB-ByBit-Demo", "API_KEY")
api_secret = keyring.get_password("TB-ByBit-Demo", "API_SECRET")


async def qfeeder(q: asyncio.Queue):
    try:
        # print("\nBBFM(MarketType.SPOT, q, ConnMode.TESTNET):")
        # bbfm = BBFM(MarketType.SPOT, q, ConnMode.TESTNET)
        # print("\nbbfm.start_feed('SOLUSDC', 1, proc_msg_market):")
        # bbfm.start_feed("SOLUSDC", 1)

        # print("\nBBFM(MarketType.FUTURE, q, ConnMode.TESTNET):")
        # bbfm = BBFM(MarketType.FUTURE, q, ConnMode.TESTNET)
        # print("\nbbfm.start_feed('BTCUSDT', 1, proc_msg_market):")
        # bbfm.start_feed("BTCUSDT", 1)

        print("\nBBFM(MarketType.FUTURE, q, ConnMode.DEMO):")
        bbfm = BBFM(MarketType.FUTURE, q, ConnMode.DEMO)
        print("\nbbfm.start_feed('BTCUSDT', 1, proc_msg_market):")
        bbfm.start_feed("BTCUSDT", 1)
    except Exception as e:
        print("[ERROR]", e)

async def qhandler(q: asyncio.Queue):
    while True:
        data = await q.get()
        pprint(data)

# async def qfeeder(q: asyncio.Queue):
#     try:
#         print("\nBBFA(api_key, api_secret, q, test=True):")
#         bbfa = BBFA(api_key, api_secret, q, test=True)
#         print("\nbbfa.start_feed_tx():")
#         await asyncio.to_thread(bbfa.start_feed_tx)
#     except Exception as e:
#         print("[ERROR]", e)
#
# async def qhandler(q: asyncio.Queue):
#     while True:
#         data = await q.get()
#         pprint(data)

async def main():
    q = asyncio.Queue()
    asyncio.create_task(qhandler(q))
    asyncio.create_task(qfeeder(q))
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
