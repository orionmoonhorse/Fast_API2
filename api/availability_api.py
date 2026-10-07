# availability_api.py

from datetime import datetime, time, timedelta
from fastapi import APIRouter, Depends
from db import get_db
import psycopg2.extras

router = APIRouter()

# --- SAFE TIME PARSER ---
def parse_time_safe(t):
    if not t:
        return None

    if isinstance(t, time):
        return datetime.combine(datetime.today(), t)
    if isinstance(t, datetime):
        return t

    t = str(t).strip().upper()

    try:
        return datetime.strptime(t, "%I:%M %p")
    except ValueError:
        pass

    parts = t.split(":")
    if len(parts) >= 2:
        hour = parts[0].zfill(2)
        minute = parts[1]
        t = f"{hour}:{minute}"

    try:
        return datetime.strptime(t, "%H:%M")
    except ValueError:
        return None


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    try:
        # Validate input date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        provider_id = 1
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # -------------------------------------------------------------
        # 1. Fetch the provider's shift limits from daily_schedule
        # -------------------------------------------------------------
        cur.execute("""
            SELECT start_time, end_time 
            FROM daily_schedule 
            WHERE provider_id = %s AND date = %s AND active = TRUE
            LIMIT 1
        """, (provider_id, date))
        schedule = cur.fetchone()

        # Fallback: If no custom schedule is set for this day, default to a standard 9 AM - 5 PM shift
        if schedule:
            shift_start = parse_time_safe(schedule["start_time"])
            shift_end = parse_time_safe(schedule["end_time"])
        else:
            shift_start = parse_time_safe("09:00")
            shift_end = parse_time_safe("17:00")

        if not shift_start or not shift_end:
            return []

        # -------------------------------------------------------------
        # 2. Dynamically generate time slot options every 30 minutes
        # -------------------------------------------------------------
        slots = []
        current_slot = shift_start
        while current_slot < shift_end:
            slots.append(current_slot)
            current_slot += timedelta(minutes=30)  # Change 30 to any duration increment you want

        # -------------------------------------------------------------
        # 3. Gather all active booked windows from the appointments table
        # -------------------------------------------------------------
        blocked_ranges = []
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

        # -------------------------------------------------------------
        # 4. Filter out any slots that conflict with bookings
        # -------------------------------------------------------------
        open_slots = []
        for slot_start in slots:
            is_blocked = False
            
            for block_start, block_end in blocked_ranges:
                # If the generated slot falls during a booked meeting, mark it blocked
                if block_start <= slot_start < block_end:
                    is_blocked = True
                    break
            
            if not is_blocked:
                open_slots.append(format_time(slot_start))

        return open_slots

    except Exception as e:
        print("AVAILABILITY ERROR:", e)
        return []
