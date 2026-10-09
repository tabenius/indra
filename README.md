<p align="center"><img src="web/assets/indra-logo.svg" width="160" alt="Indra: a domed net of connected jewels" /></p>

# Indra

**A net of connection. A place to belong.**

Indra is a RAGBAZ development copy of the public OSHI source, with its history
and MIT attribution retained.

## Current state

- Local Git copy of [Lastoneparis/OSHI](https://github.com/Lastoneparis/OSHI),
  based on `6048720cafac4e72cb12267985197ce0d5d22f97`, on branch `indra`.
- Original material: [upstream README](README.upstream.md), [license](LICENSE),
  [protocol](docs/protocol.md), [published core](src/), and [bot SDK](sdk/).
- New Indra identity: scalable SVG mark, small-size favicon, monochrome mark,
  launcher artwork, PNG exports, and an offline-capable [project page](web/index.html).
- **Not a released or installable Indra app.** The upstream public repository
  explicitly excludes the application shell/UI. No APK, Xcode application project,
  or signed store build is supplied by this copy.
- Dual-network support is a development goal, not implemented or verified yet.
  Upstream crypto, transport identifiers, and source names are retained.

## Project page

```bash
python3 -m http.server 8091 --bind 127.0.0.1 --directory web
```

Open <http://127.0.0.1:8091>. The static page uses local assets, system fonts,
and no analytics, remote dependencies, or JavaScript. It is ready for static
  hosting. Source is published at [tabenius/indra](https://github.com/tabenius/indra);
  no public website deployment has been performed.

## Technical planning

See the [network plan](docs/indra-networks.md) for source observations, profile
boundaries, and the evidence needed for future dual-network implementation.

The [Android debug link](docs/android-debug-link.md) provides asynchronous,
full-duplex timestamped messages through the debug Android bridge and `adb forward`.

## Branding and checks

See [brand guidance](brand/README.md) for scale-specific assets and provenance.

```bash
python3 tools/verify_indra.py
# Optional artwork export / visual proofs; requires Selenium + Pillow + Chromium/ChromeDriver:
python3 tools/render_brand.py
```

The names and geometry invoke a jewel net and interdependence. The artwork uses
Tobias's hemispherical, hair-net-like interpretation; it does not claim to be a
historically authenticated depiction of Siddhartha's hair or headwear.

## Attribution

Upstream source copyright © 2026 OSHI, MIT licensed. New Indra artwork, page,
and tooling copyright © 2026 RAGBAZ, MIT licensed under [LICENSE.indra](LICENSE.indra).
Indra is an independent project, not an official OSHI release or endorsement.
