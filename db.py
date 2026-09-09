# db.py

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require"  # Railway Postgres requires SSL
    )
    conn.autocommit = True
    return conn
