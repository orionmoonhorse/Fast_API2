# booking_api.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Literal
import psycopg2.extras
from datetime import datetime

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
# ROUTE
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
        estimate
    ))

    booking_id = cur.fetchone()["id"]
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
        "services": payload.services,
        "client_id": client_id
    }
