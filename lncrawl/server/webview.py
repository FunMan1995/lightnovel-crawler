import logging
import socket
import threading
import time

import webview

from ..assets.htmls import loading_html
from ..context import ctx
from ..enums import UserRole
from ..utils.sockets import free_port

logger = logging.getLogger(__name__)


def _wait_for_server(host: str, port: int, timeout: float = 60) -> bool:
    from ..commands.server import server

    t = threading.Thread(
        target=server,
        kwargs={
            "host": host,
            "port": port,
        },
        daemon=True,
        name="server",
    )
    t.start()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def start() -> None:
    window = webview.create_window(
        "Lightnovel Crawler",
        html=loading_html(),
        width=1280,
        height=800,
    )

    def _boot():
        ctx.setup(reset_db_on_failure=True)
        ctx.logger.progress_bar = False
        token = ctx.users.generate_token(
            user=ctx.users.get_admin(),
            expiry_minutes=100 * 365 * 24 * 60,  # 100 years
            scopes=[UserRole.LOCAL],
        )

        host = "localhost"
        port = free_port(host, 31580)
        if window and _wait_for_server(host, port):
            window.load_url(f"http://{host}:{port}/?authToken={token}")

    storage_path = str(ctx.config.app.app_dir / "webview")
    try:
        webview.start(
            func=_boot,
            private_mode=False,
            storage_path=storage_path,
        )
    except Exception:
        logger.exception("Webview window exited with an error")

    ctx.destroy()
