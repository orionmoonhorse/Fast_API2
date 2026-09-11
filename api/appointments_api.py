# appointments_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import secrets
import psycopg2.extras   # REQUIRED for RealDictCursor

from db import get_db
from api.sms import send_sms

router = APIRouter()


def parse_time(t: str) -> datetime:
    return datetime.strptime(t, "%H:%M")


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


@router.post("/appointment/create")
def create_appointment(payload: dict, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("\n=== RAW APPOINTMENT PAYLOAD RECEIVED ===")
    print(payload)
    print("========================================\n")

    estimate_id = payload.get("estimate_id")
    client_id = payload.get("client_id")
    date = payload.get("date")
    start_time = payload.get("start_time")

    if not estimate_id or not client_id or not date or not start_time:
        raise HTTPException(status_code=400, detail="Missing required fields")

    # -----------------------------
    # 1. Compute duration from estimate_services
    # -----------------------------
    cur.execute("""
        SELECT SUM(duration_minutes) AS total_duration
        FROM estimate_services
        WHERE estimate_id = %s
    """, (estimate_id,))
    row = cur.fetchone()

    duration = row["total_duration"] if row["total_duration"] else 60

    # -----------------------------
    # 2. Provider assignment (placeholder)
    # -----------------------------
    provider_id = 1

    # -----------------------------
    # 3. Compute end time
    # -----------------------------
    slot_start = parse_time(start_time)
    slot_end = slot_start + timedelta(minutes=duration)

    # -----------------------------
    # 4. Generate reschedule token
    # -----------------------------
    token = secrets.token_hex(8)

    # -----------------------------
    # 5. Insert appointment
    # -----------------------------
    cur.execute("""
        INSERT INTO appointments (
            estimate_id, client_id, provider_id,
            date, start_time, end_time,
            status, reschedule_token
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s)
        RETURNING id
    """, (
        estimate_id,
        client_id,
        provider_id,
        date,
        start_time,
        format_time(slot_end),
        token
    ))

    appointment_id = cur.fetchone()["id"]
    conn.commit()

    # -----------------------------
    # 6. Fetch client info for SMS/email
    # -----------------------------
    cur.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    client = cur.fetchone()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # -----------------------------
    # 7. Send confirmation SMS
    # -----------------------------
    send_sms(
        client["phone"],
        f"Hi {client['name']}! Your appointment is scheduled for {date} at {start_time}. "
        "Reply CONFIRM, CANCEL, or RESCHEDULE."
    )

    # -----------------------------
    # 8. Notify owner
    # -----------------------------
    send_sms(
        "YOUR_OWNER_PHONE_NUMBER",
        f"New appointment scheduled: {client['name']} ({client['phone']}) on {date} at {start_time}."
    )

    return {
        "appointment_id": appointment_id,
        "estimate_id": estimate_id,
        "provider_id": provider_id,
        "client_id": client_id,
        "date": date,
        "start_time": start_time,
        "end_time": format_time(slot_end),
        "status": "scheduled",
        "reschedule_link": f"/reschedule?appointment_id={appointment_id}&token={token}",
        "cancel_link": f"/cancel?appointment_id={appointment_id}&token={token}"
    }
