"""Running a job, wherever it runs.

The API serves HTTP and the Celery worker consumes a queue; neither should
own what a job actually *is*. That lives here, so the two deployments run
identical code and a trace produced inline is indistinguishable from one
produced on a worker.
"""

from . import runner, service

__all__ = ["runner", "service"]
