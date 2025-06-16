from datetime import datetime, timedelta, UTC

from log import mplog
from agent.tx_log import TxLog


class MoneyGuard:
    def __init__(self, params: dict, tx_log: TxLog):
        self.log = mplog.get_logger("MoneyGuard")

        # restore settings
        self.max_drawdown_limit = float(params["max_drawdown_limit"])
        self.loss_series_len_limit = int(params["loss_series_len_limit"])
        self.limits_period_h = int(params["limits_period_h"])

        # restore stats
        self.tx_log = tx_log
        self.max_drawdown = 0.
        self.loss_series_len = 0
        self.agent_allowance = (True, "", 0)
        self.update_agent_allowance()

    def get_now_ts(self) -> int:
        now = datetime.now(UTC)
        new_time = now - timedelta(hours=self.limits_period_h)
        return int(new_time.timestamp() * 1000)

    def verify_agent(self) -> (bool, str, float):
        if self.max_drawdown:
            if self.max_drawdown >= self.max_drawdown_limit:
                self.log.error(f"Trade is disallowed: drawdown {self.max_drawdown} above limit {self.max_drawdown_limit}")
                return False, "drawdown", self.max_drawdown
        if self.loss_series_len:
            if self.loss_series_len >= self.loss_series_len_limit:
                self.log.error(f"Trade is disallowed: loss series {self.loss_series_len} above limit {self.loss_series_len_limit}")
                return False, "losses", self.loss_series_len
        return True, "", 0.

    def update_agent_allowance(self) -> bool:
        try:
            from_ts = self.get_now_ts()
            self.max_drawdown = self.tx_log.get_max_drawdown(from_ts)
            self.loss_series_len = self.tx_log.get_loss_series_length(from_ts)
            self.agent_allowance = self.verify_agent()
            return self.agent_allowance[0]
        except Exception as e:
            self.log.error(e, exc_info=True)
        return False

    async def trade_allowed(self) -> bool:
        return self.agent_allowance[0]

    async def trade_disallowance_reason(self) -> str | None:
        if not self.agent_allowance[0]:
            return f"Tx from agent not allowed: {self.agent_allowance[1]} limit exceeded: {self.agent_allowance[2]}"
        return None
