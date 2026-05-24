from importlib import import_module

__all__ = ["SlurmManager", "SyncManager", "Host", "SlurmHost", "config"]

_LAZY_EXPORTS = {
    "SlurmManager": ("ssync.manager", "SlurmManager"),
    "SyncManager": ("ssync.sync", "SyncManager"),
    "Host": ("ssync.models.cluster", "Host"),
    "SlurmHost": ("ssync.models.cluster", "SlurmHost"),
    "config": ("ssync.utils.config", "config"),
}


def __getattr__(name):
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
