# Bundled browser dependencies

These files are copied into release builds so the CDC Sim dashboard and scenario editor do not depend on a public CDN at runtime.

| Component | Version | Files | Upstream distribution | Selected license |
| --- | --- | --- | --- | --- |
| Leaflet | 1.9.4 | `leaflet/leaflet.js`, `leaflet/leaflet.css`, marker images | https://unpkg.com/leaflet@1.9.4/ | BSD-2-Clause; see `leaflet/LICENSE` |
| JSZip | 3.10.1 | `jszip/jszip.min.js` | https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js | MIT option selected; see `jszip/LICENSE-MIT.txt` |
| pako/zlib (embedded in JSZip) | 1.0.11 / zlib 1.2.8 port | contained in `jszip/jszip.min.js` | https://github.com/nodeca/pako/tree/1.0.11 | MIT plus zlib terms; see `jszip/PAKO-LICENSE-MIT.txt` and `jszip/PAKO-ZLIB-LICENSE.txt` |

Release-source checksums:

- Leaflet JavaScript: `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a`
- Leaflet CSS: `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6`
- JSZip JavaScript: `ebf3bdf5397570107bd3ed32293b20e3de3755c40e95147b186a2f5646ad1a79`

Do not update these files without updating the version, license copy, checksums, release validation, and browser regression tests.

