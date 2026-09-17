# deconflict.py

from datetime import datetime, timedelta
import psycopg2.extras


def provider_exists(conn, provider_id):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = "SELECT id FROM providers WHERE id = %s"
    cur.execute(q, (provider_id,))
    return cur.fetchone() is not None


def generate_availability(conn, provider_id, date, duration_minutes):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    date_obj = datetime.strptime(date, "%Y-%m-%d")
    day_index = date_obj.weekday()
    date_str = date

    # Check overrides first
    q_override = """
        SELECT start_time, end_time, is_closed
        FROM provider_hour_overrides
        WHERE provider_id = %s
        AND date = %s
    """
    cur.execute(q_override, (provider_id, date_str))
    override = cur.fetchone()

    if override:
        if override["is_closed"] == 1:
            return []

        if override["start_time"] and override["end_time"]:
            work_start = datetime.strptime(f"{date} {override['start_time']}", "%Y-%m-%d %H:%M")
            work_end   = datetime.strptime(f"{date} {override['end_time']}", "%Y-%m-%d %H:%M")
        else:
            return []
    else:
        q_base = """
            SELECT start_time, end_time
            FROM provider_hours
            WHERE provider_id = %s
            AND day_of_week = %s
        """
        cur.execute(q_base, (provider_id, day_index))
        row = cur.fetchone()
        if not row:
            return []

        work_start = datetime.strptime(f"{date} {row['start_time']}", "%Y-%m-%d %H:%M")
        work_end   = datetime.strptime(f"{date} {row['end_time']}", "%Y-%m-%d %H:%M")

    slots = []
    current = work_start

    while current + timedelta(minutes=duration_minutes) <= work_end:
        result = deconflict(conn, provider_id, current, duration_minutes)
        if result["ok"]:
            slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=15)

    return slots


def blackout_conflict(conn, provider_id, start_dt):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = """
        SELECT id FROM blackouts
        WHERE provider_id = %s
        AND date = %s
    """
    cur.execute(q, (provider_id, start_dt.date()))
    return cur.fetchone() is not None


def provider_hours_conflict(conn, provider_id, start_dt, end_dt):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    day_index = start_dt.weekday()
    date_str = start_dt.strftime("%Y-%m-%d")

    q_override = """
        SELECT start_time, end_time, is_closed
        FROM provider_hour_overrides
        WHERE provider_id = %s
        AND date = %s
    """
    cur.execute(q_override, (provider_id, date_str))
    override = cur.fetchone()

    if override:
        if override["is_closed"] == 1:
            return True

        if override["start_time"] and override["end_time"]:
            h_start = datetime.strptime(override["start_time"], "%H:%M").time()
            h_end   = datetime.strptime(override["end_time"], "%H:%M").time()

            if start_dt.time() < h_start or end_dt.time() > h_end:
                return True

            return False

    q_base = """
        SELECT start_time, end_time
        FROM provider_hours
        WHERE provider_id = %s
        AND day_of_week = %s
    """
    cur.execute(q_base, (provider_id, day_index))
    row = cur.fetchone()

    if not row:
        return True

    h_start = datetime.strptime(row["start_time"], "%H:%M").time()
    h_end   = datetime.strptime(row["end_time"], "%H:%M").time()

    if start_dt.time() < h_start or end_dt.time() > h_end:
        return True

    return False


def overlaps(conn, provider_id, start_dt, end_dt):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    q = """
        SELECT a.date, a.start_time, a.end_time
        FROM appointments a
        WHERE a.provider_id = %s
        AND a.status != 'cancelled'
    """
    cur.execute(q, (provider_id,))
    rows = cur.fetchall()

    for r in rows:
        a_start = datetime.strptime(f"{r['date']} {r['start_time']}", "%Y-%m-%d %H:%M")
        a_end   = datetime.strptime(f"{r['date']} {r['end_time']}", "%Y-%m-%d %H:%M")

        if start_dt < a_end and end_dt > a_start:
            return True

    return False


def buffer_conflict(conn, provider_id, start_dt, end_dt):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT buffer_minutes FROM providers WHERE id = %s", (provider_id,))
    row = cur.fetchone()

    buffer_minutes = row["buffer_minutes"] if row else 0
    buffer_delta = timedelta(minutes=buffer_minutes)

    q = """
        SELECT a.date, a.start_time, a.end_time
        FROM appointments a
        WHERE a.provider_id = %s
        AND a.status != 'cancelled'
    """
    cur.execute(q, (provider_id,))
    rows = cur.fetchall()

    for r in rows:
        a_start = datetime.strptime(f"{r['date']} {r['start_time']}", "%Y-%m-%d %H:%M")
        a_end   = datetime.strptime(f"{r['date']} {r['end_time']}", "%Y-%m-%d %H:%M")

        if start_dt < (a_end + buffer_delta) and end_dt > (a_start - buffer_delta):
            return True

    return False


def travel_conflict(conn, provider_id, start_dt, end_dt):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT travel_time_minutes FROM providers WHERE id = %s", (provider_id,))
    row = cur.fetchone()

    travel_minutes = row["travel_time_minutes"] if row else 0
    travel_delta = timedelta(minutes=travel_minutes)

    q = """
        SELECT a.date, a.start_time, a.end_time
        FROM appointments a
        WHERE a.provider_id = %s
        AND a.status != 'cancelled'
    """
    cur.execute(q, (provider_id,))
    rows = cur.fetchall()

    for r in rows:
        a_start = datetime.strptime(f"{r['date']} {r['start_time']}", "%Y-%m-%d %H:%M")
        a_end   = datetime.strptime(f"{r['date']} {r['end_time']}", "%Y-%m-%d %H:%M")

        if start_dt < (a_end + travel_delta) and end_dt > (a_start - travel_delta):
            return True

    return False


def deconflict(conn, provider_id, start_dt, duration_minutes):
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    if not provider_exists(conn, provider_id):
        return {"ok": False, "reason": "provider_not_found"}

    if blackout_conflict(conn, provider_id, start_dt):
        return {"ok": False, "reason": "provider_blackout"}

    if provider_hours_conflict(conn, provider_id, start_dt, end_dt):
        return {"ok": False, "reason": "outside_provider_hours"}

    if overlaps(conn, provider_id, start_dt, end_dt):
        return {"ok": False, "reason": "overlap"}

    if buffer_conflict(conn, provider_id, start_dt, end_dt):
        return {"ok": False, "reason": "buffer_time_conflict"}

    if travel_conflict(conn, provider_id, start_dt, end_dt):
        return {"ok": False, "reason": "travel_time_conflict"}

    return {"ok": True}
