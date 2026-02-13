"""Session management for conversation history."""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from contextlib import contextmanager

import pgembed
import sqlalchemy as sa
from sqlalchemy_utils import database_exists, create_database
from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename

DATA_DIR = Path.home() / ".nanobot"


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in PostgreSQL database via pgembed.
    """

    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """Get message history for LLM context."""
        recent = (
            self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        )
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored in a PostgreSQL database via pgembed.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = ensure_dir(DATA_DIR / "sessions_db")
        self._cache: dict[str, Session] = {}
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the PostgreSQL database."""
        self.pg_dir = self.data_dir
        self.database_name = "sessions"
        self._engine = None

    @contextmanager
    def _get_connection(self):
        """Get a database connection."""
        with pgembed.get_server(self.pg_dir) as pg:
            uri = pg.get_uri(self.database_name)
            if not database_exists(uri):
                create_database(uri)
            engine = sa.create_engine(uri, isolation_level="AUTOCOMMIT")
            conn = engine.connect()
            try:
                with conn.begin():
                    conn.execute(
                        sa.text("""
                        CREATE TABLE IF NOT EXISTS sessions (
                            key VARCHAR(255) PRIMARY KEY,
                            created_at TIMESTAMP NOT NULL,
                            updated_at TIMESTAMP NOT NULL,
                            metadata TEXT,
                            messages TEXT NOT NULL
                        )
                    """)
                    )
                yield conn
            finally:
                conn.close()

    def _load(self, key: str) -> Session | None:
        """Load a session from database."""
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT created_at, updated_at, metadata, messages FROM sessions WHERE key = :key"
                    ),
                    {"key": key},
                )
                row = result.fetchone()
                if row is None:
                    return None
                created_at, updated_at, metadata_json, messages_json = row
                return Session(
                    key=key,
                    messages=json.loads(messages_json) if messages_json else [],
                    created_at=created_at,
                    updated_at=updated_at,
                    metadata=json.loads(metadata_json) if metadata_json else {},
                )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None

    def save(self, session: Session) -> None:
        """Save a session to database."""
        try:
            with self._get_connection() as conn:
                metadata_json = json.dumps(session.metadata)
                messages_json = json.dumps(session.messages)
                conn.execute(
                    sa.text("""
                        INSERT INTO sessions (key, created_at, updated_at, metadata, messages)
                        VALUES (:key, :created_at, :updated_at, :metadata, :messages)
                        ON CONFLICT (key) DO UPDATE SET
                            updated_at = :updated_at,
                            metadata = :metadata,
                            messages = :messages
                    """),
                    {
                        "key": session.key,
                        "created_at": session.created_at,
                        "updated_at": session.updated_at,
                        "metadata": metadata_json,
                        "messages": messages_json,
                    },
                )
            self._cache[session.key] = session
        except Exception as e:
            logger.error(f"Failed to save session {session.key}: {e}")

    def get_or_create(self, key: str) -> Session:
        """Get an existing session or create a new one."""
        if key in self._cache:
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key=key)

        self._cache[key] = session
        return session

    def delete(self, key: str) -> bool:
        """Delete a session."""
        self._cache.pop(key, None)
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text("DELETE FROM sessions WHERE key = :key"), {"key": key}
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete session {key}: {e}")
            return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT key, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
                    )
                )
                return [
                    {
                        "key": row[0],
                        "created_at": row[1].isoformat() if row[1] else None,
                        "updated_at": row[2].isoformat() if row[2] else None,
                    }
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
