# api/notifications_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import json
import psycopg2.extras

from db import get_db

router = APIRouter()


# -----------------------------
# EMAIL + SMS STUBS
# -----------------------------
def send_email(to: str, subject: str, body: str):
    print(f"[EMAIL] To: {to} | Subject: {subject} | Body: {body}")


def send_sms(to: str, message: str):
    print(f"[SMS] To: {to} | Message: {message}")


# -----------------------------
# FETCH CLIENT + PROVIDER INFO
# -----------------------------
def get_client(conn, client_id: int):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    return cur.fetchone()


def get_provider(conn, provider_id: int):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM providers WHERE id = %s", (provider_id,))
    return cur.fetchone()


def get_booking_details(conn, booking_id: int):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT *
        FROM bookings
        WHERE id = %s
    """, (booking_id,))
    return cur.fetchone()


# -----------------------------
# NOTIFICATION TEMPLATES
# -----------------------------
def build_confirmation_message(appt, booking):
    services = ", ".join(booking["services"])
    estimate = booking["estimate_json"]

    estimate_text = ""
    if estimate and "total_estimate" in estimate:
        est = estimate["total_estimate"]
        estimate_text = f"Estimated Cost: ${est['min']} - ${est['max']}\n"

    return (
        f"Your appointment is confirmed for {appt['date']} at {appt['start_time']}.\n"
        f"Services: {services}\n"
        f"Issue: {booking['issue_description']}\n"
        f"{estimate_text}"
        f"Reschedule link: /reschedule?appointment_id={appt['id']}&token={appt['reschedule_token']}"
    )


def build_reschedule_message(appt, booking, old_date, old_time):
    services = ", ".join(booking["services"])

    return (
        f"Your appointment has been rescheduled.\n"
        f"Old time: {old_date} {old_time}\n"
        f"New time: {appt['date']} {appt['start_time']}\n"
        f"Services: {services}\n"
        f"Reschedule link: /reschedule?appointment_id={appt['id']}&token={appt['reschedule_token']}"
    )


def build_cancellation_message(appt, booking):
    services = ", ".join(booking["services"])

    return (
        f"Your appointment for {services} on {appt['date']} at {appt['start_time']} "
        f"has been cancelled.\n"
        f"If this was a mistake, you can reschedule using your link."
    )


# -----------------------------
# SEND CONFIRMATION
# -----------------------------
@router.post("/notify/confirmation")
def send_confirmation(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    booking = get_booking_details(conn, appt["booking_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_confirmation_message(appt, booking)

    send_email(client["email"], "Appointment Confirmed", message)
    send_sms(client["phone"], f"Confirmed: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "New Appointment Scheduled", message)

    return {"status": "sent", "type": "confirmation"}


# -----------------------------
# SEND RESCHEDULE NOTIFICATION
# -----------------------------
@router.post("/notify/reschedule")
def send_reschedule_notification(appointment_id: int, old_date: str, old_time: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    booking = get_booking_details(conn, appt["booking_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_reschedule_message(appt, booking, old_date, old_time)

    send_email(client["email"], "Appointment Rescheduled", message)
    send_sms(client["phone"], f"Rescheduled: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "Appointment Rescheduled", message)

    return {"status": "sent", "type": "reschedule"}


# -----------------------------
# SEND CANCELLATION NOTIFICATION
# -----------------------------
@router.post("/notify/cancel")
def send_cancel_notification(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    booking = get_booking_details(conn, appt["booking_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_cancellation_message(appt, booking)

    send_email(client["email"], "Appointment Cancelled", message)
    send_sms(client["phone"], f"Cancelled: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "Appointment Cancelled", message)

    return {"status": "sent", "type": "cancel"}
