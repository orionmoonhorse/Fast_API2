# api/job_api.py  (updated for washer/dryer system)

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import psycopg2.extras
from db import get_db

router = APIRouter()


# -----------------------------
# CREATE APPOINTMENT FROM BOOKING
# -----------------------------
@router.post("/appointment/create")
def create_appointment(booking_id: int, date: str, start_time: str, end_time: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Validate booking exists
    cur.execute("""
        SELECT client_id
        FROM bookings
        WHERE id = %s
    """, (booking_id,))
    booking = cur.fetchone()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    client_id = booking["client_id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create appointment
    cur.execute("""
        INSERT INTO appointments (booking_id, client_id, date, start_time, end_time, status, created_at)
        VALUES (%s, %s, %s, %s, %s, 'scheduled', %s)
        RETURNING id
    """, (booking_id, client_id, date, start_time, end_time, now))

    appt_id = cur.fetchone()["id"]
    conn.commit()

    return {
        "appointment_id": appt_id,
        "booking_id": booking_id,
        "client_id": client_id,
        "status": "scheduled",
        "message": "Appointment created and ready for provider assignment"
    }


# -----------------------------
# GET APPOINTMENT DETAILS
# -----------------------------
@router.get("/appointment/{appointment_id}")
def get_appointment(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT a.*, 
               b.services,
               b.issue_description,
               b.estimate_json
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        WHERE a.id = %s
    """, (appointment_id,))

    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {
        "appointment_id": row["id"],
        "booking_id": row["booking_id"],
        "client_id": row["client_id"],
        "provider_id": row["provider_id"],
        "date": row["date"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "status": row["status"],
        "services": row["services"],
        "issue_description": row["issue_description"],
        "estimate": row["estimate_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


# -----------------------------
# UPDATE APPOINTMENT STATUS
# -----------------------------
@router.put("/appointment/{appointment_id}/status")
def update_appointment_status(appointment_id: int, status: str, conn=Depends(get_db)):
    valid_statuses = [
        "scheduled",
        "in_progress",
        "completed",
        "cancelled"
    ]

    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Appointment not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE appointments
        SET status = %s, updated_at = %s
        WHERE id = %s
    """, (status, now, appointment_id))

    conn.commit()

    return {
        "appointment_id": appointment_id,
        "status": status,
        "message": "Appointment status updated"
    }


# -----------------------------
# ASSIGN PROVIDER TO APPOINTMENT
# -----------------------------
@router.put("/appointment/{appointment_id}/assign")
def assign_provider(appointment_id: int, provider_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Validate appointment
    cur.execute("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Validate provider
    cur.execute("SELECT id FROM providers WHERE id = %s", (provider_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Provider not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE appointments
        SET provider_id = %s, updated_at = %s
        WHERE id = %s
    """, (provider_id, now, appointment_id))

    conn.commit()

    return {
        "appointment_id": appointment_id,
        "provider_id": provider_id,
        "message": "Provider assigned to appointment"
    }
