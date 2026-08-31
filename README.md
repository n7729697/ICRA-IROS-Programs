# ICRA & IROS Program Atlas

A fast, searchable static browser for five robotics conference programs:

- ICRA 2024, 2025, and 2026
- IROS 2024 and 2025

The site follows the useful information architecture of a PaperCept program—conference/day navigation, sessions, papers, authors, keywords, and a saved program—while using an original responsive interface. It has no server or database and is designed for GitHub Pages.

**Live site:** [n7729697.github.io/ICRA-IROS-Programs](https://n7729697.github.io/ICRA-IROS-Programs/)

## Features

- Switch between all five conference editions
- Browse by day and technical session
- Search titles, authors, affiliations, keywords, and session names
- View either session groups or a compact paper grid
- Save papers locally in the browser
- Follow DOI and program-source links
- Rebuild every JSON catalog from source with one Python command

Abstracts are deliberately excluded. This keeps the repository small and limits the catalog to factual program metadata.

## Data provenance

| Edition | Program source | Coverage |
| --- | --- | --- |
| ICRA 2024 | Archived PaperCept pages | Complete program pages for Tuesday–Thursday |
| ICRA 2025 | Archived PaperCept pages | Complete program pages for Tuesday–Thursday |
| ICRA 2026 | Live PaperCept pages | Complete listed program, Sunday–Friday |
| IROS 2024 | Archived PaperCept pages, author/keyword indexes, Crossref | Wednesday–Thursday pages are direct; missing pages are conservatively reconstructed and visibly labeled |
| IROS 2025 | Live PaperCept pages | Complete listed program, Tuesday–Thursday |

The archived IROS 2024 capture does not contain its Monday, Tuesday, or Friday content pages. The builder therefore uses the archived author and keyword indexes to recover paper codes and days, then associates a title only when the listed authors identify one Crossref proceedings record. It never invents a time, room, or session title. Unresolved entries remain visible as placeholders, and unmatched proceedings papers remain searchable in a separate “Proceedings index” day.

Source URLs are recorded in every generated catalog. This project is independent and is not affiliated with IEEE, RAS, RSJ, or PaperCept.

## Run locally

No JavaScript build step is needed.

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000>.

## Rebuild the catalogs

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/build_catalog.py
python3 scripts/validate_catalog.py
```

Downloads are cached under `.cache/`. Pass `--refresh` to retrieve every source again, or `--only iros-2024` to rebuild a single edition.

## Repository layout

```text
assets/                  Browser application and styles
data/                    Generated, edition-specific JSON catalogs
scripts/build_catalog.py Reproducible downloader and parser
scripts/validate_catalog.py Catalog integrity checks
index.html               Static application shell
```

## License

The site code and data-building scripts are released under the [MIT License](LICENSE). Conference names, program metadata, and linked source material remain subject to their respective owners’ terms.

