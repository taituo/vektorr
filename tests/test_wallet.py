import os
from wallet import PaperWallet


def test_wallet_place_and_settle_win():
    w = PaperWallet({'WALLET_START': 100.0, 'STAKE': 10.0})
    w.log_file = "/dev/null"
    trade = w.place_bet("m1", 30, "OVER", 2.0, 1.95, 0.05, True)
    assert trade.filled
    assert w.balance == 90.0
    w.settle(trade, won=True)
    assert trade.outcome == "WIN"
    assert trade.pnl == (1.95 * 10) - 10  # 9.5
    assert w.balance == 90.0 + 10 + 9.5


def test_wallet_place_and_settle_loss():
    w = PaperWallet({'WALLET_START': 100.0, 'STAKE': 10.0})
    w.log_file = "/dev/null"
    trade = w.place_bet("m1", 30, "OVER", 2.0, 1.95, 0.05, True)
    w.settle(trade, won=False)
    assert trade.outcome == "LOSS"
    assert trade.pnl == -10.0
    assert w.balance == 90.0


def test_wallet_rejected():
    w = PaperWallet({'WALLET_START': 100.0, 'STAKE': 10.0})
    w.log_file = "/dev/null"
    trade = w.place_bet("m1", 30, "OVER", 2.0, None, 0.0, False)
    assert not trade.filled
    assert w.balance == 100.0


def test_wallet_summary():
    w = PaperWallet({'WALLET_START': 100.0, 'STAKE': 10.0})
    w.log_file = "/dev/null"
    t1 = w.place_bet("m1", 30, "OVER", 2.0, 1.95, 0.05, True)
    w.settle(t1, won=True)
    t2 = w.place_bet("m1", 60, "OVER", 2.0, 1.90, 0.10, True)
    w.settle(t2, won=False)
    s = w.summary()
    assert s["total_trades"] == 2
    assert s["wins"] == 1
    assert s["losses"] == 1
