__all__ = ["app", "create_app", "run"]


def __getattr__(name: str):
    if name in __all__:
        from crxzipple.interfaces.http.app import app, create_app, run

        return {"app": app, "create_app": create_app, "run": run}[name]
    raise AttributeError(name)
