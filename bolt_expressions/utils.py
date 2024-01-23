from typing import Any, Dict

from beet import Context
from bolt import Runtime

__all__ = [
    "type_name",
    "identifier_generator",
]


def type_name(obj: Any) -> str:
    return type(obj).__name__


def identifier_generator(ctx: Context | None = None):
    if ctx:
        runtime = ctx.inject(Runtime)
        incr: Dict[str, int] = {}

        while True:
            path = runtime.modules.current_path
            incr[path] = incr.setdefault(path, -1) + 1

            yield ctx.generate.format(f"{{hash}}_{incr[path]}", path)
    else:
        counter = 0
        while True:
            yield str(f"i{counter}")
