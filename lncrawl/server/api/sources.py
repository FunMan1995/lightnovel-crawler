import asyncio
import traceback
from threading import Thread
from typing import Optional

from fastapi import APIRouter, Body, Path, Security
from fastapi.responses import StreamingResponse

from ...context import ctx
from ...dao import User
from ...utils.log_sink import LogSink
from ..models import (
    CrawlerTestRequest,
    SourceCodeResponse,
    SourcePRRequest,
    SourcePRResponse,
)
from ..security import ensure_user

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
    summary="Test crawler source code against a novel URL",
)
async def test_source(
    req: CrawlerTestRequest = Body(...),
) -> StreamingResponse:
    sink = LogSink()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def put(item: Optional[str]):
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def run():
        try:
            with sink.pipe(put):
                ctx.sources.test_crawler(req.url, req.content, sink)
        except Exception as e:
            sink.print("<!> ERROR:", repr(e))
            sink.print(traceback.format_exc())
        finally:
            put(None)

    Thread(target=run, daemon=True).start()

    async def drain():
        while (item := await queue.get()) is not None:
            yield item

    return StreamingResponse(drain(), media_type="text/event-stream")
