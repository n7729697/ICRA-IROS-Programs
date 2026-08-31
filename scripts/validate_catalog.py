#!/usr/bin/env python3
"""Validate generated conference catalogs and their cross-references."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXPECTED = {"icra-2024", "icra-2025", "icra-2026", "iros-2024", "iros-2025"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    indexed = {conference["key"] for conference in index["conferences"]}
    require(indexed == EXPECTED, f"index editions differ: {indexed ^ EXPECTED}")

    total_papers = 0
    for key in sorted(EXPECTED):
        path = DATA / f"{key}.json"
        require(path.exists(), f"missing {path.name}")
        catalog = json.loads(path.read_text(encoding="utf-8"))
        require(catalog["schema_version"] == 1, f"{key}: unsupported schema")
        require(catalog["conference"]["key"] == key, f"{key}: mismatched conference key")
        require(catalog["conference"]["root_url"].startswith("https://"), f"{key}: invalid root URL")

        sessions = catalog["sessions"]
        papers = catalog["papers"]
        session_ids = [session["id"] for session in sessions]
        paper_ids = [paper["id"] for paper in papers]
        require(len(session_ids) == len(set(session_ids)), f"{key}: duplicate session id")
        require(len(paper_ids) == len(set(paper_ids)), f"{key}: duplicate paper id")
        require(sessions and papers, f"{key}: empty program")

        paper_id_set = set(paper_ids)
        for session in sessions:
            require(set(session["paper_ids"]) <= paper_id_set, f"{key}: dangling paper in {session['id']}")
            require(session["day_index"] in {day["index"] for day in catalog["days"]}, f"{key}: invalid session day")
        for paper in papers:
            require("abstract" not in paper, f"{key}: abstracts must not be stored")
            require(bool(paper["title"]), f"{key}: blank title in {paper['id']}")
            require("<sup>" not in paper["title"].lower(), f"{key}: unclean title markup")
            if paper["session_id"]:
                require(paper["session_id"] in set(session_ids), f"{key}: missing session for {paper['id']}")
            if paper["doi"]:
                require(paper["doi"].startswith("10."), f"{key}: malformed DOI")

        real_papers = [paper for paper in papers if not paper.get("is_placeholder")]
        require(catalog["counts"]["papers"] == len(real_papers), f"{key}: paper count mismatch")
        require(catalog["counts"]["sessions"] == len(sessions), f"{key}: session count mismatch")
        total_papers += len(real_papers)
        print(
            f"{key:10}  {len(sessions):4} sessions  {len(real_papers):4} paper records  "
            f"{sum(p.get('is_placeholder', False) for p in papers):4} placeholders"
        )

    for asset in [ROOT / "index.html", ROOT / "assets/app.js", ROOT / "assets/styles.css"]:
        require(asset.exists() and asset.stat().st_size > 0, f"missing site asset: {asset}")
    print(f"Validated {len(EXPECTED)} editions and {total_papers:,} paper records.")


if __name__ == "__main__":
    main()

