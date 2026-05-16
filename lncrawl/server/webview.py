from contextlib import suppress
import logging
import socket
import subprocess
import threading
import time
import webbrowser

from ..context import ctx
from ..enums import UserRole
from ..utils.browser_detect import find_chrome_executables, find_edge_executables, pick_executable
from ..utils.sockets import free_port

logger = logging.getLogger(__name__)


def _start_server(host: str, port: int, timeout: float = 60):
    from ..commands.server import server

    t = threading.Thread(
        daemon=True,
        name="server",
        target=server,
        kwargs=dict(
            host=host,
            port=port,
        ),
    )
    t.start()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return t
        except OSError:
            pass
    return None


def _start_app_in_browser(url: str, storage_path: str):
    binaries = find_chrome_executables()
    if not binaries:
        binaries = find_edge_executables()
    if not binaries:
        return None
    binary = pick_executable(binaries)

    logger.info(f"Opening app-mode browser: {binary}")
    args = [
        str(binary),
        f"--app={url}",
        "--new-window",
        "--window-size=1280,720",
        f"--user-data-dir={storage_path}",
    ]
    return subprocess.Popen(args)


def start() -> None:
    host = "localhost"
    port = free_port(host, 31580)

    ctx.setup(
        log_level="INFO",
        reset_db_on_failure=True,
    )
    ctx.logger.progress_bar = False

    token = ctx.users.generate_token(
        user=ctx.users.get_admin(),
        expiry_minutes=100 * 365 * 24 * 60,  # 100 years
        scopes=[UserRole.LOCAL],
    )
    url = f"http://{host}:{port}/?authToken={token}"

    storage_path = str(ctx.config.app.app_dir / "app-browser")
    proc = _start_app_in_browser(url, storage_path)

    try:
        server_thread = _start_server(host, port)
        if not server_thread:
            raise Exception("Server failed to start")

        if not proc:
            logger.warning("Falling back to system browser")
            webbrowser.open(url)

        with suppress(KeyboardInterrupt):
            while not proc or proc.poll() is None:
                with suppress(TimeoutError):
                    server_thread.join(0.1)

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(2)
            except BaseException:
                proc.kill()

        ctx.destroy()
