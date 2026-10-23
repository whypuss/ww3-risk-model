"""Tests for WW3 Risk Model Protests Detail (Summary + Sources)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ww3_risk.dashboard import build_dashboard


def test_protests_snapshot_has_summary_and_sources():
    """Verify data/protests_snapshot.json has summary and sources for all 33 countries:
    - summary: non-empty string, length >= 10
    - sources: non-empty list, each with name and http(s) URL
    - evidence == 'verified' countries have >= 2 sources
    """
    protests_file = Path("data/protests_snapshot.json")
    assert protests_file.exists(), "data/protests_snapshot.json must exist"

    protests = json.loads(protests_file.read_text(encoding="utf-8"))
    countries = protests["countries"]
    assert len(countries) == 33

    for c in countries:
        name = c["name_zh"]
        # summary field
        assert "summary" in c, f"{name}: missing 'summary' field"
        summary = c["summary"]
        assert isinstance(summary, str), f"{name}: summary must be string"
        assert len(summary) >= 10, f"{name}: summary too short ({len(summary)} chars): {summary}"

        # sources field
        assert "sources" in c, f"{name}: missing 'sources' field"
        sources = c["sources"]
        assert isinstance(sources, list), f"{name}: sources must be list"
        assert len(sources) > 0, f"{name}: sources list must not be empty"

        for src in sources:
            assert "name" in src, f"{name}: source missing 'name'"
            assert isinstance(src["name"], str) and src["name"], f"{name}: source name must be non-empty string"
            assert "url" in src, f"{name}: source missing 'url'"
            url = src["url"]
            assert isinstance(url, str) and url, f"{name}: source url must be non-empty string"
            assert url.startswith("http://") or url.startswith("https://"), f"{name}: url must start with http:// or https://: {url}"

        # evidence == 'verified' countries must have >= 2 sources
        if c.get("evidence") == "verified":
            assert len(sources) >= 2, f"{name}: verified country must have >= 2 sources, got {len(sources)}"


def test_dashboard_html_contains_protests_detail(tmp_path):
    """Verify generated dashboard HTML contains protest inspector detail:
    - Contains '來源' text
    - At least one target="_blank" source link
    - Contains France summary text (e.g., '憤怒日')
    """
    out_html = tmp_path / "dashboard.html"
    out_json = tmp_path / "dashboard_data.json"

    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=out_json,
        ui_step=5,
    )

    content = out_html.read_text(encoding="utf-8")

    # 1. Contains '來源' label (in JS or HTML)
    assert "來源：" in content, "HTML missing '來源：' label"

    # 2. At least one target="_blank" source link (in JS constant or HTML)
    target_blank_links = re.findall(r'target="_blank"', content)
    assert len(target_blank_links) >= 1, f"Expected at least one target='_blank' link, found {len(target_blank_links)}"

    # 3. Contains France summary text (e.g., '憤怒日') in pre-rendered HTML
    assert "憤怒日" in content, "HTML missing France summary text '憤怒日'"

    # 4. protest-inspector-detail container exists
    assert 'id="protest-inspector-detail"' in content, "Missing protest-inspector-detail container"

    # 5. protest-inspector-summary class exists (in pre-rendered HTML)
    assert 'class="protest-inspector-summary"' in content, "Missing protest-inspector-summary class"

    # 6. protest-source-list class exists (in JS code as string)
    assert "protest-source-list" in content, "Missing protest-source-list class reference"

    # 7. Default text mentions new functionality
    assert "事件簡述與來源連結" in content, "Default inspector text missing new functionality description"


def test_protests_detail_default_france_rendered(tmp_path):
    """Verify that on page load, France details are pre-rendered in inspector detail."""
    out_html = tmp_path / "dashboard.html"
    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )

    content = out_html.read_text(encoding="utf-8")

    # Check that initProtestsMonitor calls selectProtestCountry for France
    assert 'data-country="法國"' in content
    assert "selectProtestCountry" in content


def test_protests_verified_countries_sources_count():
    """Verify all verified evidence countries have >= 2 sources."""
    protests_file = Path("data/protests_snapshot.json")
    protests = json.loads(protests_file.read_text(encoding="utf-8"))
    countries = protests["countries"]

    verified_countries = [c for c in countries if c.get("evidence") == "verified"]
    assert len(verified_countries) == 22

    for c in verified_countries:
        sources = c.get("sources", [])
        assert len(sources) >= 2, f"{c['name_zh']}: verified but only {len(sources)} sources"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])