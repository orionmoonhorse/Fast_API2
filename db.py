# db.py

import os
import psycopg2
import psycopg2.pool

DATABASE_URL = os.getenv("DATABASE_URL")

# -----------------------------
# CONNECTION POOL (recommended)
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

def get_db():
    try:
        conn = pool.getconn()
        conn.autocommit = True
        return conn
    except Exception as e:
        print("DB connection error:", e)
        raise

def release_db(conn):
    try:
        pool.putconn(conn)
    except Exception as e:
        print("DB release error:", e)
