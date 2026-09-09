# api/admin_dashboard_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from db import get_db   # <-- unified DB dependency

router = APIRouter()


# -----------------------------
# ADMIN OVERVIEW
# -----------------------------
@router.get("/admin/overview")
def admin_overview(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM clients")
    clients = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM providers")
    providers = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM jobs")
    jobs = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM appointments")
    appointments = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE status = 'completed'
    """)
    completed = cur.fetchone()["count"]

    return {
        "clients": clients,
        "providers": providers,
        "jobs": jobs,
        "appointments": appointments,
        "completed_appointments": completed
    }


# -----------------------------
# REVENUE STATS
# -----------------------------
@router.get("/admin/revenue")
def admin_revenue(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT SUM(price) AS total FROM estimates")
    total_revenue = cur.fetchone()["total"] or 0

    cur.execute("""
        SELECT SUM(price) AS total
        FROM estimates
        WHERE created_at >= date('now', '-30 days')
    """)
    last_30 = cur.fetchone()["total"] or 0

    cur.execute("SELECT AVG(price) AS avg_price FROM estimates")
    avg_price = cur.fetchone()["avg_price"] or 0

    return {
        "total_revenue": round(total_revenue, 2),
        "last_30_days": round(last_30, 2),
        "average_job_value": round(avg_price, 2)
    }


# -----------------------------
# JOB STATS
# -----------------------------
@router.get("/admin/jobs")
def admin_jobs(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT status, COUNT(*) AS count
        FROM jobs
        GROUP BY status
    """)
    rows = cur.fetchall()

    return [
        {"status": r["status"], "count": r["count"]}
        for r in rows
    ]


# -----------------------------
# APPOINTMENT STATS
# -----------------------------
@router.get("/admin/appointments")
def admin_appointments(conn=Depends(get_db)):
    cur = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE date >= ? AND status != 'cancelled'
    """, (today,))
    upcoming = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE status = 'completed'
    """)
    completed = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE status = 'cancelled'
    """)
    cancelled = cur.fetchone()["count"]

    return {
        "upcoming": upcoming,
        "completed": completed,
        "cancelled": cancelled
    }


# -----------------------------
# PROVIDER PERFORMANCE
# -----------------------------
@router.get("/admin/providers/performance")
def provider_performance(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            p.id AS provider_id,
            p.name AS provider_name,
            COUNT(a.id) AS total_appointments,
            SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN a.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled
        FROM providers p
        LEFT JOIN estimates e ON e.provider_id = p.id
        LEFT JOIN appointments a ON a.estimate_id = e.id
        GROUP BY p.id
    """)

    rows = cur.fetchall()

    return [
        {
            "provider_id": r["provider_id"],
            "provider_name": r["provider_name"],
            "total_appointments": r["total_appointments"],
            "completed": r["completed"],
            "cancelled": r["cancelled"]
        }
        for r in rows
    ]


# -----------------------------
# SERVICE CATEGORY BREAKDOWN
# -----------------------------
@router.get("/admin/services/categories")
def admin_service_categories(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT st.category, COUNT(*) AS count
        FROM estimates e
        JOIN service_types st ON e.service_type_id = st.id
        GROUP BY st.category
    """)

    rows = cur.fetchall()

    return [
        {"category": r["category"], "count": r["count"]}
        for r in rows
    ]


# -----------------------------
# RECENT ACTIVITY FEED
# -----------------------------
@router.get("/admin/activity")
def admin_activity(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.status,
            c.name AS client_name,
            st.name AS service_name
        FROM appointments a
        JOIN clients c ON a.client_id = c.id
        JOIN estimates e ON a.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        ORDER BY a.id DESC
        LIMIT 25
    """)

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "client": r["client_name"],
            "service": r["service_name"],
            "date": r["date"],
            "time": r["start_time"],
            "status": r["status"]
        }
        for r in rows
    ]
