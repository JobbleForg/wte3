from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SESSION_VERSION = 1


@dataclass
class SessionTreeNode:
    name: str
    kind: str
    children: list["SessionTreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionTreeNode":
        return cls(
            name=str(payload.get("name", "")).strip(),
            kind=str(payload.get("kind", "group")).strip() or "group",
            children=[
                cls.from_dict(child)
                for child in payload.get("children", [])
                if isinstance(child, dict)
            ],
        )


@dataclass
class WorkspaceSession:
    version: int = SESSION_VERSION
    hierarchy: list[SessionTreeNode] = field(default_factory=list)
    imported_tags: list[str] = field(default_factory=list)
    trend_state: dict[str, Any] = field(default_factory=dict)
    legend_state: dict[str, Any] = field(default_factory=dict)
    analytics_state: dict[str, Any] = field(default_factory=dict)
    settings_state: dict[str, Any] = field(default_factory=dict)
    ui_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "hierarchy": [node.to_dict() for node in self.hierarchy],
            "imported_tags": list(self.imported_tags),
            "trend_state": dict(self.trend_state),
            "legend_state": dict(self.legend_state),
            "analytics_state": dict(self.analytics_state),
            "settings_state": dict(self.settings_state),
            "ui_state": dict(self.ui_state),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceSession":
        imported_tags = [
            str(tag).strip()
            for tag in payload.get("imported_tags", [])
            if str(tag).strip()
        ]
        return cls(
            version=int(payload.get("version", SESSION_VERSION)),
            hierarchy=[
                SessionTreeNode.from_dict(node)
                for node in payload.get("hierarchy", [])
                if isinstance(node, dict)
            ],
            imported_tags=imported_tags,
            trend_state=dict(payload.get("trend_state", {})),
            legend_state=dict(payload.get("legend_state", {})),
            analytics_state=dict(payload.get("analytics_state", {})),
            settings_state=dict(payload.get("settings_state", {})),
            ui_state=dict(payload.get("ui_state", {})),
        )


class SessionStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else self.default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_base_dir() -> Path:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "WTE Trend Viewer" / "sessions"

    @property
    def last_session_path(self) -> Path:
        return self.base_dir / "last-session.json"

    def load(self, path: str | Path) -> WorkspaceSession:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Session file must contain a JSON object.")
        return WorkspaceSession.from_dict(payload)

    def save(self, session: WorkspaceSession, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(target.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        temp_path.replace(target)
        return target

    def load_last_session(self) -> WorkspaceSession:
        return self.load(self.last_session_path)

    def save_last_session(self, session: WorkspaceSession) -> Path:
        return self.save(session, self.last_session_path)
