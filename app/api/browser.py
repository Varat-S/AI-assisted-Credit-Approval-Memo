"""Local browser entry point for inspecting saved cases."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.api.deps import get_session

router = APIRouter(tags=["browser"])
_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=True,
)


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """UI entry point; evidence inspection and advanced routes remain available."""
    return HTMLResponse(_env.get_template("home.html.j2").render(request=request))


@router.get("/bo", response_class=HTMLResponse)
def business_overview_runs(session: Session = Depends(get_session)) -> HTMLResponse:
    """Case selection for the Business Overview workbench."""
    from app.services.bo.workbench import bo_runs

    return HTMLResponse(
        _env.get_template("bo_workbench.html.j2").render(
            runs=bo_runs(session), view=None))
