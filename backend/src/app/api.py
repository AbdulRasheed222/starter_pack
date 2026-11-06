import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin import router as admin_router

# [module:ai]
from app.ai.ask import router as ask_router
from app.ai.documents import router as documents_router
from app.ai.usage import router as usage_router

# [/module:ai]
# [module:billing]
from app.billing import router as billing_router

# [/module:billing]
from app.config import get_settings
from app.jobs import work_forever

# [module:notes]
from app.notes import router as notes_router

# [/module:notes]
from app.workspaces import router as workspaces_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs a background job worker in this process, unless jobs run elsewhere (jobs.py)."""
    stop = threading.Event()
    if get_settings().jobs_worker_in_api:
        threading.Thread(target=work_forever, args=(stop,), daemon=True, name="jobs").start()
    yield
    stop.set()


app = FastAPI(title="Starter API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(workspaces_router)
app.include_router(admin_router)
# [module:notes]
app.include_router(notes_router)
# [/module:notes]
# [module:ai]
app.include_router(documents_router)
app.include_router(ask_router)
app.include_router(usage_router)
# [/module:ai]
# [module:billing]
app.include_router(billing_router)
# [/module:billing]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
