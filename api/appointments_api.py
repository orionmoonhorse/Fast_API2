# appointments_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import secrets
import psycopg2.extras

from db import get_db
from api.sms import send_sms

router = APIRouter()

# --- SAFE TIME PARSER ---
def parse_time_safe(t) -> datetime:
    if not t:
        raise ValueError("Missing time string")
    
    t = str(t).strip().upper()
    
    # Try AM/PM formats first
    try:
        return datetime.strptime(t, "%I:%M %p")
    except ValueError:
        pass

    # Normalize formats like "09:00:00" to "09:00"
    parts = t.split(":")
    if len(parts) >= 2:
        hour = parts[0].zfill(2)
        minute = parts[1]
        t = f"{hour}:{minute}"

    try:
        return datetime.strptime(t, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {t}. Use HH:MM.")


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
    start_time_raw = payload.get("start_time")

    if not estimate_id or not client_id or not date or not start_time_raw:
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Validate date format explicitly
    try:
        datetime.strptime(str(date).strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        # -----------------------------
        # 1. Compute duration from estimate_services
        # -----------------------------
        cur.execute("""
            SELECT SUM(duration_minutes) AS total_duration
            FROM estimate_services
            WHERE estimate_id = %s
        """, (estimate_id,))
        row = cur.fetchone()

        duration = row["total_duration"] if row and row["total_duration"] else 60

        # -----------------------------
        # 2. Provider assignment (placeholder)
        # -----------------------------
        provider_id = 1

        # -----------------------------
        # 3. Compute clean start and end times
        # -----------------------------
        slot_start = parse_time_safe(start_time_raw)
        slot_end = slot_start + timedelta(minutes=duration)
        
        start_time_clean = format_time(slot_start)
        end_time_clean = format_time(slot_end)

        # -----------------------------
        # 4. Generate reschedule token
        # -----------------------------
        token = secrets.token_hex(8)

        # -----------------------------
        # 5. Insert appointment (Matching start_time/end_time columns)
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
            start_time_clean,
            end_time_clean,
            token
        ))

        appointment_id = cur.fetchone()["id"]
        
        # -----------------------------
        # 6. Fetch client info for SMS
        # -----------------------------
        cur.execute("SELECT name, phone FROM clients WHERE id = %s", (client_id,))
        client = cur.fetchone()

        if not client:
            # Rollback if client record is somehow missing
            conn.rollback()
            raise HTTPException(status_code=404, detail="Client not found")

        # Commit transaction once all steps succeed
        conn.commit()

        # -----------------------------
        # 7. Send confirmation SMS
        # -----------------------------
        try:
            send_sms(
                client["phone"],
                f"Hi {client['name']}! Your appointment is scheduled for {date} at {start_time_clean}. "
                "Reply CONFIRM, CANCEL, or RESCHEDULE."
            )
            
            # 8. Notify owner
            send_sms(
                "YOUR_OWNER_PHONE_NUMBER",
                f"New appointment scheduled: {client['name']} ({client['phone']}) on {date} at {start_time_clean}."
            )
        except Exception as sms_error:
            # Log SMS errors but don't break the web response since DB insertion succeeded
            print("SMS Notification Error:", sms_error)

        return {
            "appointment_id": appointment_id,
            "estimate_id": estimate_id,
            "provider_id": provider_id,
            "client_id": client_id,
            "date": date,
            "start_time": start_time_clean,
            "end_time": end_time_clean,
            "status": "scheduled",
            "reschedule_link": f"/reschedule?appointment_id={appointment_id}&token={token}",
            "cancel_link": f"/cancel?appointment_id={appointment_id}&token={token}"
        }

    except Exception as e:
        conn.rollback()
        print("APPOINTMENT CREATION CRASH:", e)
        raise HTTPException(status_code=500, detail="Internal server error saving appointment.")
