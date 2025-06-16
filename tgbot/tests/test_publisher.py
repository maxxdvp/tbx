import zmq
import time

from constants import msg_queue
from proto.tgbot_pb2 import TGBotMsg, TxNotice, AgentError
from connectors.enums import Provider, MarketType, OpSide, OpType


if __name__ == "__main__":
    context = None
    out_socket = None

    try:
        context = zmq.Context()

        out_socket = context.socket(zmq.PUSH)
        out_socket.setsockopt(zmq.SNDHWM, 1000)
        out_socket.connect(msg_queue.TGBOT_SOCKET)
        time.sleep(0.1)

        for i in range(1, 6, 2):
            try:
                notice = TxNotice(provider=Provider.BYBIT.value, market=MarketType.FUTURE.value, ticker="BTCUSDT", op_side=OpSide.BUY.value, op_type=OpType.NON_AUTO.value,
                                  value=str(0.01), value_base=str(999.99), price=str(99999.99), fee=str(0.55), pnl=f"P&L={0.}", ts_ms=int(time.time() * 1000))
                msg = TGBotMsg(rid=i, tx_notice=notice)
                out_socket.send(msg.SerializeToString(), zmq.DONTWAIT)

                notice = TxNotice(provider=Provider.BYBIT.value, market=MarketType.FUTURE.value, ticker="BTCUSDT", op_side=OpSide.SELL.value, op_type=OpType.TAKE_PROFIT.value,
                                  value=str(0.01), value_base=str(1009.99), price=str(100999.99), fee=str(0.55), pnl=f"P&L={10.0}", ts_ms=int(time.time() * 1000))
                msg = TGBotMsg(rid=i + 1, tx_notice=notice)
                out_socket.send(msg.SerializeToString(), zmq.DONTWAIT)
            except zmq.Again:
                #todo: handle full buffer: log, drop, save to disk
                print("The message not delivered")

        error = AgentError(ts_ms=int(time.time() * 1000), source="AgentService", message="Connection closed by host.", details="")
        msg = TGBotMsg(rid=7, agent_error=error)
        out_socket.send(msg.SerializeToString(), zmq.DONTWAIT)

    except Exception as e:
        print(f"error: {e}")

    if out_socket:
        out_socket.disconnect(msg_queue.TGBOT_SOCKET)
        out_socket.close()
