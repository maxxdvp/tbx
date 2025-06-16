from connectors.enums import OpSide
from ..tx_log import TxLog


if __name__ == '__main__':
    trade_stats = TxLog('trade_stats.db')

    # Adding operations
    trade_stats.add_operation(1622530800, 101, 202, 303, OpSide.BUY, 'buy_params', 100.5)
    trade_stats.add_operation(1622534400, 101, 202, 303, OpSide.SELL, 'sell_params', -50.3)

    # Get total sequential losses
    total_losses = trade_stats.get_loss_series_length(1622530800)
    print(f'Total sequential losses: {total_losses}')

    # Get total drawdown
    total_drawdown = trade_stats.get_max_drawdown(1622530800)
    print(f'Total drawdown: {total_drawdown}')

    # Close the connection
    trade_stats.close()
