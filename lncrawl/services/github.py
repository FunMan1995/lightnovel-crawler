import base64
import time
from pathlib import Path

import httpx

from ..context import ctx
from ..exceptions import ServerErrors
from ..server.models.sources import SourceCodeResponse, SourcePRRequest

_GITHUB_API = "https://api.github.com"


class GitHubService:
    def _token(self) -> str:
        admin = ctx.users.get_admin()
        token = ctx.secrets.get_value(admin.id, "GITHUB_TOKEN")
        if not token:
            raise ServerErrors.server_error.with_extra(
                "Set 'GITHUB_TOKEN' in admin secrets to enable PR creation"
            )
        return token

    def _crawler_file(self, source_id: str) -> Path:
        ctx.sources.ensure_load()
        crawler_cls = ctx.sources.crawlers.get(source_id)
        if not crawler_cls:
            raise ServerErrors.not_found
        return Path(getattr(crawler_cls, "__file__"))

    def _repo_rel_path(self, file: Path) -> str:
        repo_root = ctx.config.crawler.local_sources.parent
        try:
            return file.relative_to(repo_root).as_posix()
        except ValueError:
            return file.name

    def get_source_code(self, source_id: str) -> SourceCodeResponse:
        file = self._crawler_file(source_id)
        if not file.exists():
            raise ServerErrors.no_such_file
        return SourceCodeResponse(
            file_path=self._repo_rel_path(file),
            content=file.read_text(encoding="utf-8"),
        )

    def create_source_pr(self, source_id: str, req: SourcePRRequest) -> str:
        file = self._crawler_file(source_id)
        file_path = self._repo_rel_path(file)
        token = self._token()

        stem = file.stem  # e.g. "novelspl"
        ts = int(time.time())
        branch = req.branch or f"fix/{stem}-{ts}"
        title = req.title or f"Fix {stem} source crawler"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(headers=headers, base_url=_GITHUB_API) as gh:
                repo = gh.get(f"/repos/{req.repo}").raise_for_status().json()
                default_branch = repo["default_branch"]

                file_data = (
                    gh.get(f"/repos/{req.repo}/contents/{file_path}").raise_for_status().json()
                )
                file_sha = file_data["sha"]

                head_sha = (
                    gh.get(f"/repos/{req.repo}/git/ref/heads/{default_branch}")
                    .raise_for_status()
                    .json()["object"]["sha"]
                )

                gh.post(
                    f"/repos/{req.repo}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": head_sha},
                ).raise_for_status()

                gh.put(
                    f"/repos/{req.repo}/contents/{file_path}",
                    json={
                        "message": title,
                        "content": base64.b64encode(req.content.encode()).decode(),
                        "sha": file_sha,
                        "branch": branch,
                    },
                ).raise_for_status()

                pr = gh.post(
                    f"/repos/{req.repo}/pulls",
                    json={
                        "title": title,
                        "body": req.body,
                        "head": branch,
                        "base": default_branch,
                    },
                ).raise_for_status().json()

                return pr["html_url"]
        except httpx.HTTPStatusError as e:
            raise ServerErrors.server_error.with_extra(f"GitHub API error: {e.response.text}")
