import sqlite3

def init_db():
    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER,
        f1 REAL,
        f2 REAL,
        f3 REAL
    )
    """)

    conn.commit()
    conn.close()
