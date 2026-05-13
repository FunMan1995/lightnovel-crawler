import asyncio
import logging
import time

from fastapi import APIRouter, Query, WebSocket, status

from ...context import ctx

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/lsp")
async def lsp_proxy(ws: WebSocket, token: str = Query()):
    """Proxy WebSocket connections to the pylsp subprocess."""
    try:
        user = ctx.users.verify_token(token)
        if not user.is_active and not user.is_admin:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # restart it on demand.
    if not ctx.lsp.is_running:
        ctx.lsp.restart_if_needed()

    # Always connect to the local process; 0.0.0.0 is a listen wildcard,
    # not a valid connect destination.
    host = "127.0.0.1" if ctx.lsp.host == "0.0.0.0" else ctx.lsp.host
    if not ctx.lsp.is_running or not await _wait_for_lsp_ready(host, ctx.lsp.port):
        await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await ws.accept()

    try:
        await _relay_tcp(ws, host, ctx.lsp.port)
    except Exception:
        logger.debug("LSP proxy session ended", exc_info=True)


async def _wait_for_lsp_ready(host: str, port: int, timeout: float = 5.0) -> bool:
    """Return True once the LSP port accepts TCP connections, False on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.1)
    return False


async def _relay_tcp(client: WebSocket, host: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)

    async def _forward_to_upstream():
        try:
            while True:
                body = (await client.receive_text()).encode()
                writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
        except Exception:
            pass

    async def _forward_to_client():
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = (await reader.readline()).decode("ascii").strip()
                    if not line:
                        break
                    k, _, v = line.partition(":")
                    headers[k.strip().lower()] = v.strip()
                length = int(headers.get("content-length", 0))
                if not length:
                    break
                body = await reader.readexactly(length)
                await client.send_text(body.decode())
        except Exception:
            pass

    tasks = [
        asyncio.create_task(_forward_to_upstream()),
        asyncio.create_task(_forward_to_client()),
    ]
    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    writer.close()
