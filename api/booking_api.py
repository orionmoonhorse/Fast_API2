# bookint_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import secrets

from db import get_db   # <-- unified DB dependency

router = APIRouter()


@router.post("/booking/create")
def create_booking(payload: dict, conn=Depends(get_db)):
    cur = conn.cursor()

    # -----------------------------
    # Extract client info
    # -----------------------------
    client = payload.get("client", {})
    name = client.get("name")
    phone = client.get("phone")
    email = client.get("email")
    address = client.get("service_address")
    notes = client.get("notes")

    if not name or not phone or not address:
        raise HTTPException(status_code=400, detail="Missing required client fields")

    # -----------------------------
    # Extract estimate info
    # -----------------------------
    estimate = payload.get("estimate", {})
    total_min = estimate.get("total_min_price", 0.0)
    total_max = estimate.get("total_max_price", 0.0)

    # -----------------------------
    # Extract services list
    # -----------------------------
    services = payload.get("services", [])
    if not services:
        raise HTTPException(status_code=400, detail="At least one service is required")

    # -----------------------------
    # Extract appointment info
    # -----------------------------
    appointment = payload.get("appointment", {})
    date = appointment.get("date")
    start_time = appointment.get("start_time")
    end_time = appointment.get("end_time")

    if not date or not start_time or not end_time:
        raise HTTPException(status_code=400, detail="Missing appointment fields")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------
    # Prevent double booking
    # -----------------------------
    cur.execute("""
        SELECT id FROM appointments
        WHERE date = ? AND start_time = ? AND end_time = ?
    """, (date, start_time, end_time))

    existing = cur.fetchone()

    if existing:
        conn.rollback()   # IMPORTANT
        raise HTTPException(
            status_code=409,
            detail="This time slot has already been booked. Please choose another."
        )

    # -----------------------------
    # Insert client
    # -----------------------------
    cur.execute("""
        INSERT INTO clients (name, phone, email, address, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, phone, email, address, notes, now))

    client_id = cur.lastrowid

    # -----------------------------
    # Insert estimate header
    # -----------------------------
    cur.execute("""
        INSERT INTO estimates (client_id, total_min_price, total_max_price)
        VALUES (?, ?, ?)
    """, (client_id, total_min, total_max))

    estimate_id = cur.lastrowid

    # -----------------------------
    # Insert service line items
    # -----------------------------
    for svc in services:
        cur.execute("""
            INSERT INTO estimate_services (
                estimate_id,
                service_type_id,
                service_name,
                linear_feet,
                square_feet,
                stories,
                debris_level,
                buildup_level,
                surface_type,
                min_price,
                max_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            estimate_id,
            svc.get("service_type_id"),
            svc.get("service_name"),
            svc.get("linear_feet", 0.0),
            svc.get("square_feet", 0.0),
            svc.get("stories", 0),
            svc.get("debris_level"),
            svc.get("buildup_level"),
            svc.get("surface_type"),
            svc.get("min_price"),
            svc.get("max_price")
        ))

    # -----------------------------
    # Insert appointment
    # -----------------------------
    reschedule_token = secrets.token_hex(8)

    cur.execute("""
        INSERT INTO appointments (
            estimate_id,
            client_id,
            provider_id,
            date,
            start_time,
            end_time,
            status,
            reschedule_token
        )
        VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
    """, (
        estimate_id,
        client_id,
        1,   # ⭐ FIXED — provider_id must NOT be None
        date,
        start_time,
        end_time,
        reschedule_token
    ))

    appointment_id = cur.lastrowid

    conn.commit()

    return {
        "client_id": client_id,
        "estimate_id": estimate_id,
        "appointment_id": appointment_id,
        "status": "booking_created"
    }
