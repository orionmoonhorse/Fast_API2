# api/client_portal_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import psycopg2.extras
from db import get_db

router = APIRouter()


# -----------------------------
# CLIENT PROFILE
# -----------------------------
@router.get("/portal/client/{client_id}")
def client_profile(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
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
# CLIENT BOOKINGS LIST
# -----------------------------
@router.get("/portal/client/{client_id}/bookings")
def client_bookings(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, services, issue_description, date, time, estimate_json, created_at
        FROM bookings
        WHERE client_id = %s
        ORDER BY created_at DESC
    """, (client_id,))

    rows = cur.fetchall()

    return [
        {
            "booking_id": r["id"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "date": r["date"],
            "time": r["time"],
            "estimate": r["estimate_json"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


# -----------------------------
# BOOKING DETAILS
# -----------------------------
@router.get("/portal/booking/{booking_id}")
def booking_details(booking_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, client_id, services, issue_description, date, time, estimate_json, created_at
        FROM bookings
        WHERE id = %s
    """, (booking_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Booking not found")

    return {
        "booking_id": r["id"],
        "client_id": r["client_id"],
        "services": r["services"],
        "issue_description": r["issue_description"],
        "date": r["date"],
        "time": r["time"],
        "estimate": r["estimate_json"],
        "created_at": r["created_at"]
    }


# -----------------------------
# CLIENT APPOINTMENTS LIST
# -----------------------------
@router.get("/portal/client/{client_id}/appointments")
def client_appointments(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT a.id AS appointment_id,
               a.date, a.start_time, a.end_time, a.status,
               a.reschedule_token,
               b.id AS booking_id,
               b.services,
               b.issue_description
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        WHERE a.client_id = %s
        ORDER BY a.date ASC, a.start_time ASC
    """, (client_id,))

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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Total bookings
    cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE client_id = %s", (client_id,))
    bookings_count = cur.fetchone()["count"]

    # Total appointments
    cur.execute("SELECT COUNT(*) AS count FROM appointments WHERE client_id = %s", (client_id,))
    appointments_count = cur.fetchone()["count"]

    # Upcoming appointments (today or later, not cancelled)
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM appointments
        WHERE client_id = %s AND date >= %s AND status != 'cancelled'
    """, (client_id, today))
    upcoming = cur.fetchone()["count"]

    # Last booking summary
    cur.execute("""
        SELECT id, services, issue_description, date, time, estimate_json, created_at
        FROM bookings
        WHERE client_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (client_id,))
    last_booking = cur.fetchone()

    last_booking_data = None
    if last_booking:
        last_booking_data = {
            "booking_id": last_booking["id"],
            "services": last_booking["services"],
            "issue_description": last_booking["issue_description"],
            "date": last_booking["date"],
            "time": last_booking["time"],
            "estimate": last_booking["estimate_json"],
            "created_at": last_booking["created_at"]
        }

    return {
        "total_bookings": bookings_count,
        "total_appointments": appointments_count,
        "upcoming_appointments": upcoming,
        "last_booking": last_booking_data
    }
