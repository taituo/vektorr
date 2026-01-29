"""
Base Agent - Phase 3

Foundation class for all Vektorr agents.

Agents are autonomous workers that:
- Have their own state and lifecycle
- Communicate via messages
- Can be started/stopped independently
- Report health metrics
"""

import time
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from queue import Queue, Empty
import threading


class AgentState(Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentMessage:
    """Message for inter-agent communication."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str = ""
    recipient: str = ""  # Empty = broadcast
    type: str = "info"  # info, request, response, alert
    payload: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: int = 0  # Higher = more urgent

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
        }


@dataclass
class AgentHealth:
    """Agent health metrics."""
    agent_id: str
    state: AgentState
    last_heartbeat: datetime
    uptime_seconds: float
    errors_count: int
    messages_processed: int
    last_error: Optional[str] = None


class BaseAgent(ABC):
    """
    Base class for all Vektorr agents.

    Subclasses must implement:
    - process(): Main processing logic
    - on_message(): Handle incoming messages

    Usage:
        class MyAgent(BaseAgent):
            def process(self):
                # Do work
                pass

            def on_message(self, msg):
                # Handle message
                pass

        agent = MyAgent("my_agent")
        agent.start()
    """

    def __init__(
        self,
        agent_id: str,
        config: Optional[Dict] = None,
        message_bus: Optional['MessageBus'] = None,
    ):
        self.agent_id = agent_id
        self.config = config or {}
        self.message_bus = message_bus

        self.state = AgentState.IDLE
        self.started_at: Optional[datetime] = None
        self.errors_count = 0
        self.messages_processed = 0
        self.last_error: Optional[str] = None

        self._inbox: Queue = Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.logger = logging.getLogger(f"agent.{agent_id}")

    @abstractmethod
    def process(self) -> None:
        """
        Main processing logic. Called periodically when running.
        Override in subclass.
        """
        pass

    @abstractmethod
    def on_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        Handle incoming message.
        Override in subclass.

        Returns:
            Optional response message
        """
        pass

    def start(self, blocking: bool = False) -> None:
        """Start the agent."""
        if self.state == AgentState.RUNNING:
            self.logger.warning(f"Agent {self.agent_id} already running")
            return

        self.state = AgentState.RUNNING
        self.started_at = datetime.utcnow()
        self._stop_event.clear()

        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

        self.logger.info(f"Agent {self.agent_id} started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the agent gracefully."""
        self.logger.info(f"Stopping agent {self.agent_id}")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self.state = AgentState.STOPPED
        self.logger.info(f"Agent {self.agent_id} stopped")

    def pause(self) -> None:
        """Pause the agent."""
        if self.state == AgentState.RUNNING:
            self.state = AgentState.PAUSED
            self.logger.info(f"Agent {self.agent_id} paused")

    def resume(self) -> None:
        """Resume paused agent."""
        if self.state == AgentState.PAUSED:
            self.state = AgentState.RUNNING
            self.logger.info(f"Agent {self.agent_id} resumed")

    def send_message(self, message: AgentMessage) -> None:
        """Send message to another agent or broadcast."""
        message.sender = self.agent_id
        if self.message_bus:
            self.message_bus.publish(message)
        else:
            self.logger.warning(f"No message bus, cannot send: {message}")

    def receive_message(self, message: AgentMessage) -> None:
        """Receive message (called by message bus)."""
        self._inbox.put(message)

    def get_health(self) -> AgentHealth:
        """Get agent health metrics."""
        uptime = 0.0
        if self.started_at:
            uptime = (datetime.utcnow() - self.started_at).total_seconds()

        return AgentHealth(
            agent_id=self.agent_id,
            state=self.state,
            last_heartbeat=datetime.utcnow(),
            uptime_seconds=uptime,
            errors_count=self.errors_count,
            messages_processed=self.messages_processed,
            last_error=self.last_error,
        )

    def _run_loop(self) -> None:
        """Main agent loop."""
        interval = self.config.get("process_interval", 1.0)

        while not self._stop_event.is_set():
            try:
                # Process incoming messages
                self._process_inbox()

                # Run main processing if not paused
                if self.state == AgentState.RUNNING:
                    self.process()

            except Exception as e:
                self.errors_count += 1
                self.last_error = str(e)
                self.logger.error(f"Agent {self.agent_id} error: {e}")

                if self.errors_count > self.config.get("max_errors", 10):
                    self.state = AgentState.ERROR
                    self.logger.critical(f"Agent {self.agent_id} entering error state")
                    break

            # Sleep between iterations
            self._stop_event.wait(timeout=interval)

    def _process_inbox(self) -> None:
        """Process all messages in inbox."""
        while True:
            try:
                message = self._inbox.get_nowait()
                self.messages_processed += 1

                response = self.on_message(message)
                if response:
                    response.recipient = message.sender
                    self.send_message(response)

            except Empty:
                break


class MessageBus:
    """
    Simple message bus for inter-agent communication.

    Usage:
        bus = MessageBus()
        bus.register(agent1)
        bus.register(agent2)

        agent1.send_message(AgentMessage(recipient="agent2", ...))
    """

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.logger = logging.getLogger("message_bus")

    def register(self, agent: BaseAgent) -> None:
        """Register an agent with the bus."""
        self.agents[agent.agent_id] = agent
        agent.message_bus = self
        self.logger.info(f"Registered agent: {agent.agent_id}")

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self.agents:
            self.agents[agent_id].message_bus = None
            del self.agents[agent_id]
            self.logger.info(f"Unregistered agent: {agent_id}")

    def subscribe(self, message_type: str, callback: Callable) -> None:
        """Subscribe to message type."""
        if message_type not in self.subscribers:
            self.subscribers[message_type] = []
        self.subscribers[message_type].append(callback)

    def publish(self, message: AgentMessage) -> None:
        """Publish message to recipient or broadcast."""
        if message.recipient:
            # Direct message
            if message.recipient in self.agents:
                self.agents[message.recipient].receive_message(message)
            else:
                self.logger.warning(f"Unknown recipient: {message.recipient}")
        else:
            # Broadcast to all agents (except sender)
            for agent_id, agent in self.agents.items():
                if agent_id != message.sender:
                    agent.receive_message(message)

        # Notify subscribers
        if message.type in self.subscribers:
            for callback in self.subscribers[message.type]:
                try:
                    callback(message)
                except Exception as e:
                    self.logger.error(f"Subscriber error: {e}")

    def get_all_health(self) -> Dict[str, AgentHealth]:
        """Get health of all agents."""
        return {
            agent_id: agent.get_health()
            for agent_id, agent in self.agents.items()
        }
