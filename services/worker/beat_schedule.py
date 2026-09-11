"""Celery Beat scheduler — Phase 0 placeholder. Tasks added in later phases."""
from __future__ import annotations

from celery.schedules import crontab  # noqa: F401 — imported for Phase 1+ use

# Beat schedule populated in Phase 1+
# Example (Phase 2+):
# CELERYBEAT_SCHEDULE = {
#     "scheduled-evaluation-runs": {
#         "task": "services.worker.tasks.evaluation_tasks.run_scheduled_evaluations",
#         "schedule": crontab(minute="*/5"),
#     },
# }
CELERYBEAT_SCHEDULE: dict = {}
