import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from middleware.trx_id import TRX_ID_HEADER, TrxIdMiddleware
from routers import events, telemetry
from services.engine import engine
from services.simulator import spawn_simulator_task


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
    return {"message": "WIP Exception Engine API is running. Access /docs for Swagger UI."}
