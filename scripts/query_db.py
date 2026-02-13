import pgembed
import sqlalchemy as sa
import json

db_path = "sessions_db"

with pgembed.get_server(db_path) as pg:
    database_name = "sessions"
    uri = pg.get_uri(database_name)

    engine = sa.create_engine(uri, isolation_level="AUTOCOMMIT")
    conn = engine.connect()

    # result = conn.execute(sa.text("SELECT datname FROM pg_database"))
    # rows = result.fetchall()
    # for row in rows:
    #     print(row)

    print("=== SELECT * FROM memories ===")
    result = conn.execute(sa.text("SELECT * FROM memories"))
    for row in result:
        print(row)
        # Try to pretty print JSON columns
        for col in ["content", "metadata", "messages"]:
            if hasattr(row, col):
                try:
                    data = json.loads(getattr(row, col))
                    print(f"{col}: {json.dumps(data, indent=2)}")
                except:
                    pass
        print("----")

    result = conn.execute(sa.text("SELECT * FROM sessions order by updated_at limit 5"))
    for row in result:
        print(row)
        # Try to pretty print JSON columns
        for col in ["content", "metadata", "messages"]:
            if hasattr(row, col):
                try:
                    data = json.loads(getattr(row, col))
                    print(f"{col}: {json.dumps(data, indent=2)}")
                except:
                    pass
        print("----")

    print("=== SELECT * FROM session_messages ===")
    result = conn.execute(
        sa.text("SELECT * FROM session_messages ORDER BY session_key, message_index")
    )
    for row in result:
        print(row)
        if hasattr(row, "message"):
            try:
                data = json.loads(row.message)
                print(f"message: {json.dumps(data, indent=2)}")
            except:
                pass
        print("----")

    print("=== SELECT * FROM user_preferences ===")
    result = conn.execute(sa.text("SELECT * FROM user_preferences ORDER BY created_at"))
    for row in result:
        print(row)
        print("----")

    conn.close()
