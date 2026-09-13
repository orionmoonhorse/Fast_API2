# booking_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import secrets
import psycopg2.extras

from db import get_db

from email import (
    sendBookingEmail,
    sendCustomerEmail,
    sendLeadEmail,
    sendDayBeforeEmail,
    sendArrivalEmail
)

router = APIRouter()


@router.post("/booking/create")
def create_booking(payload: dict, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("DEBUG: Connected to DB:", conn.dsn)
    print("DEBUG: Incoming payload:", payload)

    # -----------------------------
    # Extract client info
    # -----------------------------
    client = payload.get("client", {})
    name = client.get("name")
    phone = client.get("phone")
    email = client.get("email")
    address = client.get("service_address")
    notes = client.get("notes")

    print("DEBUG: Client info:", client)

    if not name or not phone or not address:
        raise HTTPException(status_code=400, detail="Missing required client fields")

    # -----------------------------
    # Extract estimate info
    # -----------------------------
    estimate = payload.get("estimate", {})
    total_min = estimate.get("total_min_price", 0.0)
    total_max = estimate.get("total_max_price", 0.0)

    print("DEBUG: Estimate info:", estimate)
    print("DEBUG: total_min:", total_min, "total_max:", total_max)

    # -----------------------------
    # Extract services list
    # -----------------------------
    services = payload.get("services", [])
    print("DEBUG: Services list:", services)

    if not services:
        raise HTTPException(status_code=400, detail="At least one service is required")

    # -----------------------------
    # Extract appointment info
    # -----------------------------
    appointment = payload.get("appointment", {})
    date = appointment.get("date")
    start_time = appointment.get("start_time")
    end_time = appointment.get("end_time")

    print("DEBUG: Appointment info:", appointment)

    if not date or not start_time or not end_time:
        raise HTTPException(status_code=400, detail="Missing appointment fields")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------
    # Prevent double booking
    # -----------------------------
    print("DEBUG: Checking for double booking:", date, start_time, end_time)

    cur.execute("""
        SELECT id FROM appointments
        WHERE date = %s AND start_time = %s AND end_time = %s
    """, (date, start_time, end_time))

    existing = cur.fetchone()
    print("DEBUG: Existing appointment:", existing)

    if existing:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="This time slot has already been booked. Please choose another."
        )

    # -----------------------------
    # Insert or reuse client
    # -----------------------------
    print("DEBUG: Checking for existing client by phone:", phone)

    cur.execute("""
        SELECT id FROM clients
        WHERE phone = %s
        LIMIT 1
    """, (phone,))

    existing_client = cur.fetchone()

    if existing_client:
        client_id = existing_client["id"]
        print("DEBUG: Reusing existing client:", client_id)
    else:
        print("DEBUG: Creating new client:", name, phone, email, address, notes)
        cur.execute("""
            INSERT INTO clients (name, phone, email, address, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, phone, email, address, notes, now))
        client_id = cur.fetchone()["id"]

    print("DEBUG: Final client_id:", client_id)

    # -----------------------------
    # Insert estimate header
    # -----------------------------
    print("DEBUG: Inserting estimate header with:",
          "client_id:", client_id,
          "total_min:", total_min,
          "total_max:", total_max)

    cur.execute("""
        INSERT INTO estimates (client_id, total_min_price, total_max_price)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (client_id, total_min, total_max))

    estimate_id = cur.fetchone()["id"]
    print("DEBUG: New estimate_id:", estimate_id)

    # -----------------------------
    # Insert service line items
    # -----------------------------
    for svc in services:
        print("DEBUG: Inserting service:", svc)

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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    print("DEBUG: Inserting appointment:",
          "estimate_id:", estimate_id,
          "client_id:", client_id,
          "provider_id:", 1,
          "date:", date,
          "start:", start_time,
          "end:", end_time)

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
        VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s)
        RETURNING id
    """, (
        estimate_id,
        client_id,
        1,
        date,
        start_time,
        end_time,
        reschedule_token
    ))

    appointment_id = cur.fetchone()["id"]
    print("DEBUG: New appointment_id:", appointment_id)

    conn.commit()
    print("DEBUG: Booking committed successfully")

    # ----------------------------------------------------
    # 🔥 SEND EMAILS (Booking Confirmation + Lead Notice)
    # ----------------------------------------------------
    try:
        print("🔥 DEBUG: About to send emails...")

        lead_payload = {
            "name": name,
            "phone": phone,
            "email": email,
            "address": address,
            "service": services[0].get("service_name"),
            "details": notes,
            "createdAt": now
        }

        print("🔥 DEBUG: Lead email payload:", lead_payload)

        booking_payload = {
            "name": name,
            "email": email,
            "service": services[0].get("service_name"),
            "date": date,
            "time": start_time
        }

        print("🔥 DEBUG: Booking email payload:", booking_payload)

        print("🔥 DEBUG: Calling sendLeadEmail...")
        sendLeadEmail(lead_payload)

        print("🔥 DEBUG: Calling sendBookingEmail...")
        sendBookingEmail(booking_payload)

        print("🔥 DEBUG: Email functions executed successfully.")

    except Exception as e:
        print("❌ DEBUG: Email sending error:", e)

    return {
        "client_id": client_id,
        "estimate_id": estimate_id,
        "appointment_id": appointment_id,
        "status": "booking_created"
    }
