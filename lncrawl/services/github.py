import hashlib
import logging
import traceback
from pathlib import Path

from ..context import ctx
from ..dao import User
from ..exceptions import ServerErrors
from ..server.models import SourceCodeResponse, SourcePRRequest, SourcePRResponse
from ..utils.github import GithubClient
from ..utils.log_sink import LogSink

logger = logging.getLogger(__name__)


class GitHubService:
    def _crawler_file(self, source_id: str) -> Path:
        ctx.sources.ensure_load()
        crawler_cls = ctx.sources.crawlers.get(source_id)
        if not crawler_cls:
            raise ServerErrors.no_crawler
        return Path(getattr(crawler_cls, "__file__"))

    def _repo_rel_path(self, file: Path) -> str:
        repo_root = ctx.config.crawler.local_sources.parent
        return file.relative_to(repo_root).as_posix()

    def get_source_code(self, source_id: str) -> SourceCodeResponse:
        file = self._crawler_file(source_id)
        file_path = self._repo_rel_path(file)
        if not file.exists():
            raise ServerErrors.no_such_file
        return SourceCodeResponse(
            file_path=file_path,
            content=file.read_text(encoding="utf-8"),
        )

    def _run_crawler_test(self, url: str, content: str) -> str:
        sink = LogSink()
        parts: list[str] = []

        def collect(s: str) -> None:
            logger.debug(s)
            parts.append(s)

        try:
            logger.debug(f"Running test for crawler: {url!r}")
            with sink.pipe(parts.append):
                ctx.sources.test_crawler(url, content, sink, verbose=False)
            logger.debug("Crawler test passed")
            return "".join(parts)
        except Exception as e:
            logger.info(f"Crawler test failed: {repr(e)}")
            collect(traceback.format_exc())
            raise ServerErrors.crawler_test_failure from e

    def create_source_pr(
        self,
        user: User,
        source_id: str,
        req: SourcePRRequest,
    ) -> SourcePRResponse:
        file = self._crawler_file(source_id)
        file_path = self._repo_rel_path(file)

        test_logs = self._run_crawler_test(req.url, req.content)

        stem = file.stem
        branch = req.branch or f"fix/sources/{stem}"
        title = req.title or f"Update source: {stem}"

        user_link = f"{ctx.config.server.base_url}/admin/user/{user.id}"
        body = req.body or (
            f"> Submitted by [{user.name}]({user_link})\n"
            f"> Test URL: {req.url}\n"
            f"> File: {GithubClient.get_remote_link(file_path)}\n\n"
            f"```\n{test_logs}\n```"
        )

        user_hash = hashlib.shake_256(user.email.encode()).hexdigest(6)
        labels = ["source-update", f"user:{user_hash}"]

        with GithubClient() as gh:
            pr = gh.find_open_pr(branch)
            if not pr:
                gh.ensure_branch(branch)

            committed = gh.commit_file(
                message=title,
                branch=branch,
                content=req.content,
                file_path=file_path,
                user_name=user.name or "Server User",
                user_email=user.email,
            )

            if pr:
                gh.update_pr(pr["number"], title, body)
            elif not committed:
                raise ServerErrors.invalid_input.with_extra(
                    "Source content is identical to the current version"
                )
            else:
                pr = gh.create_pr(title, body, branch)

            gh.add_labels(pr["number"], labels)

            return SourcePRResponse(
                url=pr["html_url"],
                sha=pr["head"]["sha"],
                branch=pr["head"]["ref"],
            )
