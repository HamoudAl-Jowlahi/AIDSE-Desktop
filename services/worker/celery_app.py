"""
AIDSE Platform — Celery Application Factory
Section 12.1 (services/worker), Section 8.1 (Async Layer)

All long-running and CPU-intensive work runs here, never in the
request/response cycle (Section 8.1 architecture requirement).

Phase 0: Scaffold only — no tasks yet.
Phase 1 adds: evaluation_tasks.py
Phase 3 adds: profiling_tasks.py
Phase 4 adds: training_tasks.py
"""
from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "aidse",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        # Phase 0: no tasks yet — add modules here as phases progress
        # "services.worker.tasks.evaluation_tasks",   # Phase 1
        # "services.worker.tasks.profiling_tasks",    # Phase 3
        "services.worker.tasks.training_tasks",     # Phase 4
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true",
    # Reliability (Section 8.3): tasks must be idempotent and retry-safe
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,
    # Queues
    task_default_queue="default",
    task_queues={
        "default": {},
        "evaluation": {},   # High-priority: eval runs
        "profiling": {},
        "training": {},
    },
    # Result expiry
    result_expires=3600,  # 1 hour
    # Timezone
    timezone="UTC",
    enable_utc=True,
)
