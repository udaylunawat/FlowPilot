import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ui_bot.models import (
    AgentAction,
    FeedbackCreate,
    LocationCreate,
    SavedLocation,
    StoredFeedback,
    WorkflowRun,
    WorkflowTemplate,
)


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        self._conn.executescript("""
            create table if not exists sessions (
                id text primary key,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );
            create table if not exists messages (
                id integer primary key autoincrement,
                session_id text not null,
                role text not null,
                content text not null,
                created_at text not null default current_timestamp
            );
            create table if not exists page_snapshots (
                id integer primary key autoincrement,
                session_id text not null,
                url text not null,
                title text not null,
                payload text not null,
                created_at text not null default current_timestamp
            );
            create table if not exists locations (
                id integer primary key autoincrement,
                session_id text not null,
                name text not null,
                url text not null,
                title text not null,
                notes text not null,
                metadata text not null,
                created_at text not null default current_timestamp
            );
            create table if not exists workflow_runs (
                id text primary key,
                session_id text not null,
                goal text not null,
                status text not null default 'running',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );
            create table if not exists workflow_steps (
                id integer primary key autoincrement,
                trace_id text not null,
                session_id text not null,
                action_type text not null,
                action_payload text not null,
                result text not null default '',
                url text not null default '',
                title text not null default '',
                created_at text not null default current_timestamp
            );
            create table if not exists human_feedback (
                id integer primary key autoincrement,
                session_id text not null,
                trace_id text,
                kind text not null,
                target_action text not null,
                url text not null default '',
                page_title text not null default '',
                comment text not null default '',
                correction text not null,
                created_at text not null default current_timestamp
            );
            create table if not exists workflow_templates (
                id integer primary key autoincrement,
                kind text not null,
                page_url_pattern text not null,
                field_label text not null default '',
                selector text not null default '',
                action text not null default '',
                confidence real not null default 1.0,
                uses integer not null default 0,
                metadata text not null,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                unique(kind, page_url_pattern, field_label, selector, action)
            );
            """)
        self._conn.commit()

    def upsert_session(self, session_id: str) -> None:
        self._conn.execute(
            """
            insert into sessions (id) values (?)
            on conflict(id) do update set updated_at = current_timestamp
            """,
            (session_id,),
        )
        self._conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.upsert_session(session_id)
        self._conn.execute(
            "insert into messages (session_id, role, content) values (?, ?, ?)",
            (session_id, role, content),
        )
        self._conn.commit()

    def add_snapshot(
        self, session_id: str, url: str, title: str, payload: dict[str, Any]
    ) -> None:
        self.upsert_session(session_id)
        self._conn.execute(
            """
            insert into page_snapshots (session_id, url, title, payload)
            values (?, ?, ?, ?)
            """,
            (session_id, url, title, json.dumps(payload)),
        )
        self._conn.commit()

    def start_workflow_run(self, trace_id: str, session_id: str, goal: str) -> None:
        self.upsert_session(session_id)
        self._conn.execute(
            """
            insert into workflow_runs (id, session_id, goal, status)
            values (?, ?, ?, 'running')
            on conflict(id) do update set
                goal = excluded.goal,
                updated_at = current_timestamp
            """,
            (trace_id, session_id, goal),
        )
        self._conn.commit()

    def finish_workflow_run(self, trace_id: str, status: str) -> None:
        self._conn.execute(
            """
            update workflow_runs
            set status = ?, updated_at = current_timestamp
            where id = ?
            """,
            (status, trace_id),
        )
        self._conn.commit()

    def add_workflow_step(
        self,
        trace_id: str,
        session_id: str,
        action: AgentAction,
        *,
        result: str = "",
        url: str = "",
        title: str = "",
    ) -> None:
        self._conn.execute(
            """
            insert into workflow_steps (
                trace_id, session_id, action_type, action_payload, result, url, title
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                session_id,
                action.type,
                action.model_dump_json(),
                result,
                url,
                title,
            ),
        )
        self._conn.commit()

    def list_workflow_runs(self, session_id: str | None = None) -> list[WorkflowRun]:
        if session_id:
            rows = self._conn.execute(
                """
                select * from workflow_runs
                where session_id = ?
                order by created_at desc
                """,
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "select * from workflow_runs order by created_at desc"
            ).fetchall()
        return [self._workflow_run_from_row(row) for row in rows]

    def add_feedback(self, feedback: FeedbackCreate) -> StoredFeedback:
        cursor = self._conn.execute(
            """
            insert into human_feedback (
                session_id, trace_id, kind, target_action, url, page_title,
                comment, correction
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback.session_id,
                feedback.trace_id,
                feedback.kind,
                (
                    feedback.target_action.model_dump_json()
                    if feedback.target_action
                    else "{}"
                ),
                feedback.url,
                feedback.page_title,
                feedback.comment,
                json.dumps(feedback.correction),
            ),
        )
        if feedback.kind == "correct" and feedback.promote_to_template:
            self._promote_feedback_template(feedback)
        self._conn.commit()
        row = self._conn.execute(
            "select * from human_feedback where id = ?", (cursor.lastrowid,)
        ).fetchone()
        return self._feedback_from_row(row)

    def list_feedback(self, session_id: str | None = None) -> list[StoredFeedback]:
        if session_id:
            rows = self._conn.execute(
                """
                select * from human_feedback
                where session_id = ?
                order by id desc
                """,
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "select * from human_feedback order by id desc"
            ).fetchall()
        return [self._feedback_from_row(row) for row in rows]

    def list_templates(self, url: str | None = None) -> list[WorkflowTemplate]:
        rows = self._conn.execute(
            "select * from workflow_templates order by updated_at desc"
        ).fetchall()
        templates = [self._template_from_row(row) for row in rows]
        if url is None:
            return templates
        return [
            template
            for template in templates
            if _url_matches_pattern(url, template.page_url_pattern)
        ]

    def increment_template_use(self, template_id: int) -> None:
        self._conn.execute(
            """
            update workflow_templates
            set uses = uses + 1, updated_at = current_timestamp
            where id = ?
            """,
            (template_id,),
        )
        self._conn.commit()

    def save_location(self, location: LocationCreate) -> SavedLocation:
        self.upsert_session(location.session_id)
        cursor = self._conn.execute(
            """
            insert into locations (session_id, name, url, title, notes, metadata)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                location.session_id,
                location.name,
                location.url,
                location.title,
                location.notes,
                json.dumps(location.metadata),
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "select * from locations where id = ?", (cursor.lastrowid,)
        ).fetchone()
        return self._location_from_row(row)

    def list_locations(self, session_id: str | None = None) -> list[SavedLocation]:
        if session_id:
            rows: Iterable[sqlite3.Row] = self._conn.execute(
                "select * from locations where session_id = ? order by id desc",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "select * from locations order by id desc"
            ).fetchall()
        return [self._location_from_row(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _location_from_row(row: sqlite3.Row) -> SavedLocation:
        return SavedLocation(
            id=row["id"],
            session_id=row["session_id"],
            name=row["name"],
            url=row["url"],
            title=row["title"],
            notes=row["notes"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _workflow_run_from_row(row: sqlite3.Row) -> WorkflowRun:
        return WorkflowRun(
            id=row["id"],
            session_id=row["session_id"],
            goal=row["goal"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _feedback_from_row(row: sqlite3.Row) -> StoredFeedback:
        target_action = json.loads(row["target_action"])
        return StoredFeedback(
            id=row["id"],
            session_id=row["session_id"],
            trace_id=row["trace_id"],
            kind=row["kind"],
            target_action=AgentAction(**target_action) if target_action else None,
            url=row["url"],
            page_title=row["page_title"],
            comment=row["comment"],
            correction=json.loads(row["correction"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _template_from_row(row: sqlite3.Row) -> WorkflowTemplate:
        return WorkflowTemplate(
            id=row["id"],
            kind=row["kind"],
            page_url_pattern=row["page_url_pattern"],
            field_label=row["field_label"],
            selector=row["selector"],
            action=row["action"],
            confidence=row["confidence"],
            uses=row["uses"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _promote_feedback_template(self, feedback: FeedbackCreate) -> None:
        correction = feedback.correction
        kind = str(correction.get("kind") or "")
        if kind != "field_selector":
            return
        field_label = str(correction.get("field_label") or "").strip()
        selector = str(correction.get("selector") or "").strip()
        if not field_label or not selector:
            return
        page_pattern = _page_pattern(feedback.url)
        self._conn.execute(
            """
            insert into workflow_templates (
                kind, page_url_pattern, field_label, selector, action, metadata
            )
            values ('field_selector', ?, ?, ?, 'fill', ?)
            on conflict(kind, page_url_pattern, field_label, selector, action)
            do update set
                confidence = min(1.0, confidence + 0.05),
                updated_at = current_timestamp,
                metadata = excluded.metadata
            """,
            (
                page_pattern,
                field_label,
                selector,
                json.dumps(correction),
            ),
        )


def _page_pattern(url: str) -> str:
    if not url:
        return "*"
    return url.split("?", 1)[0].rstrip("/") or url


def _url_matches_pattern(url: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    normalized_url = _page_pattern(url)
    normalized_pattern = pattern.rstrip("/")
    return normalized_url == normalized_pattern or normalized_url.startswith(
        normalized_pattern + "/"
    )
