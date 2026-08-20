"""TWT (Trip Without Trap) — FastAPI entrypoint (Phase 1)."""
import os
import logging
from pathlib import Path

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Configure logging BEFORE importing modules that use logger.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s :: %(message)s',
)
logger = logging.getLogger("twt")

from db import db, client, ensure_indexes  # noqa: E402
from auth import router as auth_router  # noqa: E402
from trips import router as trips_router  # noqa: E402
from stops import router as stops_router  # noqa: E402
from attractions import stop_router as attractions_stop_router, trip_router as attractions_trip_router  # noqa: E402
from hotels import stop_router as hotels_stop_router, trip_router as hotels_trip_router  # noqa: E402
from expenses import router as expenses_router  # noqa: E402
from exchange_rates import router as rates_router  # noqa: E402
from summary import router as summary_router  # noqa: E402
from members import trip_router as members_trip_router, invites_router  # noqa: E402
from notifications import trip_router as km_trip_router, notif_router  # noqa: E402
from map_routes import router as map_router  # noqa: E402

app = FastAPI(
    title="TWT — Trip Without Trap",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"app": "TWT", "phase": 1, "status": "ok"}


@api_router.get("/health")
async def health():
    return {"ok": True, "env": os.environ.get("ENV", "dev")}


api_router.include_router(auth_router)
api_router.include_router(trips_router)
api_router.include_router(stops_router)
api_router.include_router(attractions_stop_router)
api_router.include_router(attractions_trip_router)
api_router.include_router(hotels_stop_router)
api_router.include_router(hotels_trip_router)
api_router.include_router(expenses_router)
api_router.include_router(rates_router)
api_router.include_router(summary_router)
api_router.include_router(members_trip_router)
api_router.include_router(invites_router)
api_router.include_router(km_trip_router)
api_router.include_router(notif_router)
api_router.include_router(map_router)
app.include_router(api_router)

# CORS — allow credentials so the httpOnly cookie flows in cross-origin requests.
_cors_env = os.environ.get("CORS_ORIGINS", "*")
_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_origin_regex=".*" if _origins == ["*"] else None,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    await ensure_indexes()
    logger.info("TWT backend started env=%s", os.environ.get("ENV", "dev"))


@app.on_event("shutdown")
async def _on_shutdown():
    client.close()
