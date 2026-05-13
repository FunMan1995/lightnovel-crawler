import hashlib
import logging

from ..context import ctx
from ..dao import User
from ..exceptions import ServerErrors
from ..server.models import CreatePRRequest, CreatePRResponse
from ..utils.github import GithubClient

logger = logging.getLogger(__name__)


class GitHubService:
    def get_source_code(self, domain: str) -> str:
        source = ctx.sources.get_source(domain)
        file_path = source.file_path
        file = ctx.config.crawler.local_sources.parent / file_path
        if not file.exists():
            raise ServerErrors.no_such_file.with_extra(source.file_path)
        return file.read_text(encoding="utf-8")

    def create_source_pr(
        self,
        user: User,
        domain: str,
        req: CreatePRRequest,
    ) -> CreatePRResponse:
        source = ctx.sources.get_source(domain)

        branch = f"fix/{domain}"
        title = req.title.strip().capitalize() or f"Update source: {domain}"

        user_link = f"{ctx.config.server.base_url}/admin/user/{user.id}"
        page_link = f"{ctx.config.server.base_url}/source/{domain}"
        body = req.body or (
            f"> Submitted by [{user.name}]({user_link}) <br>\n"
            f"> From: {page_link} <br>\n"
            f"> File: {source.github_url}\n"
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
                file_path=source.file_path,
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

            return CreatePRResponse(
                url=pr["html_url"],
                number=pr["number"],
                branch=pr["head"]["ref"],
            )
