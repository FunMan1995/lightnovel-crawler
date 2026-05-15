import gzip
import hashlib
import io
import logging
from pathlib import Path

from ..context import ctx
from ..dao import User
from ..exceptions import ServerErrors
from ..server.models import CrawlerIndex, PRCreateRequest, PRResponse
from ..utils.github import GithubClient

logger = logging.getLogger(__name__)


class GitHubService:
    def fetch_online_source(self) -> CrawlerIndex:
        index_url = GithubClient.get_remote_raw_link("sources/_index.zip")
        compressed = ctx.http.get(index_url)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as fp:
            json_str = fp.read().decode()
            return CrawlerIndex.model_validate_json(json_str)

    def download_online_source(self, file_path: str) -> None:
        user_sources = ctx.config.crawler.user_sources.parent
        dst_file = user_sources / file_path
        raw_url = GithubClient.get_remote_raw_link(file_path)
        ctx.http.download(raw_url, dst_file)

    def get_source_code(self, domain: str) -> str:
        ctx.sources.update()
        crawler = ctx.sources.get_crawler(domain)
        crawler_file = getattr(crawler, "__file__", None)
        if not crawler_file:
            raise ServerErrors.no_such_file.with_extra("crawler.__file__")
        file = Path(crawler_file)
        if not file.exists():
            raise ServerErrors.no_such_file.with_extra(crawler_file)
        return file.read_text(encoding="utf-8")

    def fetch_source_pr(self, domain: str) -> PRResponse:
        branch = f"fix/{domain}"
        with GithubClient() as gh:
            pr = gh.find_open_pr(branch)
            if not pr:
                raise ServerErrors.not_found.with_extra("No PR found for the domain")

            return PRResponse(
                url=pr["html_url"],
                number=pr["number"],
                branch=pr["head"]["ref"],
            )

    def create_source_pr(
        self,
        user: User,
        domain: str,
        req: PRCreateRequest,
    ) -> PRResponse:
        source = ctx.sources.get_source(domain)

        branch = f"fix/{domain}"
        title = req.title.strip().capitalize()
        body = req.body

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

            return PRResponse(
                url=pr["html_url"],
                number=pr["number"],
                branch=pr["head"]["ref"],
            )
