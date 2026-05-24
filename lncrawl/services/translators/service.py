from hashlib import sha256
import logging
from threading import Event
import time
from typing import Dict, Generator, Iterable, List, Optional, Tuple, Union

import sqlmodel as sq

from ...context import ctx
from ...dao import Chapter, ChapterTranslation, Novel, NovelTranslation, Volume, VolumeTranslation
from ...enums import LanguageCode
from ...exceptions import ServerErrors
from .backend_baidu import BaiduTranslate
from .backend_base import BackendBase
from .backend_bing import BingTranslate
from .backend_google import GoogleClient5Translate, GoogleGtxTranslate, GoogleMobileTranslate
from .backend_lingva import LingvaTranslate

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self) -> None:
        self._failing: Dict[BackendBase, float] = {}
        self._backends: List[BackendBase] = [
            BingTranslate(),
            GoogleMobileTranslate(),
            LingvaTranslate(),
            BaiduTranslate(),
            GoogleGtxTranslate(),
            GoogleClient5Translate(),
        ]

    def close(self):
        for backend in self._backends:
            backend.close()

    # ---------------------------------------------------------------------------------------------
    # Public Methods
    # ---------------------------------------------------------------------------------------------

    def _available_backends(self, language: LanguageCode):
        for backend in self._backends:
            if not backend.is_enabled(language):
                continue
            last_fail = self._failing.get(backend, 0)
            if time.monotonic() - last_fail < 5 * 60:
                continue
            yield backend

    def _on_backend_error(self, backend: BackendBase, e: Exception):
        message = f"{repr(backend)} failed: {':'.join(str(e).split(':')[:2])}"
        logger.info(message, exc_info=ctx.logger.is_debug)
        if "429 Client Error" in message:
            logger.warning(f"Disabling '{backend.name}' to avoid 429 error")
            self._failing[backend] = time.monotonic()

    def translate_text(
        self,
        text: str,
        target: LanguageCode,
        signal: Optional[Event] = None,
    ) -> str:
        for backend in self._available_backends(target):
            try:
                logger.info(f"Using {backend.name} for Text ({target})")
                return backend.translate(text, target, signal=signal)
            except Exception as e:
                self._on_backend_error(backend, e)
        raise ServerErrors.translation_failure.with_extra("all backends down")

    def translate_batch(
        self,
        text: Iterable[str],
        target: LanguageCode,
        signal: Optional[Event] = None,
    ) -> Iterable[str]:
        for backend in self._available_backends(target):
            try:
                logger.info(f"Using {backend.name} for Batch Text ({target})")
                return backend.translate_batch(text, target, signal=signal)
            except Exception as e:
                self._on_backend_error(backend, e)
        raise ServerErrors.translation_failure.with_extra("all backends down")

    def translate_html(
        self,
        html: str,
        target: LanguageCode,
        signal: Optional[Event] = None,
    ) -> Generator[Union[int, str], None, None]:
        for backend in self._available_backends(target):
            try:
                logger.info(f"Using {backend.name} for HTML ({target})")
                return backend.translate_html(html, target, signal=signal)
            except Exception as e:
                self._on_backend_error(backend, e)
        raise ServerErrors.translation_failure.with_extra("all backends down")

    def translate_novel(
        self,
        novel: Novel,
        target: LanguageCode,
        signal: Optional[Event] = None,
    ):
        translation = ctx.novels.get_novel_translation(novel, target)
        if translation:
            return

        texts = [
            novel.title,
            novel.authors or "",
            "; ".join(novel.tags),
        ]

        done = 0
        total = 3
        translated: List[str] = [""] * 4
        if novel.synopsis:
            synopsis: List[str] = []
            for out in self.translate_html(novel.synopsis, target, signal):
                if isinstance(out, int):
                    done = 0
                    synopsis = []
                    total = 3 + out
                else:
                    done += 1
                    synopsis.append(out)
                yield done, total
            translated[0] = "".join(synopsis)

        for i, out in enumerate(self.translate_batch(texts, target, signal)):
            done += 1
            translated[i + 1] = out
            yield done, total

        tags = translated[3].split("; ")
        if tags:
            ctx.tags.insert(tags)

        with ctx.db.session() as sess:
            translation = NovelTranslation(
                novel_id=novel.id,
                language=target,
                synopsis=translated[0],
                title=translated[1],
                authors=translated[2],
                tags=tags,
            )
            sess.add(translation)
            sess.commit()

    def translate_volume(
        self,
        volume: Volume,
        target: LanguageCode,
        signal: Optional[Event] = None,
    ):
        translation = ctx.volumes.get_volume_translation(volume, target)
        if translation:
            return

        title = self.translate_text(volume.title, target, signal)
        with ctx.db.session() as sess:
            translation = VolumeTranslation(
                novel_id=volume.novel_id,
                volume_serial=volume.serial,
                language=target,
                volume_title=title,
            )
            sess.add(translation)
            sess.commit()

    def translate_chapter(
        self,
        chapter: Chapter,
        target: LanguageCode,
        signal: Optional[Event] = None,
    ) -> Generator[Tuple[int, int], None, None]:
        translation = ctx.chapters.get_chapter_translation(chapter, target)

        content = ctx.files.load_text(chapter.content_file)
        content_hash = sha256(content.encode()).hexdigest()
        if translation and translation.content_hash == content_hash and translation.is_available:
            yield 1, 1
            return

        total = 1
        results = []
        for out in self.translate_html(content, target, signal):
            if isinstance(out, str):
                results.append(out)
            else:
                total = out + 1
                results.clear()
            yield len(results), total
        translated = "".join(results)

        title = self.translate_text(chapter.title, target)
        yield total, total

        with ctx.db.session() as sess:
            if not translation:
                translation = ChapterTranslation(
                    novel_id=chapter.novel_id,
                    chapter_serial=chapter.serial,
                    language=target,
                    chapter_title=title,
                    content_hash=content_hash,
                )
                sess.add(translation)
            else:
                sess.exec(
                    sq.update(ChapterTranslation)
                    .where(sq.col(ChapterTranslation.id) == translation.id)
                    .values(
                        chapter_title=title,
                        content_hash=content_hash,
                    )
                )
            sess.commit()

        ctx.files.save_text(translation.translation_file, translated)
