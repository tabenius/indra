#!/usr/bin/env python3
"""Check local site references, SVG structure, JSON, and upstream core preservation."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.headings = 0
        self.bad_images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "h1":
            self.headings += 1
        if tag == "img" and "alt" not in attrs:
            self.bad_images.append(attrs.get("src"))
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])


def main():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text())
    assert page.headings == 1, "Expected one h1"
    assert not page.bad_images, page.bad_images
    for link in page.links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            continue
        if url.path:
            assert (ROOT / "web" / unquote(url.path)).is_file(), f"Missing site asset: {link}"
        elif url.fragment:
            assert url.fragment in page.ids, f"Missing anchor: {link}"
    for path in (ROOT / "web/assets").glob("*.svg"):
        svg = ET.parse(path).getroot()
        assert svg.tag == "{http://www.w3.org/2000/svg}svg" and svg.get("viewBox"), path
        assert not any(el.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"} for el in svg.iter()), path
        assert not any(k.rsplit("}", 1)[-1] == "href" for el in svg.iter() for k in el.attrib), path
    for size in (16, 32, 48, 64, 128, 192, 256, 512, 1024):
        path = ROOT / "web/assets" / f"indra-icon-{size}.png"
        header = path.read_bytes()[:24]
        assert header[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG: {path}"
        assert struct.unpack(">II", header[16:24]) == (size, size), f"Wrong PNG dimensions: {path}"
    ico = (ROOT / "web/assets/favicon.ico").read_bytes()
    assert struct.unpack("<HHH", ico[:6]) == (0, 1, 3), "Expected three-size ICO"
    provenance = json.loads((ROOT / "docs/upstream.json").read_text())
    base = provenance["base_revision"]
    assert subprocess.run(["git", "diff", "--exit-code", base, "--", "src", "sdk", "LICENSE"], cwd=ROOT).returncode == 0, "Unexpected upstream core changes"
    original = subprocess.check_output(["git", "show", f"{base}:README.md"], cwd=ROOT)
    assert (ROOT / "README.upstream.md").read_bytes() == original, "Upstream README altered"
    for name in ("README.md", "CONTRIBUTING.md"):
        text = (ROOT / name).read_text()
        for link in re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'src="([^"]+)"', text):
            if link.startswith(("http", "mailto:", "#")):
                continue
            assert (ROOT / link.split("#")[0]).exists(), f"Missing {name} reference: {link}"
    print("Indra checks passed: links/anchors, SVGs, PNG/ICO sizes, page structure, provenance, and unchanged upstream core.")


if __name__ == "__main__":
    main()
