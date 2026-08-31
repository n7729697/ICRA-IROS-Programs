#!/usr/bin/env python3
"""Build static ICRA/IROS program data from PaperCept and public indexes.

The generated catalog intentionally excludes abstracts.  It stores only the
metadata needed to browse a conference program: sessions, titles, authors,
keywords, locations, times, and source links.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html as html_lib
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache"
DATA_DIR = ROOT / "data"
USER_AGENT = "ICRA-IROS-Programs/1.0 (metadata catalog; contact via github.com/n7729697)"
PAPERCEPT = "https://ras.papercept.net/conferences/conferences"
WAYBACK = "https://web.archive.org/web"


def archived(timestamp: str, code: str, filename: str = "") -> str:
    original = f"{PAPERCEPT}/{code}/program/{filename}"
    return f"{WAYBACK}/{timestamp}id_/{original}"


CONFERENCES: list[dict[str, Any]] = [
    {
        "key": "icra-2024",
        "code": "ICRA24",
        "series": "ICRA",
        "year": 2024,
        "title": "2024 IEEE International Conference on Robotics and Automation",
        "dates": "May 13–17, 2024",
        "location": "Yokohama, Japan",
        "root_url": archived("20240522050614", "ICRA24"),
        "days": [
            ("Tuesday", archived("20240523150146", "ICRA24", "ICRA24_ContentListWeb_1.html")),
            ("Wednesday", archived("20240522044512", "ICRA24", "ICRA24_ContentListWeb_2.html")),
            ("Thursday", archived("20240516030112", "ICRA24", "ICRA24_ContentListWeb_3.html")),
        ],
        "source_note": "Complete program recovered from archived PaperCept pages.",
    },
    {
        "key": "icra-2025",
        "code": "ICRA25",
        "series": "ICRA",
        "year": 2025,
        "title": "2025 IEEE International Conference on Robotics and Automation",
        "dates": "May 19–23, 2025",
        "location": "Atlanta, USA",
        "root_url": archived("20250703172020", "ICRA25"),
        "days": [
            ("Tuesday", archived("20250415180814", "ICRA25", "ICRA25_ContentListWeb_1.html")),
            ("Wednesday", archived("20250421010636", "ICRA25", "ICRA25_ContentListWeb_2.html")),
            ("Thursday", archived("20250520015650", "ICRA25", "ICRA25_ContentListWeb_3.html")),
        ],
        "source_note": "Complete program recovered from archived PaperCept pages.",
    },
    {
        "key": "icra-2026",
        "code": "ICRA26",
        "series": "ICRA",
        "year": 2026,
        "title": "2026 IEEE International Conference on Robotics and Automation",
        "dates": "June 1–5, 2026",
        "location": "Vienna, Austria",
        "root_url": f"{PAPERCEPT}/ICRA26/program/",
        "days": [
            (day, f"{PAPERCEPT}/ICRA26/program/ICRA26_ContentListWeb_{number}.html")
            for number, day in enumerate(
                ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], start=1
            )
        ],
        "source_note": "Program parsed from the live PaperCept pages.",
    },
    {
        "key": "iros-2024",
        "code": "IROS24",
        "series": "IROS",
        "year": 2024,
        "title": "2024 IEEE/RSJ International Conference on Intelligent Robots and Systems",
        "dates": "October 14–18, 2024",
        "location": "Abu Dhabi, UAE",
        "root_url": archived("20241008053148", "IROS24"),
        "days": [
            ("Monday", None),
            ("Tuesday", None),
            ("Wednesday", archived("20241008060523", "IROS24", "IROS24_ContentListWeb_3.html")),
            ("Thursday", archived("20250323082720", "IROS24", "IROS24_ContentListWeb_4.html")),
            ("Friday", None),
        ],
        "author_index": archived("20241008063023", "IROS24", "IROS24_AuthorIndexWeb.html"),
        "keyword_index": archived("20241008062942", "IROS24", "IROS24_KeywordIndexWeb.html"),
        "crossref_container": "2024 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)",
        "source_note": (
            "Wednesday and Thursday come from archived PaperCept program pages. "
            "Monday, Tuesday, and Friday are reconstructed from the archived official "
            "author/keyword indexes and matched conservatively to Crossref metadata; "
            "unavailable time, room, and session-title fields remain blank."
        ),
    },
    {
        "key": "iros-2025",
        "code": "IROS25",
        "series": "IROS",
        "year": 2025,
        "title": "2025 IEEE/RSJ International Conference on Intelligent Robots and Systems",
        "dates": "October 19–25, 2025",
        "location": "Hangzhou, China",
        "root_url": f"{PAPERCEPT}/IROS25/program/",
        "days": [
            (day, f"{PAPERCEPT}/IROS25/program/IROS25_ContentListWeb_{number}.html")
            for number, day in enumerate(["Tuesday", "Wednesday", "Thursday"], start=1)
        ],
        "source_note": "Program parsed from the live PaperCept pages.",
    },
    {
        "key": "iros-2026",
        "code": "IROS26",
        "series": "IROS",
        "year": 2026,
        "title": "2026 IEEE/RSJ International Conference on Intelligent Robots and Systems",
        "dates": "September 27–October 1, 2026",
        "location": "Pittsburgh, PA, USA",
        "root_url": "https://2026.ieee-iros.org/",
        "days": [],
        "program_status": "not-published",
        "source_note": (
            "IROS 2026 has announced its accepted-paper results, but its public PaperCept "
            "session program has not been published as of August 31, 2026. This edition is "
            "already represented in the atlas and can be rebuilt as soon as the program goes live."
        ),
    },
]

KNOWN_TITLE_CORRECTIONS = {
    ("icra-2024", "tual-ex_15"): (
        "Actual Shape-Based Obstacle Avoidance Synthesized by Velocity–Acceleration "
        "Minimization for Redundant Manipulators: An Optimization Perspective"
    ),
    ("icra-2024", "thbl-ex_27"): (
        "Exploring Human’s Gender Perception and Bias Toward Non-Humanoid Robots"
    ),
}


# Reported conference-paper statistics. Definitions changed over time (notably
# whether journal transfers were included), so the UI presents the figures as
# reported and links the source notes rather than implying a perfectly uniform
# denominator. Older ICRA estimates are explicitly marked as approximate.
STATISTICS: dict[str, Any] = {
    "schema_version": 1,
    "range": [2010, 2026],
    "scope_note": (
        "Reported conference-paper submissions and acceptances. Track definitions vary by year; "
        "some years include journal-option papers or presentations. Approximate values are marked ≈."
    ),
    "series": [
        {
            "name": "ICRA",
            "color": "#1769d2",
            "source_url": "https://csconfstats.xoveexu.com/conferences/icra/",
            "points": [
                {"year": 2010, "submitted": 2020, "accepted": 853, "approximate": True, "sources": ["icra-history"]},
                {"year": 2011, "submitted": 1980, "accepted": 1025, "approximate": True, "sources": ["icra-history"]},
                {"year": 2012, "submitted": 2067, "accepted": 836, "sources": ["icra-2012"]},
                {"year": 2013, "submitted": 2270, "accepted": 870, "approximate": True, "sources": ["icra-history"]},
                {"year": 2014, "submitted": 2090, "accepted": 1015, "approximate": True, "sources": ["icra-history"]},
                {"year": 2015, "submitted": 2280, "accepted": 940, "approximate": True, "sources": ["icra-history", "icra-2015"]},
                {"year": 2016, "submitted": 2358, "accepted": 816, "sources": ["icra-history"]},
                {"year": 2017, "submitted": 2289, "accepted": 939, "sources": ["icra-history"]},
                {"year": 2018, "submitted": 2586, "accepted": 1056, "sources": ["icra-history"]},
                {"year": 2019, "submitted": 2916, "accepted": 1317, "sources": ["icra-history"]},
                {"year": 2020, "submitted": 2902, "accepted": 1277, "sources": ["icra-history"]},
                {"year": 2021, "submitted": 3877, "accepted": 1690, "sources": ["icra-history"]},
                {"year": 2022, "submitted": 3263, "accepted": 1428, "sources": ["icra-history"]},
                {"year": 2023, "submitted": 3125, "accepted": 1345, "sources": ["icra-history"]},
                {"year": 2024, "submitted": 3937, "accepted": 1760, "sources": ["icra-2024"]},
                {"year": 2025, "submitted": 4153, "accepted": 1606, "sources": ["icra-2025"]},
                {
                    "year": 2026,
                    "submitted": 5088,
                    "accepted": 1800,
                    "accepted_approximate": True,
                    "sources": ["icra-2026-submissions", "icra-2026-acceptance"],
                },
            ],
        },
        {
            "name": "IROS",
            "color": "#087f7b",
            "source_url": "https://csconfstats.xoveexu.com/conferences/iros/",
            "points": [
                {"year": 2010, "submitted": 1798, "accepted": 828, "sources": ["iros-history"]},
                {"year": 2011, "submitted": 2459, "accepted": 790, "sources": ["iros-2011"]},
                {"year": 2012, "submitted": 1825, "accepted": 806, "sources": ["iros-history"]},
                {"year": 2013, "submitted": 2094, "accepted": 904, "sources": ["iros-history"]},
                {"year": 2014, "submitted": 1600, "accepted": 750, "approximate": True, "sources": ["iros-history"]},
                {"year": 2015, "submitted": 2134, "accepted": 969, "sources": ["iros-2015"]},
                {"year": 2016, "submitted": 1719, "accepted": 830, "sources": ["iros-2018-wrap"]},
                {"year": 2017, "submitted": 2164, "accepted": 970, "sources": ["iros-2017"]},
                {"year": 2018, "submitted": 2700, "accepted": 1254, "sources": ["iros-history", "iros-2018-wrap"]},
                {"year": 2019, "submitted": 2494, "accepted": 1108, "sources": ["iros-history"]},
                {"year": 2020, "submitted": 2996, "accepted": 1420, "sources": ["iros-history"]},
                {"year": 2021, "submitted": 2786, "accepted": 1301, "sources": ["iros-history"]},
                {"year": 2022, "submitted": 3579, "accepted": 1716, "sources": ["iros-2022"]},
                {"year": 2023, "submitted": 2760, "accepted": 1196, "sources": ["iros-history"]},
                {"year": 2024, "submitted": 3344, "accepted": 1587, "sources": ["iros-2024"]},
                {"year": 2025, "submitted": 4306, "accepted": 1991, "sources": ["iros-2025"]},
                {"year": 2026, "submitted": 4348, "accepted": 1585, "sources": ["iros-2026"]},
            ],
        },
    ],
    "sources": [
        {
            "id": "icra-history",
            "label": "ICRA acceptance-rate history (compiled with per-year evidence)",
            "url": "https://csconfstats.xoveexu.com/conferences/icra/",
        },
        {
            "id": "icra-2012",
            "label": "ICRA 2012 official conference page",
            "url": "https://ewh.ieee.org/soc/ras/conf/fullysponsored/icra/2012/",
        },
        {
            "id": "icra-2015",
            "label": "ICRA 2015 official archived homepage",
            "url": "https://ewh.ieee.org/soc/ras/conf/fullysponsored/icra/ICRA2015updated/web.archive.org/web/20200522131042/http_/icra2015.org/index.html",
        },
        {
            "id": "icra-2024",
            "label": "IEEE RAS AdCom minutes — ICRA 2024 statistics",
            "url": "https://www.ieee-ras.org/images/AdCom_Meeting_Minutes/2024/APPROVED_AdCom_Meeting_Minutes__ICRA_2024_05172024pdf_1.pdf",
        },
        {
            "id": "icra-2025",
            "label": "IEEE Robotics & Automation Magazine — ICRA 2025 report",
            "url": "https://doi.org/10.1109/MRA.2025.3588644",
        },
        {
            "id": "icra-2026-submissions",
            "label": "ICRA 2026 official announcement — 5,088 submissions",
            "url": "https://2026.ieee-icra.org/announcement_categories/contribute/",
        },
        {
            "id": "icra-2026-acceptance",
            "label": "ICRA official conference post — approximately 1,800 accepted",
            "url": "https://www.linkedin.com/posts/ieee-icra_icra2026-ieee-ras-activity-7425260175734902784-Ho2H",
        },
        {
            "id": "iros-history",
            "label": "IROS acceptance-rate history (compiled with per-year evidence)",
            "url": "https://csconfstats.xoveexu.com/conferences/iros/",
        },
        {
            "id": "iros-2011",
            "label": "IROS 2011 official homepage",
            "url": "https://ewh.ieee.org/soc/ras/conf/financiallycosponsored/IROS/2011/IROS/index.html",
        },
        {
            "id": "iros-2015",
            "label": "IROS 2015 official conference digest",
            "url": "https://www.iros2015.org/docs/IROS_Digest_WWW.pdf",
        },
        {
            "id": "iros-2017",
            "label": "IROS 2017 official conference digest",
            "url": "https://ewh.ieee.org/conf/iros/2017/iros2017.org/images/IROS_2017_Digest_LowRes.pdf",
        },
        {
            "id": "iros-2018-wrap",
            "label": "IROS 2018 official wrap-up statistics",
            "url": "https://cbffc750-6217-497c-ba81-a78d7194278d.filesusr.com/ugd/09d8d3_eb1720ab2a234e7c93e30783c982372b.pdf",
        },
        {
            "id": "iros-2022",
            "label": "IROS 2022 official conference digest",
            "url": "https://iros2022.org/cms/wp-content/uploads/2022/10/IROS2022_ConferenceDigest_Web.pdf",
        },
        {
            "id": "iros-2024",
            "label": "IROS 2024 decision statistics (archived evidence)",
            "url": "https://staff.aist.go.jp/k.koide/evidence.html?id=iros2024",
        },
        {
            "id": "iros-2025",
            "label": "IROS 2025 official conference digest",
            "url": "https://www.iros25.org/templates/iros2025/doc/IROS2025-Digest.pdf",
        },
        {
            "id": "iros-2026",
            "label": "IROS 2026 decision figures reported by UIC Engineering",
            "url": "https://bme.uic.edu/news-stories/internship-leads-to-a-published-paper-for-undergrad/",
        },
    ],
}


def clean(value: str | Tag | None) -> str:
    if value is None:
        return ""
    if isinstance(value, Tag):
        text = value.get_text(" ", strip=True)
    else:
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def cache_path(url: str) -> Path:
    suffix = Path(url.split("?", 1)[0]).suffix or ".html"
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    return CACHE_DIR / f"{digest}{suffix}"


def fetch(url: str, refresh: bool = False, attempts: int = 4) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = cache_path(url)
    if target.exists() and not refresh:
        payload = target.read_bytes()
        return gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload

    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
            with urlopen(request, timeout=120) as response:
                payload = response.read()
            if payload.startswith(b"\x1f\x8b"):
                payload = gzip.decompress(payload)
            target.write_bytes(payload)
            return payload
        except (HTTPError, URLError, TimeoutError) as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Unable to download {url}: {error}")


def direct_rows(table: Tag) -> list[Tag]:
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]


def session_span(papers: list[dict[str, Any]]) -> str:
    times = [paper.get("time", "") for paper in papers if paper.get("time")]
    if not times:
        return ""
    first = re.match(r"([^–-]+)[–-]([^–-]+)$", times[0])
    last = re.match(r"([^–-]+)[–-]([^–-]+)$", times[-1])
    if not first or not last:
        return times[0]
    return f"{first.group(1).strip()}–{last.group(2).strip()}"


def parse_program_page(
    payload: bytes,
    conference_key: str,
    day_index: int,
    day_label: str,
    source_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    soup = BeautifulSoup(payload, "html.parser", from_encoding="windows-1252")
    sessions: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    anchor_occurrences: dict[str, int] = defaultdict(int)

    for table in soup.select("table.trk"):
        rows = direct_rows(table)
        headers = [row for row in rows if "sHdr" in (row.get("class") or [])]
        if not headers:
            continue
        session_anchor = headers[0].find("a", attrs={"name": True})
        if not session_anchor:
            continue

        anchor = str(session_anchor.get("name", "")).lower()
        code_node = session_anchor.find("b")
        code = clean(code_node) or anchor.upper()
        heading = clean(session_anchor)
        detail = heading[len(code) :].strip(" ,") if heading.lower().startswith(code.lower()) else heading
        kind, room = detail, ""
        if "," in detail:
            kind, room = [part.strip() for part in detail.split(",", 1)]
        title = ""
        if len(headers) > 1:
            title_node = headers[1].find("b") or headers[1].find("a")
            title = clean(title_node)

        first_paper_position = next(
            (position for position, row in enumerate(rows) if "pHdr" in (row.get("class") or [])),
            len(rows),
        )
        chairs: list[dict[str, str]] = []
        for row in rows[:first_paper_position]:
            text = clean(row)
            if not (text.startswith("Chair:") or text.startswith("Co-Chair:")):
                continue
            author = row.select_one('a[href*="AuthorIndexWeb"]')
            cells = row.find_all("td", recursive=False)
            chairs.append(
                {
                    "role": "Co-Chair" if text.startswith("Co-Chair:") else "Chair",
                    "name": clean(author),
                    "affiliation": clean(cells[-1]) if len(cells) > 1 else "",
                }
            )

        session_id = f"{conference_key}:{anchor}"
        session_papers: list[dict[str, Any]] = []
        paper_positions = [
            position for position, row in enumerate(rows) if "pHdr" in (row.get("class") or [])
        ]
        for list_position, position in enumerate(paper_positions):
            row = rows[position]
            paper_anchor = row.find("a", attrs={"name": True})
            if not paper_anchor:
                continue
            paper_anchor_name = str(paper_anchor.get("name", "")).lower()
            anchor_occurrences[paper_anchor_name] += 1
            occurrence = anchor_occurrences[paper_anchor_name]
            id_anchor = paper_anchor_name if occurrence == 1 else f"{paper_anchor_name}~{occurrence}"
            header_text = clean(paper_anchor)
            match = re.match(r"(.+?),\s*Paper\s+(.+)$", header_text, flags=re.IGNORECASE)
            paper_time = match.group(1).strip().replace("-", "–") if match else ""
            paper_code = match.group(2).strip() if match else header_text
            end = paper_positions[list_position + 1] if list_position + 1 < len(paper_positions) else len(rows)
            block = rows[position + 1 : end]
            title_node = next((item.select_one(".pTtl") for item in block if item.select_one(".pTtl")), None)
            title_text = clean(title_node)
            title_text = KNOWN_TITLE_CORRECTIONS.get(
                (conference_key, paper_anchor_name), title_text
            )

            authors: list[dict[str, str]] = []
            seen_authors: set[str] = set()
            for item in block:
                for author in item.select('a[href*="AuthorIndexWeb"]'):
                    name = clean(author)
                    if not name or name in seen_authors:
                        continue
                    seen_authors.add(name)
                    cells = item.find_all("td", recursive=False)
                    authors.append(
                        {
                            "name": name,
                            "affiliation": clean(cells[-1]) if len(cells) > 1 else "",
                        }
                    )

            keywords: list[str] = []
            for item in block:
                for keyword in item.select('a[href*="KeywordIndexWeb"]'):
                    value = clean(keyword)
                    if value and value not in keywords:
                        keywords.append(value)

            paper = {
                "id": f"{conference_key}:{id_anchor}",
                "anchor": paper_anchor_name,
                "code": paper_code,
                "title": title_text or f"Program entry {paper_code}",
                "authors": authors,
                "keywords": keywords,
                "day_index": day_index,
                "day": day_label,
                "session_id": session_id,
                "time": paper_time,
                "doi": "",
                "source_url": f"{source_url}#{paper_anchor_name}",
                "schedule_status": "official-program",
                "is_placeholder": not bool(title_text),
            }
            session_papers.append(paper)
            papers.append(paper)

        sessions.append(
            {
                "id": session_id,
                "anchor": anchor,
                "code": code,
                "title": title or code,
                "kind": kind,
                "room": room,
                "time": session_span(session_papers),
                "day_index": day_index,
                "day": day_label,
                "chairs": chairs,
                "paper_ids": [paper["id"] for paper in session_papers],
                "schedule_status": "official-program",
                "source_url": f"{source_url}#{anchor}",
            }
        )

    if not sessions:
        raise RuntimeError(f"No sessions found in {source_url}")
    return sessions, papers


def paper_link_parts(href: str) -> tuple[int, str] | None:
    match = re.search(r"ContentListWeb_(\d+)\.html#([A-Za-z0-9_]+)", href)
    if not match or not re.search(r"_\d+$", match.group(2)):
        return None
    return int(match.group(1)), match.group(2).lower()


def parse_author_index(payload: bytes) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(payload, "html.parser", from_encoding="windows-1252")
    entries: dict[str, dict[str, Any]] = {}
    current_author = ""
    for row in soup.select("table.lT tr"):
        named = row.select_one("a.field[name]")
        if named:
            current_author = clean(named)
        if not current_author:
            continue
        for link in row.select('a[href*="ContentListWeb_"]'):
            parts = paper_link_parts(str(link.get("href", "")))
            if not parts:
                continue
            day_index, anchor = parts
            entry = entries.setdefault(
                anchor,
                {"anchor": anchor, "day_index": day_index, "code": clean(link), "authors": []},
            )
            if current_author not in entry["authors"]:
                entry["authors"].append(current_author)
    return entries


def parse_keyword_index(payload: bytes) -> dict[str, list[str]]:
    soup = BeautifulSoup(payload, "html.parser", from_encoding="windows-1252")
    entries: dict[str, list[str]] = defaultdict(list)
    for row in soup.select("table.kT tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        keyword_node = cells[0].find("a", attrs={"name": True})
        keyword = clean(keyword_node)
        if not keyword:
            continue
        for link in cells[1].select('a[href*="ContentListWeb_"]'):
            parts = paper_link_parts(str(link.get("href", "")))
            if not parts:
                continue
            _, anchor = parts
            if keyword not in entries[anchor]:
                entries[anchor].append(keyword)
    return dict(entries)


def person_signature(name: str) -> tuple[str, str]:
    if "," in name:
        family, given = [part.strip() for part in name.split(",", 1)]
    else:
        pieces = name.split()
        family, given = (pieces[-1], " ".join(pieces[:-1])) if pieces else ("", "")
    family_key = normalized(family)
    given_key = normalized(given)
    return family_key, given_key[:1]


def author_signature(names: Iterable[str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(signature for name in names if (signature := person_signature(name))[0]))


def crossref_records(container: str, refresh: bool = False) -> list[dict[str, Any]]:
    endpoint = "https://api.crossref.org/works"
    exact: dict[str, dict[str, Any]] = {}
    saw_exact = False
    for offset in range(0, 10000, 1000):
        query = urlencode(
            {
                "query.container-title": container,
                "filter": "type:proceedings-article,from-pub-date:2024-01-01,until-pub-date:2025-12-31",
                "rows": 1000,
                "offset": offset,
                "select": "DOI,title,author,container-title,published,page,URL",
                "mailto": "n7729697@users.noreply.github.com",
            }
        )
        response = json.loads(fetch(f"{endpoint}?{query}", refresh=refresh).decode("utf-8"))
        items = response.get("message", {}).get("items", [])
        page_exact = 0
        for item in items:
            containers = item.get("container-title") or []
            if container not in containers:
                continue
            doi = str(item.get("DOI", "")).lower()
            title_values = item.get("title") or []
            title = clean(title_values[0]) if title_values else ""
            if not doi or not title:
                continue
            exact[doi] = item
            page_exact += 1
        saw_exact = saw_exact or page_exact > 0
        if saw_exact and page_exact == 0:
            break
        if len(items) < 1000:
            break
    return list(exact.values())


FRONT_MATTER = re.compile(
    r"^(iros\s*2024\s*)?(programme|program|commentary|preface|author index|cover page|subject index|table of contents|toc)$",
    re.IGNORECASE,
)


def crossref_paper(item: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in item.get("author") or []:
        given = clean(author.get("given", ""))
        family = clean(author.get("family", ""))
        display = f"{family}, {given}".strip(" ,")
        if display:
            authors.append({"name": display, "affiliation": ""})
    title_values = item.get("title") or []
    return {
        "doi": str(item.get("DOI", "")).lower(),
        "title": clean(title_values[0]) if title_values else "",
        "authors": authors,
        "page": clean(item.get("page", "")),
    }


def enrich_iros_2024(
    config: dict[str, Any],
    sessions: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    refresh: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    author_entries = parse_author_index(fetch(config["author_index"], refresh=refresh))
    keyword_entries = parse_keyword_index(fetch(config["keyword_index"], refresh=refresh))
    records = [crossref_paper(item) for item in crossref_records(config["crossref_container"], refresh=refresh)]
    records = [record for record in records if record["title"] and not FRONT_MATTER.match(record["title"])]

    records_by_doi = {record["doi"]: record for record in records}
    used_dois: set[str] = set()
    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_title[normalized(record["title"])].append(record)

    exact_title_matches = 0
    for paper in papers:
        candidates = by_title.get(normalized(paper["title"]), [])
        if len(candidates) != 1:
            continue
        record = candidates[0]
        paper["doi"] = record["doi"]
        paper["page"] = record["page"]
        used_dois.add(record["doi"])
        exact_title_matches += 1

    signature_map: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = defaultdict(list)
    record_signatures: dict[str, set[tuple[str, str]]] = {}
    for record in records:
        signature_map[author_signature(author["name"] for author in record["authors"])].append(record)
        record_signatures[record["doi"]] = set(
            author_signature(author["name"] for author in record["authors"])
        )

    direct_anchors = {paper["anchor"] for paper in papers}
    inferred_matches = 0
    subset_matches = 0
    placeholders = 0
    missing_entries = [entry for anchor, entry in author_entries.items() if anchor not in direct_anchors]
    missing_entries.sort(key=lambda entry: (entry["day_index"], entry["code"], entry["anchor"]))

    sessions_by_id = {session["id"]: session for session in sessions}
    index_source = config["author_index"]
    day_labels = {index: label for index, (label, _) in enumerate(config["days"], start=1)}

    for entry in missing_entries:
        day_index = entry["day_index"]
        code = entry["code"] or entry["anchor"].upper()
        session_code = code.rsplit(".", 1)[0] if "." in code else entry["anchor"].rsplit("_", 1)[0].upper()
        session_anchor = entry["anchor"].rsplit("_", 1)[0]
        session_id = f"{config['key']}:{session_anchor}"
        if session_id not in sessions_by_id:
            session = {
                "id": session_id,
                "anchor": session_anchor,
                "code": session_code,
                "title": f"Session {session_code}",
                "kind": "",
                "room": "",
                "time": "",
                "day_index": day_index,
                "day": day_labels[day_index],
                "chairs": [],
                "paper_ids": [],
                "schedule_status": "index-reconstructed",
                "source_url": index_source,
            }
            sessions.append(session)
            sessions_by_id[session_id] = session

        signature = author_signature(entry["authors"])
        candidates = [] if day_index == 1 else signature_map.get(signature, [])
        matched_by_subset = False
        # The archived author index sometimes lists presenters rather than every
        # co-author. A subset is accepted only when it identifies exactly one
        # proceedings record. Monday is workshops/tutorials, so no proceedings
        # inference is attempted there.
        if len(candidates) != 1 and day_index != 1 and signature:
            signature_members = set(signature)
            candidates = [
                candidate
                for candidate in records
                if signature_members.issubset(record_signatures[candidate["doi"]])
            ]
            matched_by_subset = len(candidates) == 1
        record = candidates[0] if len(candidates) == 1 else None
        if record:
            title = record["title"]
            doi = record["doi"]
            page = record["page"]
            used_dois.add(doi)
            inferred_matches += 1
            subset_matches += int(matched_by_subset)
            placeholder = False
        else:
            title = f"Program entry {code}"
            doi = ""
            page = ""
            placeholders += 1
            placeholder = True

        paper = {
            "id": f"{config['key']}:{entry['anchor']}",
            "anchor": entry["anchor"],
            "code": code,
            "title": title,
            "authors": [{"name": name, "affiliation": ""} for name in entry["authors"]],
            "keywords": keyword_entries.get(entry["anchor"], []),
            "day_index": day_index,
            "day": day_labels[day_index],
            "session_id": session_id,
            "time": "",
            "doi": doi,
            "page": page,
            "source_url": index_source,
            "schedule_status": "index-reconstructed",
            "is_placeholder": placeholder,
        }
        papers.append(paper)
        sessions_by_id[session_id]["paper_ids"].append(paper["id"])

    proceedings_only = 0
    remaining = [record for doi, record in records_by_doi.items() if doi not in used_dois]
    for record in sorted(remaining, key=lambda item: normalized(item["title"])):
        doi_token = record["doi"].replace("/", "-")
        papers.append(
            {
                "id": f"{config['key']}:doi:{doi_token}",
                "anchor": "",
                "code": "",
                "title": record["title"],
                "authors": record["authors"],
                "keywords": [],
                "day_index": None,
                "day": "Proceedings index",
                "session_id": "",
                "time": "",
                "doi": record["doi"],
                "page": record["page"],
                "source_url": f"https://doi.org/{record['doi']}",
                "schedule_status": "proceedings-only",
                "is_placeholder": False,
            }
        )
        proceedings_only += 1

    stats = {
        "crossref_records": len(records),
        "exact_title_matches": exact_title_matches,
        "index_author_matches": inferred_matches,
        "index_subset_matches": subset_matches,
        "unresolved_index_entries": placeholders,
        "proceedings_only_records": proceedings_only,
    }
    return sessions, papers, stats


def deduplicate(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = record["id"]
        if key in seen:
            raise RuntimeError(f"Duplicate {kind} id: {key}")
        seen.add(key)
        output.append(record)
    return output


def build_conference(config: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    for day_index, (day_label, url) in enumerate(config["days"], start=1):
        if not url:
            continue
        day_sessions, day_papers = parse_program_page(
            fetch(url, refresh=refresh), config["key"], day_index, day_label, url
        )
        sessions.extend(day_sessions)
        papers.extend(day_papers)

    reconstruction: dict[str, int] = {}
    if config["key"] == "iros-2024":
        sessions, papers, reconstruction = enrich_iros_2024(config, sessions, papers, refresh)

    sessions = deduplicate(sessions, "session")
    papers = deduplicate(papers, "paper")
    sessions.sort(key=lambda item: (item["day_index"], item.get("time", ""), item["code"]))
    papers.sort(
        key=lambda item: (
            item["day_index"] if item["day_index"] is not None else 99,
            item.get("time", ""),
            item.get("code", ""),
            normalized(item["title"]),
        )
    )

    real_papers = [paper for paper in papers if not paper.get("is_placeholder")]
    conference = {
        field: config[field]
        for field in ["key", "code", "series", "year", "title", "dates", "location", "root_url", "source_note"]
    }
    conference["program_status"] = config.get("program_status", "available")
    return {
        "schema_version": 1,
        "conference": conference,
        "days": [
            {"index": index, "label": label, "source_url": url or ""}
            for index, (label, url) in enumerate(config["days"], start=1)
        ],
        "sessions": sessions,
        "papers": papers,
        "counts": {
            "sessions": len(sessions),
            "papers": len(real_papers),
            "schedule_entries": len(papers),
            "authors": len({author["name"] for paper in real_papers for author in paper["authors"]}),
            "keywords": len({keyword for paper in real_papers for keyword in paper["keywords"]}),
        },
        "reconstruction": reconstruction,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="ignore the local download cache")
    parser.add_argument("--only", choices=[config["key"] for config in CONFERENCES])
    args = parser.parse_args()

    selected = [config for config in CONFERENCES if not args.only or config["key"] == args.only]
    built: list[dict[str, Any]] = []
    for config in selected:
        print(f"Building {config['key']}…", flush=True)
        catalog = build_conference(config, refresh=args.refresh)
        write_json(DATA_DIR / f"{config['key']}.json", catalog)
        built.append(catalog)
        print(
            f"  {catalog['counts']['sessions']} sessions, "
            f"{catalog['counts']['papers']} papers, "
            f"{catalog['counts']['authors']} authors",
            flush=True,
        )

    if args.only:
        existing = []
        for config in CONFERENCES:
            path = DATA_DIR / f"{config['key']}.json"
            if path.exists():
                existing.append(json.loads(path.read_text(encoding="utf-8")))
        built = existing

    by_key = {catalog["conference"]["key"]: catalog for catalog in built}
    if len(by_key) == len(CONFERENCES):
        index = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "statistics_url": "data/statistics.json",
            "conferences": [
                {
                    **catalog["conference"],
                    "counts": catalog["counts"],
                    "data_url": f"data/{catalog['conference']['key']}.json",
                }
                for catalog in (by_key[config["key"]] for config in CONFERENCES)
            ],
        }
        write_json(DATA_DIR / "index.json", index)
        write_json(DATA_DIR / "statistics.json", STATISTICS)
        print("Wrote data/index.json", flush=True)
        print("Wrote data/statistics.json", flush=True)


if __name__ == "__main__":
    main()
