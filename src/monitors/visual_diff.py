"""Tier 3 — Screenshot comparison via Playwright stealth + imagehash."""
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.config.settings import PROGRAM_URLS, settings
from src.types import RawSignal

logger = logging.getLogger(__name__)

_HASH_STORE: dict[str, str] = {}


def _phash_image(image_bytes: bytes) -> str:
    try:
        from PIL import Image
        import imagehash
        import io

        img = Image.open(io.BytesIO(image_bytes))
        return str(imagehash.phash(img))
    except Exception as exc:
        logger.warning("Erro ao calcular phash: %s", exc)
        return hashlib.sha256(image_bytes).hexdigest()


async def _screenshot(url: str) -> bytes | None:
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await stealth_async(page)
            await page.goto(url, timeout=30_000, wait_until="networkidle")
            screenshot = await page.screenshot(full_page=False, type="png")
            await browser.close()
            return screenshot
    except Exception as exc:
        logger.warning("Falha no screenshot de %s: %s", url, exc)
        return None


def scan_visual_diff(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Captura screenshots e detecta mudanças visuais via perceptual hash."""
    import asyncio

    if urls is None:
        urls = PROGRAM_URLS

    signals: list[RawSignal] = []

    async def _run() -> None:
        for program, url in urls.items():
            screenshot = await _screenshot(url)
            if screenshot is None:
                continue

            new_hash = _phash_image(screenshot)
            old_hash = _HASH_STORE.get(url)
            _HASH_STORE[url] = new_hash

            if old_hash and old_hash != new_hash:
                logger.info("visual_diff: mudança detectada para %s", program)
                signals.append(
                    RawSignal(
                        source_url=url,
                        source_program=program,
                        source_type="visual_diff",
                        fetched_at=datetime.now(timezone.utc),
                        extra={"old_phash": old_hash, "new_phash": new_hash},
                    )
                )
            elif not old_hash:
                logger.debug("visual_diff: hash inicial registrado para %s", program)

    asyncio.run(_run())
    return signals
