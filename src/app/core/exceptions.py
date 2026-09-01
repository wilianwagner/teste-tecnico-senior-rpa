class AppError(Exception):
    """Base class for application errors."""


class JobNotFoundError(AppError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} not found")
        self.job_id = job_id


class CrawlerError(AppError):
    """Raised when a crawler fails to collect data from its source."""


class PublishError(AppError):
    """Raised when a message cannot be published to the broker."""
