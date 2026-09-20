# booking_api.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Literal
import psycopg2.extras
from datetime import datetime
import json

from db import get_db
from api.sms import send_sms

router = APIRouter()

# ============================
# MODEL
# ============================
class BookingPayload(BaseModel):
    name: str
    phone: str
    email: str | None = None
    service_address: str | None = None
    services: List[Literal["diagnostic", "washer", "dryer"]]
    issue_description: str | None = None
    date: str
    time: str


# ============================
# SNAPSHOT RANGES (ESTIMATED)
# ============================
def get_snapshot_ranges():
    return {
        "washer_repair_min": 129,
        "washer_repair_max": 299,
        "washer_estimated": "129–299 estimated",

        "dryer_repair_min": 129,
        "dryer_repair_max": 279,
        "dryer_estimated": "129–279 estimated",

        "diagnostic_min": 79,
        "diagnostic_max": 129,
        "diagnostic_estimated": "79–129 estimated",

        "note": "Diagnostic fee is credited toward repair cost."
    }


# ============================
# SERVICE LABEL MAPPER
# ============================
def map_service_labels(services: list):
    mapped = []

    if "washer" in services:
        mapped.append("Washer Repair")

    if "dryer" in services:
        mapped.append("Dryer Repair")

    if "diagnostic" in services:
        if "washer" in services:
            mapped.append("Washer Diagnostic")
        if "dryer" in services:
            mapped.append("Dryer Diagnostic")
        if "washer" not in services and "dryer" not in services:
            mapped.append("General Diagnostic")

    return mapped


# ============================
# PRICE RANGE EXTRACTOR
# ============================
def extract_price_ranges(estimate: dict):
    if estimate["type"] == "diagnostic_only":
        return estimate["diagnostic_min"], estimate["diagnostic_max"]
    return estimate["total_estimate"]["min"], estimate["total_estimate"]["max"]


# ============================
# ESTIMATOR LOGIC
# ============================
def estimate_cost(services: list, issue_description: str | None):
    issue_description = (issue_description or "").lower()

    diagnostic_min = 79
    diagnostic_max = 129

    if "diagnostic" in services:
        return {
            "type": "diagnostic_only",
            "diagnostic_min": diagnostic_min,
            "diagnostic_max": diagnostic_max,
            "diagnostic_estimated": f"{diagnostic_min}–{diagnostic_max} estimated",
            "total_estimate": {
                "min": diagnostic_min,
                "max": diagnostic_max,
                "estimated": f"{diagnostic_min}–{diagnostic_max} estimated"
            },
            "note": "Diagnostic selected — repair pricing hidden until after diagnosis."
        }

    washer_min = 129
    washer_max = 299
    dryer_min = 129
    dryer_max = 279

    issue_keywords = {
        "not spinning": 45,
        "not draining": 60,
        "leaking": 70,
        "no power": 50,
        "not heating": 65,
        "loud noise": 40,
        "burning smell": 80
    }

    additional = sum(
        price for keyword, price in issue_keywords.items()
        if keyword in issue_description
    )

    breakdown = {}
    total_min = 0
    total_max = 0

    if "washer" in services:
        washer_total_min = washer_min + additional
        washer_total_max = washer_max + additional
        breakdown["washer"] = {
            "min": washer_total_min,
            "max": washer_total_max,
            "estimated": f"{washer_total_min}–{washer_total_max} estimated"
        }
        total_min += washer_total_min
        total_max += washer_total_max

    if "dryer" in services:
        dryer_total_min = dryer_min + additional
        dryer_total_max = dryer_max + additional
        breakdown["dryer"] = {
            "min": dryer_total_min,
            "max": dryer_total_max,
            "estimated": f"{dryer_total_min}–{dryer_total_max} estimated"
        }
        total_min += dryer_total_min
        total_max += dryer_total_max

    return {
        "type": "repair_estimate",
        "breakdown": breakdown,
        "additional": additional,
        "total_estimate": {
            "min": total_min,
            "max": total_max,
            "estimated": f"{total_min}–{total_max} estimated"
        }
    }


# ============================
# ROUTE — CREATE BOOKING
# ============================
@router.post("/booking/create")
def create_booking(payload: BookingPayload, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Auto-create or reuse client
    cur.execute("SELECT id FROM clients WHERE phone = %s LIMIT 1", (payload.phone,))
    existing = cur.fetchone()

    if existing:
        client_id = existing["id"]
    else:
        cur.execute("""
            INSERT INTO clients (name, phone, email, address, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            payload.name,
            payload.phone,
            payload.email,
            payload.service_address,
            payload.issue_description,
            datetime.now().isoformat()
        ))
        client_id = cur.fetchone()["id"]

    # Compute estimate
    estimate = estimate_cost(payload.services, payload.issue_description)

    # Insert booking
    cur.execute("""
        INSERT INTO bookings (client_id, services, issue_description, date, time, estimate_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        client_id,
        payload.services,
        payload.issue_description,
        payload.date,
        payload.time,
        json.dumps(estimate)
    ))

    booking_id = cur.fetchone()["id"]

    # Build readable service labels
    full_labels = map_service_labels(payload.services)

    # Extract min/max pricing
    price_min, price_max = extract_price_ranges(estimate)

    # Insert into daily_appointments
    cur.execute("""
        INSERT INTO daily_appointments (
            booking_id, client_id, name, phone, service_address,
            services, issue_description, date, time,
            price_min, price_max
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        booking_id,
        client_id,
        payload.name,
        payload.phone,
        payload.service_address,
        full_labels,
        payload.issue_description,
        payload.date,
        payload.time,
        price_min,
        price_max
    ))

    conn.commit()

    # SMS confirmation
    if estimate["type"] == "diagnostic_only":
        sms_message = (
            f"Hi {payload.name}! Your diagnostic appointment is scheduled for "
            f"{payload.date} at {payload.time}. Diagnostic fee is "
            f"${estimate['diagnostic_min']}–${estimate['diagnostic_max']} estimated."
        )
    else:
        sms_message = (
            f"Hi {payload.name}! Your repair appointment is scheduled for "
            f"{payload.date} at {payload.time}. Estimated range: "
            f"{estimate['total_estimate']['estimated']}."
        )

    send_sms(payload.phone, sms_message)

    return {
        "booking_id": booking_id,
        "estimate": estimate,
        "snapshot": get_snapshot_ranges(),
        "services": full_labels,
        "client_id": client_id
    }


# ============================
# ROUTE — DAILY APPOINTMENTS
# ============================
@router.get("/appointments/daily")
def get_daily_appointments(date: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT *
        FROM daily_appointments
        WHERE date = %s
        ORDER BY time
    """, (date,))
    return cur.fetchall()


# ============================
# ROUTE — AVAILABILITY (FINAL FIX)
# ============================
@router.get("/availability")
def get_availability(date: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Load all active slots
    cur.execute("""
        SELECT slot_time
        FROM slots
        WHERE active = TRUE
        ORDER BY slot_time
    """)
    all_slots = [row["slot_time"].strftime("%H:%M") for row in cur.fetchall()]

    # Load booked slots from bookings
    cur.execute("""
        SELECT time
        FROM bookings
        WHERE date = %s
    """, (date,))
    booked_from_bookings = [row["time"] for row in cur.fetchall()]

    # Load booked slots from daily_appointments
    cur.execute("""
        SELECT time
        FROM daily_appointments
        WHERE date = %s
    """, (date,))
    booked_from_daily = [row["time"] for row in cur.fetchall()]

    # Combine booked slots
    booked_slots = set(booked_from_bookings + booked_from_daily)

    # Remove booked slots
    open_slots = [slot for slot in all_slots if slot not in booked_slots]

    return open_slots