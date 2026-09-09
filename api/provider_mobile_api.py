# api/provider_mobile_api.py

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from datetime import datetime, timedelta
import json
import os

from db import get_db   # <-- unified DB dependency

router = APIRouter()
PHOTO_DIR = "job_photos/"


# -----------------------------
# PROVIDER LOGIN
# -----------------------------
@router.post("/provider/login")
def provider_login(email: str, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT id, name FROM providers WHERE email = ?", (email,))
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {
        "provider_id": row["id"],
        "name": row["name"],
        "message": "Login successful"
    }


# -----------------------------
# TODAY'S JOBS
# -----------------------------
@router.get("/provider/{provider_id}/today")
def provider_today(provider_id: int, conn=Depends(get_db)):
    today = datetime.now().strftime("%Y-%m-%d")

    cur = conn.cursor()

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            j.id AS job_id,
            c.name AS client_name,
            c.address AS client_address,
            st.name AS service_name,
            e.price
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN jobs j           ON j.estimate_id = e.id
        JOIN clients c        ON a.client_id = c.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = ? AND a.date = ?
        ORDER BY a.start_time ASC
    """, (provider_id, today))

    rows = cur.fetchall()

    return [
        {
            "appointment_id": r["appointment_id"],
            "job_id": r["job_id"],
            "client_name": r["client_name"],
            "client_address": r["client_address"],
            "service": r["service_name"],
            "price": r["price"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
        }
        for r in rows
    ]


# -----------------------------
# UPCOMING JOBS (next 7 days)
# -----------------------------
@router.get("/provider/{provider_id}/upcoming")
def provider_upcoming(provider_id: int, conn=Depends(get_db)):
    today = datetime.now()
    end = today + timedelta(days=7)

    cur = conn.cursor()

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            j.id AS job_id,
            c.name AS client_name,
            st.name AS service_name,
            e.price
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN jobs j           ON j.estimate_id = e.id
        JOIN clients c        ON a.client_id = c.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = ?
          AND a.date BETWEEN ? AND ?
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
            "job_id": r["job_id"],
            "client_name": r["client_name"],
            "service": r["service_name"],
            "price": r["price"],
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

    cur = conn.cursor()

    cur.execute("""
        SELECT 
            a.id AS appointment_id,
            a.date,
            a.start_time,
            a.end_time,
            a.status,
            j.id AS job_id,
            c.name AS client_name,
            c.address AS client_address,
            st.name AS service_name,
            e.price
        FROM appointments a
        JOIN estimates e      ON a.estimate_id = e.id
        JOIN jobs j           ON j.estimate_id = e.id
        JOIN clients c        ON a.client_id = c.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE e.provider_id = ?
          AND a.date BETWEEN ? AND ?
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
            "job_id": r["job_id"],
            "client_name": r["client_name"],
            "client_address": r["client_address"],
            "service": r["service_name"],
            "price": r["price"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "status": r["status"],
            "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
        })

    return week


# -----------------------------
# JOB DETAILS
# -----------------------------
@router.get("/provider/job/{job_id}")
def provider_job_details(job_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            j.id AS job_id,
            j.status,
            e.id AS estimate_id,
            e.price,
            e.duration_minutes,
            e.linear_feet,
            e.square_feet,
            e.stories,
            e.add_ons,
            st.name AS service_name,
            st.category AS service_category,
            c.name AS client_name,
            c.phone AS client_phone,
            c.address AS client_address
        FROM jobs j
        JOIN estimates e ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        JOIN clients c ON j.client_id = c.id
        WHERE j.id = ?
    """, (job_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": r["job_id"],
        "status": r["status"],
        "service": r["service_name"],
        "category": r["service_category"],
        "price": r["price"],
        "duration_minutes": r["duration_minutes"],
        "linear_feet": r["linear_feet"],
        "square_feet": r["square_feet"],
        "stories": r["stories"],
        "add_ons": json.loads(r["add_ons"]) if r["add_ons"] else {},
        "client_name": r["client_name"],
        "client_phone": r["client_phone"],
        "client_address": r["client_address"],
        "navigate_link": f"https://maps.google.com/?q={r['client_address']}"
    }


# -----------------------------
# START JOB
# -----------------------------
@router.put("/provider/job/{job_id}/start")
def provider_start_job(job_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE jobs
        SET status = 'in_progress', updated_at = ?
        WHERE id = ?
    """, (now, job_id))

    conn.commit()

    return {"job_id": job_id, "status": "in_progress"}


# -----------------------------
# COMPLETE JOB
# -----------------------------
@router.put("/provider/job/{job_id}/complete")
def provider_complete_job(job_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE jobs
        SET status = 'completed', updated_at = ?
        WHERE id = ?
    """, (now, job_id))

    conn.commit()

    return {"job_id": job_id, "status": "completed"}


# -----------------------------
# UPLOAD JOB PHOTOS
# -----------------------------
@router.post("/provider/job/{job_id}/photo")
def provider_upload_photo(job_id: int, file: UploadFile = File(...)):
    if not os.path.exists(PHOTO_DIR):
        os.makedirs(PHOTO_DIR)

    filename = f"{job_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    filepath = os.path.join(PHOTO_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(file.file.read())

    return {
        "job_id": job_id,
        "photo_path": filepath,
        "message": "Photo uploaded"
    }


# -----------------------------
# ADD JOB NOTES
# -----------------------------
@router.post("/provider/job/{job_id}/notes")
def provider_add_notes(job_id: int, notes: str, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO job_notes (job_id, notes, created_at)
        VALUES (?, ?, ?)
    """, (job_id, notes, now))

    conn.commit()

    return {"job_id": job_id, "notes": notes, "message": "Notes added"}
