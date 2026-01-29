"""
Vektorr Telegram Bot - Health & Alert Notifications

Sends periodic health updates and instant alerts to Telegram.

Usage:
    # Set environment variables
    export TELEGRAM_BOT_TOKEN="your-bot-token"
    export TELEGRAM_CHAT_ID="your-chat-id"

    # Run bot
    python tools/telegram_bot.py

    # Or import and use programmatically
    from tools.telegram_bot import TelegramNotifier
    notifier = TelegramNotifier(token, chat_id)
    notifier.send_message("Hello!")
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("telegram_bot")


@dataclass
class BotConfig:
    """Telegram bot configuration."""
    token: str
    chat_id: str
    brain_url: str = "http://localhost:8000"
    health_interval_s: int = 900  # 15 minutes
    alert_on_freeze: bool = True
    alert_on_bet: bool = False
    daily_summary_hour: int = 22


class TelegramNotifier:
    """
    Send notifications to Telegram.

    Setup:
    1. Create bot with @BotFather, get token
    2. Add bot to group or start chat
    3. Get chat_id from https://api.telegram.org/bot<TOKEN>/getUpdates
    """

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def send_alert(self, level: str, title: str, message: str) -> bool:
        """Send formatted alert message."""
        emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(level, "📢")

        text = f"{emoji} <b>{title}</b>\n\n{message}"
        return self.send_message(text)

    def send_health_update(self, status: Dict) -> bool:
        """Send health status update."""
        wallet = status.get("bankroll", {}).get("current", "?")
        stage = status.get("system", {}).get("stage", "?")
        state = status.get("system", {}).get("state", "?")

        emoji = "✅" if state == "running" else "🛑"

        text = f"""
{emoji} <b>Vektorr Status</b>

💰 Wallet: <b>€{wallet:.2f}</b>
🎯 Stage: {stage}
⚡ State: {state}

📊 Metrics:
• Fill rate: {status.get('metrics', {}).get('fill_rate', 'N/A')}
• Latency: {status.get('metrics', {}).get('avg_latency_ms', 'N/A')}ms
• Losses streak: {status.get('metrics', {}).get('consecutive_losses', 0)}

🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        """.strip()

        return self.send_message(text)

    def send_daily_summary(self, metrics: Dict) -> bool:
        """Send daily performance summary."""
        text = f"""
📊 <b>Daily Summary</b>

Decisions: {metrics.get('total_decisions', 0)}
Bets: {metrics.get('total_bets', 0)}
Bet rate: {metrics.get('bet_rate', 0):.1%}

💵 P&L: €{metrics.get('total_pnl', 0):.2f}
📈 ROI: {metrics.get('roi', 0):.2%} if metrics.get('roi') else 'N/A'

CLV Mean: {metrics.get('clv_mean', 'N/A')}
CLV Positive: {metrics.get('clv_positive_pct', 'N/A')}

<b>Gate Breakdown:</b>
{format_gates(metrics.get('reasons', {}))}
        """.strip()

        return self.send_message(text)


def format_gates(reasons: Dict) -> str:
    """Format gate statistics for display."""
    if not reasons:
        return "No data"

    lines = []
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1])[:8]:
        lines.append(f"• {reason}: {count}")
    return "\n".join(lines)


class VektorrBot:
    """
    Main bot that monitors Vektorr and sends notifications.
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.notifier = TelegramNotifier(config.token, config.chat_id)
        self._last_health_check = 0
        self._last_daily_summary = None
        self._last_state = "unknown"

    def fetch_status(self) -> Optional[Dict]:
        """Fetch status from Brain API."""
        try:
            url = f"{self.config.brain_url}/kill_switch/status"
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"Failed to fetch status: {e}")
            return None

    def fetch_metrics(self) -> Optional[Dict]:
        """Fetch metrics from Brain API."""
        try:
            url = f"{self.config.brain_url}/metrics"
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"Failed to fetch metrics: {e}")
            return None

    def check_and_alert(self) -> None:
        """Check status and send alerts if needed."""
        status = self.fetch_status()
        if not status:
            return

        ks_status = status.get("status", {})
        current_state = ks_status.get("state", "unknown")

        # Alert on state change
        if current_state != self._last_state:
            if current_state == "frozen" and self.config.alert_on_freeze:
                reason = ks_status.get("frozen_reason", {})
                self.notifier.send_alert(
                    "critical",
                    "SYSTEM FROZEN",
                    f"Reason: {reason.get('message', 'Unknown')}\n"
                    f"Trigger: {reason.get('trigger', 'Unknown')}"
                )
            elif current_state == "running" and self._last_state == "frozen":
                self.notifier.send_alert(
                    "info",
                    "System Resumed",
                    "Vektorr is back online."
                )

            self._last_state = current_state

    def send_periodic_health(self) -> None:
        """Send periodic health update."""
        now = time.time()

        if now - self._last_health_check < self.config.health_interval_s:
            return

        status = self.fetch_status()
        if status:
            # Build status dict for send_health_update
            ks_status = status.get("status", {})
            metrics = status.get("metrics", {})

            health_data = {
                "system": {
                    "state": ks_status.get("state", "unknown"),
                    "stage": "live",  # Would need to fetch from rollout
                },
                "bankroll": {
                    "current": metrics.get("bankroll", 0) if metrics else 0,
                },
                "metrics": {
                    "fill_rate": f"{metrics.get('fill_rate', 0):.1%}" if metrics else "N/A",
                    "avg_latency_ms": metrics.get("avg_latency_ms", 0) if metrics else 0,
                    "consecutive_losses": metrics.get("consecutive_losses", 0) if metrics else 0,
                },
            }

            self.notifier.send_health_update(health_data)
            self._last_health_check = now
            logger.info("Sent health update")

    def send_daily_summary_if_needed(self) -> None:
        """Send daily summary at configured hour."""
        now = datetime.utcnow()

        if self._last_daily_summary and self._last_daily_summary.date() == now.date():
            return  # Already sent today

        if now.hour != self.config.daily_summary_hour:
            return

        metrics = self.fetch_metrics()
        if metrics:
            self.notifier.send_daily_summary(metrics)
            self._last_daily_summary = now
            logger.info("Sent daily summary")

    def run(self) -> None:
        """Run the bot loop."""
        logger.info("Starting Vektorr Telegram Bot")
        self.notifier.send_message("🤖 Vektorr Bot started")

        while True:
            try:
                self.check_and_alert()
                self.send_periodic_health()
                self.send_daily_summary_if_needed()
            except Exception as e:
                logger.error(f"Bot error: {e}")

            time.sleep(60)  # Check every minute


def main():
    parser = argparse.ArgumentParser(description="Vektorr Telegram Bot")
    parser.add_argument("--token", default=os.getenv("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_CHAT_ID"))
    parser.add_argument("--brain-url", default="http://localhost:8000")
    parser.add_argument("--interval", type=int, default=900, help="Health check interval (seconds)")
    parser.add_argument("--test", action="store_true", help="Send test message and exit")

    args = parser.parse_args()

    if not args.token or not args.chat_id:
        print("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")
        print("Set via environment variables or --token/--chat-id flags")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    if args.test:
        notifier = TelegramNotifier(args.token, args.chat_id)
        success = notifier.send_message("🧪 Test message from Vektorr Bot")
        print("Test message sent!" if success else "Failed to send test message")
        return

    config = BotConfig(
        token=args.token,
        chat_id=args.chat_id,
        brain_url=args.brain_url,
        health_interval_s=args.interval,
    )

    bot = VektorrBot(config)
    bot.run()


if __name__ == "__main__":
    main()
