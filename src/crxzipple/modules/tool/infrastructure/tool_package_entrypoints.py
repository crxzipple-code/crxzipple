from __future__ import annotations

import importlib

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def load_tool_entrypoint(entrypoint: str):
    module_name, separator, symbol_name = entrypoint.partition(":")
    module_name = module_name.strip()
    symbol_name = symbol_name.strip()
    if separator != ":" or not module_name or not symbol_name:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' must use the form 'module.path:callable_name'.",
        )
    module = importlib.import_module(module_name)
    target = getattr(module, symbol_name, None)
    if target is None:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' could not resolve callable '{symbol_name}'.",
        )
    if not callable(target):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' resolved non-callable symbol '{symbol_name}'.",
        )
    return target


__all__ = ["load_tool_entrypoint"]
