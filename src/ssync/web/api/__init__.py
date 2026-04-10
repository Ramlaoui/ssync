"""Route registration helpers grouped by HTTP API concern."""

from .cluster import register_cluster_routes
from .job import register_job_routes
from .launch import register_launch_routes
from .local_fs import register_local_fs_routes
from .notifications import register_notification_routes
from .status import register_status_routes
from .system import register_system_routes
from .watchers import register_watcher_routes

__all__ = [
    "register_cluster_routes",
    "register_job_routes",
    "register_launch_routes",
    "register_local_fs_routes",
    "register_notification_routes",
    "register_status_routes",
    "register_system_routes",
    "register_watcher_routes",
]
