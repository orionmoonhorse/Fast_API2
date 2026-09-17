# api/provider_mobile_api.py

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from datetime import datetime, timedelta
import json
import os
import psycopg2.extras

from db import get_db

router = APIRouter()
PHOTO_DIR = "appointment_photos/"


# -----------------------------
# PROVIDER LOGIN
# -----------------------------
@router.post("/provider/login")
def provider_login(email: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, name FROM providers WHERE email = %s", (email,))
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {
        "provider_id": row["id"],
        "name": row["name"],
        "message": "Login successful"
    }


# -----------------------------
# TODAY'S APPOINTMENTS
# -----------------------------
@router.get("/provider/{provider_id}/today")
def provider_today(provider_id: int, conn=Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            b.id AS booking_id,
            b.services,
            b.issue_description,
            b.estimate_json,
            c.name AS client_name,
            c.address AS client_address
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        JOIN clients c ON a.client_id = c.id
        WHERE a.provider_id = %s AND a.date = %s
        ORDER BY a.start_time ASC
    """, (provider_id, today))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "booking_id": r["booking_id"],
            "client_name": r["client_name"],
            "client_address": r["client_address"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "estimate": r["estimate_json"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
        }
        for r in rows
    ]


# -----------------------------
# UPCOMING APPOINTMENTS (next 7 days)
# -----------------------------
@router.get("/provider/{provider_id}/upcoming")
def provider_upcoming(provider_id: int, conn=Depends(get_db)):
    today = datetime.now()
    end = today + timedelta(days=7)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            b.id AS booking_id,
            b.services,
            b.issue_description,
            c.name AS client_name
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        JOIN clients c ON a.client_id = c.id
        WHERE a.provider_id = %s
          AND a.date BETWEEN %s AND %s
        ORDER BY a.date ASC, a.start_time ASC
    """, (
        provider_id,
        today.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    ))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "booking_id": r["booking_id"],
            "client_name": r["client_name"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "date": r["date"],
            "start_time": r["start_time"]
        }
        for r in rows
    ]


# -----------------------------
# WEEKLY SCHEDULE
# -----------------------------
@router.get("/provider/{provider_id}/week")
def provider_week(provider_id: int, conn=Depends(get_db)):
    today = datetime.now().date()
    end = today + timedelta(days=6)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            b.id AS booking_id,
            b.services,
            b.issue_description,
            b.estimate_json,
            c.name AS client_name,
            c.address AS client_address
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        JOIN clients c ON a.client_id = c.id
        WHERE a.provider_id = %s
          AND a.date BETWEEN %s AND %s
        ORDER BY a.date ASC, a.start_time ASC
    """, (
        provider_id,
        today.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d")
    ))

    rows = cur.fetchall()

    week = {}
    for r in rows:
        d = r["date"]
        if d not in week:
            week[d] = []

        week[d].append({
            "appointment_id": r["appointment_id"],
            "booking_id": r["booking_id"],
            "client_name": r["client_name"],
            "client_address": r["client_address"],
            "services": r["services"],
            "issue_description": r["issue_description"],
            "estimate": r["estimate_json"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
        })

    return week


# -----------------------------
# APPOINTMENT DETAILS
# -----------------------------
@router.get("/provider/appointment/{appointment_id}")
def provider_appointment_details(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            a.*,
            b.services,
            b.issue_description,
            b.estimate_json,
            c.name AS client_name,
            c.phone AS client_phone,
            c.address AS client_address
        FROM appointments a
        JOIN bookings b ON a.booking_id = b.id
        JOIN clients c ON a.client_id = c.id
        WHERE a.id = %s
    """, (appointment_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {
        "appointment_id": r["id"],
        "booking_id": r["booking_id"],
        "provider_id": r["provider_id"],
        "client_name": r["client_name"],
        "client_phone": r["client_phone"],
        "client_address": r["client_address"],
        "services": r["services"],
        "issue_description": r["issue_description"],
        "estimate": r["estimate_json"],
        "date": r["date"],
        "start_time": r["start_time"],
        "end_time": r["end_time"],
        "status": r["status"],
        "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
    }


# -----------------------------
# START APPOINTMENT
# -----------------------------
@router.put("/provider/appointment/{appointment_id}/start")
def provider_start_appointment(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Appointment not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE appointments
        SET status = 'in_progress', updated_at = %s
        WHERE id = %s
    """, (now, appointment_id))

    conn.commit()

    return {"appointment_id": appointment_id, "status": "in_progress"}


# -----------------------------
# COMPLETE APPOINTMENT
# -----------------------------
@router.put("/provider/appointment/{appointment_id}/complete")
def provider_complete_appointment(appointment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Appointment not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE appointments
        SET status = 'completed', updated_at = %s
        WHERE id = %s
    """, (now, appointment_id))

    conn.commit()

    return {"appointment_id": appointment_id, "status": "completed"}


# -----------------------------
# UPLOAD APPOINTMENT PHOTOS
# -----------------------------
@router.post("/provider/appointment/{appointment_id}/photo")
def provider_upload_photo(appointment_id: int, file: UploadFile = File(...)):
    if not os.path.exists(PHOTO_DIR):
        os.makedirs(PHOTO_DIR)

    filename = f"{appointment_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    filepath = os.path.join(PHOTO_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(file.file.read())

    return {
        "appointment_id": appointment_id,
        "photo_path": filepath,
        "message": "Photo uploaded"
    }


# -----------------------------
# ADD APPOINTMENT NOTES
# -----------------------------
@router.post("/provider/appointment/{appointment_id}/notes")
def provider_add_notes(appointment_id: int, notes: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Appointment not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO appointment_notes (appointment_id, notes, created_at)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (appointment_id, notes, now))

    note_id = cur.fetchone()["id"]
    conn.commit()

    return {"appointment_id": appointment_id, "note_id": note_id, "notes": notes, "message": "Notes added"}
