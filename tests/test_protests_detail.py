"""Tests for WW3 Risk Model Protests Detail (Summary + Sources)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
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


def extract_script_blocks(html: str) -> list[str]:
    """Extract all <script>...</script> block contents from HTML that are JavaScript (not JSON)."""
    # Match <script> blocks but exclude type="application/json"
    pattern = r'<script(?![^>]*type="application/json")[^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
    return [m.strip() for m in matches]


def test_dashboard_js_syntax_valid(tmp_path):
    """Validate all <script> blocks in generated dashboard with node --check."""
    out_html = tmp_path / "dashboard.html"

    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        output_json_path=tmp_path / "dashboard_data.json",
        ui_step=5,
    )

    content = out_html.read_text(encoding="utf-8")
    script_blocks = extract_script_blocks(content)

    # node must be available
    node_path = shutil.which("node")
    if not node_path:
        import pytest
        pytest.skip("node not available in PATH, skipping JS syntax check")

    for i, script in enumerate(script_blocks):
        if not script.strip():
            continue
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(script)
            temp_js = f.name
        try:
            result = subprocess.run(
                [node_path, "--check", temp_js],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"Script block {i} failed node --check:\n{result.stderr}\nScript:\n{script[:500]}..."
        finally:
            Path(temp_js).unlink(missing_ok=True)


def test_dashboard_pre_rendered_france_sources(tmp_path):
    """Verify pre-rendered inspector contains France summary and first source link with correct href, target, and text."""
    out_html = tmp_path / "dashboard.html"

    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )

    content = out_html.read_text(encoding="utf-8")

    # Load protests data to get expected France source
    protests = json.loads(Path("data/protests_snapshot.json").read_text(encoding="utf-8"))
    france = next(c for c in protests["countries"] if c["name_zh"] == "法國")
    first_source = france["sources"][0]
    expected_name = first_source["name"]
    expected_url = first_source["url"]

    # Check protest-inspector-detail container exists
    assert 'id="protest-inspector-detail"' in content, "Missing protest-inspector-detail container"

    # Extract the pre-rendered content inside protest-inspector-detail
    detail_match = re.search(
        r'id="protest-inspector-detail">(.*?)</div>\s*</div>\s*</div>',
        content,
        re.DOTALL,
    )
    assert detail_match, "Could not find protest-inspector-detail content"
    detail_html = detail_match.group(1)

    # Check France summary is present
    assert "憤怒日" in detail_html, "France summary missing '憤怒日' in pre-rendered detail"

    # Check protest-inspector-summary class exists
    assert 'class="protest-inspector-summary"' in detail_html, "Missing protest-inspector-summary class"

    # Check protest-source-list class exists
    assert 'class="protest-source-list"' in detail_html, "Missing protest-source-list class"

    # Check "來源：" label
    assert "來源：" in detail_html, "Missing '來源：' label in pre-rendered sources"

    # Check first source link: href, target="_blank", rel="noopener noreferrer", and link text
    source_link_pattern = (
        r'<a href="' + re.escape(expected_url) + r'" target="_blank" rel="noopener noreferrer">' + re.escape(expected_name) + r"</a>"
    )
    assert re.search(source_link_pattern, detail_html), (
        f"First source link not found or incorrect in pre-rendered detail. "
        f"Expected: <a href=\"{expected_url}\" target=\"_blank\" rel=\"noopener noreferrer\">{expected_name}</a>"
    )


def test_dashboard_js_click_path_and_no_dead_code(tmp_path):
    """Verify JS click path exists and dead code (TARGET_BLANK_ATTR, (void)) is removed."""
    out_html = tmp_path / "dashboard.html"

    build_dashboard(
        scenario_path="scenarios/baseline_2026.json",
        output_html_path=out_html,
        ui_step=5,
    )

    content = out_html.read_text(encoding="utf-8")
    script_blocks = extract_script_blocks(content)

    # Combine all script blocks for searching
    all_js = "\n".join(script_blocks)

    # 1. selectProtestCountry function must exist
    assert "selectProtestCountry" in all_js, "JS missing selectProtestCountry function"

    # 2. createElement must be used (for dynamic source link creation in JS path)
    assert "createElement" in all_js, "JS missing createElement usage (dynamic source rendering)"

    # 3. Dead code must NOT exist
    assert "TARGET_BLANK_ATTR" not in all_js, "Dead code TARGET_BLANK_ATTR still present in JS"
    assert "(void)" not in all_js, "Dead code (void) still present in JS"


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