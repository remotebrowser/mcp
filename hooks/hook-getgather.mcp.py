from __future__ import annotations

from pathlib import Path

import yaml

_yaml_path = Path(__file__).parents[1] / "getgather" / "mcp" / "mcp-tools.yaml"
with open(_yaml_path) as _f:
    _config = yaml.safe_load(_f)

# Collect all custom-brand modules that are dynamically imported in
# getgather.mcp.declarative_mcp.create_declarative_mcp_tools() via
# importlib.import_module(f"getgather.mcp.{module_name}").
# Without this, PyInstaller's static analyser cannot discover them and
# the frozen executable will fail with ModuleNotFoundError.
_hidden: list[str] = []
for _entry in _config:
    if _entry.get("custom"):
        _module_name: str = _entry.get("module") or _entry.get("id", "")
        if _module_name:
            _hidden.append(f"getgather.mcp.{_module_name}")

hiddenimports = _hidden
