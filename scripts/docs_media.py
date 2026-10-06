"""Screenshots and the demo GIF for the README and docs/, taken from a running demo.

    docker compose up -d
    uv run --with playwright --with pillow python scripts/docs_media.py

Uses an installed Microsoft Edge or Google Chrome through Playwright (no browser download).
The demo database changes: one count is entered on the way, as a counter would.
"""

import argparse
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

TABLET = {"width": 1024, "height": 720}
GIF_WIDTH = 880


@dataclass
class Recorder:
    """Collects GIF frames and how long each one stays on screen."""

    frames: list[Image.Image] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)

    def add(self, page: Page, milliseconds: int) -> None:
        image = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
        height = round(image.height * GIF_WIDTH / image.width)
        self.frames.append(image.resize((GIF_WIDTH, height), Image.Resampling.LANCZOS))
        self.durations.append(milliseconds)

    def save(self, path: Path) -> None:
        # One shared palette keeps the colours steady between frames.
        palette = self.frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        frames = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in self.frames
        ]
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
        )


def api(base: str, path: str) -> Any:
    with urlopen(f"{base}{path}") as response:
        return json.load(response)


def first(documents: list[dict[str, Any]], status: str) -> dict[str, Any]:
    return next(d for d in documents if d["status"] == status)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("docs"))
    args = parser.parse_args()
    base: str = args.base_url.rstrip("/")
    images: Path = args.output / "images"
    images.mkdir(parents=True, exist_ok=True)

    snapshot = api(base, "/api/snapshots")[0]["id"]
    documents = api(base, f"/api/documents?snapshot_id={snapshot}")
    counting = first(documents, "v_stetju")
    racks = api(base, f"/api/snapshots/{snapshot}/dashboard")["regali"]
    closed = next(r for r in racks if r["status"] == "zakljucen" and r["z_razliko"])
    gif = Recorder()

    with sync_playwright() as playwright:
        browser = None
        for channel in ("msedge", "chrome"):
            try:
                browser = playwright.chromium.launch(channel=channel)
                break
            except PlaywrightError:  # not installed: try the next browser
                continue
        if browser is None:
            raise SystemExit("Microsoft Edge or Google Chrome is needed for the screenshots.")
        page = browser.new_page(viewport=TABLET, locale="sl-SI", color_scheme="light")

        # 1. Imports and the count documents, one per rack.
        page.goto(f"{base}/")
        page.screenshot(path=images / "uvozi.png")
        gif.add(page, 2500)

        # 2. The printable count sheet of a rack.
        page.goto(f"{base}/api/documents/{counting['id']}/count-sheet.html")
        page.screenshot(path=images / "popisni_list.png")
        gif.add(page, 2200)

        # 3. Counting on the tablet: type a quantity, Enter saves it and moves on.
        page.goto(f"{base}/documents/{counting['id']}")
        page.fill("#stevec", "Ana")
        page.check("#only-open")
        row = page.locator("#items tr:not(.counted)").first
        row_id = row.get_attribute("id")
        page.screenshot(path=images / "stetje.png")
        gif.add(page, 2200)
        quantity = row.locator("input.qty")
        quantity.click()
        quantity.type("12", delay=120)
        gif.add(page, 1200)
        quantity.press("Enter")
        page.uncheck("#only-open")
        page.wait_for_selector(f"#{row_id}.counted, #{row_id}.has-error")
        page.locator(f"#{row_id}").scroll_into_view_if_needed()
        gif.add(page, 2200)

        # 4. Variances for the count manager, after the recount round.
        page.goto(f"{base}/documents/{closed['dokument_id']}/variances")
        page.check("#only-diff")
        page.screenshot(path=images / "razlike.png")
        gif.add(page, 2800)

        # 5. The dashboard.
        page.set_viewport_size({"width": 1024, "height": 900})
        page.goto(f"{base}/dashboard/{snapshot}")
        page.wait_for_function("window.Chart && Chart.getChart('chart-net')")
        page.screenshot(path=images / "nadzorna_plosca.png")
        gif.add(page, 3500)

        browser.close()

    gif.save(args.output / "demo.gif")
    print(
        f"Wrote {len(gif.frames)} GIF frames to {args.output / 'demo.gif'} and images to {images}"
    )


if __name__ == "__main__":
    main()
