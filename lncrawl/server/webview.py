import logging
import socket
import threading

import webview

from ..commands.server import server
from ..context import ctx
from ..dao.enums import UserRole

logger = logging.getLogger(__name__)


def start() -> None:
    host = "localhost"

    # Find an available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        port = s.getsockname()[1]

    ctx.setup(reset_db_on_failure=True)
    token = ctx.users.generate_token(
        user=ctx.users.get_admin(),
        expiry_minutes=100 * 365 * 24 * 60,  # 100 years
        scopes=[UserRole.LOCAL],
    )

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

    webview.create_window(
        "Lightnovel Crawler",
        f"http://{host}:{port}/?authToken={token}",
        # maximized=True,
        width=1280,
        height=800,
    )
    webview.start()
