# api/job_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from db import get_db   # <-- unified DB dependency

router = APIRouter()


# -----------------------------
# CREATE JOB FROM ESTIMATE
# -----------------------------
@router.post("/job/create")
def create_job(estimate_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    # Fetch estimate
    cur.execute("""
        SELECT client_id, service_type_id
        FROM estimates
        WHERE id = ?
    """, (estimate_id,))
    est = cur.fetchone()

    if not est:
        raise HTTPException(status_code=404, detail="Estimate not found")

    client_id = est["client_id"]

    # Create job
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO jobs (estimate_id, client_id, status, created_at, updated_at)
        VALUES (?, ?, 'pending', ?, ?)
    """, (estimate_id, client_id, now, now))

    conn.commit()
    job_id = cur.lastrowid

    return {
        "job_id": job_id,
        "estimate_id": estimate_id,
        "client_id": client_id,
        "status": "pending",
        "message": "Job created and ready for scheduling"
    }


# -----------------------------
# GET JOB DETAILS
# -----------------------------
@router.get("/job/{job_id}")
def get_job(job_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT j.*, 
               e.linear_feet, e.square_feet, e.stories,
               e.add_ons, e.price, e.duration_minutes,
               st.name AS service_name, st.category AS service_category
        FROM jobs j
        JOIN estimates e      ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE j.id = ?
    """, (job_id,))

    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": row["id"],
        "status": row["status"],
        "service": row["service_name"],
        "category": row["service_category"],
        "price": row["price"],
        "duration_minutes": row["duration_minutes"],
        "linear_feet": row["linear_feet"],
        "square_feet": row["square_feet"],
        "stories": row["stories"],
        "add_ons": row["add_ons"],
        "estimate_id": row["estimate_id"],
        "client_id": row["client_id"],
        "provider_id": row["provider_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


# -----------------------------
# UPDATE JOB STATUS
# -----------------------------
@router.put("/job/{job_id}/status")
def update_job_status(job_id: int, status: str, conn=Depends(get_db)):
    valid_statuses = [
        "pending",
        "scheduled",
        "in_progress",
        "completed",
        "cancelled"
    ]

    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE jobs
        SET status = ?, updated_at = ?
        WHERE id = ?
    """, (status, now, job_id))

    conn.commit()

    return {
        "job_id": job_id,
        "status": status,
        "message": "Job status updated"
    }


# -----------------------------
# ASSIGN PROVIDER TO JOB
# -----------------------------
@router.put("/job/{job_id}/assign")
def assign_provider(job_id: int, provider_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    # Validate job
    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate provider
    cur.execute("SELECT id FROM providers WHERE id = ?", (provider_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Provider not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE jobs
        SET provider_id = ?, updated_at = ?
        WHERE id = ?
    """, (provider_id, now, job_id))

    conn.commit()

    return {
        "job_id": job_id,
        "provider_id": provider_id,
        "message": "Provider assigned to job"
    }
