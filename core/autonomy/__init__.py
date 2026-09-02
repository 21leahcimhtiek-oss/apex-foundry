"""Autonomy stack — self-running agent cycles on the Memory Vault."""

from core.autonomy.engine import AUTONOMY_TAG, AutonomyEngine
from core.autonomy.intent import EVENT_TAG, IntentRouter, UnknownIntentError
from core.autonomy.scheduler import MaintenanceScheduler

__all__ = [
    "AUTONOMY_TAG",
    "EVENT_TAG",
    "AutonomyEngine",
    "IntentRouter",
    "MaintenanceScheduler",
    "UnknownIntentError",
]