# api/cancel_api.py

from fastapi import APIRouter, HTTPException, Depends
from db import get_db   # <-- unified DB dependency

router = APIRouter()


@router.put("/cancel")
def cancel_appointment(appointment_id: int, token: str, conn=Depends(get_db)):
    cur = conn.cursor()

    # 1. Fetch appointment
    cur.execute("""
        SELECT id, reschedule_token, status
        FROM appointments
        WHERE id = ?
    """, (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # 2. Validate token
    if appt["reschedule_token"] != token:
        raise HTTPException(status_code=403, detail="Invalid token")

    # 3. Prevent double cancellation
    if appt["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Appointment already cancelled")

    # 4. Update status
    cur.execute("""
        UPDATE appointments
        SET status = 'cancelled'
        WHERE id = ?
    """, (appointment_id,))

    conn.commit()

    return {
        "status": "cancelled",
        "appointment_id": appointment_id
    }
