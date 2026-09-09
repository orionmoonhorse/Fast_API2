# api/reschedule_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta

from api.deconflict import deconflict
from db import get_db   # <-- unified DB dependency

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
    cur = conn.cursor()

    # -----------------------------
    # 1. Fetch existing appointment
    # -----------------------------
    cur.execute("""
        SELECT id, estimate_id, client_id,
               date, start_time, end_time, reschedule_token
        FROM appointments
        WHERE id = ?
    """, (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appt["reschedule_token"] != token:
        raise HTTPException(status_code=403, detail="Invalid reschedule token")

    estimate_id = appt["estimate_id"]

    # -----------------------------
    # 2. Fetch estimate (provider + duration)
    # -----------------------------
    cur.execute("""
        SELECT provider_id, duration_minutes
        FROM estimates
        WHERE id = ?
    """, (estimate_id,))
    est = cur.fetchone()

    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")

    provider_id = est["provider_id"]
    duration = est["duration_minutes"]

    # Convert new start time into full datetime
    new_start_dt = datetime.strptime(f"{new_date} {new_start_time}", "%Y-%m-%d %H:%M")

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
        SET date = ?, start_time = ?, end_time = ?, status = 'rescheduled'
        WHERE id = ?
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
