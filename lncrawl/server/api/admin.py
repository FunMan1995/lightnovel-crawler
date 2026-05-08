import asyncio
from threading import Thread
from typing import List, Optional

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from ...context import ctx
from ...utils.log_queue import LogSink
from ..models.config import ConfigSection, ConfigUpdateRequest
from ..models.sources import CrawlerTestRequest, SourceCodeResponse, SourcePRRequest

# The root router
router = APIRouter()


@router.post("/update-sources", summary="Update sources from the repository")
async def update() -> int:
    return ctx.admin.update_sources()


@router.post("/soft-restart", summary="Reload application context and restart the scheduler")
def soft_restart() -> None:
    ctx.admin.soft_restart()


@router.get("/runner/status", summary="Get runner status")
def status() -> bool:
    return bool(ctx.scheduler.running)


@router.post("/runner/start", summary="Start the runner")
def start() -> bool:
    ctx.scheduler.start()
    return True


@router.post("/runner/stop", summary="Stops the runner")
def stop() -> bool:
    ctx.scheduler.stop()
    return True


@router.get(
    "/configs",
    summary="List application configs",
)
def list_configs() -> List[ConfigSection]:
    return ctx.admin.config_sections()


@router.patch(
    "/configs",
    summary="Update application configs",
)
def patch_configs(
    body: List[ConfigUpdateRequest] = Body(...),
) -> None:
    ctx.admin.update_config(body)


@router.post("/sources/test", summary="Test crawler source code against a novel URL")
async def test_source(req: CrawlerTestRequest = Body(...)) -> StreamingResponse:
    sink = LogSink()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def put(item: Optional[str]):
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def run():
        try:
            with sink.pipe(put):
                ctx.sources.test_crawler(req.url, req.content, sink)
        finally:
            put(None)

    Thread(target=run, daemon=True).start()

    async def drain():
        while (item := await queue.get()) is not None:
            yield item

    return StreamingResponse(drain(), media_type="text/event-stream")


@router.get("/sources/{source_id}/code", summary="Get source crawler file content")
def get_source_code(source_id: str) -> SourceCodeResponse:
    return ctx.github.get_source_code(source_id)


@router.post("/sources/{source_id}/pr", summary="Create a GitHub PR with an edited source crawler")
def create_source_pr(source_id: str, req: SourcePRRequest = Body(...)) -> str:
    return ctx.github.create_source_pr(source_id, req)
