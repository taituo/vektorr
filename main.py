import time
import yaml
import logging
import json
import numpy as np
from datetime import datetime, timedelta

from engine import BettingEngine
from execution import ExecutionStub
from wallet import PaperWallet
from mock_provider import MockProvider
from schemas import MatchState

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_mvp():
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml not found. Using defaults.")
        config = {}

    engine = BettingEngine(config)
    executor = ExecutionStub(config)
    wallet = PaperWallet(config)

    match_id = "live_match_001"
    bets_in_match = 0
    max_bets = config.get('MAX_BETS_PER_MATCH', 1)
    provider = MockProvider(match_id=match_id)
    odds_history = []
    last_signal_price = None
    last_signal_time = None

    logger.info("Starting MVP Betting System (Paper Trading Mode)")
    logger.info(f"Wallet: {wallet.balance:.2f} | Stake: {wallet.stake:.2f}")

    for current_minute in range(1, 91):
        try:
            # 1. Ingest
            events, odds = provider.get_data(current_minute)

            # Log raw data for replay
            with open("events_log.jsonl", "a") as f:
                for e in events:
                    f.write(e.model_dump_json() + "\n")
            with open("odds_log.jsonl", "a") as f:
                f.write(odds.model_dump_json() + "\n")

            # 2. State
            tps = engine.calculate_tps(events)
            event_latencies = [(e.t_recv - e.t_event).total_seconds() for e in events]
            p95 = float(np.percentile(event_latencies, 95)) if event_latencies else 0.0
            odds_latency = (odds.t_recv - odds.t_seen).total_seconds()
            odds_history.append((odds.t_seen, odds.price))
            if len(odds_history) > 500:
                odds_history = odds_history[-500:]

            def _price_ago(seconds: int):
                target = odds.t_seen - timedelta(seconds=seconds)
                for ts, price in reversed(odds_history):
                    if ts <= target:
                        return price
                return None

            odds_price_prev = odds_history[-2][1] if len(odds_history) >= 2 else None
            odds_signal_age = None
            if last_signal_time:
                odds_signal_age = (datetime.now() - last_signal_time).total_seconds()

            state = MatchState(
                match_id=match_id,
                minute=current_minute,
                score=provider.score,
                tps_label=tps,
                t_event_latest=events[-1].t_event if events else datetime.now(),
                t_recv_latest=datetime.now(),
                event_latency_p95=p95,
                odds_latency_p95=odds_latency,
                odds_price_prev=odds_price_prev,
                odds_price_signal=last_signal_price,
                odds_signal_age_s=odds_signal_age,
                odds_price_5s_ago=_price_ago(5),
                odds_price_30s_ago=_price_ago(30),
                odds_price_60s_ago=_price_ago(60),
            )

            # 3. Match limit gate
            if bets_in_match >= max_bets:
                reason = "MATCH_LIMIT"
                can_bet = False
                p_model, ev = 0.0, 0.0
            else:
                can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, events)

            # 4. Execute if BET_READY
            exec_result = None
            trade = None
            if can_bet:
                exec_result = executor.execute(odds.price)
                trade = wallet.place_bet(
                    match_id=match_id,
                    minute=current_minute,
                    selection=odds.selection,
                    price_seen=odds.price,
                    price_filled=exec_result.price_filled,
                    slippage=exec_result.slippage,
                    filled=exec_result.filled,
                    p_model=p_model
                )
                if exec_result.filled:
                    bets_in_match += 1
                last_signal_price = odds.price
                last_signal_time = datetime.now()

            # 5. Audit log
            xg_10m = sum(e.xg for e in events if e.type == "SHOT")
            decision_log = {
                "timestamp": datetime.now().isoformat(),
                "match_id": match_id,
                "minute": current_minute,
                "tps": tps,
                "xg_10m": round(xg_10m, 3),
                "latency_p95": round(p95, 3),
                "can_bet": can_bet,
                "reason": reason,
                "price": round(odds.price, 3)
            }
            if exec_result:
                decision_log["execution"] = exec_result.reason
                decision_log["price_filled"] = exec_result.price_filled
                decision_log["slippage"] = exec_result.slippage
            if trade and trade.outcome in ("WIN", "LOSS"):
                decision_log["outcome"] = trade.outcome
                decision_log["pnl"] = trade.pnl

            with open("decisions.jsonl", "a") as f:
                f.write(json.dumps(decision_log) + "\n")

            # 6. Console
            if can_bet and exec_result:
                if exec_result.filled:
                    outcome_str = f" | {trade.outcome} P&L:{trade.pnl:+.2f}" if trade else ""
                    logger.info(
                        f"MIN {current_minute:2d} | BET {odds.selection} @ {odds.price:.2f} -> "
                        f"FILL @ {exec_result.price_filled:.2f} (slip:{exec_result.slippage:.3f})"
                        f"{outcome_str}"
                    )
                else:
                    logger.info(f"MIN {current_minute:2d} | BET SIGNAL but REJECTED | {odds.selection} @ {odds.price:.2f}")
            elif reason == "MATCH_LIMIT":
                pass  # silent after limit reached
            elif reason not in ("QUALITY_LOW",):
                logger.info(f"MIN {current_minute:2d} | SKIP: {reason} | TPS: {tps} | P95: {p95:.2f}s")

            time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in core loop: {e}", exc_info=True)
            time.sleep(1)

    # Settle all pending trades based on actual match outcome
    total_goals = provider.total_goals
    for trade in wallet.trades:
        if trade.outcome == "PENDING":
            # OU_2.5 market: OVER wins if total goals > 2.5
            won = total_goals >= 3
            wallet.settle(trade, won)

    logger.info(f"Final score: {provider.score} ({total_goals} goals)")

    # Match summary
    summary = wallet.summary()
    logger.info("=" * 50)
    logger.info("MATCH SUMMARY")
    logger.info(f"  Balance: {summary['balance']:.2f}")
    logger.info(f"  Trades: {summary['total_trades']} (W:{summary['wins']} L:{summary['losses']})")
    logger.info(f"  P&L: {summary['total_pnl']:+.2f} | ROI: {summary['roi_pct']:.1f}%")
    logger.info("=" * 50)


if __name__ == "__main__":
    run_mvp()
