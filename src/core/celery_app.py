from celery import Celery
from core.config_manager import ConfigManager

# Ensure configuration is loaded
ConfigManager.load()

# Initialize Celery app
celery_app = Celery("ledger_alpha")

# Configure Celery from ConfigManager
celery_app.conf.update(
    broker_url=ConfigManager.get_str("celery.broker_url", "redis://localhost:6379/0"),
    result_backend=ConfigManager.get_str("celery.result_backend", "redis://localhost:6379/1"),
    timezone=ConfigManager.get_str("celery.timezone", "UTC"),
    enable_utc=ConfigManager.get_bool("celery.enable_utc", True),
    task_track_started=ConfigManager.get_bool("celery.task_track_started", True),
    task_time_limit=ConfigManager.get_int("celery.task_time_limit", 300),
)

# Auto-discover tasks from all registered modules
# This assumes that tasks are defined in files like `src/accounting/tasks.py`
# You may need to manually register modules if auto-discovery doesn't work as expected with your directory structure
celery_app.autodiscover_tasks([
    "api.api_tasks",
    # Add other modules with tasks here in the future, e.g.:
    # "accounting.tasks",
    # "accounting.report_tasks",
])

if __name__ == "__main__":
    celery_app.start()
