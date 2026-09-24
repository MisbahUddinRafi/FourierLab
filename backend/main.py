from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
ASSETS_DIR = BASE_DIR / "assets"

for sub in ["audio/samples", "audio/saved", "images/samples", "images/saved"]:
    (ASSETS_DIR / sub).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FourierLab API")

from routes.audio_routes import router as audio_router
app.include_router(audio_router, prefix="/api/audio")

# from routes.image_routes import router as image_router
# app.include_router(image_router, prefix="/api/image")

app.mount("/media", StaticFiles(directory=ASSETS_DIR), name="media")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)