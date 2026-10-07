# availability_api.py

from datetime import datetime, time, timedelta
from fastapi import APIRouter, Depends
from db import get_db
import psycopg2.extras

router = APIRouter()

# --- SAFE TIME PARSER (UPGRADED) ---
def parse_time_safe(t):
    if not t:
        return None

    # Handle native PostgreSQL TIME objects already converted by psycopg2
    if isinstance(t, time):
        return datetime.combine(datetime.today(), t)
    if isinstance(t, datetime):
        return t

    t = str(t).strip().upper()

    # Try AM/PM formats first
    try:
        return datetime.strptime(t, "%I:%M %p")
    except ValueError:
        pass

    # Normalize formats: "9:00", "09:00:00", "17:00:00.000000"
    parts = t.split(":")
    if len(parts) >= 2:
        hour = parts[0].zfill(2)
        minute = parts[1]
        t = f"{hour}:{minute}"

    # Try 24-hour format
    try:
        return datetime.strptime(t, "%H:%M")
    except ValueError:
        return None


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    try:
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        provider_id = 1
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Load your baseline template slots (e.g., 09:00, 09:30, 10:00)
        cur.execute("""
            SELECT slot_time
            FROM time_slots
            WHERE provider_id = %s AND active = TRUE
            ORDER BY slot_time
        """, (provider_id,))
        rows = cur.fetchall()

        slots = []
        for row in rows:
            parsed_slot = parse_time_safe(row["slot_time"])
            if parsed_slot:
                slots.append(parsed_slot)

        # This list stores time ranges that are blocked: (start_dt, end_dt)
        blocked_ranges = []

        # 2. Get booked windows from appointments (aligned with start_time/end_time)
        cur.execute("""
            SELECT start_time, end_time
            FROM appointments
            WHERE date = %s AND status != 'cancelled'
        """, (date,))
        for row in cur.fetchall():
            start_dt = parse_time_safe(row["start_time"])
            end_dt = parse_time_safe(row["end_time"])
            if start_dt and end_dt:
                blocked_ranges.append((start_dt, end_dt))

        # 3. Get booked windows from daily_appointments
        # Assumes daily_appointments uses start_time/end_time, falls back to static 60m if only time exists
        cur.execute("""
            SELECT 
                COALESCE(start_time, time) AS start_time,
                COALESCE(end_time, NULL) AS end_time
            FROM daily_appointments
            WHERE date = %s
        """, (date,))
        for row in cur.fetchall():
            start_dt = parse_time_safe(row["start_time"])
            if start_dt:
                # If your daily appointments don't have an end_time column yet, default to a 60-minute duration block
                end_dt = parse_time_safe(row["end_time"]) if row.get("end_time") else start_dt + timedelta(minutes=60)
                blocked_ranges.append((start_dt, end_dt))

        # 4. Filter baseline slots against blocked time ranges
        open_slots = []
        for slot_start in slots:
            is_blocked = False
            
            for block_start, block_end in blocked_ranges:
                # A template slot is blocked if it drops exactly inside or on an active appointment window
                if block_start <= slot_start < block_end:
                    is_blocked = True
                    break
            
            if not is_blocked:
                open_slots.append(format_time(slot_start))

        return open_slots

    except Exception as e:
        print("AVAILABILITY ERROR:", e)
        return []

