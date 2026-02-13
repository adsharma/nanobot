import pgembed
import sqlalchemy as sa
import json

db_path = "sessions_db"

with pgembed.get_server(db_path) as pg:
    database_name = "sessions"
    uri = pg.get_uri(database_name)

    engine = sa.create_engine(uri, isolation_level="AUTOCOMMIT")
    conn = engine.connect()

    with conn.begin():
        # Create new tables if not exist
        conn.execute(
            sa.text("""
        CREATE TABLE IF NOT EXISTS session_messages (
            session_key VARCHAR(255) REFERENCES sessions(key) ON DELETE CASCADE,
            message_index INT,
            message JSONB NOT NULL,
            PRIMARY KEY (session_key, message_index)
        )
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

        # Migrate sessions
        print("Migrating sessions...")
        # Check if messages column exists
        result = conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'sessions' AND column_name = 'messages'"
            )
        )
        if result.fetchone():
            # Alter metadata to JSONB
            conn.execute(
                sa.text(
                    "ALTER TABLE sessions ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb"
                )
            )
            # Add messages data to session_messages
            result = conn.execute(
                sa.text("SELECT key, messages FROM sessions WHERE messages IS NOT NULL")
            )
            for row in result.fetchall():
                key, messages_json = row
                try:
                    messages = json.loads(messages_json)
                    for i, msg in enumerate(messages):
                        msg_json = json.dumps(msg)
                        conn.execute(
                            sa.text(
                                "INSERT INTO session_messages (session_key, message_index, message) VALUES (:key, :index, :message)"
                            ),
                            {"key": key, "index": i, "message": msg_json},
                        )
                except:
                    pass
            # Drop messages column
            conn.execute(sa.text("ALTER TABLE sessions DROP COLUMN messages"))
        else:
            print("Messages column not found, skipping sessions migration.")

        # Migrate memories long-term to user_preferences
        print("Migrating long-term memory...")
        result = conn.execute(sa.text("SELECT COUNT(*) FROM user_preferences"))
        row = result.fetchone()
        if row and row[0] == 0:
            result = conn.execute(
                sa.text("SELECT content FROM memories WHERE memory_type = 'longterm' LIMIT 1")
            )
            row = result.fetchone()
            if row:
                content = row[0]
                # Parse likes and dislikes
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
                # Insert into user_preferences
                for item in likes:
                    conn.execute(
                        sa.text(
                            "INSERT INTO user_preferences (preference_type, item, created_at) VALUES ('like', :item, NOW())"
                        ),
                        {"item": item},
                    )
                for item in dislikes:
                    conn.execute(
                        sa.text(
                            "INSERT INTO user_preferences (preference_type, item, created_at) VALUES ('dislike', :item, NOW())"
                        ),
                        {"item": item},
                    )
        else:
            print("User preferences already populated, skipping memories migration.")

    conn.close()

print("Migration complete.")
