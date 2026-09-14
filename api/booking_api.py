# booking_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, date
import secrets
import psycopg2.extras
import requests

from db import get_db

router = APIRouter()

# Correct Node endpoint
NODE_EMAIL_URL = "https://nodejs-production-77535.up.railway.app/send-booking-email"


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

    client = payload.get("client", {})
    name = client.get("name")
    phone = client.get("phone")
    email = client.get("email")
    address = client.get("service_address")
    notes = client.get("notes")

    estimate = payload.get("estimate", {})
    total_min = estimate.get("total_min_price", 0.0)
    total_max = estimate.get("total_max_price", 0.0)

    services = payload.get("services", [])
    appointment = payload.get("appointment", {})
    date_str = appointment.get("date")
    start_time = appointment.get("start_time")
    end_time = appointment.get("end_time")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ----------------------------------------------------
    # 🚫 PREVENT SAME-DAY BOOKINGS
    # ----------------------------------------------------
    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        raise HTTPException(status_code=400, detail="Invalid appointment date format.")

    today = date.today()

    if appt_date <= today:
        raise HTTPException(
            status_code=400,
            detail="Same-day bookings are not allowed. Please select a future date."
        )

    # Prevent double booking
    cur.execute("""
        SELECT id FROM appointments
        WHERE date = %s AND start_time = %s AND end_time = %s
    """, (date_str, start_time, end_time))

    if cur.fetchone():
        conn.rollback()
        raise HTTPException(status_code=409, detail="This time slot has already been booked.")

    # Insert or reuse client
    cur.execute("SELECT id FROM clients WHERE phone = %s LIMIT 1", (phone,))
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

    # Insert estimate
    cur.execute("""
        INSERT INTO estimates (client_id, total_min_price, total_max_price)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (client_id, total_min, total_max))

    estimate_id = cur.fetchone()["id"]

    # Insert services
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

    # Insert appointment
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
        date_str,
        start_time,
        end_time,
        reschedule_token
    ))

    appointment_id = cur.fetchone()["id"]
    conn.commit()

    # Log booking event
    log_message(conn, {
        "direction": "outbound",
        "channel": "system",
        "to": email,
        "from": "River City Backend",
        "body": f"Booking created for {name} on {date_str} at {start_time}",
        "status": "created",
        "relatedLeadId": client_id
    })

    # ----------------------------------------------------
    # CALL NODE.JS EMAIL SERVICE
    # ----------------------------------------------------
    try:
        node_payload = {
            "name": name,
            "email": email,
            "service": services[0].get("service_name"),
            "date": date_str,
            "time": start_time,
            "phone": phone,
            "address": address,
            "details": notes,
            "leadId": client_id
        }

        print("DEBUG: Sending POST to Node:", NODE_EMAIL_URL)
        print("DEBUG: Node payload:", node_payload)

        node_response = requests.post(
            NODE_EMAIL_URL,
            json=node_payload,
            timeout=10
        )

        print("DEBUG: Node response status:", node_response.status_code)
        print("DEBUG: Node response body:", node_response.text)

        log_message(conn, {
            "direction": "outbound",
            "channel": "system",
            "to": email,
            "from": "River City Backend",
            "body": f"Node.js email service triggered. Status: {node_response.status_code}, Body: {node_response.text}",
            "status": "sent",
            "relatedLeadId": client_id
        })

    except Exception as e:
        print("ERROR: Node.js email service failed:", e)

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
