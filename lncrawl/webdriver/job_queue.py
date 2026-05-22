import atexit
import logging
from threading import Semaphore
from typing import List, Optional

import nodriver

logger = logging.getLogger(__name__)

MAX_BROWSER_INSTANCES = 8

__open_browsers: List[nodriver.Browser] = []
__semaphore = Semaphore(MAX_BROWSER_INSTANCES)


def __override_stop(browser: nodriver.Browser) -> None:
    __open_browsers.append(browser)
    original_stop = browser.stop

    def override() -> None:
        if browser in __open_browsers:
            __semaphore.release()
            __open_browsers.remove(browser)
            logger.info("Destroyed browser instance")
        original_stop()

    browser.stop = override  # type: ignore[method-assign]


def acquire_queue(timeout: Optional[float] = None) -> None:
    acquired = __semaphore.acquire(True, timeout)
    if not acquired:
        raise TimeoutError("Failed to acquire browser semaphore")


def release_queue(browser: nodriver.Browser) -> None:
    __override_stop(browser)


def check_active(browser: Optional[nodriver.Browser]) -> bool:
    if not isinstance(browser, nodriver.Browser):
        return False
    return browser in __open_browsers


def cleanup_drivers() -> None:
    for browser in list(__open_browsers):
        try:
            browser.stop()
        except Exception:
            pass


atexit.register(cleanup_drivers)
