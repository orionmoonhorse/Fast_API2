# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

app = FastAPI()

# ============================
# CORS
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# ROUTER IMPORTS
# ============================
from api.provider_mobile_api import router as provider_mobile_router
from api.provider_dashboard_api import router as provider_dashboard_router
from api.reschedule_api import router as reschedule_router
from api.availability_api import router as availability_router
from api.admin_dashboard_api import router as admin_dashboard_router
from api.appointments_api import router as appointments_router
from api.cancel_api import router as cancel_router
from api.client_dashboard_api import router as client_dashboard_router
from api.client_payment_api import router as client_payment_router
from api.client_portal_api import router as client_portal_router
from api.job_api import router as job_router
from api.notifications_api import router as notifications_router
from api.services_api import router as services_router
from api.booking_api import router as booking_router

# ============================
# ROUTER MOUNTING
# ============================
app.include_router(provider_mobile_router)
app.include_router(provider_dashboard_router)
app.include_router(reschedule_router)
app.include_router(availability_router)
app.include_router(admin_dashboard_router)
app.include_router(appointments_router)
app.include_router(cancel_router)
app.include_router(client_dashboard_router)
app.include_router(client_payment_router)
app.include_router(client_portal_router)
app.include_router(job_router)
app.include_router(notifications_router)
app.include_router(services_router)
app.include_router(booking_router)

# ============================
# OPTIONS PREFLIGHT HANDLER
# ============================
@app.options("/{path:path}")
def preflight_handler(path: str):
    return Response(status_code=200)

# ============================
# ROOT
# ============================
@app.get("/")
def root():
    return {"message": "Backend is running"}
