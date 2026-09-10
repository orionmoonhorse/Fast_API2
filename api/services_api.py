# api/service_types_api.py

from fastapi import APIRouter, HTTPException, Depends
import psycopg2.extras
from db import get_db

router = APIRouter()


# -----------------------------
# GET ALL SERVICE TYPES
# -----------------------------
@router.get("/service-types")
def get_service_types(conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, name, category, base_price, price_per_unit, unit_type, active
        FROM service_types
        WHERE active = 1
    """)

    rows = cur.fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "base_price": r["base_price"],
            "price_per_unit": r["price_per_unit"],
            "unit_type": r["unit_type"],
            "active": r["active"]
        }
        for r in rows
    ]


# -----------------------------
# GET SINGLE SERVICE TYPE
# -----------------------------
@router.get("/service-types/{service_type_id}")
def get_service_type(service_type_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, name, category, base_price, price_per_unit, unit_type, active
        FROM service_types
        WHERE id = %s
    """, (service_type_id,))

    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Service type not found")

    return row


# -----------------------------
# CREATE SERVICE TYPE
# -----------------------------
@router.post("/service-types")
def create_service_type(
    name: str,
    category: str,
    base_price: float,
    price_per_unit: float,
    unit_type: str,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        INSERT INTO service_types (name, category, base_price, price_per_unit, unit_type, active)
        VALUES (%s, %s, %s, %s, %s, 1)
        RETURNING id
    """, (name, category, base_price, price_per_unit, unit_type))

    new_id = cur.fetchone()["id"]
    conn.commit()

    return {"status": "success", "service_type_id": new_id}


# -----------------------------
# UPDATE SERVICE TYPE
# -----------------------------
@router.put("/service-types/{service_type_id}")
def update_service_type(
    service_type_id: int,
    name: str = None,
    category: str = None,
    base_price: float = None,
    price_per_unit: float = None,
    unit_type: str = None,
    active: int = None,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    fields = []
    values = []

    if name:
        fields.append("name = %s")
        values.append(name)

    if category:
        fields.append("category = %s")
        values.append(category)

    if base_price is not None:
        fields.append("base_price = %s")
        values.append(base_price)

    if price_per_unit is not None:
        fields.append("price_per_unit = %s")
        values.append(price_per_unit)

    if unit_type:
        fields.append("unit_type = %s")
        values.append(unit_type)

    if active is not None:
        fields.append("active = %s")
        values.append(active)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(service_type_id)

    query = f"UPDATE service_types SET {', '.join(fields)} WHERE id = %s"

    cur.execute(query, tuple(values))
    conn.commit()

    return {"status": "updated", "service_type_id": service_type_id}


# -----------------------------
# DEACTIVATE SERVICE TYPE
# -----------------------------
@router.delete("/service-types/{service_type_id}")
def delete_service_type(service_type_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        UPDATE service_types
        SET active = 0
        WHERE id = %s
    """, (service_type_id,))

    conn.commit()

    return {"status": "deactivated", "service_type_id": service_type_id}
