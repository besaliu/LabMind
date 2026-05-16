from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routers import analytics, instruments, experiments, rag

app = FastAPI(title="LabMind Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics.router)
app.include_router(instruments.router)
app.include_router(experiments.router)
app.include_router(rag.router)

# Serve dashboard static files if the build exists
static_dir = Path(__file__).parent.parent / "dashboard" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="dashboard")


@app.get("/health")
def health():
    return {"status": "ok"}
