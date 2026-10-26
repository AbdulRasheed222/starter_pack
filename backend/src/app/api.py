from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.ask import router as ask_router
from app.ai.documents import router as documents_router
from app.ai.usage import router as usage_router
from app.config import get_settings
from app.notes import router as notes_router
from app.workspaces import router as workspaces_router

app = FastAPI(title="Starter API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(workspaces_router)
app.include_router(notes_router)
app.include_router(documents_router)
app.include_router(ask_router)
app.include_router(usage_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
