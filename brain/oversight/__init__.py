"""
Vektorr Oversight - Phase 3

Human-in-the-loop approval system.

- HumanOversight: Approval workflow
- ApprovalRequest: Pending approval items
- NotificationChannel: Telegram/Slack integration
"""

from .human_loop import HumanOversight, ApprovalRequest, ApprovalStatus, ActionType

__all__ = [
    "HumanOversight",
    "ApprovalRequest",
    "ApprovalStatus",
    "ActionType",
]
