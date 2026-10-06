import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from middleware.trx_id import TRX_ID_HEADER, TrxIdMiddleware
from routers import events, telemetry
from services.engine import engine
from services.simulator import spawn_simulator_task

load_dotenv()

TELEMETRY_FILL_PATH = f"{telemetry.router.prefix}{telemetry.FILL_ROUTE}"

_default_ledger_host = os.getenv("API_HOST", "127.0.0.1")
_default_ledger_port = os.getenv("API_PORT", "8000")
DEFAULT_CENTRAL_LEDGER_URL = (
    f"http://{_default_ledger_host}:{_default_ledger_port}{TELEMETRY_FILL_PATH}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    simulator_task = spawn_simulator_task(engine)
    try:
        yield
    finally:
        simulator_task.cancel()
        try:
            await simulator_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="WIP Exception Engine API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[TRX_ID_HEADER],
)
app.add_middleware(TrxIdMiddleware)

app.include_router(telemetry.router)
app.include_router(events.router)


@app.get("/")
def read_root():
    return {
        "message": "WIP Exception Engine API is running. Access /docs for Swagger UI.",
        "telemetry_fill_endpoint": TELEMETRY_FILL_PATH,
        "central_ledger_url_default": DEFAULT_CENTRAL_LEDGER_URL,
    }
