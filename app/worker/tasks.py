from __future__ import annotations

from celery import shared_task


@shared_task(name="worker.ping")
def ping() -> dict[str, str]:
    """Small health task used to validate worker wiring."""
    return {"status": "ok"}
