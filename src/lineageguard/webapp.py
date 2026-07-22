from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lineageguard.analyzer import review_sql
from lineageguard.models import DatasetContext, ReviewReport


class ReviewRequest(BaseModel):
    sql: str
    context: DatasetContext
    dialect: str | None = None


def create_app() -> FastAPI:
    application = FastAPI(title="LineageGuard", version="0.1.0")
    index_path = Path(__file__).parent / "static" / "index.html"

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(index_path)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/review")
    def review(request: ReviewRequest) -> ReviewReport:
        return review_sql(request.sql, request.context, dialect=request.dialect)

    return application


app = create_app()
