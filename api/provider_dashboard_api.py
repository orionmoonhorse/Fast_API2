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
            b.id AS booking_id,
            b.services,
            b.issue_description,
            b.estimate_json
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        WHERE a.provider_id = %s AND a.date = %s
        ORDER BY a.start_time ASC
    """, (provider_id, date))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "booking_id": r["booking_id"],
            "date": r["date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "estimate": r["estimate_json"]
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
            b.id AS booking_id,
            b.services,
            b.issue_description,
            b.estimate_json
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        WHERE a.provider_id = %s
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
            "booking_id": r["booking_id"],
            "date": r["date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "estimate": r["estimate_json"]
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
        FROM appointments
        WHERE provider_id = %s AND status != 'cancelled'
    """, (provider_id,))
    total = cur.fetchone()["total"]

    # completed
    cur.execute("""
        SELECT COUNT(*) AS completed
        FROM appointments
        WHERE provider_id = %s AND status = 'completed'
    """, (provider_id,))
    completed = cur.fetchone()["completed"]

    # cancelled
    cur.execute("""
        SELECT COUNT(*) AS cancelled
        FROM appointments
        WHERE provider_id = %s AND status = 'cancelled'
    """, (provider_id,))
    cancelled = cur.fetchone()["cancelled"]

    # by service type (washer/dryer/diagnostic)
    cur.execute("""
        SELECT b.services, COUNT(*) AS count
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        WHERE a.provider_id = %s AND a.status != 'cancelled'
        GROUP BY b.services
    """, (provider_id,))
    categories = cur.fetchall()

    return {
        "total": total,
        "completed": completed,
        "cancelled": cancelled,
        "categories": [
            {"services": r["services"], "count": r["count"]} for r in categories
        ],
    }
