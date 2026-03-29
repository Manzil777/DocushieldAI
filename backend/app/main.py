from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.routes.auth import router as auth_router

app = FastAPI(title="DocuShield AI")

app.include_router(health_router)
app.include_router(auth_router)

@app.get("/")
def root():
    return {"message": "DocuShield API running"}
