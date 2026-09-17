# api/reschedule_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import psycopg2.extras

from api.deconflict import deconflict
from db import get_db

router = APIRouter()


def parse_time(t: str) -> datetime:
    return datetime.strptime(t, "%H:%M")


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


@router.put("/reschedule")
def reschedule_appointment(
    appointment_id: int,
    token: str,
    new_date: str,
    new_start_time: str,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # -----------------------------
    # 1. Fetch existing appointment
    # -----------------------------
    cur.execute("""
        SELECT id, booking_id, client_id, provider_id,
               date, start_time, end_time, reschedule_token
        FROM appointments
        WHERE id = %s
    """, (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt["reschedule_token"] != token:
        raise HTTPException(status_code=403, detail="Invalid reschedule token")

    booking_id = appt["booking_id"]
    provider_id = appt["provider_id"]

    # -----------------------------
    # 2. Fetch booking (duration + estimate)
    # -----------------------------
    cur.execute("""
        SELECT duration_minutes
        FROM bookings
        WHERE id = %s
    """, (booking_id,))
    booking = cur.fetchone()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    duration = booking["duration_minutes"]

    # Convert new start time into full datetime
    new_start_dt = datetime.strptime(
        f"{new_date} {new_start_time}", "%Y-%m-%d %H:%M"
    )

    # -----------------------------
    # 3. Run deconflict engine
    # -----------------------------
    result = deconflict(conn, provider_id, new_start_dt, duration)

    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["reason"])

    # -----------------------------
    # 4. Update appointment
    # -----------------------------
    new_end_dt = new_start_dt + timedelta(minutes=duration)

    cur.execute("""
        UPDATE appointments
        SET date = %s, start_time = %s, end_time = %s, status = 'rescheduled'
        WHERE id = %s
    """, (
        new_date,
        new_start_time,
        new_end_dt.strftime("%H:%M"),
        appointment_id
    ))

    conn.commit()

    return {
        "status": "success",
        "appointment_id": appointment_id,
        "old_date": appt["date"],
        "old_start_time": appt["start_time"],
        "new_date": new_date,
        "new_start_time": new_start_time,
        "new_end_time": new_end_dt.strftime("%H:%M")
    }
