import importlib.util
import logging
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from typing import IO, List, Optional

from ..context import ctx
from ..utils.sockets import free_port

# Canonical project root: one level above the `lncrawl` package directory.
# Used as pylsp's cwd so it discovers pyproject.toml and the sources/ tree.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger(__name__)


class PythonLanguageServer:
    def __init__(self) -> None:
        self._signal = Event()
        self._process: Optional[subprocess.Popen[str]] = None
        self.mode = ctx.config.lsp.mode
        self.host = ctx.config.lsp.host
        self.port = ctx.config.lsp.port

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        if self.is_running:
            logger.warning("LSP service is already running")
            return
        if not ctx.config.lsp.enabled:
            logger.debug("LSP service is disabled; skipping start")
            return
        if not self._is_pylsp_available():
            logger.error(
                "python-lsp-server is not installed. "
                "Install it with: pip install 'lightnovel-crawler[lsp]'"
            )
            return

        cmd = self._build_cmd()
        logger.info("Starting LSP server: %s", " ".join(cmd))

        # Isolate the child from the parent's console so Ctrl+C is not
        # forwarded to pylsp (we terminate it ourselves in stop()).
        extra: dict = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        )
        self._process = subprocess.Popen(
            cmd,
            cwd=str(_PROJECT_ROOT),
            env=self._build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **extra,
        )
        self._start_pipe_reader(self._process.stdout, logging.DEBUG)
        self._start_pipe_reader(self._process.stderr, logging.WARNING)
        logger.info(
            "LSP server started (pid=%d) on %s:%d [%s]",
            self._process.pid,
            ctx.config.lsp.host,
            ctx.config.lsp.port,
            ctx.config.lsp.mode,
        )

    def stop(self) -> None:
        if not self._process or not self.is_running:
            return
        self._signal.set()
        pid = self._process.pid
        logger.info("Stopping LSP server (pid=%d)", pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("LSP server (pid=%d) did not exit cleanly; killing", pid)
            self._process.kill()
            self._process.wait()
        self._process = None
        self._signal = Event()
        logger.info("LSP server stopped")

    @staticmethod
    def _is_pylsp_available() -> bool:
        return importlib.util.find_spec("pylsp") is not None

    def _build_cmd(self) -> List[str]:
        if self.port == 0:
            self.port = free_port(self.host)
        cmd = [sys.executable, "-m", "pylsp"]
        if self.mode == "ws":
            cmd += ["--ws", "--host", self.host, "--port", str(self.port)]
        else:
            cmd += ["--tcp", "--host", self.host, "--port", str(self.port)]
        return cmd

    def _build_env(self) -> dict:
        env = os.environ.copy()
        # Collect workspace roots so jedi can resolve lncrawl + sources imports.
        extra: List[str] = [str(_PROJECT_ROOT)]
        for path in [ctx.config.crawler.user_sources]:
            if path.exists():
                extra.append(str(path))
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([*extra, existing] if existing else extra)
        return env

    def _start_pipe_reader(self, pipe: Optional[IO[str]], level: int):
        if pipe is None:
            return

        def _drain():
            for line in pipe:
                if self._signal.is_set():
                    break
                line = line.rstrip("\n")
                if line:
                    logger.log(level, "[pylsp] %s", line)

        Thread(
            target=_drain,
            daemon=True,
            name=f"lsp-reader-{level}",
        ).start()
