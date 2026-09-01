from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_INDEX_PATH = Path(__file__).resolve().parents[2] / "static" / "index.html"


@router.get("/", include_in_schema=False)
def dashboard() -> HTMLResponse:
    return HTMLResponse(_INDEX_PATH.read_text(encoding="utf-8"))
