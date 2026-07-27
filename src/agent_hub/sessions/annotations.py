"""会话注释：用户标记、忽略状态、跟进标签等本地元数据。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SessionAnnotation(BaseModel):
    """会话注释模型：保存用户对会话的本地标记。"""

    session_id: str
    ignored: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    follow_up: bool = False


class SessionAnnotationStore:
    """会话注释持久化存储。"""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        if storage_path is None:
            storage_path = Path.home() / ".agenthub" / "session_annotations.json"
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._annotations: dict[str, SessionAnnotation] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载注释数据。"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._annotations = {
                key: SessionAnnotation.model_validate(value) for key, value in data.items()
            }
        except (json.JSONDecodeError, ValueError):
            self._annotations = {}

    def _save(self) -> None:
        """保存注释数据到文件。"""
        data = {key: value.model_dump() for key, value in self._annotations.items()}
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, session_id: str) -> SessionAnnotation:
        """获取会话注释，不存在则返回默认值。"""
        if session_id not in self._annotations:
            self._annotations[session_id] = SessionAnnotation(session_id=session_id)
        return self._annotations[session_id]

    def is_ignored(self, session_id: str) -> bool:
        """检查会话是否被忽略。"""
        return self.get(session_id).ignored

    def set_ignored(self, session_id: str, ignored: bool) -> None:
        """设置会话的忽略状态。"""
        annotation = self.get(session_id)
        annotation.ignored = ignored
        self._save()

    def set_follow_up(self, session_id: str, follow_up: bool) -> None:
        """设置会话的跟进标记。"""
        annotation = self.get(session_id)
        annotation.follow_up = follow_up
        self._save()

    def add_tag(self, session_id: str, tag: str) -> None:
        """为会话添加标签。"""
        annotation = self.get(session_id)
        if tag not in annotation.tags:
            annotation.tags.append(tag)
            self._save()

    def remove_tag(self, session_id: str, tag: str) -> None:
        """移除会话标签。"""
        annotation = self.get(session_id)
        if tag in annotation.tags:
            annotation.tags.remove(tag)
            self._save()

    def set_notes(self, session_id: str, notes: str) -> None:
        """设置会话备注。"""
        annotation = self.get(session_id)
        annotation.notes = notes
        self._save()

    def list_all(self) -> dict[str, SessionAnnotation]:
        """列出所有注释。"""
        return dict(self._annotations)
