# api/notifications_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import json

from db import get_db   # <-- unified DB dependency

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
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    return cur.fetchone()


def get_provider(conn, provider_id: int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
    return cur.fetchone()


def get_estimate_details(conn, estimate_id: int):
    cur = conn.cursor()
    cur.execute("""
        SELECT e.*, st.name AS service_name, st.category AS service_category
        FROM estimates e
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.id = ?
    """, (estimate_id,))
    return cur.fetchone()


# -----------------------------
# NOTIFICATION TEMPLATES
# -----------------------------
def build_confirmation_message(appt, est):
    add_ons = json.loads(est["add_ons"]) if est["add_ons"] else {}

    details = (
        f"Service: {est['service_name']} ({est['service_category']})\n"
        f"Price: ${est['price']}\n"
        f"Duration: {est['duration_minutes']} minutes\n"
    )

    if est["linear_feet"]:
        details += f"Linear Feet: {est['linear_feet']}\n"

    if est["square_feet"]:
        details += f"Square Feet: {est['square_feet']}\n"

    if add_ons:
        details += f"Add-ons: {', '.join(add_ons.keys())}\n"

    return (
        f"Your appointment is confirmed for {appt['date']} at {appt['start_time']}.\n"
        f"{details}"
        f"Reschedule link: /reschedule?appointment_id={appt['id']}&token={appt['reschedule_token']}"
    )


def build_reschedule_message(appt, est, old_date, old_time):
    return (
        f"Your appointment has been rescheduled.\n"
        f"Old time: {old_date} {old_time}\n"
        f"New time: {appt['date']} {appt['start_time']}\n"
        f"Service: {est['service_name']}\n"
        f"Reschedule link: /reschedule?appointment_id={appt['id']}&token={appt['reschedule_token']}"
    )


def build_cancellation_message(appt, est):
    return (
        f"Your appointment for {est['service_name']} on {appt['date']} at {appt['start_time']} "
        f"has been cancelled.\n"
        f"If this was a mistake, you can reschedule using your link."
    )


# -----------------------------
# SEND CONFIRMATION
# -----------------------------
@router.post("/notify/confirmation")
def send_confirmation(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    est = get_estimate_details(conn, appt["estimate_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_confirmation_message(appt, est)

    send_email(client["email"], "Appointment Confirmed", message)
    send_sms(client["phone"], f"Confirmed: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "New Appointment Scheduled", message)

    return {"status": "sent", "type": "confirmation"}


# -----------------------------
# SEND RESCHEDULE NOTIFICATION
# -----------------------------
@router.post("/notify/reschedule")
def send_reschedule_notification(appointment_id: int, old_date: str, old_time: str, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    est = get_estimate_details(conn, appt["estimate_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_reschedule_message(appt, est, old_date, old_time)

    send_email(client["email"], "Appointment Rescheduled", message)
    send_sms(client["phone"], f"Rescheduled: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "Appointment Rescheduled", message)

    return {"status": "sent", "type": "reschedule"}


# -----------------------------
# SEND CANCELLATION NOTIFICATION
# -----------------------------
@router.post("/notify/cancel")
def send_cancel_notification(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    appt = cur.fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    est = get_estimate_details(conn, appt["estimate_id"])
    client = get_client(conn, appt["client_id"])
    provider = get_provider(conn, appt["provider_id"])

    message = build_cancellation_message(appt, est)

    send_email(client["email"], "Appointment Cancelled", message)
    send_sms(client["phone"], f"Cancelled: {appt['date']} at {appt['start_time']}")
    send_email(provider["email"], "Appointment Cancelled", message)

    return {"status": "sent", "type": "cancel"}
