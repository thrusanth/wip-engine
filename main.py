import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import telemetry, events

load_dotenv()

# Canonical path for edge interceptor / recovery workers (POST).
TELEMETRY_FILL_PATH = f"{telemetry.router.prefix}{telemetry.FILL_ROUTE}"

_default_ledger_host = os.getenv("API_HOST", "127.0.0.1")
_default_ledger_port = os.getenv("API_PORT", "8000")
DEFAULT_CENTRAL_LEDGER_URL = (
    f"http://{_default_ledger_host}:{_default_ledger_port}{TELEMETRY_FILL_PATH}"
)

app = FastAPI(title="WIP Exception Engine API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(telemetry.router)
app.include_router(events.router)

@app.get("/")
def read_root():
    return {
        "message": "WIP Exception Engine API is running. Access /docs for Swagger UI.",
        "telemetry_fill_endpoint": TELEMETRY_FILL_PATH,
        "central_ledger_url_default": DEFAULT_CENTRAL_LEDGER_URL,
    }