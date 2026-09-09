# api/client_portal_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import json

from db import get_db   # <-- unified DB dependency

router = APIRouter()


# -----------------------------
# CLIENT PROFILE
# -----------------------------
@router.get("/portal/client/{client_id}")
def client_profile(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "client_id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "address": row["address"]
    }


# -----------------------------
# CLIENT ESTIMATES LIST
# -----------------------------
@router.get("/portal/client/{client_id}/estimates")
def client_estimates(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT e.id, e.price, e.duration_minutes, e.created_at,
               st.name AS service_name, st.category AS service_category
        FROM estimates e
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.client_id = ?
        ORDER BY e.created_at DESC
    """, (client_id,))

    rows = cur.fetchall()

    return [
        {
            "estimate_id": r["id"],
            "service": r["service_name"],
            "category": r["service_category"],
            "price": r["price"],
            "duration_minutes": r["duration_minutes"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


# -----------------------------
# CLIENT ESTIMATE DETAILS
# -----------------------------
@router.get("/portal/estimate/{estimate_id}")
def estimate_details(estimate_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT e.*, st.name AS service_name, st.category AS service_category
        FROM estimates e
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.id = ?
    """, (estimate_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Estimate not found")

    return {
        "estimate_id": r["id"],
        "service": r["service_name"],
        "category": r["service_category"],
        "price": r["price"],
        "duration_minutes": r["duration_minutes"],
        "linear_feet": r["linear_feet"],
        "square_feet": r["square_feet"],
        "stories": r["stories"],
        "add_ons": json.loads(r["add_ons"]) if r["add_ons"] else {},
        "created_at": r["created_at"]
    }


# -----------------------------
# APPROVE ESTIMATE → CREATE JOB
# -----------------------------
@router.post("/portal/estimate/{estimate_id}/approve")
def approve_estimate(estimate_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT client_id FROM estimates WHERE id = ?", (estimate_id,))
    est = cur.fetchone()

    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")

    client_id = est["client_id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO jobs (estimate_id, client_id, status, created_at, updated_at)
        VALUES (?, ?, 'pending', ?, ?)
    """, (estimate_id, client_id, now, now))

    conn.commit()
    job_id = cur.lastrowid

    return {
        "job_id": job_id,
        "estimate_id": estimate_id,
        "message": "Estimate approved. Job created and ready for scheduling."
    }


# -----------------------------
# CLIENT JOB LIST
# -----------------------------
@router.get("/portal/client/{client_id}/jobs")
def client_jobs(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT j.id AS job_id, j.status, j.created_at,
               st.name AS service_name, st.category AS service_category,
               e.price
        FROM jobs j
        JOIN estimates e ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE j.client_id = ?
        ORDER BY j.created_at DESC
    """, (client_id,))

    rows = cur.fetchall()

    return [
        {
            "job_id": r["job_id"],
            "status": r["status"],
            "service": r["service_name"],
            "category": r["service_category"],
            "price": r["price"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


# -----------------------------
# CLIENT APPOINTMENTS LIST
# -----------------------------
@router.get("/portal/client/{client_id}/appointments")
def client_appointments(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT a.id AS appointment_id,
               a.date, a.start_time, a.end_time, a.status,
               st.name AS service_name, st.category AS service_category,
               a.reschedule_token
        FROM appointments a
        JOIN estimates e ON a.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE a.client_id = ?
        ORDER BY a.date ASC, a.start_time ASC
    """, (client_id,))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "date": r["date"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "service": r["service_name"],
            "category": r["service_category"],
            "reschedule_link": f"/reschedule?appointment_id={r['appointment_id']}&token={r['reschedule_token']}",
            "cancel_link": f"/cancel?appointment_id={r['appointment_id']}&token={r['reschedule_token']}"
        }
        for r in rows
    ]


# -----------------------------
# CLIENT PORTAL DASHBOARD
# -----------------------------
@router.get("/portal/client/{client_id}/dashboard")
def client_dashboard(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM estimates WHERE client_id = ?", (client_id,))
    estimates = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM jobs WHERE client_id = ?", (client_id,))
    jobs = cur.fetchone()["count"]

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE client_id = ? AND date >= ? AND status != 'cancelled'
    """, (client_id, today))
    upcoming = cur.fetchone()["count"]

    return {
        "total_estimates": estimates,
        "total_jobs": jobs,
        "upcoming_appointments": upcoming
    }
