from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.services.storage_service import LOCAL_STORAGE_ROOT

app = FastAPI(title="DocuShield AI")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.mount(
    "/local-storage",
    StaticFiles(directory=LOCAL_STORAGE_ROOT, check_dir=False),
    name="local-storage",
)

@app.get("/")
def root():
    return {"message": "DocuShield API running"}
