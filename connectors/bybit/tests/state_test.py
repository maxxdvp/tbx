import time
from pprint import pprint
import keyring

# from connectors import enums
from connectors.enums import ConnMode
from connectors.bybit.state import TradingState as BBTS


api_key = keyring.get_password("TB-ByBit-Test", "API_KEY")
api_secret = keyring.get_password("TB-ByBit-Test", "API_SECRET")

mode = ConnMode.TESTNET

bbts = BBTS(api_key, api_secret, mode)


# try:
#     print("\nbbts.get_assets():")
#     assets = bbts.get_assets()
#     pprint(assets, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_funds():")
#     funds = bbts.get_funds()
#     pprint(funds, width=120)
# except Exception as e:
#     print(e)
#todo: debug
# try:
#     print("\nbbts.get_options():")
#     options = bbts.get_options()
#     pprint(options, width=120)
# except Exception as e:
#     print(e)

##### ASSET INFO #####

#todo: debug
# try:
#     print("\nbbts.get_asset_info('SOLUSDT'):")
#     info = bbts.get_asset_info("SOLUSDT")
#     pprint(info, width=120)
# except Exception as e:
#     print(e)

##### HISTORIC PRICES #####

#todo: debug
# try:
#     print("\nbbts.get_price_history(enums.MarketType.SPOT, 'BTCUSDT', 5, 64):")
#     start = time.perf_counter()
#     prices = bbts.get_price_history(enums.MarketType.SPOT, "BTCUSDT", 5, 64)
#     end = time.perf_counter()
#     pprint(prices, width=200)
#     print(f"{len(prices)} rows; execution time: {end - start:.6f} s")
#
#     print("\nbbts.get_price_history(enums.MarketType.SPOT, 'BTCUSDT', 60, 8766):")  # 1h for 1 year
#     start = time.perf_counter()
#     prices = bbts.get_price_history(enums.MarketType.SPOT, "BTCUSDT", 60, 8766)
#     end = time.perf_counter()
#     pprint(prices, width=200)
#     print(f"{len(prices)} rows; execution time: {end - start:.6f} s")
#
#     print("\nbbts.get_price_history(enums.MarketType.SPOT, 'BTCUSDT', 5, 105192):")  # 5m for 1 year
#     start = time.perf_counter()
#     prices = bbts.get_price_history(enums.MarketType.SPOT, "BTCUSDT", 5, 105192)
#     end = time.perf_counter()
#     pprint(prices, width=200)
#     print(f"{len(prices)} rows; execution time: {end - start:.6f} s")
# except Exception as e:
#     print(e)

##### POSITIONS #####

# try:
#     print("\nbbts.get_positions(enums.MarketType.FUTURE, base_asset='USDT'):")
#     positions = bbts.get_positions(enums.MarketType.FUTURE, base_asset="USDT")
#     pprint(positions, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_positions(enums.MarketType.FUTURE, base_asset='USDC'):")
#     positions = bbts.get_positions(enums.MarketType.FUTURE, base_asset="USDC")
#     pprint(positions, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_positions(enums.MarketType.FUTURE, asset='SOLUSDT'):")
#     positions = bbts.get_positions(enums.MarketType.FUTURE, asset="SOLUSDT")
#     pprint(positions, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_positions(enums.MarketType.FUTURE, asset='SOLUSDC'):")
#     positions = bbts.get_positions(enums.MarketType.FUTURE, asset="SOLUSDC")
#     pprint(positions, width=120)
# except Exception as e:
#     print(e)
#todo: test options
# try:
#     print("\nbbts.get_positions(enums.MarketType.OPTION, base_asset='SOLUSDT'):")
#     positions = bbts.get_positions(enums.MarketType.OPTION, asset="SOLUSDT")
#     pprint(positions, width=120)
# except Exception as e:
#     print(e)

##### ORDERS #####

# try:
#     print("\nbbts.get_orders(enums.MarketType.SPOT):")
#     orders = bbts.get_orders(enums.MarketType.SPOT)
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_orders(enums.MarketType.SPOT, base_asset='USDT'):")
#     orders = bbts.get_orders(enums.MarketType.SPOT, base_asset="USDT")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_orders(enums.MarketType.SPOT, base_asset='USDC'):")
#     orders = bbts.get_orders(enums.MarketType.SPOT, base_asset="USDC")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_orders(enums.MarketType.SPOT, asset='SOLUSDT'):")
#     orders = bbts.get_orders(enums.MarketType.SPOT, asset="SOLUSDT")
#     pprint(orders, width=120)
# except Exception as e:
#     pprint(e)
# try:
#     print("\nbbts.get_orders(enums.MarketType.SPOT, asset='ETHUSDC'):")
#     orders = bbts.get_orders(enums.MarketType.SPOT, asset="ETHUSDC")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
#todo: test futures
# try:
#     print("\nbbts.get_orders(enums.MarketType.FUTURE, asset='ETHUSDC'):")
#     orders = bbts.get_orders(enums.MarketType.FUTURE, asset="ETHUSDC")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
#todo: test options
# try:
#     print("\nbbts.get_orders(enums.MarketType.OPTION, asset='ETHUSDC'):")
#     orders = bbts.get_orders(enums.MarketType.OPTION, asset="ETHUSDC")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)

##### TX HISTORY #####

# try:
#     print("\nbbts.get_tx_history(enums.MarketType.FUTURE):")
#     orders = bbts.get_tx_history(enums.MarketType.FUTURE)
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_tx_history(enums.MarketType.FUTURE, asset='SOLUSDT'):")
#     orders = bbts.get_tx_history(enums.MarketType.FUTURE, asset="SOLUSDT")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_tx_history(enums.MarketType.FUTURE, asset='SOLUSDC'):")
#     orders = bbts.get_tx_history(enums.MarketType.FUTURE, asset="SOLUSDC")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_tx_history(enums.MarketType.FUTURE, base_asset='SOL'):")
#     orders = bbts.get_tx_history(enums.MarketType.FUTURE, base_asset="SOL")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)

##### ORDER HISTORY #####

# try:
#     print("\nbbts.get_order_history(enums.MarketType.SPOT):")
#     orders = bbts.get_order_history(enums.MarketType.SPOT)
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_order_history(enums.MarketType.SPOT, status='Filled'):")
#     orders = bbts.get_order_history(enums.MarketType.SPOT, status="Filled")
#     # orders = bbts.get_order_history(enums.MarketType.SPOT, status="PartiallyFilledCanceled")
#     # orders = bbts.get_order_history(enums.MarketType.SPOT, status="PartiallyFilled")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_order_history(enums.MarketType.SPOT, base_asset='USDT'):")
#     orders = bbts.get_order_history(enums.MarketType.SPOT, base_asset="SOL")
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
# try:
#     print("\nbbts.get_order_history(enums.MarketType.FUTURE):")
#     orders = bbts.get_order_history(enums.MarketType.FUTURE)
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)

##### FUTURES PNLS #####

# try:
#     print("\nbbts.get_futures_pnl_history(enums.MarketType.FUTURE):")
#     orders = bbts.get_futures_pnl_history(enums.MarketType.FUTURE)
#     pprint(orders, width=120)
# except Exception as e:
#     print(e)
