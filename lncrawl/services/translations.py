from hashlib import sha256
import logging
from threading import Event
from typing import Generator, Iterable, List, Optional, Tuple

import sqlmodel as sq

from ..context import ctx
from ..core import PageSoup, Scraper, TaskManager
from ..dao.chapter import ChapterTranslation
from ..exceptions import ServerErrors
from ..utils.event_lock import EventLock

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 4500
_SEPARATOR = r"😶🙂😀😆😎"


class TranslationService:
    def __init__(self) -> None:
        self.lock = EventLock()
        self.scraper = Scraper()
        self.taskman = TaskManager(ratelimit=0.5)

    def close(self):
        self.lock.abort()
        self.scraper.close()
        self.taskman.close()

    # ---------------------------------------------------------------------------------------------
    # Translator Backends
    # ---------------------------------------------------------------------------------------------

    def _google_translate(self, text: str, language: str) -> str:
        data = self.scraper.get_json(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "dt": "t",
                "sl": "auto",
                "tl": language,
                "q": text,
            },
            timeout=60,
        )
        return "".join(part[0] for part in data[0] if part[0])

    def _google_client5_translate(self, text: str, language: str):
        data = self.scraper.get_json(
            "https://clients5.google.com/translate_a/t",
            params={
                "client": "dict-chrome-ex",
                "sl": "auto",
                "tl": language,
                "q": text,
            },
            timeout=60,
        )
        return "".join(part[0] for part in data if part[0])

    def _google_mobile_translate(self, text: str, language: str) -> str:
        soup = self.scraper.get_soup(
            "https://translate.google.com/m",
            params={
                "sl": "auto",
                "tl": language,
                "q": text,
            },
            timeout=60,
        )
        result = soup.select_one("div.result-container")
        if not result:
            raise ValueError("Could not find translation result in Google mobile response")
        return result.get_text()

    # ---------------------------------------------------------------------------------------------
    # Public Methods
    # ---------------------------------------------------------------------------------------------

    def translate_text(
        self,
        text: str,
        language: str,
        signal: Optional[Event] = None,
    ) -> str:
        for method in [
            self._google_mobile_translate,
            self._google_client5_translate,
            self._google_translate,
        ]:
            with self.lock.using(signal):
                self.scraper.signal = signal
                try:
                    return method(text, language)
                except Exception as e:
                    logger.warning(
                        f"{method.__name__} failed: {':'.join(str(e).split(':')[:2])}",
                        exc_info=ctx.logger.is_debug,
                    )
        raise ServerErrors.translation_failure.with_extra("All translation providers failed")

    def translate_batch(
        self,
        texts: Iterable[str],
        language: str,
        signal: Optional[Event] = None,
    ) -> Iterable[str]:
        sep = f"\n\n{_SEPARATOR}\n\n"

        # split into chunks
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0
        input_total = 0
        for text in texts:
            input_total += 1
            if current_len > 0 and current_len + len(text) > _CHUNK_SIZE:
                chunks.append(sep.join(current))
                current_len, current = 0, []
            current.append(text)
            current_len += len(text)
        if current_len > 0:
            chunks.append(sep.join(current))

        # resolve as futures
        futures = [
            self.taskman.submit_task(
                self.translate_text,
                chunk,
                language,
                signal=signal,
            )
            for chunk in chunks
        ]
        self.taskman.resolve(
            futures,
            fail_fast=True,
            desc="Translating",
            unit="chunk",
        )

        # split the result
        output_total = 0
        for future in futures:
            translated = future.result().split(_SEPARATOR)
            output_total += len(translated)
            yield from translated

        if input_total != output_total:
            raise ServerErrors.translation_failure.with_extra(
                f"Sent {input_total} blocks, received {output_total} blocks"
            )

    def translate_html(
        self,
        soup: PageSoup,
        language: str,
        signal: Optional[Event] = None,
    ) -> Generator[Tuple[int, int], None, None]:
        children = soup.body.children
        texts = [p.text for p in children]
        total = len(texts)
        translations = self.translate_batch(texts, language, signal)
        for i, t in enumerate(translations):
            children[i].text = t
            yield i + 1, total

    def translate_chapter(
        self,
        chapter_id: str,
        language: str,
        signal: Optional[Event] = None,
    ) -> Generator[Tuple[int, int], None, None]:
        chapter = ctx.chapters.get(chapter_id)
        if not chapter.is_available:
            raise ServerErrors.no_such_file

        with ctx.db.session() as sess:
            row = sess.exec(
                sq.select(ChapterTranslation).where(
                    ChapterTranslation.novel_id == chapter.novel_id,
                    ChapterTranslation.chapter_serial == chapter.serial,
                    ChapterTranslation.language == language,
                )
            ).first()

        content = ctx.files.load_text(chapter.content_file)
        content_hash = sha256(content.encode()).hexdigest()
        if row and row.content_hash == content_hash and row.is_available:
            return

        soup = PageSoup.create(content, parser="html5lib")
        yield from self.translate_html(soup, language, signal)
        translated = soup.body.inner_html

        with ctx.db.session() as sess:
            if row is None:
                row = ChapterTranslation(
                    novel_id=chapter.novel_id,
                    chapter_serial=chapter.serial,
                    language=language,
                    content_hash=content_hash,
                )
                sess.add(row)
            else:
                row.content_hash = content_hash
                sess.merge(row)
            sess.commit()

        ctx.files.save_text(row.translation_file, translated)
