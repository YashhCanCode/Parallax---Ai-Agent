import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')

settings = get_settings()
log = logging.getLogger("finsight.watchlist")


async def _watchlist_loop(minutes: int) -> None:
    from app.agents.watchlist import check_all
    from app.db import watchlist_rows
    from app.integrations.meterless.hmem import HmemClient

    while True:
        await asyncio.sleep(minutes * 60)
        try:
            rows = watchlist_rows()
            if rows:
                hmem = HmemClient(settings.hmem_url) if settings.hmem_enabled else None
                reports = await check_all(rows, settings, hmem)
                log.info("scheduled watchlist check: %s", [(r["ticker"], len(r.get("changes", []))) for r in reports])
        except Exception:  # noqa: BLE001 - keep the loop alive; the error is logged
            log.exception("scheduled watchlist check failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_watchlist_loop(settings.watchlist_check_minutes)) if settings.watchlist_check_minutes > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Parallax", version="0.1.0", lifespan=lifespan,
              description="Evidence-led financial investigations. Educational use only; not financial advice.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "data_mode": settings.data_mode, "version": app.version}
