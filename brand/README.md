# Indra identity

Original artwork: a hemispherical net with four faceted diamond-shaped jewels.
The interdependence motif evokes Indra's jewel net; the dome follows Tobias's
hair-net-like interpretation. This is contemporary symbolic artwork, not a
claim about historical Buddhist dress or a literal polyhedral model.

## Asset selection

| Use | Asset |
|---|---|
| Website / large mark on light backgrounds | `../web/assets/indra-logo.svg` |
| Single-color print, engraving, recoloring | `../web/assets/indra-mono.svg` (`currentColor`) |
| Launcher and app-store source artwork | `../web/assets/indra-icon.svg` (opaque, square) |
| 16–32 px favicon or tiny thumbnail | `../web/assets/favicon.svg` (reduced lattice) |
| Legacy browser favicon | `../web/assets/favicon.ico` |
| App-store 1024 px export | `../web/assets/indra-icon-1024.png` |
| Android/PWA source exports | `../web/assets/indra-icon-192.png`, `../web/assets/indra-icon-512.png` |

PNG sizes: 16, 32, 48, 64, 128, 192, 256, 512, 1024. Small exports use the
simplified lattice; 64 px and above use the full artwork. Source artwork has
no text, filters, external resources, fonts, or embedded raster images.

Use the opaque square source for platform-generated corner masks. Geometry is
inside the central safe zone to tolerate circular cropping; exports are artwork,
not a completed Android adaptive-icon resource package or store submission.

Palette: teal `#123E3A`, gold `#E9B85C`, warm paper `#F6F3EA`. The webpage's
semantic color aliases are in `../web/styles.css`. The full mark uses two inks;
the launcher tile adds its paper-colored threads. Do not add shadows or gradients
to the logo. Avoid the fine full lattice below 48 px.

Rebuild exports and a scale proof with `python3 tools/render_brand.py` from the
repository root. The script uses existing Selenium, Pillow, Chromium, and ChromeDriver;
it does not download browser packages. See `brand/scale-proof.png` and
`brand/web-desktop.png` / `brand/web-mobile.png` for visual checks.

New artwork and page: MIT, see `../LICENSE.indra`. Upstream OSHI branding in
`../assets/` is retained for source provenance, not used as the Indra identity.
