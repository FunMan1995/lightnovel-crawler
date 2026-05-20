from contextlib import suppress
import logging
from pathlib import Path
import socket
import subprocess
import threading
import time

from ..assets.images import lncrawl_icon
from ..context import ctx
from ..enums import UserRole
from ..utils.browser_detect import find_chrome_executables, find_edge_executables, pick_executable
from ..utils.sockets import free_port

logger = logging.getLogger(__name__)


def _start_server(host: str, port: int) -> threading.Thread:
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
    return t


def _wait_for_server(host: str, port: int, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return True
        except OSError:
            pass
    return False


def _build_url(host: str, port: int, storage_path: Path):
    saved_url_path = storage_path / "app.url"

    if saved_url_path.is_file():
        return saved_url_path.read_text().strip()

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

    saved_url_path.parent.mkdir(parents=True, exist_ok=True)
    saved_url_path.write_text(url)
    return url


def _start_app_in_browser(url: str, storage_path: Path):
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


def _start_fallback_window(url: str, host: str, port: int) -> None:
    import tkinter as tk
    import webbrowser

    root = tk.Tk()
    root.title("Lightnovel Crawler")
    root.resizable(False, False)
    root.configure(bg="#141414")
    with suppress(Exception):
        root.iconbitmap(str(lncrawl_icon()))

    tk.Label(
        root,
        text="Lightnovel Crawler",
        bg="#141414",
        fg="#e8e8e8",
        font=("Segoe UI", 13, "bold"),
    ).pack(anchor="w", padx=20, pady=(16, 4))

    status_lbl = tk.Label(
        root,
        text="Starting server…",
        bg="#141414",
        fg="#8b949e",
        font=("Segoe UI", 9),
        justify="left",
    )
    status_lbl.pack(anchor="w", padx=20)

    url_frame = tk.Frame(root, bg="#1e1e1e")
    url_frame.pack(fill="x", padx=20, pady=12)
    url_lbl = tk.Label(
        url_frame,
        text=url.split("?")[0],
        bg="#1e1e1e",
        fg="#888888",
        font=("Courier New", 10),
        padx=12,
        pady=8,
    )
    url_lbl.pack(side="left")

    btn_frame = tk.Frame(root, bg="#141414")
    btn_frame.pack(padx=20, pady=(0, 16), anchor="w")
    tk.Button(
        btn_frame,
        text="Stop Server",
        command=root.destroy,
        bg="#b91c1c",
        fg="#fff",
        relief="flat",
        padx=10,
        pady=5,
        cursor="hand2",
    ).pack(side="left")

    def _on_server_ready():
        webbrowser.open(url)
        with suppress(Exception):
            status_lbl.configure(
                text="Server is running. No app-mode browser (Chrome/Edge)\n"
                "was found — opened in your default browser instead."
            )
            url_lbl.configure(
                fg="#58a6ff",
                cursor="hand2",
            )
            url_lbl.bind("<Button-1>", lambda *_: webbrowser.open(url))

    def _wait_and_open():
        if _wait_for_server(host, port):
            root.after(0, _on_server_ready)

    threading.Thread(target=_wait_and_open, daemon=True).start()

    root.mainloop()


def start() -> None:
    host = "localhost"
    port = free_port(host, 31580)
    storage_path = ctx.config.app.app_dir / "app-browser"

    url = _build_url(host, port, storage_path)

    server_thread = _start_server(host, port)
    proc = _start_app_in_browser(url, storage_path)

    if not proc:
        return _start_fallback_window(url, host, port)

    try:
        with suppress(KeyboardInterrupt):
            while proc.poll() is None:
                with suppress(TimeoutError):
                    server_thread.join(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(2)
        except BaseException:
            proc.kill()
