"""One-shot session cleanup entry point for the Container Apps cron job."""
import json
import time

from service.jobs import JobQueue
from service.sessions import delete_session, expired, purge_orphans
from service.settings import Settings


def main() -> int:
    settings = Settings()
    queue = JobQueue(settings)
    deleted = 0
    for sid in expired(settings, time.time()):
        delete_session(settings, queue, sid)
        deleted += 1
    result = {"sessions": deleted, **purge_orphans(settings, time.time())}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
