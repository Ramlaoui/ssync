"""Watcher models for job monitoring."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WatcherState(Enum):
    """State of a watcher."""

    ACTIVE = "active"
    PAUSED = "paused"
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    COMPLETED = "completed"


class ActionType(Enum):
    """Built-in action types."""

    CANCEL_JOB = "cancel_job"
    RESUBMIT = "resubmit"
    NOTIFY_EMAIL = "notify_email"
    NOTIFY_SLACK = "notify_slack"
    RUN_COMMAND = "run_command"
    STORE_METRIC = "store_metric"
    PAUSE_WATCHER = "pause_watcher"
    LOG_EVENT = "log_event"


@dataclass
class WatcherAction:
    """Represents an action to take when a condition is met."""

    type: ActionType
    params: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None  # Additional condition for this action


@dataclass
class WatcherDefinition:
    """Definition of a watcher from script or config."""

    name: Optional[str] = None
    pattern: str = ""
    interval_seconds: int = 60
    captures: List[str] = field(default_factory=list)
    condition: Optional[str] = None
    actions: List[WatcherAction] = field(default_factory=list)
    max_triggers: Optional[int] = None  # Limit number of triggers
    output_type: str = "stdout"  # stdout, stderr, or both


@dataclass
class WatcherInstance:
    """Runtime instance of a watcher."""

    id: Optional[int] = None
    job_id: str = ""
    hostname: str = ""
    definition: WatcherDefinition = field(default_factory=WatcherDefinition)
    state: WatcherState = WatcherState.ACTIVE
    last_check: Optional[datetime] = None
    last_position: int = 0  # Last read position in output file
    trigger_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    variables: Dict[str, Any] = field(default_factory=dict)  # Captured variables


@dataclass
class WatcherEvent:
    """Represents a triggered watcher event."""

    id: Optional[int] = None
    watcher_id: int = 0
    job_id: str = ""
    hostname: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    matched_text: Optional[str] = None
    captured_vars: Dict[str, Any] = field(default_factory=dict)
    action_type: str = ""
    action_result: Optional[str] = None
    success: bool = False


@dataclass
class WatcherConfig:
    """Global watcher configuration."""

    enabled: bool = True
    max_watchers_per_job: int = 10
    min_interval_seconds: int = 10
    max_interval_seconds: int = 3600
    default_interval_seconds: int = 60
    max_pattern_length: int = 1000
    max_condition_length: int = 500
    max_action_params_size: int = 10000
    enable_notifications: bool = True
    notification_rate_limit: int = 10  # Max notifications per hour


@dataclass
class WatcherTemplate:
    """Reusable watcher template from config."""

    name: str
    description: Optional[str] = None
    definition: WatcherDefinition = field(default_factory=WatcherDefinition)
    tags: List[str] = field(default_factory=list)
