from __future__ import annotations

from epistemic_case_mapper.map_briefing_memo_metadata import ensure_reader_memo_metadata, source_list_lines


def test_reader_memo_metadata_links_source_list_and_inline_mentions() -> None:
    memo = """## Decision Brief

The strongest support comes from Dehghan 2020 (Egg Consumption And Risk Of Cardiovascular Disease: Three Large Prospective US Cohort Studies, Systematic Review, And Updated Meta Analysis), while Study Without Url is retained as a source label only.

**Confidence:** medium
"""
    scaffold = {
        "source_display_names": {
            "dehghan": "Dehghan 2020",
            "bmj": "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis",
            "study_without_url": "Study Without Url",
        },
        "source_urls": {
            "dehghan": "https://example.org/dehghan",
            "bmj": "https://example.org/bmj",
        },
        "source_citation_labels": {"bmj": "Drouin-Chartier et al. 2020"},
    }

    updated = ensure_reader_memo_metadata(memo, scaffold)

    assert "[Dehghan 2020](https://example.org/dehghan)" in updated
    assert "[Drouin-Chartier et al. 2020](https://example.org/bmj)" in updated
    assert "Egg Consumption And Risk Of Cardiovascular Disease: Three Large Prospective US Cohort Studies" not in updated
    assert "- [Dehghan 2020](https://example.org/dehghan)" in updated
    assert "- [Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis](https://example.org/bmj)" in updated
    assert "- Study Without Url" in updated
    assert "[Study Without Url]" not in updated


def test_source_list_lines_ignores_unlinkable_urls() -> None:
    lines = source_list_lines(
        {
            "source_display_names": {"s1": "Source One"},
            "source_urls": {"s1": "javascript:alert(1)"},
        }
    )

    assert "- Source One" in lines
    assert "javascript:" not in "\n".join(lines)


def test_reader_memo_metadata_smooths_generic_intro_and_duplicate_prefixed_evidence() -> None:
    memo = """## Decision Brief

The current map supports a neutral under stated conditions answer frame. The main support is: Evidence supports a neutral default under stated conditions. The strongest counterposition is: Counterevidence supports caution because some evidence indicates higher risk.

## Why This Read

Default population: Moderate intake was not associated with worse outcomes (Study A). Dose boundary: Moderate intake was not associated with worse outcomes (Study A). Hard-outcome support: Better evidence used clinical events (Study B); and Moderate intake was not associated with worse outcomes (Study A).

**Confidence:** medium
"""

    updated = ensure_reader_memo_metadata(memo, {"source_display_names": {"a": "Study A"}})

    assert "answer frame" not in updated
    assert "The current map supports a neutral under stated conditions read." in updated
    assert updated.count("Moderate intake was not associated with worse outcomes") == 1
    assert "Better evidence used clinical events" in updated

