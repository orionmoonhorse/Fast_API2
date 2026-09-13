# booking_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import secrets
import psycopg2.extras
import requests

from db import get_db

router = APIRouter()

NODE_EMAIL_URL = "http://localhost:3000/send-booking-email"


# ----------------------------------------------------
# MESSAGE LOGGING HELPER
# ----------------------------------------------------
def log_message(conn, msg):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages (
            direction,
            channel,
            to_number,
            from_number,
            message_body,
            status,
            related_lead_id,
            createdAt
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        msg.get("direction"),
        msg.get("channel"),
        msg.get("to"),
        msg.get("from"),
        msg.get("body"),
        msg.get("status"),
        msg.get("relatedLeadId"),
        datetime.now().isoformat()
    ))
    conn.commit()


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
    cur.execute("""
        SELECT id FROM appointments
        WHERE date = %s AND start_time = %s AND end_time = %s
    """, (date, start_time, end_time))

    existing = cur.fetchone()

    if existing:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="This time slot has already been booked. Please choose another."
        )

    # -----------------------------
    # Insert or reuse client
    # -----------------------------
    cur.execute("""
        SELECT id FROM clients
        WHERE phone = %s
        LIMIT 1
    """, (phone,))

    existing_client = cur.fetchone()

    if existing_client:
        client_id = existing_client["id"]
    else:
        cur.execute("""
            INSERT INTO clients (name, phone, email, address, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, phone, email, address, notes, now))
        client_id = cur.fetchone()["id"]

    # -----------------------------
    # Insert estimate header
    # -----------------------------
    cur.execute("""
        INSERT INTO estimates (client_id, total_min_price, total_max_price)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (client_id, total_min, total_max))

    estimate_id = cur.fetchone()["id"]

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

    conn.commit()

    # ----------------------------------------------------
    # LOG BOOKING EVENT
    # ----------------------------------------------------
    log_message(conn, {
        "direction": "outbound",
        "channel": "system",
        "to": email,
        "from": "River City Backend",
        "body": f"Booking created for {name} on {date} at {start_time}",
        "status": "created",
        "relatedLeadId": client_id
    })

    # ----------------------------------------------------
    # CALL NODE.JS EMAIL SERVICE
    # ----------------------------------------------------
    try:
        requests.post(NODE_EMAIL_URL, json={
            "name": name,
            "email": email,
            "service": services[0].get("service_name"),
            "date": date,
            "time": start_time,
            "phone": phone,
            "address": address,
            "details": notes,
            "leadId": client_id
        })

        log_message(conn, {
            "direction": "outbound",
            "channel": "system",
            "to": email,
            "from": "River City Backend",
            "body": "Node.js email service triggered",
            "status": "sent",
            "relatedLeadId": client_id
        })

    except Exception as e:
        log_message(conn, {
            "direction": "outbound",
            "channel": "system",
            "to": email,
            "from": "River City Backend",
            "body": f"Node.js email service failed: {e}",
            "status": "error",
            "relatedLeadId": client_id
        })

    return {
        "client_id": client_id,
        "estimate_id": estimate_id,
        "appointment_id": appointment_id,
        "status": "booking_created"
    }
