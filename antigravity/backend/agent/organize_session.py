"""病例整理会话存储。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .tools_sandbox import PathJail


def _now() -> float:
    return time.time()


@dataclass
class OrganizeSession:
    id: str
    work_path: str
    out_path: str
    project_id: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    tool_log: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "idle"  # idle | running | done | error
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    meta_dir: str = ""

    def jail(self) -> PathJail:
        return PathJail([Path(self.work_path), Path(self.out_path)])

    def touch(self):
        self.updated_at = _now()

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "work_path": self.work_path,
            "out_path": self.out_path,
            "project_id": self.project_id,
            "status": self.status,
            "message_count": len(self.messages),
            "has_plan": bool(self.plan),
            "plan_summary": {
                "patient_count": (self.plan or {}).get("patient_count"),
                "file_count": (self.plan or {}).get("file_count"),
                "needs_confirm": (self.plan or {}).get("needs_confirm"),
                "patients": (self.plan or {}).get("patients") or [],
            } if self.plan else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def save(self, root: Path):
        d = root / self.id
        d.mkdir(parents=True, exist_ok=True)
        self.meta_dir = str(d)
        (d / "session.json").write_text(
            json.dumps({
                "id": self.id,
                "work_path": self.work_path,
                "out_path": self.out_path,
                "project_id": self.project_id,
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "plan": self.plan,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with (d / "messages.jsonl").open("w", encoding="utf-8") as fh:
            for m in self.messages:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        with (d / "tool_log.jsonl").open("w", encoding="utf-8") as fh:
            for t in self.tool_log:
                fh.write(json.dumps(t, ensure_ascii=False) + "\n")


class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, OrganizeSession] = {}

    def create(self, work_path: str, out_path: str, project_id: str = "", persist_root: Optional[Path] = None) -> OrganizeSession:
        work = Path(work_path).expanduser().resolve()
        out = Path(out_path).expanduser().resolve()
        if not work.exists():
            raise ValueError(f"工作目录不存在: {work}")
        out.mkdir(parents=True, exist_ok=True)
        sid = uuid.uuid4().hex[:12]
        sess = OrganizeSession(
            id=sid,
            work_path=str(work),
            out_path=str(out),
            project_id=project_id or "",
        )
        sess.messages.append({
            "role": "system",
            "content": "session_created",
            "ts": _now(),
        })
        self._sessions[sid] = sess
        if persist_root:
            sess.save(persist_root)
        return sess

    def get(self, session_id: str) -> Optional[OrganizeSession]:
        return self._sessions.get(session_id)

    def all(self) -> List[OrganizeSession]:
        return list(self._sessions.values())


session_store = SessionStore()
