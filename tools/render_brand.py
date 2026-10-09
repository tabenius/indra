#!/usr/bin/env python3
"""Render Indra artwork and responsive proofs using already installed tools."""
from contextlib import contextmanager
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "web" / "assets"
BRAND = ROOT / "brand"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.path = "/assets/favicon.svg"
        super().do_GET()


@contextmanager
def website():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "web")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    if not ASSETS.is_dir() or not BRAND.is_dir():
        raise SystemExit("Expected web/assets/ and brand/ directories")
    options = webdriver.ChromeOptions()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    with website() as url, webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options) as page:
        def viewport(width, height):
            page.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})

        def screenshot(path, full=False):
            args = {"format": "png", "captureBeyondViewport": full}
            if full:
                bounds = page.execute_cdp_cmd("Page.getLayoutMetrics", {})["cssContentSize"]
                args["clip"] = {"x": 0, "y": 0, "width": bounds["width"], "height": bounds["height"], "scale": 1}
            image = page.execute_cdp_cmd("Page.captureScreenshot", args)
            path.write_bytes(base64.b64decode(image["data"]))

        for size in (16, 32, 48, 64, 128, 192, 256, 512, 1024):
            source = "favicon.svg" if size <= 48 else "indra-icon.svg"
            viewport(size, size)
            page.get(f"{url}/assets/{source}")
            screenshot(ASSETS / f"indra-icon-{size}.png")
        Image.open(ASSETS / "indra-icon-48.png").save(
            ASSETS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        for source, name in (("indra-logo.svg", "indra-logo.png"), ("indra-mono.svg", "indra-mono.png")):
            viewport(512, 512)
            page.execute_cdp_cmd("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
            page.get(f"{url}/assets/{source}")
            screenshot(BRAND / name)
        page.execute_cdp_cmd("Emulation.setDefaultBackgroundColorOverride", {})

        proof = Image.new("RGB", (1200, 520), "#F6F3EA")
        draw = ImageDraw.Draw(proof)
        font = ImageFont.load_default(size=18)
        draw.text((32, 26), "INDRA / SCALE PROOF", fill="#123E3A", font=font)
        x = 32
        for size in (16, 32, 48, 64, 128, 256, 512):
            display = min(size, 320)
            icon = Image.open(ASSETS / f"indra-icon-{size}.png").convert("RGB")
            if display != size:
                icon = icon.resize((display, display), Image.Resampling.LANCZOS)
            proof.paste(icon, (x, 110 + (320 - display) // 2))
            label = f"{size}px" if display == size else f"{size}px / shown at {display}"
            draw.text((x, 450), label, fill="#123E3A", font=font)
            x += display + 32
        proof.save(BRAND / "scale-proof.png")
        for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844), ("narrow", 320, 740)):
            viewport(width, height)
            page.get(url)
            screenshot(BRAND / f"web-{name}.png", full=True)
            assert page.title == "Indra — A net of connection"
            assert page.execute_script("return document.documentElement.scrollWidth <= window.innerWidth"), f"Overflow at {width}px"
            assert page.execute_script("return [...document.images].every(i => i.complete && i.naturalWidth > 0)"), "Missing image"
            page.find_element(By.TAG_NAME, "body").send_keys(Keys.TAB)
            assert page.execute_script("return document.querySelector('.skip') === document.activeElement"), "Skip link not first keyboard stop"
            print(f"Browser proof passed: {name}, {width}px, no overflow or missing images")
        errors = [entry for entry in page.get_log("browser") if entry["level"] == "SEVERE"]
        assert not errors, errors
    print("Rendered 9 PNG sizes, ICO, transparent marks, scale proof, and responsive page proofs.")


if __name__ == "__main__":
    main()
