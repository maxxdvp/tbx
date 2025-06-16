'''
Transaction log
'''

import sqlite3
from decimal import Decimal

from connectors.enums import OpSide, OpType, MarketType, Provider


class TxLog:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.create_table()

    def create_table(self):
        query = """
            CREATE TABLE IF NOT EXISTS trades (
                timestamp INTEGER NOT NULL,
                provider INTEGER NOT NULL, 
                market INTEGER NOT NULL, 
                ticker TEXT NOT NULL,
                value DECIMAL NOT NULL, 
                price REAL NOT NULL, 
                op_side INTEGER NOT NULL, 
                op_type INTEGER NOT NULL, 
                fee REAL NOT NULL 
            );"""
        self.conn.execute(query)
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(timestamp);')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_provider ON trades(provider);')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_market ON trades(market);')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_ticker ON trades(ticker);')
        self.conn.commit()

    # pnl includes all current fees
    def add_operation(self, ts_ms: int, provider: Provider, market: MarketType, ticker: str, value: Decimal, price: Decimal,
                      op_side: OpSide, op_type: OpType, fee: Decimal) -> None:
        # print(ts_ms) #dbg
        query = """INSERT INTO trades (timestamp, provider, market, ticker, value, price, op_side, op_type, fee)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"""
        self.conn.execute(query, (ts_ms, provider.value, market.value, ticker, float(value), float(price), op_side.value, op_type.value, float(fee)))
        self.conn.commit()

    # returns 0 when db is empty
    def get_last_record_ts(self) -> int:
        query = "SELECT COALESCE(MAX(timestamp), 0) FROM trades;"
        cursor = self.conn.execute(query)
        return cursor.fetchone()[0]

    def get_loss_series_length(self, from_ts_ms: int) -> int:
        # 1 = BUY → cash outflow
        # 2 = SELL → cash inflow
        query = """
            WITH trades_cte AS (
                SELECT timestamp,
                       CASE op_side
                            WHEN 1 THEN -value * price - fee
                            WHEN 2 THEN value * price - fee
                            ELSE 0.0
                       END AS equity_change
                FROM trades
                WHERE timestamp >= ?
                ORDER BY timestamp
            ),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (ORDER BY timestamp) AS row_num
                FROM trades_cte
            ),
            loss_grouping AS (
                SELECT *,
                       row_num - ROW_NUMBER() OVER (
                           PARTITION BY CASE WHEN equity_change < 0 THEN 1 ELSE 0 END
                           ORDER BY timestamp
                       ) AS grp
                FROM ranked
            ),
            last_loss_group AS (
                SELECT grp
                FROM loss_grouping
                WHERE equity_change < 0
                ORDER BY timestamp DESC
                LIMIT 1
            )
            SELECT COUNT(*)
            FROM loss_grouping
            WHERE equity_change < 0
              AND grp = (SELECT grp FROM last_loss_group);
        """
        cursor = self.conn.execute(query, (from_ts_ms,))
        return cursor.fetchone()[0]

    def get_max_drawdown(self, from_ts_ms: int) -> float:
        query = """
            WITH trades_cte AS (
                SELECT timestamp,
                       CASE op_side
                            WHEN 1 THEN -value * price - fee
                            WHEN 2 THEN  value * price - fee
                            ELSE 0.0
                       END AS equity_change
                FROM trades
                WHERE timestamp >= ?
                  AND op_side IN (1, 2)
                ORDER BY timestamp
            ),
            equity_curve AS (
                SELECT
                    t1.timestamp,
                    SUM(t2.equity_change) AS equity
                FROM trades_cte t1
                JOIN trades_cte t2 ON t2.timestamp <= t1.timestamp
                GROUP BY t1.timestamp
            ),
            peak_curve AS (
                SELECT ec1.timestamp,
                       ec1.equity,
                       MAX(ec2.equity) AS peak
                FROM equity_curve ec1
                JOIN equity_curve ec2 ON ec2.timestamp <= ec1.timestamp
                GROUP BY ec1.timestamp
            )
            SELECT COALESCE(MAX((peak - equity) / NULLIF(peak, 0)), 0.0) AS max_drawdown
            FROM peak_curve;
        """
        cursor = self.conn.execute(query, (from_ts_ms,))
        return cursor.fetchone()[0]

    def get_total_pnl(self, from_ts_ms: int) -> float:
        # 1 = BUY → cash outflow
        # 2 = SELL → cash inflow
        query = """
            SELECT COALESCE(SUM(
                CASE op_side
                    WHEN 1 THEN -value * price - fee
                    WHEN 2 THEN  value * price - fee
                    ELSE 0.0
                END
            ), 0.0) AS total_pnl
            FROM trades
            WHERE timestamp >= ?
              AND op_side IN (1, 2);
        """
        cursor = self.conn.execute(query, (from_ts_ms,))
        return cursor.fetchone()[0]

    def close(self):
        self.conn.close()
