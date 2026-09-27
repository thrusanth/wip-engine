from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import telemetry, events

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
    return {"message": "WIP Exception Engine API is running. Access /docs for Swagger UI."}