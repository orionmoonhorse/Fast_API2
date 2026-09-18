# db.py

import os
import psycopg2
import psycopg2.pool

DATABASE_URL = os.getenv("DATABASE_URL")

# -----------------------------
# CONNECTION POOL
# -----------------------------
pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL,
    sslmode="require",
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5
)

# -----------------------------
# FASTAPI DEPENDENCY (CORRECT)
# -----------------------------
def get_db():
    conn = pool.getconn()
    conn.autocommit = True
    try:
        yield conn
    finally:
        pool.putconn(conn)
