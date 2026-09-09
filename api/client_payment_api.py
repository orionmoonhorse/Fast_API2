# api/client_payment_api.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from db import get_db   # <-- unified DB dependency

router = APIRouter()


# -----------------------------
# GET INVOICE FOR A JOB
# -----------------------------
@router.get("/payment/invoice/{job_id}")
def get_invoice(job_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            j.id AS job_id,
            j.status,
            e.price,
            st.name AS service_name,
            c.name AS client_name,
            c.email AS client_email
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
        "service": r["service_name"],
        "client_name": r["client_name"],
        "client_email": r["client_email"],
        "amount_due": r["price"],
        "status": r["status"]
    }


# -----------------------------
# MAKE PAYMENT
# -----------------------------
@router.post("/payment/pay")
def make_payment(job_id: int, client_id: int, amount: float, method: str, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Job not found")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO payments (job_id, client_id, amount, method, status, created_at)
        VALUES (?, ?, ?, ?, 'paid', ?)
    """, (job_id, client_id, amount, method, now))

    conn.commit()
    payment_id = cur.lastrowid

    return {
        "payment_id": payment_id,
        "job_id": job_id,
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
    cur = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO client_cards (client_id, last4, brand, token, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, last4, brand, token, now))

    conn.commit()
    card_id = cur.lastrowid

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
def charge_saved_card(job_id: int, client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM client_cards
        WHERE client_id = ?
        ORDER BY id DESC LIMIT 1
    """, (client_id,))
    card = cur.fetchone()

    if not card:
        raise HTTPException(status_code=404, detail="No saved card found")

    cur.execute("""
        SELECT e.price
        FROM jobs j
        JOIN estimates e ON j.estimate_id = e.id
        WHERE j.id = ?
    """, (job_id,))
    job = cur.fetchone()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    amount = job["price"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO payments (job_id, client_id, amount, method, status, created_at)
        VALUES (?, ?, ?, ?, 'paid', ?)
    """, (job_id, client_id, amount, f"card:{card['last4']}", now))

    conn.commit()
    payment_id = cur.lastrowid

    return {
        "payment_id": payment_id,
        "job_id": job_id,
        "amount": amount,
        "method": f"card:{card['last4']}",
        "message": "Card charged successfully"
    }


# -----------------------------
# PAYMENT HISTORY
# -----------------------------
@router.get("/payment/history/{client_id}")
def payment_history(client_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            p.id AS payment_id,
            p.amount,
            p.method,
            p.status,
            p.created_at,
            st.name AS service_name
        FROM payments p
        JOIN jobs j ON p.job_id = j.id
        JOIN estimates e ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE p.client_id = ?
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
            "service": r["service_name"]
        }
        for r in rows
    ]


# -----------------------------
# PAYMENT RECEIPT
# -----------------------------
@router.get("/payment/receipt/{payment_id}")
def payment_receipt(payment_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            p.id AS payment_id,
            p.amount,
            p.method,
            p.created_at,
            c.name AS client_name,
            c.email AS client_email,
            st.name AS service_name
        FROM payments p
        JOIN clients c ON p.client_id = c.id
        JOIN jobs j ON p.job_id = j.id
        JOIN estimates e ON j.estimate_id = e.id
        JOIN service_types st ON e.service_type_id = st.id
        WHERE p.id = ?
    """, (payment_id,))

    r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "payment_id": r["payment_id"],
        "client_name": r["client_name"],
        "client_email": r["client_email"],
        "service": r["service_name"],
        "amount": r["amount"],
        "method": r["method"],
        "created_at": r["created_at"],
        "message": "Receipt generated"
    }
