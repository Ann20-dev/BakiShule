from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.db import Base, engine
from app.routes.ussd import router as ussd_router
from app.routes.sms import router as sms_router
from app.routes.dashboard import router as dashboard_router
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="BakiShule", description="School attendance early-warning system", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ussd_router)
app.include_router(sms_router)
app.include_router(dashboard_router)


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"
