# Engineering license and intellectual-property risk report

Assessment baseline: 2026-09-04, source commit `3bb8c01`; runtime-asset update: 2026-09-05. This is engineering-level risk analysis and release preparation, not legal advice or a determination of ownership. The product license and repository visibility were not changed. Leaflet and JSZip were subsequently bundled locally with their upstream notices and recorded hashes.

## 1. Findings and release decision

A future proprietary product is technically feasible, but this checkout is not yet cleared for proprietary external distribution. The commercial build now excludes the historical project license from product terms, selects JSZip's MIT option, and removes unapproved external map/elevation services. The remaining primary issues are ownership and relicensing authority for previously published code, the unfinished EULA, scenario and asset provenance, and native libraries bundled with GIS/image packages.

None of the six direct Python libraries or two direct browser libraries requires replacement solely because of its main license. That does not clear every binary/font inside their distributions, and it does not override the project's own GPL license.

| Requested classification | Finding | Engineering action |
| --- | --- | --- |
| Can remain proprietary in a future release | Independently owned/authorized core, backend, UI/editor and newly authored scenario material, after rights are established | Record ownership/permissions and preserve third-party terms; keep authoritative core hosted privately |
| Must retain open-license/source obligations when distributed | Existing GPL-covered copies; certifi's MPL-covered material; applicable LGPL/MPL native components; GCC runtime under its exception; applicable open-data derivatives | Preserve exact licenses and satisfy the relevant component/source requirements; do not label everything proprietary |
| Requires replacement or disabling | Any incorporated third-party code that cannot be licensed for the intended proprietary distribution; unapproved commercial API/service use; unverified/restricted native implementation if it cannot be cleared | Resolve rights, replace/rebuild, or exclude affected functionality from the release; no specific first-party source file is proven to require rewriting by this audit |
| Needs attribution/notices | Permissive dependencies, native libraries, browser libraries, bundled fonts, map providers and scenario data sources | Generate artifact-specific notices and per-pack provenance; preserve required visible map credits |

A hosted beta keeps server code off users' machines. It does not remove obligations for browser assets delivered to users, authorize third-party services, or establish rights for later customer-hosted distribution.

## 2. Evidence and limits

Reviewed tracked file inventory, `LICENSE`, dependency pins, source import/API/asset references, tracked template/test scenario metadata, author-name history, and installed Python distribution records. The [environment inventory](evidence/python-environment-2026-09-04.json) records **33 installed distributions**, their declared requirements, license metadata, notice paths and native filenames. All six direct installed versions match `requirements.txt`.

That JSON is a Windows Python 3.12.14 environment snapshot, not a release SBOM, complete static-link inventory or reproducible lock. Optional dependencies listed in metadata are declarations, not proof they are installed. Native versions/build options need separate provenance. A Linux image or rebuilt Windows artifact must be audited independently.

Git contains two author display names, which may represent one person; commit authorship alone establishes neither copyright ownership nor permission to relicense. No complete per-scenario provenance manifest was found. Intentionally excluded private campaign content, including `afghan`, was not audited or restored. A focused source scan found no embedded private-key blocks or common high-confidence access-token patterns. The former OpenTopography client and remote public basemap endpoints have been removed from the commercial runtime; `dem_scanner.py` now accepts only local, rights-cleared GeoTIFF inputs. This was not a full Git-history or entropy scan. Read-only checks on 2026-09-12 found both configured GitHub remotes available with authenticated access but unavailable through unauthenticated GitHub API requests; no visibility setting or remote content was changed. A vulnerability audit and final binary reverse-dependency analysis were not performed.

The initial assessment baseline was 89 passing tests. The productization branch now passes 140 application tests with one expected Windows symlink-privilege skip, plus 5 Windows release-policy tests and the scenario-authoring Node test. Functional success is separate from licensing clearance.

## 3. Existing project license and ownership

The root [LICENSE](../../LICENSE) is GNU GPLv3. Section 2 describes the existing grant's durability; changing Git visibility does not retract rights already granted to compliant recipients. Sections 0 and 6 distinguish network interaction from conveying a copy and describe corresponding-source requirements for covered object-code distribution.

Do not replace this file with proprietary terms as a mechanical restructuring step. Prepare an ownership ledger for core modules, editor/UI, documentation, scenarios and imported snippets, including contractor, contributor and employer/school rights where applicable. Multiple non-exclusive licenses are possible for code whose relevant rights are controlled; see the [GNU FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#ReleaseUnderGPLAndNF). Existing GPL recipients retain their applicable rights.

Engineering implications:

- Commercial use or charging a fee does not itself require removing GPL code; the issue is the intended proprietary distribution/access policy.
- If distributing this covered application under GPL, plan for corresponding source and permitted recipient rights. A closed executable alone is not a workaround.
- Private hosted server operation and shipping a customer container are different distribution cases. Browser JavaScript is delivered to users and needs its own license review.
- Future independently authored/authorized scenario packs can have distinct terms, but previously released material and third-party data retain their applicable rights. JSON format does not make content automatically proprietary.

No ownership clearance or new commercial agreement is asserted here.

## 4. Direct dependencies

License descriptions below combine local installed notices/metadata with upstream sources. Full notices for the actual chosen artifact take precedence over a short label. Current upstream pages are not substituted for historical bundled license texts.

| Component | Exact used version and principal license | Proprietary-release preparation |
| --- | --- | --- |
| Flask | 3.0.0, BSD-3-Clause | Retain copyright/terms/disclaimer; audit its resolved dependencies. [Official license](https://flask.palletsprojects.com/en/stable/license/) |
| NumPy | 1.26.0, BSD-3-Clause for NumPy | Preserve full wheel notice, including OpenBLAS/LAPACK/compiler-runtime sections. [1.26 license](https://numpy.org/doc/1.26/license.html) |
| Pillow | 10.0.1, historical PIL/HPND terms in installed metadata/notice | Retain its actual permission/copyright text and bundled-library notices; do not relabel it from a newer release. [Exact-version metadata](https://pypi.org/project/pillow/10.0.1/) |
| Rasterio | 1.3.9, BSD-3-Clause for Rasterio | Retain BSD notice and audit every bundled native component; the wheel is not BSD-only. [Exact-version metadata](https://pypi.org/project/rasterio/1.3.9/) |
| Requests | 2.31.0, Apache-2.0 | Preserve license and applicable notices, identify changes to upstream files; audit certifi and other transitives. [Exact-version metadata](https://pypi.org/project/requests/2.31.0/) |
| Matplotlib | 3.8.0, Matplotlib's PSF-based license | Retain its license/copyright and modification summary when applicable; preserve native and font notices. [Versioned license](https://matplotlib.org/3.8.0/users/project/license.html) |
| Leaflet | 1.9.4 bundled under `static/vendor/leaflet`, BSD-2-Clause | Preserve its bundled license with the JavaScript, CSS, and marker images. Its license does not license map data. [Upstream license](https://github.com/Leaflet/Leaflet/blob/main/LICENSE) |
| JSZip | 3.10.1 bundled under `static/vendor/jszip`, MIT option selected | The commercial resource keeps only `LICENSE-MIT.txt`; embedded pako 1.0.11 and its zlib 1.2.8 port retain separate MIT and zlib notices. Re-audit the browser bundle on upgrade. [Official project](https://stuk.github.io/jszip/) |

Leaflet and JSZip now load from the local release resources. Their exact upstream URLs, SHA-256 values, chosen license terms, and notice locations are recorded in `static/vendor/README.md`. Release validation requires those files and notices. No unnecessary library replacement is recommended.

### Resolved Python dependencies beyond the six direct pins

The following records are from the installed metadata snapshot; retain exact notice files rather than treating a family label as exhaustive clearance.

| Group | Observed versions | Main notice family / action |
| --- | --- | --- |
| Flask stack | Werkzeug 3.1.8, Jinja2 3.1.6, MarkupSafe 3.0.3, itsdangerous 2.2.0, click 8.4.1 | BSD family; preserve installed notices and any bundled assets |
| Shared signal/UI helpers | blinker 1.9.0, colorama 0.4.6 | MIT / BSD respectively |
| Rasterio helpers | affine 2.4.0, attrs 26.1.0, click-plugins 1.1.1.2, cligj 0.7.2, snuggs 1.4.7 | BSD/MIT families; preserve individual texts |
| Network dependencies | certifi 2026.5.20, charset-normalizer 3.4.7, idna 3.18, urllib3 2.7.0 | certifi MPL-2.0; others MIT/BSD; native charset-normalizer files also recorded |
| Plotting dependencies | contourpy 1.3.3, cycler 0.12.1, fonttools 4.63.0, kiwisolver 1.5.0, pyparsing 3.3.2 | BSD/MIT families; fonttools includes `LICENSE.external` |
| Shared packaging/date helpers | packaging 26.2, python-dateutil 2.9.0.post0, six 1.17.0 | Apache/BSD options and MIT; select valid options and retain required texts |
| Installed packaging tools | pip 26.2.1, setuptools 84.0.0, wheel 0.48.0 | Main MIT terms plus vendored components; Rasterio declares setuptools as a dependency, so do not assume it can simply be deleted |

Direct pins alone do not freeze these versions. Separate development/build tools from the runtime where supported and generate the release inventory from what is actually shipped.

## 5. Native libraries and limited copyleft

| Component/evidence | Risk and obligation scope | Action before customer distribution |
| --- | --- | --- |
| certifi: installed license identifies Mozilla-derived CA bundle under MPL-2.0 | Covered-file source/notices obligations, not automatic opening of separate CDC code. [Mozilla FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) | Archive exact covered source/modifications and tell recipients how to obtain them; retain MPL terms |
| NumPy Windows OpenBLAS DLL; installed LICENSE identifies OpenBLAS/LAPACK BSD and statically linked GCC runtime GPLv3 plus Runtime Library Exception 3.1 | Exception can allow independent application code under other terms; it is not a blanket removal of runtime requirements. [GNU exception FAQ](https://www.gnu.org/licenses/gcc-exception-faq.html) | Preserve complete notices, record build/source provenance and evaluate applicable corresponding-source obligations for the actual combined binary |
| Rasterio bundles `gdal`, `geos`, `geos_c` DLLs | GDAL is generally MIT-style; GEOS has LGPL obligations. [GDAL license](https://gdal.org/en/stable/license.html), [GEOS](https://libgeos.org/) | Identify exact versions; provide applicable library source/modifications and notices; preserve required replacement/relinking/debugging rights |
| Rasterio `iconv-2` DLL | GNU libiconv library is LGPL; standalone iconv program has different GPL terms. [GNU libiconv](https://www.gnu.org/software/libiconv/) | Confirm implementation/version/license; apply library requirements, not an assumed standalone-program classification |
| Rasterio `spatialite` and `freexl-1` DLLs | Upstream offers MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later; exact shipped version must match. [SpatiaLite](https://www.gaia-gis.it/fossil/libspatialite/index), [FreeXL](https://www.gaia-gis.it/fossil/freexl/index) | Record an available MPL/LGPL choice and comply with that version's source/notice/relinking terms; dependencies keep their own terms |
| Rasterio `szip` DLL, implementation unknown | Legacy SZIP has commercial restrictions; libaec provides a different permissively licensed compatible implementation. A filename cannot establish which was shipped. [HDF historical SZIP terms](https://docs.hdfgroup.org/archive/support/doc_resource/SZIP/Commercial_szip.html), [libaec](https://github.com/Deutsches-Klimarechenzentrum/libaec) | Hold distribution clearance until identified. If necessary rebuild using approved libaec/remove unused support, or obtain applicable rights |
| Other Rasterio native files | PROJ, HDF5, netCDF, codecs, TLS/crypto, compression, SQLite and MSVC runtime appear in the recorded bundle | Inventory exact versions, build provenance and notices; Python package metadata alone is incomplete |
| Pillow native extensions and 1,220-line installed license | Codec/font/shaping/compression code may be statically linked; absence of separate DLLs is not absence of dependencies | Preserve full license bundle and identify linked components; a GPL string in a bundled notice is not by itself proof the entire extension is GPL |
| Matplotlib native extensions/fonts | Installed notices include Qhull, AMS/BaKoMa/STIX and DejaVu-related material; actual 3.8.0 STIX notice is historical custom text | Preserve exact shipped font/library notices, reserved-name and modification terms; do not substitute newer STIX OFL text for the observed old notice |

The inspected Rasterio BSD notice and GDAL notice files do not establish the full terms of its separate DLLs. This is a release-evidence gap, not a conclusion of infringement. Do not suppress all copyleft findings by labelling the wheel BSD.

For LGPL components, packaging them in a monolithic executable or preventing library replacement may create additional obligations; choose a distribution form that preserves the applicable freedoms. This ordinarily concerns the covered library and combination conditions, not a blanket demand to open all separate product code. MPL-1.1 choices must be checked against [MPL-1.1 itself](https://www.mozilla.org/en-US/MPL/1.1/), not the MPL-2.0 summary.

## 6. Assets, external APIs and data sources

| Observed use | Risk / current evidence | Required preparation |
| --- | --- | --- |
| Local generated grid in `static/js/tactical_engine.js` | Generated in the browser; no remote tile data or map-provider account is required. Leaflet 1.9.4 is bundled with its BSD-2-Clause notice and recorded checksum | Keep as the commercial default; include the bundled Leaflet files and notice in every release artifact |
| Former OSM raster-tile endpoint | Removed from the commercial runtime. Public tile infrastructure has usage limits, visible attribution requirements and no SLA; offline/prefetch downloads are prohibited. [OSMF tile policy](https://operations.osmfoundation.org/policies/tiles/) | Keep the endpoint blocked. Reintroduce OSM-derived services or data only after documenting the specific provider, commercial use, offline/redistribution rights, and attribution |
| OSM-derived data, if later bundled in packs | Database is ODbL; covered derivative databases may carry share-alike/source obligations, distinct from product source. [OSM license](https://www.openstreetmap.org/copyright) | Keep source/licensing/attribution for data layers; assess derivative database vs produced output rather than calling the whole engine open |
| Former Esri World_Topo_Map endpoint | Removed from the commercial runtime because complete provider credits and commercial service authorization were not established | Keep the endpoint blocked. Any future Esri integration requires documented service authorization and the provider credits described in [official attribution guidance](https://support.esri.com/en-us/knowledge-base/what-is-the-correct-way-to-cite-an-arcgis-online-basema-000012040) |
| Former OpenTopography `globaldem` client | Removed from `dem_scanner.py` and excluded from the commercial runtime. The editor utility now reads only local GeoTIFF inputs whose rights have been approved. OpenTopography states separate access requirements for commercial software integration. [Developer requirements](https://opentopography.org/developers) | Keep the remote client and API-key handling out of commercial builds unless an approved commercial arrangement is documented |
| SRTM GL3 elevation data formerly selected by the removed client | No SRTM raster is bundled or downloaded by the commercial profile. Provider access terms and dataset rights are distinct. | Before adding any elevation raster, record the exact source, version, acquisition date, citation, commercial-use permission, redistribution evidence, and derivation |
| Tracked scenario JSON and manuals | Template/test data has no dedicated asset/provenance manifest | Establish authorship and any copied briefing/data sources before assigning commercial terms |
| Fonts, icons and images | No standalone raster/vector/font/map files are tracked in the inspected file list; UI uses system font families and text symbols. Dependencies still contain their own assets | System font-family references do not ship fonts. If fonts/images are bundled later, inventory and license those files; preserve dependency assets/notices now |
| Bundled Leaflet 1.9.4 and JSZip 3.10.1 | Exact runtime files, upstream locations, hashes, and notices are recorded in `static/vendor/README.md`; Leaflet uses BSD-2-Clause and the JSZip MIT option is selected | Preserve both license files in release artifacts and re-audit on every dependency update |

The application retains a Leaflet attribution control, while the generated local grid has no external map-provider credit. Any future provider or offline dataset must add legible provider-specific credits in the interactive map and applicable exports.

No AWS/Azure/LLM/payment API integration was found in the inspected application source. This statement excludes optional capabilities in third-party dependencies and intentionally excluded customer data.

## 7. Release actions, in priority order

1. **Rights ledger:** identify owners/permissions for existing project code and content before proprietary distribution. Preserve historical notices and do not assume two author aliases equal complete ownership.
2. **Artifact audit:** identify native implementations/versions, especially GEOS, libiconv, SpatiaLite, FreeXL and `szip`; resolve library-source/relinking and runtime exceptions. Block customer distribution for unresolved cases.
3. **Service policy:** keep the commercial runtime local by default. The OpenTopography downloader and public Esri/OSM tile endpoints are removed; add a provider or offline dataset only after its exact commercial integration, redistribution, privacy, and attribution terms are approved and recorded.
4. **Attribution package:** generate `THIRD_PARTY_NOTICES`, exact `licenses/` texts, and required source-access materials from the release artifact. This report is not a replacement for those notices.
5. **Content provenance:** per pack, record file hash, creator/source URL, dataset version/acquisition date, license/permission evidence, modifications, redistribution scope and required credit. Unknown assets stay out of commercial packages until resolved.
6. **Repeatable build:** lock dependencies, preserve approved source/binary provenance and hashes, scan the final artifact, and recheck notices on upgrades. Keep customer payloads and secrets out of build context.

No full-engine rewrite is justified by the dependency audit. Preserve the simulation while resolving the specific distribution and provenance gaps above.
