# availability_api.py

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
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
    try:
        # Validate date format
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except:
            return []

        weekday = date_obj.weekday()
        duration = 120
        provider_id = 1

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Provider hours
        provider_hours = get_provider_hours(conn, provider_id, weekday)

        # Default hours
        start = parse_time_safe("09:00")
        end = parse_time_safe("17:00")

        if provider_hours:
            ph_start = parse_time_safe(provider_hours.get("start_time"))
            ph_end = parse_time_safe(provider_hours.get("end_time"))

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

        # Full-day block
        for r in rules:
            if r.get("is_blocked") == 1 and not r.get("start_time") and not r.get("end_time"):
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
                if r.get("is_blocked") != 1:
                    continue

                rule_start = parse_time_safe(r.get("start_time"))
                rule_end = parse_time_safe(r.get("end_time"))

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
                a_start = parse_time_safe(a.get("start_time"))
                a_end = parse_time_safe(a.get("end_time"))

                if a_start and a_end:
                    if slot_start < a_end and slot_end > a_start:
                        return True

            return False

        slots = [(s, e) for (s, e) in slots if not slot_conflicts(s, e)]

        return [format_time(s) for (s, e) in slots]

    except Exception as e:
        print("AVAILABILITY ERROR:", e)
        return []
