from execution import ExecutionStub


def test_execution_fill():
    stub = ExecutionStub({'REJECT_RATE': 0.0, 'MAX_SLIPPAGE': 0.05})
    result = stub.execute(2.10)
    assert result.filled is True
    assert result.price_filled <= 2.10
    assert result.price_filled >= 1.01
    assert result.reason == "FILLED"


def test_execution_reject():
    stub = ExecutionStub({'REJECT_RATE': 1.0})
    result = stub.execute(2.10)
    assert result.filled is False
    assert result.price_filled is None
    assert result.reason == "REJECTED"


def test_execution_slippage_bounded():
    stub = ExecutionStub({'REJECT_RATE': 0.0, 'MAX_SLIPPAGE': 0.10})
    for _ in range(50):
        result = stub.execute(2.00)
        assert result.slippage <= 0.10
        assert result.price_filled >= 1.01
