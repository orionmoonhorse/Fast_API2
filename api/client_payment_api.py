# api/client_payment_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import psycopg2.extras
from db import get_db

router = APIRouter()


# -----------------------------
# GET INVOICE FOR A BOOKING
# -----------------------------
@router.get("/payment/invoice/{booking_id}")
def get_invoice(booking_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            b.id AS booking_id,
            b.services,
            b.issue_description,
            b.estimate_json,
            c.name AS client_name,
            c.email AS client_email
        FROM bookings b
        JOIN clients c ON b.client_id = c.id
        WHERE b.id = %s
    """, (booking_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Booking not found")

    return {
        "booking_id": r["booking_id"],
        "services": r["services"],
        "issue_description": r["issue_description"],
        "estimate": r["estimate_json"],
        "client_name": r["client_name"],
        "client_email": r["client_email"],
        "message": "Invoice generated"
    }


# -----------------------------
# MAKE PAYMENT (MANUAL)
# -----------------------------
@router.post("/payment/pay")
def make_payment(booking_id: int, client_id: int, amount: float, method: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Validate booking exists
    cur.execute("SELECT id FROM bookings WHERE id = %s", (booking_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Booking not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO payments (booking_id, client_id, amount, method, status, created_at)
        VALUES (%s, %s, %s, %s, 'paid', %s)
        RETURNING id
    """, (booking_id, client_id, amount, method, now))

    payment_id = cur.fetchone()["id"]
    conn.commit()

    return {
        "payment_id": payment_id,
        "booking_id": booking_id,
        "amount": amount,
        "method": method,
        "status": "paid",
        "message": "Payment successful"
    }


# -----------------------------
# SAVE CARD ON FILE
# -----------------------------
@router.post("/payment/save-card")
def save_card(client_id: int, last4: str, brand: str, token: str, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO client_cards (client_id, last4, brand, token, created_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (client_id, last4, brand, token, now))

    card_id = cur.fetchone()["id"]
    conn.commit()

    return {
        "card_id": card_id,
        "client_id": client_id,
        "last4": last4,
        "brand": brand,
        "message": "Card saved successfully"
    }


# -----------------------------
# CHARGE SAVED CARD
# -----------------------------
@router.post("/payment/charge-card")
def charge_saved_card(booking_id: int, client_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get saved card
    cur.execute("""
        SELECT * FROM client_cards
        WHERE client_id = %s
        ORDER BY id DESC LIMIT 1
    """, (client_id,))
    card = cur.fetchone()

    if not card:
        raise HTTPException(status_code=404, detail="No saved card found")

    # Get booking + estimate
    cur.execute("""
        SELECT estimate_json
        FROM bookings
        WHERE id = %s
    """, (booking_id,))
    booking = cur.fetchone()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    estimate = booking["estimate_json"]

    # Determine amount to charge
    # Use max of the estimated range (common practice)
    if "total_estimate" in estimate:
        amount = estimate["total_estimate"]["max"]
    else:
        raise HTTPException(status_code=400, detail="Invalid estimate format")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO payments (booking_id, client_id, amount, method, status, created_at)
        VALUES (%s, %s, %s, %s, 'paid', %s)
        RETURNING id
    """, (booking_id, client_id, amount, f"card:{card['last4']}", now))

    payment_id = cur.fetchone()["id"]
    conn.commit()

    return {
        "payment_id": payment_id,
        "booking_id": booking_id,
        "amount": amount,
        "method": f"card:{card['last4']}",
        "message": "Card charged successfully"
    }


# -----------------------------
# PAYMENT HISTORY
# -----------------------------
@router.get("/payment/history/{client_id}")
def payment_history(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            p.id AS payment_id,
            p.amount,
            p.method,
            p.status,
            p.created_at,
            b.services,
            b.issue_description
        FROM payments p
        JOIN bookings b ON p.booking_id = b.id
        WHERE p.client_id = %s
        ORDER BY p.created_at DESC
    """, (client_id,))

    rows = cur.fetchall()

    return [
        {
            "payment_id": r["payment_id"],
            "amount": r["amount"],
            "method": r["method"],
            "status": r["status"],
            "created_at": r["created_at"],
            "services": r["services"],
            "issue_description": r["issue_description"]
        }
        for r in rows
    ]


# -----------------------------
# PAYMENT RECEIPT
# -----------------------------
@router.get("/payment/receipt/{payment_id}")
def payment_receipt(payment_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            p.id AS payment_id,
            p.amount,
            p.method,
            p.created_at,
            c.name AS client_name,
            c.email AS client_email,
            b.services,
            b.issue_description
        FROM payments p
        JOIN clients c ON p.client_id = c.id
        JOIN bookings b ON p.booking_id = b.id
        WHERE p.id = %s
    """, (payment_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "payment_id": r["payment_id"],
        "client_name": r["client_name"],
        "client_email": r["client_email"],
        "services": r["services"],
        "issue_description": r["issue_description"],
        "amount": r["amount"],
        "method": r["method"],
        "created_at": r["created_at"],
        "message": "Receipt generated"
    }
