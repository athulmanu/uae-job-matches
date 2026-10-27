from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (ROOT / "config.yaml")
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def all_target_roles(cfg: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for group in cfg.get("target_roles", {}).values():
        roles.extend(group)
    # preserve order, drop dupes
    seen: set[str] = set()
    out: list[str] = []
    for r in roles:
        key = r.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
