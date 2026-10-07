# booking_api.py

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Literal
import psycopg2.extras
from datetime import datetime, timedelta
import json
import logging

from db import get_db
from api.sms import send_sms

logger = logging.getLogger(__name__)
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
    date: str  # Format: "YYYY-MM-DD"
    time: str  # Format: "HH:MM"


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
            "diagnostic_estimated": f"{diagnostic_min}-{diagnostic_max} estimated",
            "total_estimate": {"min": diagnostic_min, "max": diagnostic_max},
            "note": "Diagnostic selected - repair pricing hidden until after diagnosis."
        }

    washer_min = 129
    washer_max = 299
    dryer_min = 129
    dryer_max = 279

    issue_keywords = {
        "not spinning": 45, "not draining": 60, "leaking": 70,
        "no power": 50, "not heating": 65, "loud noise": 40, "burning smell": 80,
    }

    additional = sum(price for keyword, price in issue_keywords.items() if keyword in issue_description)
    breakdown = {}
    total_min = 0
    total_max = 0

    if "washer" in services:
        washer_total_min = washer_min + additional
        washer_total_max = washer_max + additional
        breakdown["washer"] = {"min": washer_total_min, "max": washer_total_max}
        total_min += washer_total_min
        total_max += washer_total_max

    if "dryer" in services:
        dryer_total_min = dryer_min + additional
        dryer_total_max = dryer_max + additional
        breakdown["dryer"] = {"min": dryer_total_min, "max": dryer_total_max}
        total_min += dryer_total_min
        total_max += dryer_total_max

    return {
        "type": "repair_estimate",
        "breakdown": breakdown,
        "total_estimate": {"min": total_min, "max": total_max}
    }


# ============================
# ROUTE — CREATE BOOKING
# ============================
@router.post("/booking/create")
def create_booking(payload: BookingPayload, conn=Depends(get_db)):
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. PARSE TIMESTAMPS
        try:
            start_time = datetime.strptime(f"{payload.date} {payload.time}", "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=2)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date or time format.")

        # 2. STRICT OVERLAP CHECK (Changed appointment_id to id)
        cur.execute("""
            SELECT id FROM appointments 
            WHERE status != 'cancelled'
              AND start_time < %s 
              AND end_time > %s
            LIMIT 1
        """, (end_time, start_time))
        
        conflict = cur.fetchone()
        if conflict:
            raise HTTPException(
                status_code=400,
                detail="This slot overlaps with an existing appointment. Please choose a different time."
            )

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
                payload.name, payload.phone, payload.email,
                payload.service_address, payload.issue_description,
                datetime.now().isoformat()
            ))
            client_id = cur.fetchone()["id"]

        # Compute pricing estimate
        estimate = estimate_cost(payload.services, payload.issue_description)
        price_min, price_max = extract_price_ranges(estimate)
        full_labels = map_service_labels(payload.services)

        # 3. INSERT INTO appointments (Changed RETURNING clause to id)
        cur.execute("""
            INSERT INTO appointments (
                client_id, date, start_time, end_time, status, services
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            client_id,
            payload.date,
            start_time.time(),
            end_time.time(),
            "confirmed",
            ", ".join(payload.services)
        ))
        booking_id = cur.fetchone()["id"]

        # 4. INSERT INTO DAILY_APPOINTMENTS
        cur.execute("""
            INSERT INTO daily_appointments (
                booking_id, client_id, name, phone, service_address,
                services, issue_description, date, time,
                price_min, price_max
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            booking_id, client_id, payload.name, payload.phone, payload.service_address,
            full_labels, payload.issue_description, payload.date, payload.time,
            price_min, price_max
        ))

        # Commit transaction stack
        conn.commit()

        # 5. SMS CONFIRMATION
        try:
            if estimate["type"] == "diagnostic_only":
                sms_message = (
                    f"Hi {payload.name}! Your diagnostic appointment is scheduled for "
                    f"{payload.date} at {payload.time}. Diagnostic fee is "
                    f"${price_min}–${price_max} estimated."
                )
            else:
                sms_message = (
                    f"Hi {payload.name}! Your repair appointment is scheduled for "
                    f"{payload.date} at {payload.time}. Estimated cost is "
                    f"${price_min}–${price_max} based on your description."
                )
            
            send_sms(payload.phone, sms_message)
            
        except Exception as sms_err:
            logger.warning(f"SMS Notification failed to send: {sms_err}")

        return {
            "status": "success",
            "booking_id": booking_id,
            "message": "Appointment booked successfully."
        }

    except Exception as e:
        logger.error(f"BOOKING ERROR: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected database error occurred: {str(e)}"
        )