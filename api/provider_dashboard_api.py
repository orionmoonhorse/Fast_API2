# api/provider_dashboard_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import psycopg2.extras

from db import get_db

router = APIRouter()


# -----------------------------
# PROVIDER DAY VIEW
# -----------------------------
@router.get("/provider/{provider_id}/day")
def provider_day(provider_id: int, date: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            j.id AS job_id,
            e.id AS estimate_id,
            e.price,
            e.duration_minutes,
            st.name     AS service_name,
            st.category AS service_category
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN jobs j           ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = %s AND a.date = %s
        ORDER BY a.start_time ASC
    """, (provider_id, date))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "job_id": r["job_id"],
            "estimate_id": r["estimate_id"],
            "date": r["date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "service": r["service_name"],
            "category": r["service_category"],
            "price": r["price"],
            "duration_minutes": r["duration_minutes"]
        }
        for r in rows
    ]


# -----------------------------
# PROVIDER WEEK VIEW
# -----------------------------
@router.get("/provider/{provider_id}/week")
def provider_week(provider_id: int, start_date: str, conn=Depends(get_db)):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = start_dt + timedelta(days=6)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            j.id AS job_id,
            e.id AS estimate_id,
            e.price,
            e.duration_minutes,
            st.name     AS service_name,
            st.category AS service_category
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN jobs j           ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = %s
          AND a.date BETWEEN %s AND %s
        ORDER BY a.date ASC, a.start_time ASC
    """, (
        provider_id,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    ))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "job_id": r["job_id"],
            "estimate_id": r["estimate_id"],
            "date": r["date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "service": r["service_name"],
            "category": r["service_category"],
            "price": r["price"],
            "duration_minutes": r["duration_minutes"]
        }
        for r in rows
    ]


# -----------------------------
# PROVIDER STATS
# -----------------------------
@router.get("/provider/{provider_id}/stats")
def provider_stats(provider_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # total (non‑cancelled)
    cur.execute("""
        SELECT COUNT(*) AS total
        FROM appointments a
        JOIN estimates e ON a.estimate_id = e.id
        WHERE e.provider_id = %s AND a.status != 'cancelled'
    """, (provider_id,))
    total = cur.fetchone()["total"]

    # completed
    cur.execute("""
        SELECT COUNT(*) AS completed
        FROM appointments a
        JOIN estimates e ON a.estimate_id = e.id
        WHERE e.provider_id = %s AND a.status = 'completed'
    """, (provider_id,))
    completed = cur.fetchone()["completed"]

    # cancelled
    cur.execute("""
        SELECT COUNT(*) AS cancelled
        FROM appointments a
        JOIN estimates e ON a.estimate_id = e.id
        WHERE e.provider_id = %s AND a.status = 'cancelled'
    """, (provider_id,))
    cancelled = cur.fetchone()["cancelled"]

    # by service category
    cur.execute("""
        SELECT st.category AS category, COUNT(*) AS count
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = %s AND a.status != 'cancelled'
        GROUP BY st.category
    """, (provider_id,))
    categories = cur.fetchall()

    return {
        "total": total,
        "completed": completed,
        "cancelled": cancelled,
        "categories": [
            {"category": r["category"], "count": r["count"]} for r in categories
        ],
    }
