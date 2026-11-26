import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import engine
from app.migrations import sync_schema
from app.routes.ussd import router as ussd_router
from app.routes.sms import router as sms_router
from app.routes.dashboard import router as dashboard_router
from app import models  # noqa: F401
from app.services.weekly_reports import weekly_report_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    sync_schema(engine)  # creates new tables/columns in an existing database
    task = asyncio.create_task(weekly_report_scheduler()) if settings.enable_scheduler else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="BakiShule", description="School attendance early-warning system", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ussd_router)
app.include_router(sms_router)
app.include_router(dashboard_router)


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"
