# Lightnovel Crawler

[![download win](https://img.shields.io/badge/download-lncrawl.exe-red?logo=windows&style=for-the-badge)](https://go.bitanon.dev/lncrawl-windows)
[![download linux](<https://img.shields.io/badge/download-lncrawl_(linux)-brown?logo=linux&style=for-the-badge>)](https://go.bitanon.dev/lncrawl-linux)
[![download mac](<https://img.shields.io/badge/download-lncrawl_(mac)-blue?logo=apple&style=for-the-badge>)](https://go.bitanon.dev/lncrawl-mac)
<br>
[![PyPI version](https://img.shields.io/pypi/v/lightnovel-crawler.svg?logo=python)](https://pypi.org/project/lightnovel-crawler)
[![Python version](https://img.shields.io/pypi/pyversions/lightnovel-crawler.svg)](https://pypi.org/project/lightnovel-crawler)
[![Downloads](https://pepy.tech/badge/lightnovel-crawler)](https://pepy.tech/project/lightnovel-crawler)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](https://github.com/lncrawl/lightnovel-crawler/blob/master/LICENSE)
<br>
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/lncrawl/lightnovel-crawler)
[![Lint](https://github.com/lncrawl/lightnovel-crawler/actions/workflows/lint.yml/badge.svg)](https://github.com/lncrawl/lightnovel-crawler/actions/workflows/lint.yml)
[![Build and Publish](https://github.com/lncrawl/lightnovel-crawler/actions/workflows/release.yml/badge.svg)](https://github.com/lncrawl/lightnovel-crawler/actions/workflows/release.yml)

**Lightnovel Crawler** downloads _web novels and similar fiction_ from many online reading sites and saves them as **e-book** so you can read offline on a phone, tablet, or e-reader.

### What you can do with it

- Save a story you follow into a **single EPUB** (or another format) instead of hundreds of separate web pages.
- **Search** supported sites from the app and pick a title without copying long URLs by hand.
- Run a **small private server** on your home network so you can use the same workflow from another device on that network.

### Use it responsibly

Sites publish fiction under their own _terms and copyright_. This tool is meant for **personal** use only, for example keeping a backup of material you already have access to, where the licence allows it. **Do not** use it to redistribute or sell someone else's work. You are responsible for how you use Lightnovel Crawler.

## Installation

<a href="https://github.com/lncrawl/lightnovel-crawler"><img src="res/lncrawl-icon.png" width="128px" align="right"/></a>

Pick **one** approach. You do not need to do all of them.

### ⏬ Standalone

| Platform | Link                                                  | Note                                       |
| -------- | ----------------------------------------------------- | ------------------------------------------ |
| Windows  | [lncrawl.exe](https://go.bitanon.dev/lncrawl-windows) | SmartScreen may warn about an unknown app. |
| Linux    | [lncrawl](https://go.bitanon.dev/lncrawl-linux)       | **pip** is often easier for updates.       |
| macOS    | [lncrawl](https://go.bitanon.dev/lncrawl-mac)         | **pip** is often easier for updates.       |

_To get older versions visit the [Releases page](https://github.com/lncrawl/lightnovel-crawler/releases)_

Check that it works:

- Double click and run the downloaded file. _It may take some time to show the first screen depending on your machine._

[![Tutorial](res/screenshots/tutorial.png)](res/screenshots/tutorial.png)

### 📦 PIP

> PyPI package: [**lightnovel-crawler** ![version](https://img.shields.io/pypi/v/lightnovel-crawler.svg?logo=python)](https://pypi.org/project/lightnovel-crawler)

- From PyPI repository.

  ```bash
  pip install -U lightnovel-crawler
  ```

  _If it fails, you can try: `python3 -m pip`, `pip3`, or `python -m pip`._

- You can also install directly from GitHub.
  - **Stable branch (`master`):**

    ```bash
    pip install -U git+https://github.com/lncrawl/lightnovel-crawler.git#egg=lightnovel-crawler
    ```

  - **Development branch (`dev`):** may include fixes or breaking changes.

    ```bash
    pip install -U https://github.com/lncrawl/lightnovel-crawler/tarball/refs/heads/dev#egg=lightnovel-crawler
    ```

- Check that it works:

  ```bash
  lncrawl -h
  ```

  _If `lncrawl` is not found, try `python3 -m lncrawl`, or `python -m lncrawl`._

[![Terminal](res/screenshots/terminal.png)](res/screenshots/terminal.png)

### 🐳 Docker

You need to have [Docker](https://www.docker.com/get-started/) installed.

```bash
mkdir -p lncrawl-data
docker pull ghcr.io/lncrawl/lightnovel-crawler
docker run -v ./lncrawl-data:/data -it -p 8181:8181 --name lncrawl-server ghcr.io/lncrawl/lightnovel-crawler -ll server
```

Check that it works:

- Visit **[http://localhost:8181](http://localhost:8181)** in your browser.
- You can sign in with the default account: `admin` / `admin`.

[![Login](res/screenshots/login.png)](res/screenshots/login.png)

## Calibre (optional)

> If you only need **epub**, **text**, or **json** outputs, you can skip this section.

To create **PDF**, **MOBI**, **DOCX**, and other formats, install **[Calibre](https://calibre-ebook.com/download)**. Lightnovel Crawler calls Calibre's tools in the background when you pick those formats.

After installation, locate location of the `ebook-convert` in the Calibre installation directory, and add the folder to your Path variables. e.g.:

```bash
export PATH="$PATH:/Applications/calibre.app/Contents/MacOS"
```

## Using the app

### Web Interface

Just run the executable or type `lncrawl` in your terminal and you're ready to go! Browse, download, and enjoy your novels all in one place, no command line required.

[![Crawlers](res/screenshots/crawlers.png)](res/screenshots/crawlers.png)
[![Requests](res/screenshots/requests.png)](res/screenshots/requests.png)
[![Novels](res/screenshots/novels.png)](res/screenshots/novels.png)
[![Reader](res/screenshots/reader.png)](res/screenshots/reader.png)
[![Libraries](res/screenshots/libraries.png)](res/screenshots/libraries.png)
[![Settings](res/screenshots/settings.png)](res/screenshots/settings.png)

### Command Line

Check the available options in the terminal:

<!-- auto generated command line output -->
```text
$ lncrawl -h
Usage: lncrawl [OPTIONS] COMMAND [ARGS]...                                     
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --verbose             -l            Log levels: -l = warn, -ll = info, -lll  │
│                                     = debug                                  │
│ --config              -c      PATH  Config file                              │
│ --install-completion                Install completion for the current       │
│                                     shell.                                   │
│ --show-completion                   Show completion for the current shell,   │
│                                     to copy it or customize the              │
│                                     installation.                            │
│ --help                -h            Show this message and exit.              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ version  Show current version.                                               │
│ config   View and modify configuration settings.                             │
│ sources  Manage sources.                                                     │
│ crawl    Crawl from novel page URL.                                          │
│ search   Search for novels by query string.                                  │
│ server   Run web server.                                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
```
<!-- auto generated command line output -->

Download a few chapters from a novel's **main info page** URL:

```bash
lncrawl -ll crawl "https://example.com/novel/1234" -f epub --first 10
```

## Development and Contributions

Want to help with code, sources, or docs?

- [DeepWiki](https://deepwiki.com/lncrawl/lightnovel-crawler) (AI-assisted project overview)
- [.github/docs/ARCHITECTURE.md](.github/docs/ARCHITECTURE.md) (architecture and CI notes)
- [.github/docs/CREATING_CRAWLERS.md](.github/docs/CREATING_CRAWLERS.md) (add or fix a source)
- [.github/docs/DOCKER.md](.github/docs/DOCKER.md) (Docker details)
- [.github/FORKING.md](.github/FORKING.md) (CI on forks)

### Quick Setup

Install [uv](https://docs.astral.sh/uv/) (or run `make setup`, which can install it for you). From the repo root:

```bash
git clone https://github.com/lncrawl/lightnovel-crawler.git
cd lightnovel-crawler
make install    # or: make  (same default target)
make start
```

Equivalent with uv only (after submodules are initialized):

```bash
git submodule update --init --recursive
uv sync --extra dev
uv run python -m lncrawl -ll server
```

### Makefile reference

Targets are defined in the [Makefile](Makefile); `install` / `sync` / dependency targets use `uv sync --extra dev`.

```bash
# Setup and install
make setup            # Sync submodules and install uv
make install          # setup + uv sync (default target: `make` or `make all`)
make sync             # uv sync only
make upgrade          # setup + uv sync --upgrade

# Development servers and tooling
make start            # Backend server only
make watch            # Backend with auto-reload
make lint             # ruff format and check
make add-source       # Guided CLI to add a new source crawler

# Version (writes lncrawl/VERSION via scripts/bump.py)
make patch            # bump patch
make minor            # bump minor
make major            # bump major

# Build
make build            # print version + install + wheel + exe
make build-wheel      # Python wheel (python -m build -w)
make build-exe        # PyInstaller (setup_pyi.py)

# Dependencies (second word is the package name)
make add-dep <package>   # e.g. make add-dep httpx
make add-dev <package>   # add to optional extra `dev`
make rm-dep <package>
make rm-dev <package>

# Docker (uses compose.yml in repo root unless you pass -f elsewhere)
make docker-build     # Base image, then app image
make docker-base      # Base image only (Calibre + deps)
make docker-up        # docker compose up -d
make docker-down      # docker compose down
make docker-logs      # docker compose logs -f

# Other
make version          # Print version from lncrawl/VERSION
make clean            # Remove .venv, logs, build, dist, *.egg-info, __pycache__
make submodule        # git submodule sync + update (init, recursive, remote)


# Update repo + submodules without make
git pull && make submodule

# Run CLI from source
uv run python -m lncrawl
```

### Adding New Source

_Recommended_: Scaffold with the CLI (optionally, it can use AI for generation):

```bash
make add-source
```

_Manually_: Copy one example such as `[sources/_examples/_01_general_soup.py](sources/_examples/_01_general_soup.py)` into the right `sources/{lang}/` folder and implement the required methods.

_Full guide_: [.github/docs/CREATING_CRAWLERS.md](.github/docs/CREATING_CRAWLERS.md).

## Supported Formats

Natively supported formats:

| Format      | Description             | Use Case / App          |
| ----------- | ----------------------- | ----------------------- |
| 📚 **EPUB** | Standard eBook format   | Most eReaders, apps     |
| 📃 **TXT**  | Plain text file         | Any text editor, simple |
| 🗂️ **JSON** | Structured chapter data | Parsing/scripts/devs    |

Supported if Calibre’s `ebook-convert` tool is available:

| Format      | Description                 | Use Case / App         |
| ----------- | --------------------------- | ---------------------- |
| 📄 **PDF**  | Portable Document Format    | Universal, print-ready |
| 🔲 **MOBI** | Kindle eBook (legacy)       | Older Kindle devices   |
| 🔳 **AZW3** | Kindle eBook (modern)       | Current Kindles        |
| 📝 **DOCX** | Microsoft Word document     | MS Word, LibreOffice   |
| 📑 **RTF**  | Rich Text Format            | WordPad, others        |
| 📔 **FB2**  | FictionBook eBook format    | FB2 readers            |
| 📕 **LIT**  | Microsoft Reader (obsolete) | Old MS Reader          |
| 📗 **LRF**  | Sony eBook format           | Sony Readers           |
| 🗄️ **PDB**  | PalmDoc/Plucker (legacy)    | PalmOS, old devices    |
| 📘 **RB**   | RocketBook/REB1100          | Legacy readers         |
| 📙 **TCR**  | Psion eBook format          | Psion readers          |

## Supported sources

To request for a new source not included in the following list, please [create an issue](https://github.com/lncrawl/lightnovel-crawler/issues/new/choose).

<!-- auto generated supported sources list -->

We are supporting 0 sources and 0 crawlers.<!-- auto generated supported sources list -->

## Rejected sources

<!-- auto generated rejected sources list -->

<table>
<tbody>
<tr><th>Source URL</th>
<th>Rejection Cause</th>
</tr>
</tbody>
</table>

<!-- auto generated rejected sources list -->

## Get help

Questions and tips: [GitHub Discussions](https://github.com/lncrawl/lightnovel-crawler/discussions).
