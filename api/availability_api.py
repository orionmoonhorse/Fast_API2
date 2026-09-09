# api/availability_api.py

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from db import get_db   # <-- unified DB dependency

router = APIRouter()


def parse_time(t: str) -> datetime:
    return datetime.strptime(t, "%H:%M")


def format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def get_provider_hours(conn, provider_id: int, weekday: int):
    cur = conn.cursor()
    cur.execute("""
        SELECT start_time, end_time
        FROM provider_hours
        WHERE provider_id = ? AND day_of_week = ?
    """, (provider_id, weekday))
    return cur.fetchone()


@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    cur = conn.cursor()

    weekday = datetime.strptime(date, "%Y-%m-%d").weekday()

    duration = 120
    provider_id = 1

    provider_hours = get_provider_hours(conn, provider_id, weekday)

    if provider_hours:
        base_start = parse_time(provider_hours["start_time"])
        base_end = parse_time(provider_hours["end_time"])
    else:
        base_start = parse_time("09:00")
        base_end = parse_time("17:00")

    cur.execute("""
        SELECT *
        FROM availability_rules
        WHERE date = ?
    """, (date,))
    rules = cur.fetchall()

    for r in rules:
        if r["is_blocked"] == 1 and r["start_time"] is None:
            return []

    slots = []
    current = base_start

    while current + timedelta(minutes=duration) <= base_end:
        slot_start = current
        slot_end = current + timedelta(minutes=duration)
        slots.append((slot_start, slot_end))
        current += timedelta(minutes=duration)

    def slot_blocked(slot_start, slot_end):
        for r in rules:
            if r["is_blocked"] != 1:
                continue

            if r["start_time"] is None:
                return True

            rule_start = parse_time(r["start_time"])
            rule_end = parse_time(r["end_time"])

            if slot_start < rule_end and slot_end > rule_start:
                return True

        return False

    slots = [(s, e) for (s, e) in slots if not slot_blocked(s, e)]

    cur.execute("""
        SELECT start_time, end_time
        FROM appointments
        WHERE date = ?
          AND provider_id = ?
          AND status != 'cancelled'
    """, (date, provider_id))

    appts = cur.fetchall()

    def slot_conflicts(slot_start, slot_end):
        for a in appts:
            a_start = parse_time(a["start_time"])
            a_end = parse_time(a["end_time"])
            if slot_start < a_end and slot_end > a_start:
                return True
        return False

    slots = [(s, e) for (s, e) in slots if not slot_conflicts(s, e)]

    return [format_time(s) for (s, e) in slots]
