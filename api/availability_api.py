# availability_api.py

from datetime import datetime
from fastapi import APIRouter, Depends
from db import get_db
import psycopg2.extras

router = APIRouter()

# --- SAFE TIME PARSER ---
def parse_time_safe(t):
    if not t:
        return None

    t = str(t).strip().upper()

    # Try AM/PM formats first
    try:
        return datetime.strptime(t, "%I:%M %p")
    except:
        pass

    # Normalize formats: "9:00", "09:00:00", "17:00:00.000000"
    parts = t.split(":")
    if len(parts) >= 3:
        t = f"{parts[0]}:{parts[1]}"

    # Pad hour if needed
    if len(parts[0]) == 1:
        t = f"0{parts[0]}:{parts[1]}"

    # Try 24-hour format
    try:
        return datetime.strptime(t, "%H:%M")
    except:
        return None


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    try:
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except:
            return []

        provider_id = 1
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ⭐ Load slot definitions (start times only)
        cur.execute("""
            SELECT slot_time
            FROM time_slots
            WHERE provider_id = %s AND active = TRUE
            ORDER BY slot_time
        """, (provider_id,))
        rows = cur.fetchall()

        slots = []
        for row in rows:
            slot_start = parse_time_safe(row["slot_time"])
            slots.append(slot_start)

        # ⭐ Get booked slots from appointments
        cur.execute("""
            SELECT time
            FROM appointments
            WHERE date = %s
        """, (date,))
        booked_from_appointments = [row["time"] for row in cur.fetchall()]

        # ⭐ Get booked slots from daily_appointments
        cur.execute("""
            SELECT time
            FROM daily_appointments
            WHERE date = %s
        """, (date,))
        booked_from_daily = [row["time"] for row in cur.fetchall()]

        # ⭐ Combine booked slots
        booked_slots = set(booked_from_appointments + booked_from_daily)

        # ⭐ Remove ONLY exact booked start times
        open_slots = []
        for slot_start in slots:
            slot_str = format_time(slot_start)
            if slot_str not in booked_slots:
                open_slots.append(slot_str)

        return open_slots

    except Exception as e:
        print("AVAILABILITY ERROR:", e)
        return []
