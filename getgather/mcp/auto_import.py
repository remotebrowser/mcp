import importlib
import importlib.util
import inspect
import pkgutil
import re
import sys
from typing import Any

from getgather.mcp.registry import GatherMCP


def has_mcp_class(module: Any) -> bool:
    """Check if a module contains a class that inherits from GatherMCP."""
    for _, obj in inspect.getmembers(module):
        if inspect.isclass(obj):
            try:
                if issubclass(obj, GatherMCP):
                    return True
            except TypeError:
                # Skip if obj cannot be used with issubclass
                continue
    return False


def check_module_source_for_mcp(module_name: str) -> bool:
    """
    Check heuristically if a module might contain MCP classes by examining its source.
    """
    try:
        module_spec = importlib.util.find_spec(module_name)
        if not module_spec or not module_spec.origin:
            return False
        if not module_spec.origin.endswith(".py"):
            return False

        # Check for GatherMCP usage (e.g. "import GatherMCP" or "from ... import AppUIConfig, GatherMCP")
        with open(module_spec.origin, "r") as f:
            source = f.read()
        return bool(re.search(r"import\s+.*GatherMCP", source))

    except Exception:
        # If we can't check the source, assume it might have an MCP class
        return True


def auto_import(package_name: str):
    package = __import__(package_name, fromlist=["dummy"])
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        full_module_name = f"{package_name}.{module_name}"

        if check_module_source_for_mcp(full_module_name):
            module = importlib.import_module(full_module_name)
            if not has_mcp_class(module):
                if full_module_name in sys.modules:
                    del sys.modules[full_module_name]
