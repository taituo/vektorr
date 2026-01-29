"""
Human-in-the-Loop Oversight - Phase 3

Manages approval workflows for significant system changes.

Approval Categories:
- AUTO_ALLOWED: Small changes, no approval needed
- REQUIRES_APPROVAL: Large changes need human sign-off

Notification channels:
- Telegram (primary)
- Slack (alternative)
- Email (fallback)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional
from pathlib import Path


class ApprovalStatus(Enum):
    """Status of approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class ActionType(Enum):
    """Types of actions that may need approval."""
    PARAMETER_CHANGE_SMALL = "parameter_change_small"
    PARAMETER_CHANGE_LARGE = "parameter_change_large"
    NEW_SIGNAL_PROMOTION = "new_signal_promotion"
    STAKE_INCREASE = "stake_increase"
    NEW_MARKET_TYPE = "new_market_type"
    SYSTEM_UNFREEZE = "system_unfreeze"
    SIGNAL_DEMOTION = "signal_demotion"
    EXPERIMENT_PROMOTION = "experiment_promotion"


# Actions that require human approval
REQUIRES_APPROVAL = {
    ActionType.PARAMETER_CHANGE_LARGE,
    ActionType.NEW_SIGNAL_PROMOTION,
    ActionType.STAKE_INCREASE,
    ActionType.NEW_MARKET_TYPE,
    ActionType.SYSTEM_UNFREEZE,
    ActionType.EXPERIMENT_PROMOTION,
}

# Actions that can be auto-applied
AUTO_ALLOWED = {
    ActionType.PARAMETER_CHANGE_SMALL,
    ActionType.SIGNAL_DEMOTION,
}


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: ActionType = ActionType.PARAMETER_CHANGE_SMALL
    description: str = ""
    details: Dict = field(default_factory=dict)

    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    responder: Optional[str] = None

    # Callback to execute on approval
    on_approve: Optional[Callable] = None
    on_reject: Optional[Callable] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "description": self.description,
            "details": self.details,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def to_message(self) -> str:
        """Format as human-readable message."""
        lines = [
            f"🔔 Approval Required: {self.action_type.value}",
            f"",
            f"📋 {self.description}",
            f"",
        ]

        if self.details:
            lines.append("Details:")
            for key, value in self.details.items():
                lines.append(f"  • {key}: {value}")
            lines.append("")

        lines.extend([
            f"🆔 Request ID: {self.id}",
            f"⏰ Expires: {self.expires_at.strftime('%Y-%m-%d %H:%M UTC') if self.expires_at else 'Never'}",
            f"",
            f"Reply with: /approve {self.id} or /reject {self.id}",
        ])

        return "\n".join(lines)


class NotificationChannel:
    """Base class for notification channels."""

    def send(self, message: str) -> bool:
        """Send notification. Returns True if successful."""
        raise NotImplementedError

    def receive_response(self) -> Optional[Dict]:
        """Check for responses. Returns dict with request_id and approved."""
        raise NotImplementedError


class TelegramChannel(NotificationChannel):
    """Telegram notification channel."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logging.getLogger("telegram_channel")

    def send(self, message: str) -> bool:
        """Send message via Telegram."""
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Telegram send failed: {e}")
            return False

    def receive_response(self) -> Optional[Dict]:
        """Poll for responses (simplified)."""
        # In production, would use webhooks or long polling
        return None


class ConsoleChannel(NotificationChannel):
    """Console notification for testing."""

    def __init__(self):
        self.pending_responses: List[Dict] = []
        self.logger = logging.getLogger("console_channel")

    def send(self, message: str) -> bool:
        """Print message to console."""
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return True

    def receive_response(self) -> Optional[Dict]:
        """Return queued response if any."""
        if self.pending_responses:
            return self.pending_responses.pop(0)
        return None

    def queue_response(self, request_id: str, approved: bool) -> None:
        """Queue a response for testing."""
        self.pending_responses.append({
            "request_id": request_id,
            "approved": approved,
        })


class HumanOversight:
    """
    Human-in-the-loop approval system.

    Manages approval workflows for significant changes.

    Usage:
        oversight = HumanOversight()
        oversight.set_channel(TelegramChannel(token, chat_id))

        # Request approval
        request = oversight.request_approval(
            action_type=ActionType.STAKE_INCREASE,
            description="Increase max stake from €10 to €25",
            details={"current": 10, "proposed": 25},
        )

        # Check for responses
        oversight.process_responses()

        # Or approve directly (for testing)
        oversight.approve(request.id, responder="admin")
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        default_expiry_hours: int = 24,
    ):
        self.storage_path = storage_path
        self.default_expiry_hours = default_expiry_hours

        self.requests: Dict[str, ApprovalRequest] = {}
        self.channel: Optional[NotificationChannel] = None
        self.logger = logging.getLogger("human_oversight")

        # Load pending requests from storage
        if storage_path and storage_path.exists():
            self._load_requests()

    def set_channel(self, channel: NotificationChannel) -> None:
        """Set notification channel."""
        self.channel = channel

    def request_approval(
        self,
        action_type: ActionType,
        description: str,
        details: Optional[Dict] = None,
        on_approve: Optional[Callable] = None,
        on_reject: Optional[Callable] = None,
        expiry_hours: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        Request approval for an action.

        If action is in AUTO_ALLOWED, auto-approves immediately.

        Args:
            action_type: Type of action
            description: Human-readable description
            details: Additional context
            on_approve: Callback when approved
            on_reject: Callback when rejected
            expiry_hours: Hours until request expires

        Returns:
            ApprovalRequest
        """
        request = ApprovalRequest(
            action_type=action_type,
            description=description,
            details=details or {},
            on_approve=on_approve,
            on_reject=on_reject,
        )

        # Set expiry
        hours = expiry_hours or self.default_expiry_hours
        request.expires_at = datetime.utcnow() + timedelta(hours=hours)

        # Check if auto-allowed
        if action_type in AUTO_ALLOWED:
            request.status = ApprovalStatus.AUTO_APPROVED
            self.logger.info(f"Auto-approved: {action_type.value} - {description}")
            if on_approve:
                on_approve()
            return request

        # Store and notify
        self.requests[request.id] = request
        self._save_requests()

        self.logger.info(f"Approval requested: {request.id} - {action_type.value}")

        # Send notification
        if self.channel:
            self.channel.send(request.to_message())

        return request

    def approve(
        self,
        request_id: str,
        responder: str = "unknown",
    ) -> bool:
        """
        Approve a pending request.

        Args:
            request_id: Request ID
            responder: Who approved

        Returns:
            True if approved successfully
        """
        if request_id not in self.requests:
            self.logger.warning(f"Request not found: {request_id}")
            return False

        request = self.requests[request_id]

        if request.status != ApprovalStatus.PENDING:
            self.logger.warning(f"Request not pending: {request_id} ({request.status})")
            return False

        request.status = ApprovalStatus.APPROVED
        request.responded_at = datetime.utcnow()
        request.responder = responder

        self.logger.info(f"Approved by {responder}: {request_id}")

        # Execute callback
        if request.on_approve:
            try:
                request.on_approve()
            except Exception as e:
                self.logger.error(f"Approval callback failed: {e}")

        self._save_requests()
        return True

    def reject(
        self,
        request_id: str,
        responder: str = "unknown",
        reason: str = "",
    ) -> bool:
        """
        Reject a pending request.

        Args:
            request_id: Request ID
            responder: Who rejected
            reason: Optional rejection reason

        Returns:
            True if rejected successfully
        """
        if request_id not in self.requests:
            self.logger.warning(f"Request not found: {request_id}")
            return False

        request = self.requests[request_id]

        if request.status != ApprovalStatus.PENDING:
            self.logger.warning(f"Request not pending: {request_id}")
            return False

        request.status = ApprovalStatus.REJECTED
        request.responded_at = datetime.utcnow()
        request.responder = responder
        request.details["rejection_reason"] = reason

        self.logger.info(f"Rejected by {responder}: {request_id}")

        # Execute callback
        if request.on_reject:
            try:
                request.on_reject()
            except Exception as e:
                self.logger.error(f"Rejection callback failed: {e}")

        self._save_requests()
        return True

    def process_responses(self) -> int:
        """
        Check for and process any responses from notification channel.

        Returns:
            Number of responses processed
        """
        if not self.channel:
            return 0

        processed = 0

        while True:
            response = self.channel.receive_response()
            if not response:
                break

            request_id = response.get("request_id")
            approved = response.get("approved", False)
            responder = response.get("responder", "channel")

            if approved:
                self.approve(request_id, responder)
            else:
                self.reject(request_id, responder, response.get("reason", ""))

            processed += 1

        return processed

    def check_expirations(self) -> int:
        """
        Check for and expire old requests.

        Returns:
            Number of requests expired
        """
        now = datetime.utcnow()
        expired = 0

        for request in self.requests.values():
            if request.status == ApprovalStatus.PENDING:
                if request.expires_at and now > request.expires_at:
                    request.status = ApprovalStatus.EXPIRED
                    self.logger.warning(f"Request expired: {request.id}")
                    expired += 1

        if expired:
            self._save_requests()

        return expired

    def get_pending(self) -> List[ApprovalRequest]:
        """Get all pending requests."""
        return [
            r for r in self.requests.values()
            if r.status == ApprovalStatus.PENDING
        ]

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get request by ID."""
        return self.requests.get(request_id)

    def requires_approval(self, action_type: ActionType) -> bool:
        """Check if action type requires approval."""
        return action_type in REQUIRES_APPROVAL

    def _save_requests(self) -> None:
        """Persist requests to storage."""
        if not self.storage_path:
            return

        data = {
            rid: {
                **r.to_dict(),
                "responded_at": r.responded_at.isoformat() if r.responded_at else None,
                "responder": r.responder,
            }
            for rid, r in self.requests.items()
        }

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_requests(self) -> None:
        """Load requests from storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            for rid, rdata in data.items():
                request = ApprovalRequest(
                    id=rid,
                    action_type=ActionType(rdata["action_type"]),
                    description=rdata["description"],
                    details=rdata.get("details", {}),
                    status=ApprovalStatus(rdata["status"]),
                    created_at=datetime.fromisoformat(rdata["created_at"]),
                )
                if rdata.get("expires_at"):
                    request.expires_at = datetime.fromisoformat(rdata["expires_at"])
                if rdata.get("responded_at"):
                    request.responded_at = datetime.fromisoformat(rdata["responded_at"])
                request.responder = rdata.get("responder")

                self.requests[rid] = request

            self.logger.info(f"Loaded {len(self.requests)} approval requests")
        except Exception as e:
            self.logger.error(f"Failed to load requests: {e}")


# Convenience functions
def check_requires_approval(action_type: str) -> bool:
    """Check if action type string requires approval."""
    try:
        at = ActionType(action_type)
        return at in REQUIRES_APPROVAL
    except ValueError:
        return True  # Unknown actions require approval


def format_approval_message(
    action: str,
    description: str,
    details: Dict,
) -> str:
    """Format a simple approval message."""
    request = ApprovalRequest(
        action_type=ActionType.PARAMETER_CHANGE_LARGE,
        description=description,
        details=details,
    )
    return request.to_message()
