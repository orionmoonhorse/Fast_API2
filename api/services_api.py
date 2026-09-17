# api/service_types_api.py

from fastapi import APIRouter, HTTPException, Depends
import psycopg2.extras
from db import get_db

router = APIRouter()


# -----------------------------
# GET ALL SERVICES
# -----------------------------
@router.get("/services")
def get_services(conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, name, default_duration, default_estimate_min, default_estimate_max, active
        FROM services
        WHERE active = 1
    """)

    rows = cur.fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "default_duration": r["default_duration"],
            "default_estimate_min": r["default_estimate_min"],
            "default_estimate_max": r["default_estimate_max"],
            "active": r["active"]
        }
        for r in rows
    ]


# -----------------------------
# GET SINGLE SERVICE
# -----------------------------
@router.get("/services/{service_id}")
def get_service(service_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, name, default_duration, default_estimate_min, default_estimate_max, active
        FROM services
        WHERE id = %s
    """, (service_id,))

    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Service not found")

    return row


# -----------------------------
# CREATE SERVICE
# -----------------------------
@router.post("/services")
def create_service(
    name: str,
    default_duration: int,
    default_estimate_min: float,
    default_estimate_max: float,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        INSERT INTO services (name, default_duration, default_estimate_min, default_estimate_max, active)
        VALUES (%s, %s, %s, %s, 1)
        RETURNING id
    """, (name, default_duration, default_estimate_min, default_estimate_max))

    new_id = cur.fetchone()["id"]
    conn.commit()

    return {"status": "success", "service_id": new_id}


# -----------------------------
# UPDATE SERVICE
# -----------------------------
@router.put("/services/{service_id}")
def update_service(
    service_id: int,
    name: str = None,
    default_duration: int = None,
    default_estimate_min: float = None,
    default_estimate_max: float = None,
    active: int = None,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    fields = []
    values = []

    if name:
        fields.append("name = %s")
        values.append(name)

    if default_duration is not None:
        fields.append("default_duration = %s")
        values.append(default_duration)

    if default_estimate_min is not None:
        fields.append("default_estimate_min = %s")
        values.append(default_estimate_min)

    if default_estimate_max is not None:
        fields.append("default_estimate_max = %s")
        values.append(default_estimate_max)

    if active is not None:
        fields.append("active = %s")
        values.append(active)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(service_id)

    query = f"UPDATE services SET {', '.join(fields)} WHERE id = %s"

    cur.execute(query, tuple(values))
    conn.commit()

    return {"status": "updated", "service_id": service_id}


# -----------------------------
# DEACTIVATE SERVICE
# -----------------------------
@router.delete("/services/{service_id}")
def delete_service(service_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        UPDATE services
        SET active = 0
        WHERE id = %s
    """, (service_id,))

    conn.commit()

    return {"status": "deactivated", "service_id": service_id}
