# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

The [Makefile](Makefile) wraps [uv](https://docs.astral.sh/uv/); `make install` / `make sync` use `uv sync --all-extras --all-groups`. Python `>=3.9`.

```bash
# Setup and install
make setup            # Sync git submodules and ensure uv is installed
make install          # setup + uv sync (default target: `make` or `make all`)
make sync             # uv sync only (no submodule update)
make upgrade          # setup + uv sync --upgrade

# Development servers and tooling
make start            # Run backend server (python -m lncrawl -ll server)
make watch            # Run server with auto-reload (--watch)
make lint             # ruff check + ruff format --check
make lint-fix         # ruff check --fix + ruff format
make add-source       # Guided CLI to scaffold a new source crawler
make index-gen        # Regenerate source search index (scripts/index_gen.py)
make check-sources    # Validate source crawlers (scripts/check_sources.py)

# Version (writes lncrawl/VERSION via scripts/bump.py)
make patch | minor | major

# Build
make build            # version + install + wheel + exe
make build-wheel      # python -m build -w
make build-exe        # PyInstaller (setup_pyi.py)

# Dependencies (PKG is the second word; uses uv add/remove)
make add-dep <pkg>    # main dep
make add-dev <pkg>    # add to optional extra `dev`
make rm-dep <pkg>
make rm-dev <pkg>

# Docker (uses compose.yml in repo root)
make docker-base      # Calibre + system deps base image (Dockerfile.base)
make docker-build     # docker-base then app image
make docker-up | docker-down | docker-logs

# Misc
make version          # Print lncrawl/VERSION
make clean            # Remove .venv, logs, build, dist, *.egg-info, __pycache__
make submodule        # git submodule sync + update --init --recursive --remote
```

Run from source without make: `uv run python -m lncrawl [args]`.

There is **no automated test suite** — `test.py` is a developer scratchpad. Validate changes by lint, source download (`uv run python -m lncrawl -s "URL" --first 3 -f`), and running the server.

## High-Level Architecture

This project is two things in one package:

1. A **CLI/library** that scrapes individual novel sites and produces e-books.
2. A **FastAPI server + web UI** that turns the same engine into a multi-user job/library service.

Both share a single in-process `AppContext` (`ctx`) singleton; nothing is meant to span processes — concurrency is threads + asyncio inside one Python process.

### Entry points

- [lncrawl/__main__.py](lncrawl/__main__.py) → [lncrawl/app.py](lncrawl/app.py): Typer CLI. Subcommands `version`, `config`, `sources`, `crawl`, `search`, `server`, plus hidden `dev`. With no subcommand, falls back to launching the server.
- [lncrawl/server/app.py](lncrawl/server/app.py): FastAPI app. `lifespan` calls `ctx.setup()` then `ctx.scheduler.start()`. API mounted at `/api`, web SPA (the [lncrawl/server/web](lncrawl/server/web) git submodule, built artifacts) served from `/`. OpenAPI at `/docs`, `/redoc`, `/openapi.json`.

### AppContext singleton

[lncrawl/context.py](lncrawl/context.py) defines `__AppContext__` and exports `ctx`. Every service is a `@cached_property`, so imports are deferred and a service is only constructed on first access. `ctx.setup()` boots the logger, config, DB (with Alembic migrations), creates the admin user, and loads sources. `ctx.destroy()` is registered with Typer's `call_on_close`. **Always reach shared state via `ctx.<service>`** — do not instantiate service classes directly.

Important services (from `ctx`): `config`, `logger`, `db`, `mail`, `http`, `files`, `sources`, `users`, `novels`, `tags`, `secrets`, `volumes`, `chapters`, `images`, `artifacts`, `jobs`, `history`, `libraries`, `feedback`, `announcements`, `crawler`, `binder`, `scheduler`, `admin`.

### Source crawlers (the scraping layer)

- **Where**: [sources/](sources/) is grouped by language (`en/<letter>/`, `zh/`, `ja/`, `multi/`, …). User-added crawlers also load from `ctx.config.crawler.user_sources`.
- **Base classes**: [lncrawl/core/crawler.py](lncrawl/core/crawler.py) (`Crawler`, abstract — `read_novel_info` + `download_chapter_body`) and [lncrawl/core/scraper.py](lncrawl/core/scraper.py) (`Scraper`, HTTP/BS4/Cloudflare). Concurrency primitive: [lncrawl/core/taskman.py](lncrawl/core/taskman.py) (`TaskManager`, ThreadPoolExecutor wrapper).
- **Templates** ([lncrawl/templates/](lncrawl/templates/)): preferred starting point for new crawlers. `soup.general.GeneralSoupTemplate` is the recommended base — implement `parse_title`, `parse_cover`, `parse_chapter_list` (yield `Chapter`/`Volume`), `select_chapter_body`. Engine-specific templates (`madara`, `novelfull`, `novelpub`, `wordpress`, `mangastream`, `freewebnovel`, `novelmtl`) cover sites built on common platforms.
- **Discovery & registry**: [lncrawl/services/sources/service.py](lncrawl/services/sources/service.py) imports every `*.py` under the source dirs at startup, builds a `Crawler` subclass map keyed by host/URL, and maintains a full-text search index (`FTSStore`) for source lookup. A remote source index can also be pulled if `sync_remote=True`.
- **Examples & guide**: [sources/_examples/](sources/_examples/) (numbered templates `_00_basic.py` … `_17_…`); full creation guide is [.github/docs/CREATING_CRAWLERS.md](.github/docs/CREATING_CRAWLERS.md).

### Persistence layer

- ORM: SQLModel/SQLAlchemy. Models in [lncrawl/dao/](lncrawl/dao/) (`Job`, `Novel`, `Chapter`, `Volume`, `User`, `Library`, `Artifact`, `ReadHistory`, `Tag`, `Feedback`, `Announcement`, `Secret`, `ChapterImage`, `enums.py`).
- DB engine: [lncrawl/services/db.py](lncrawl/services/db.py). URL comes from `ctx.config.db.url`; defaults to local SQLite, supports PostgreSQL via `DATABASE_URL`.
- Migrations: [lncrawl/migrations/](lncrawl/migrations/) (Alembic). `ctx.db.bootstrap()` runs migrations on startup.

### Background work: jobs + scheduler

- [lncrawl/services/jobs/](lncrawl/services/jobs/) — `JobService` is the persistence/query API for `Job` rows; `events.py` is a tiny in-process pub/sub bridging worker threads to FastAPI's asyncio loop via `loop.call_soon_threadsafe`.
- [lncrawl/services/scheduler/](lncrawl/services/scheduler/) — `JobScheduler` (started in FastAPI `lifespan`) spawns worker threads: `JobRunner` runs novel-fetching/downloading jobs, `Scrubber` performs cleanup. Concurrency comes from `ctx.config.crawler.runner_concurrency`.
- Live job updates flow over WebSocket via [lncrawl/server/api/ws.py](lncrawl/server/api/ws.py).

### Output / binding

[lncrawl/services/binder/](lncrawl/services/binder/) generates artifacts. EPUB is the native format (`epub.py`); other formats (MOBI, PDF, AZW3, DOCX, FB2, …) are produced by shelling out to Calibre's `ebook-convert` (`calibre.py`); `json.py` and `text.py` are dependency-free outputs.

### Server API

Routers live in [lncrawl/server/api/](lncrawl/server/api/) and are aggregated in [lncrawl/server/api/__init__.py](lncrawl/server/api/__init__.py). Auth is enforced per-router via `Depends(ensure_user)` / `Depends(ensure_admin)` from [lncrawl/server/security.py](lncrawl/server/security.py); WebSocket routers handle their own auth and are mounted **before** the HTTP routers so they don't inherit HTTP security deps. Tier/quota logic in [lncrawl/server/tier.py](lncrawl/server/tier.py).

Pydantic request/response models live in [lncrawl/server/models/](lncrawl/server/models/), distinct from the SQLModel persistence models in `dao/`.

### Configuration

[lncrawl/config.py](lncrawl/config.py): typed config with cached properties. Data dir resolves from env `LNCRAWL_DATA_PATH` first, otherwise `typer.get_app_dir("LNCrawl", force_posix=True, roaming=True)` — on Windows this is `%APPDATA%\LNCrawl`. Config file defaults to `<data>/config.json`. Properties annotated with `Sensitive` are flagged in the admin API.

## Adding a New Source Crawler

Full guide: [.github/docs/CREATING_CRAWLERS.md](.github/docs/CREATING_CRAWLERS.md).

Recommended path: copy [sources/_examples/_01_general_soup.py](sources/_examples/_01_general_soup.py) into the right folder (`sources/en/<letter>/`, `sources/zh/`, etc.), rename the class, set `base_url`, and implement the four required methods. For search use `_02_searchable_soup.py`; for explicit volumes use `_05_with_volume_soup.py` / `_07_optional_volume_soup.py`; for JS-rendered sites use the browser examples (`_09`–`_17`).

Test a crawler end-to-end:

```bash
uv run python -m lncrawl crawl "https://site.com/novel/example" --first 3 -f epub
uv run python -m lncrawl sources list   # confirm registration
```

## Conventions worth knowing

- **Lazy imports inside `ctx` properties** are intentional — keeps CLI startup fast and avoids importing the FastAPI/DB stack for `lncrawl crawl`. Don't move imports to module top in `context.py`.
- **`ruff` config** ([pyproject.toml](pyproject.toml)): line-length 100, double quotes, target py39. Excludes `lncrawl/cloudscraper` (vendored), `lncrawl-web`, `res`, `logs`, `Lightnovels`, `.github`.
- The web frontend is a **git submodule** ([lncrawl/server/web](lncrawl/server/web) → [lncrawl-web](https://github.com/lncrawl/lncrawl-web)). It has its own CI; backend changes shouldn't touch built assets.
- README.md is **partially auto-generated** (the source list and CLI help blocks). Don't hand-edit those regions; regenerate via the appropriate script.
- The vendored [lncrawl/cloudscraper/](lncrawl/cloudscraper/) is a fork — apply upstream-style patches there rather than refactoring.
