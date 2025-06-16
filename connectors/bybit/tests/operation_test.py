import asyncio
import time
import keyring

from connectors.bybit.common import ConnMode
from connectors.bybit.operation import TradingOperation as BBTO


api_key = keyring.get_password("TB-ByBit-Test", "API_KEY")
api_secret = keyring.get_password("TB-ByBit-Test", "API_SECRET")

bbto = BBTO(api_key, api_secret, ConnMode.DEMO)

'''
https://testnet.bybit.com/user/assets/home/overview
https://testnet.bybit.com/en/trade/spot/BTC/USDT
'''


##### MARKET PRICES #####

# try:
#     print("\nbbto.get_market_prices(BBTO.AssetClass.spot, []):")
#     prices = bbto.get_market_prices(BBTO.AssetClass.spot, [])
#     print(prices)
# except Exception as e:
#     print(e)


##### SPOT ORDERS #####

# # spot market buy + sell
# try:
#     print("\nbbto.send_spot_order(market=True, asset='BTCUSDT', amount=0.0001)")
#     order_id = bbto.send_spot_order(market=True, asset="BTCUSDT", amount=0.0001)
#     print(order_id)
#     print("\nbbto.send_spot_order(market=True, asset='BTCUSDT', amount=-0.0001)")
#     order_id = bbto.send_spot_order(market=True, asset="BTCUSDT", amount=-0.0001)
#     print(order_id)
# except Exception as e:
#     print(e)

# # spot limit buy + sell
# try:
#     print("\nbbto.get_market_prices(BBTO.AssetClass.spot, ['BTCUSDT']):")
#     prices = bbto.get_market_prices(BBTO.AssetClass.spot, ["BTCUSDT"])
#     print(prices)
#     price = prices["BTCUSDT"]["last_price"]
#     print("\nbbto.send_spot_order(market=False, asset='BTCUSDT', amount=0.0001, price=price)")
#     order_id = bbto.send_spot_order(market=False, asset="BTCUSDT", amount=0.0001, price=price)
#     print(order_id)
#     print("\nbbto.send_spot_order(market=False, asset='BTCUSDT', amount=-0.0001, price=price)")
#     order_id = bbto.send_spot_order(market=False, asset="BTCUSDT", amount=-0.0001, price=price)
#     print(order_id)
# except Exception as e:
#     print(e)

# # spot market buy + set tp/sl (+/- 0.5%)
# try:
#     print("\nbbto.get_market_prices(BBTO.AssetClass.spot, ['BTCUSDT']):")
#     prices = bbto.get_market_prices(BBTO.AssetClass.spot, ["BTCUSDT"])
#     print(prices)
#     price = prices["BTCUSDT"]["last_price"]
#     # print("\nbbto.send_spot_order(market=True, asset='BTCUSDT', amount=0.0001)")
#     # order_id = bbto.send_spot_order(market=True, asset="BTCUSDT", amount=0.0001)
#     # print(order_id)
#     print("\nbbto.send_spot_order(asset='BTCUSDT', amount=0.0001, tp=price*1.005, sl=price*0.995)")
#     order_id = bbto.place_spot_tpsl(asset="BTCUSDT", amount=0.0001, tp=round_up(price * 1.005, 2), sl=round_up(price * 0.995, 2))
#     print(order_id)
# except Exception as e:
#     print(e)


##### FUTURE ORDERS #####

# future market buy + sell
async def main():
    try:
        print("open long\nbbto.place_future_order(market=True, asset='SOLUSDT', amount=0.1)")
        order_id = await bbto.place_future_order(market=True, asset="SOLUSDT", value=0.1)
        print(order_id)

        # print("close long\nbbto.send_future_order(market=True, asset='SOLUSDT', amount=-0.1, close=True)")
        # order_id = bbto.place_future_order(market=True, asset="SOLUSDT", amount=-0.1, close=True)
        # print(order_id)

        time.sleep(1)

        print("open short\nbbto.place_future_order(market=True, asset='SOLUSDT', amount=-0.2)")
        order_id = await bbto.place_future_order(market=True, asset="SOLUSDT", value=-0.2)
        print(order_id)

        time.sleep(1)

        print("close short\nbbto.send_future_order(market=True, asset='SOLUSDT', amount=0.1, close=True)")
        order_id = await bbto.place_future_order(market=True, asset="SOLUSDT", value=0.1, close=True)
        print(order_id)
    except Exception as e:
        print(e)

asyncio.run(main())


#todo: ##### OPTION ORDERS #####
