# availability_api.py

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from db import get_db
import psycopg2.extras

router = APIRouter()

# --- SAFE TIME PARSER ---
def parse_time_safe(t):
    if t is None:
        return None

    t = str(t).strip()

    # Normalize formats: "9:00", "09:00:00", "17:00:00.000000"
    parts = t.split(":")

    # If seconds exist, strip them
    if len(parts) >= 3:
        t = f"{parts[0]}:{parts[1]}"

    # Pad hour if needed
    if len(parts[0]) == 1:
        t = f"0{parts[0]}:{parts[1]}"

    try:
        return datetime.strptime(t, "%H:%M")
    except:
        return None


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def get_provider_hours(conn, provider_id: int, weekday: int):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT start_time, end_time
        FROM provider_hours
        WHERE provider_id = %s AND day_of_week = %s
    """, (provider_id, weekday))
    return cur.fetchone()


@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    weekday = datetime.strptime(date, "%Y-%m-%d").weekday()
    duration = 120
    provider_id = 1

    # Provider hours
    provider_hours = get_provider_hours(conn, provider_id, weekday)

    # Default hours
    start = parse_time_safe("09:00")
    end = parse_time_safe("17:00")

    if provider_hours:
        ph_start = parse_time_safe(provider_hours["start_time"])
        ph_end = parse_time_safe(provider_hours["end_time"])

        # Only override if valid
        if ph_start and ph_end and ph_start < ph_end:
            start, end = ph_start, ph_end

    base_start, base_end = start, end

    # Rules
    cur.execute("""
        SELECT *
        FROM availability_rules
        WHERE date = %s
    """, (date,))
    rules = cur.fetchall()

    # Full-day block (only if explicitly set)
    for r in rules:
        if r["is_blocked"] == 1 and r["start_time"] is None and r["end_time"] is None:
            return []

    # Generate slots
    slots = []
    current = base_start

    while current + timedelta(minutes=duration) <= base_end:
        slot_start = current
        slot_end = current + timedelta(minutes=duration)
        slots.append((slot_start, slot_end))
        current += timedelta(minutes=duration)

    # Rule blocking
    def slot_blocked(slot_start, slot_end):
        for r in rules:
            if r["is_blocked"] != 1:
                continue

            rule_start = parse_time_safe(r["start_time"])
            rule_end = parse_time_safe(r["end_time"])

            if rule_start and rule_end:
                if slot_start < rule_end and slot_end > rule_start:
                    return True

        return False

    slots = [(s, e) for (s, e) in slots if not slot_blocked(s, e)]

    # Appointments
    cur.execute("""
        SELECT start_time, end_time
        FROM appointments
        WHERE date = %s
          AND provider_id = %s
          AND status != 'cancelled'
    """, (date, provider_id))
    appts = cur.fetchall()

    def slot_conflicts(slot_start, slot_end):
        for a in appts:
            a_start = parse_time_safe(a["start_time"])
            a_end = parse_time_safe(a["end_time"])

            # Only check valid appointments
            if a_start and a_end:
                if slot_start < a_end and slot_end > a_start:
                    return True

        return False

    slots = [(s, e) for (s, e) in slots if not slot_conflicts(s, e)]

    return [format_time(s) for (s, e) in slots]
