import asyncio
import logging
import threading
import traceback
from pathlib import Path
from threading import Event
from typing import Dict, List, Optional, Type

from ...context import ctx
from ...core import Crawler, TaskManager
from ...dao import User
from ...exceptions import ServerErrors
from ...server.models import CrawlerIndex, CrawlerInfo, SourceItem
from ...utils.fts_store import FTSStore
from ...utils.text_tools import normalize
from ...utils.url_tools import extract_host, normalize_url
from .helper import (
    batch_import,
    create_crawler_info,
    create_source_item,
    fetch_online_source,
    load_offline_source,
    save_source,
)
from .tester import run_crawler_test

logger = logging.getLogger(__name__)
_crawlers_cache: Dict[Type[Crawler], Crawler] = {}


class Sources:
    def __init__(self) -> None:
        self._signal: Event
        self._store: FTSStore
        self._index: CrawlerIndex
        self._taskman: TaskManager
        self.rejected: Dict[str, str] = {}  # Map of host -> rejection reason
        self.crawlers: Dict[str, Type[Crawler]] = {}  # Map of host -> crawler
        self.info: Dict[str, CrawlerInfo] = {}  # Map of host -> crawler-info
        self.sources: Dict[str, SourceItem] = {}  # Map of host -> source

    @property
    def version(self) -> int:
        if not self._index:
            raise ServerErrors.source_not_loaded
        return self._index.v

    def is_rejected(self, url: str) -> Optional[str]:
        host = extract_host(url)
        return self.rejected.get(host)

    def close(self):
        if hasattr(self, "_signal"):
            self._signal.set()
        if hasattr(self, "_store"):
            self._store.close()
        if hasattr(self, "_taskman"):
            self._taskman.close()
        if hasattr(self, "_index"):
            del self._index
        self.rejected.clear()
        self.sources.clear()

    def load(self, sync_remote=True):
        self._signal = Event()
        self._store = FTSStore()
        self._taskman = TaskManager(10)

        # load offline sources first
        self.load_index(load_offline_source(sync_remote))

        # dynamically import all crawlers
        self._taskman.submit_task(
            self.load_crawlers,
            *ctx.config.crawler.local_sources.glob("**/*.py"),
            *ctx.config.crawler.user_sources.glob("**/*.py"),
        )

        # run background task get online update
        if sync_remote:
            self._taskman.submit_task(self.update)

    def ensure_load(self):
        self._taskman.as_completed(
            disable_bar=True,
            signal=self._signal,
        )

    def load_index(self, index: CrawlerIndex) -> None:
        self._index = index

        # update rejected list
        self.rejected.clear()
        for url, reason in index.rejected.items():
            host = extract_host(url)
            self.rejected[host] = reason

    def load_crawlers(self, *files: Path):
        for crawler in batch_import(*files):
            self.add_crawler(crawler)

    def add_crawler(self, crawler: Type[Crawler]):
        # add to index if not available
        name = crawler.__name__
        cid = getattr(crawler, "__id__")  # crawler id
        if cid in self._index.crawlers:
            info = self._index.crawlers[cid]
        else:
            logger.info(f"Found non-indexed crawler: {name}")
            info = create_crawler_info(crawler)
            self._index.crawlers[cid] = info

        # skip this crawler if it is not the latest
        if cid in self.info and info.version < self.info[cid].version:
            return
        self.info[cid] = info
        self.crawlers[cid] = crawler

        # load source items
        for url in info.base_urls:
            self.add_source(url, info)

    def add_source(self, url: str, info: CrawlerInfo):
        item = create_source_item(url, info, self.rejected)
        # skip this item if it is not the latest
        if item.domain in self.sources and item.version < self.sources[item.domain].version:
            return
        self.sources[item.domain] = item

        # add keys for searching
        self._store.insert(normalize_url(url), item.domain)

    def update(self) -> None:
        assert self._index
        logger.info("Sync online sources")
        online_index = fetch_online_source()
        if online_index.v <= self._index.v:
            logger.info("No latest updates found")
            return

        # save the latest index
        user_file = ctx.config.crawler.user_index_file
        save_source(user_file, self._index)

        # load the online index
        self.load_index(online_index)

        # download latest source files
        futures = []
        for id, source in online_index.crawlers.items():
            current = self._index.crawlers.get(id)
            if current and current.version >= source.version:
                continue
            user_sources = ctx.config.crawler.user_sources.parent
            dst_file = (user_sources / source.file_path).resolve()
            f = self._taskman.submit_task(ctx.http.download, source.github_url, dst_file)
            futures.append(f)

        # wait for completion
        for dst_file in self._taskman.resolve(
            futures,
            desc="Downloading",
            unit="source",
            signal=self._signal,
        ):
            if dst_file:
                self.load_crawlers(dst_file)
        logger.info("Source synced.")

    def list(
        self,
        query: Optional[str] = None,
        *,
        include_rejected: bool = False,
        can_search: Optional[bool] = None,
        can_login: Optional[bool] = None,
        has_mtl: Optional[bool] = None,
        has_manga: Optional[bool] = None,
    ) -> List[SourceItem]:
        self.ensure_load()
        domains = self._store.search(normalize(query)) if query else None
        if domains is not None and len(domains) == 0:
            return []
        return [
            item
            for item in self.sources.values()
            if all(
                [
                    domains is None or item.domain in domains,
                    has_mtl is None or item.has_mtl == has_mtl,
                    has_manga is None or item.has_manga == has_manga,
                    can_login is None or item.can_login == can_login,
                    can_search is None or item.can_search == can_search,
                    include_rejected or item.is_disabled,
                ]
            )
        ]

    def get_source(self, domain: str) -> Optional[SourceItem]:
        self.ensure_load()
        return self.sources.get(domain)

    def get_info(self, domain: str) -> Optional[CrawlerInfo]:
        source = self.get_source(domain)
        if not source:
            return None
        return self.info[source.crawler_id]

    def get_crawler(self, domain: str) -> Optional[Type[Crawler]]:
        source = self.get_source(domain)
        if not source:
            return None
        return self.crawlers[source.crawler_id]

    def find_crawler(self, url: str) -> Type[Crawler]:
        self.ensure_load()
        host = extract_host(url)
        if not host:
            raise ServerErrors.invalid_url
        if host in self.rejected:
            raise ServerErrors.host_rejected.with_extra(self.rejected[host])
        source = self.get_source(host)
        if not source:
            raise ServerErrors.no_crawler.with_extra(host)
        return self.crawlers[source.crawler_id]

    def init_crawler(
        self,
        constructor: Type[Crawler],
        workers: Optional[int] = None,
        parser: Optional[str] = None,
        renew: bool = False,
    ) -> Crawler:
        if constructor in _crawlers_cache:
            if renew:
                _crawlers_cache.pop(constructor).close()
            else:
                return _crawlers_cache[constructor]

        url = getattr(constructor, "url")
        ctx.logger.debug(f"Creating crawler instance for {url}")

        # create instance
        crawler = constructor(
            origin=url,
            workers=workers,
            parser=parser,
        )
        _crawlers_cache[constructor] = crawler

        crawler.initialize()
        return crawler

    async def test_source(self, user: User, url: str, content: str):
        event = Event()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()

        def emit(item: str = "") -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item + "\n")

        def run():
            try:
                run_crawler_test(user, url, content, emit)
                emit("\nTEST PASSED!")
            except Exception as e:
                emit(f"<!> {repr(e)}\n{traceback.format_exc()}")
                emit("\nTEST FAILED!")
            finally:
                event.set()
                emit("END")

        threading.Thread(target=run, daemon=True).start()

        while True:
            item = await queue.get()
            if event.is_set() and item == "END\n":
                break
            yield item
