import hashlib
import logging
from pathlib import Path

from ..context import ctx
from ..dao import User
from ..exceptions import ServerErrors
from ..server.models import SourceCodeResponse, SourcePRRequest, SourcePRResponse
from ..utils.github import GithubClient

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

    def create_source_pr(
        self,
        user: User,
        source_id: str,
        req: SourcePRRequest,
    ) -> SourcePRResponse:
        file = self._crawler_file(source_id)
        file_path = self._repo_rel_path(file)
        if not (req.url in req.body and "TEST PASSED!" in req.body):
            raise ServerErrors.crawler_test_failure

        branch = f"fix/{file_path}"
        title = req.title.strip().capitalize()

        user_link = f"{ctx.config.server.base_url}/admin/user/{user.id}"
        body = (
            f"{req.body}\n\n"
            f"> Submitted by [{user.name}]({user_link})\n"
            f"> Test URL: {req.url}\n"
            f"> File: {GithubClient.get_remote_link(file_path)}\n"
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
