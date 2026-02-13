"""Memory system for persistent agent memory."""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

import pgembed
import sqlalchemy as sa
from sqlalchemy_utils import database_exists, create_database

logger = logging.getLogger(__name__)

DATA_DIR = Path.home() / ".nanobot"


class MemoryStore:
    """
    Memory system for the agent.

    Stores memories in PostgreSQL database via pgembed.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = ensure_dir(DATA_DIR / "sessions_db")
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database."""
        self.pg_dir = self.data_dir
        self.database_name = "sessions"

    @contextmanager
    def _get_connection(self):
        """Get a database connection."""
        try:
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
                            CREATE TABLE IF NOT EXISTS memories (
                                id SERIAL PRIMARY KEY,
                                memory_type VARCHAR(50) NOT NULL,
                                date_key VARCHAR(50) NOT NULL,
                                content TEXT NOT NULL,
                                created_at TIMESTAMP NOT NULL,
                                updated_at TIMESTAMP NOT NULL
                            )
                        """)
                        )
                        conn.execute(
                            sa.text("""
                            CREATE INDEX IF NOT EXISTS idx_memories_type_date
                            ON memories (memory_type, date_key)
                        """)
                        )
                        conn.execute(
                            sa.text("""
                            CREATE TABLE IF NOT EXISTS user_preferences (
                                id SERIAL PRIMARY KEY,
                                preference_type VARCHAR(20) NOT NULL,
                                item VARCHAR(255) NOT NULL,
                                created_at TIMESTAMP NOT NULL
                            )
                        """)
                        )
                    yield conn
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize memory database connection: {e}", exc_info=True)
            raise

    def _get_date_key(self, dt: Optional[datetime] = None) -> str:
        """Get date key for a datetime."""
        d = dt or datetime.now()
        return d.strftime("%Y-%m-%d")

    def read_today(self) -> str:
        """Read today's memory notes."""
        date_key = self._get_date_key()
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT content FROM memories WHERE memory_type = 'daily' AND date_key = :date_key"
                    ),
                    {"date_key": date_key},
                )
                row = result.fetchone()
                return row[0] if row else ""
        except Exception as e:
            logger.error(f"Failed to read today's memory: {e}", exc_info=True)
            return ""

    def append_today(self, content: str) -> None:
        """Append content to today's memory notes."""
        date_key = self._get_date_key()
        now = datetime.now()

        try:
            existing = self.read_today()
            if existing:
                new_content = existing + "\n" + content
            else:
                new_content = f"# {date_key}\n\n{content}"

            with self._get_connection() as conn:
                conn.execute(
                    sa.text("""
                        INSERT INTO memories (memory_type, date_key, content, created_at, updated_at)
                        VALUES ('daily', :date_key, :content, :now, :now)
                        ON CONFLICT (memory_type, date_key) DO UPDATE SET
                            content = :content,
                            updated_at = :now
                    """),
                    {"date_key": date_key, "content": new_content, "now": now},
                )
            logger.info(f"[memory] appended to today's notes ({date_key})")
        except Exception as e:
            logger.error(f"Failed to append to today's memory: {e}", exc_info=True)

    def read_long_term(self) -> str:
        """Read long-term memory."""
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT preference_type, item FROM user_preferences ORDER BY created_at"
                    )
                )
                likes = []
                dislikes = []
                for row in result.fetchall():
                    pref_type, item = row
                    if pref_type == "like":
                        likes.append(item)
                    elif pref_type == "dislike":
                        dislikes.append(item)
                parts = []
                if likes:
                    parts.append("User likes:\n" + "\n".join(f"- {item}" for item in likes))
                if dislikes:
                    parts.append("User dislikes:\n" + "\n".join(f"- {item}" for item in dislikes))
                return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"Failed to read long-term memory: {e}", exc_info=True)
            return ""

    def write_long_term(self, content: str) -> None:
        """Write to long-term memory."""
        now = datetime.now()
        try:
            # Parse the content
            likes = []
            dislikes = []
            lines = content.split("\n")
            current = None
            for line in lines:
                line = line.strip()
                if line.startswith("User likes:"):
                    current = "likes"
                elif line.startswith("User dislikes:"):
                    current = "dislikes"
                elif line.startswith("- ") and current:
                    item = line[2:].strip()
                    if current == "likes":
                        likes.append(item)
                    elif current == "dislikes":
                        dislikes.append(item)
            with self._get_connection() as conn:
                # Delete old preferences
                conn.execute(sa.text("DELETE FROM user_preferences"))
                # Insert new
                for item in likes:
                    conn.execute(
                        sa.text(
                            "INSERT INTO user_preferences (preference_type, item, created_at) VALUES ('like', :item, :now)"
                        ),
                        {"item": item, "now": now},
                    )
                for item in dislikes:
                    conn.execute(
                        sa.text(
                            "INSERT INTO user_preferences (preference_type, item, created_at) VALUES ('dislike', :item, :now)"
                        ),
                        {"item": item, "now": now},
                    )
            logger.info("[memory] wrote to long-term memory")
        except Exception as e:
            logger.error(f"Failed to write long-term memory: {e}", exc_info=True)

    def get_recent_memories(self, days: int = 7) -> str:
        """Get memories from the last N days."""
        now = datetime.now()
        memories = []

        for i in range(days):
            date = now - timedelta(days=i)
            date_key = date.strftime("%Y-%m-%d")

            try:
                with self._get_connection() as conn:
                    result = conn.execute(
                        sa.text(
                            "SELECT content FROM memories WHERE memory_type = 'daily' AND date_key = :date_key"
                        ),
                        {"date_key": date_key},
                    )
                    row = result.fetchone()
                    if row:
                        memories.append(row[0])
            except Exception as e:
                logger.error(f"Failed to read memory for {date_key}: {e}", exc_info=True)
                continue

        return "\n\n---\n\n".join(memories)

    def list_memory_files(self) -> list[tuple[str, datetime]]:
        """List all memories sorted by date."""
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    sa.text(
                        "SELECT date_key, updated_at FROM memories WHERE memory_type = 'daily' ORDER BY updated_at DESC"
                    )
                )
                return [(row[0], row[1]) for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list memory files: {e}", exc_info=True)
            return []

    def get_memory_context(self) -> str:
        """Get memory context for the agent."""
        parts = []

        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)

        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)

        return "\n\n".join(parts) if parts else ""


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path
