from fastapi import APIRouter, Body, Path, Security
from fastapi.responses import StreamingResponse

from ...context import ctx
from ...dao import User
from ..models import (
    CrawlerTestRequest,
    SourceCodeResponse,
    SourcePRRequest,
    SourcePRResponse,
)
from ..security import ensure_admin, ensure_user

router = APIRouter()


@router.get(
    "/{source_id}/code",
    summary="Get source crawler file content",
)
def get_source_code(source_id: str) -> SourceCodeResponse:
    return ctx.github.get_source_code(source_id)


@router.post(
    "/{source_id}/pr",
    summary="Create a GitHub PR with an edited source crawler",
)
def create_source_pr(
    source_id: str = Path(),
    req: SourcePRRequest = Body(...),
    user: User = Security(ensure_user),
) -> SourcePRResponse:
    return ctx.github.create_source_pr(user, source_id, req)


@router.post(
    "/test",
    summary="Test crawler source code against a novel URL (Admin only)",
)
async def test_source(
    req: CrawlerTestRequest = Body(...),
    user: User = Security(ensure_admin),
) -> StreamingResponse:
    return StreamingResponse(
        ctx.sources.test_source(user, req.url, req.content),
        media_type="text/event-stream",
    )
