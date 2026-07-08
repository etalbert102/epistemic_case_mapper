from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_packet_memo import build_packet_memo_plan, render_packet_first_draft, write_packet_first_artifacts
from epistemic_case_mapper.map_briefing_reader_packet_verbalization import (
    apply_reader_packet_verbalizations,
    canonicalize_reader_packet_source_aliases,
)
from test_decision_briefing_packet import _scaffold


def test_reader_packet_verbalization_accepts_safe_prose_and_renderer_uses_it() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    plan = build_packet_memo_plan(built["decision_briefing_packet"])
    reader_packet = plan["reader_facing_packet"]
    card = reader_packet["evidence_cards"][0]

    verbalized, accepted, rejected = apply_reader_packet_verbalizations(
        reader_packet,
        {
            "verbalizations": [
                {
                    "card_id": card["card_id"],
                    "sentence": "Outcome Study reports that Option A reduced flood losses by 25% in comparable river cities [Outcome Study].",
                }
            ]
        },
    )
    plan["reader_facing_packet"] = verbalized
    draft = render_packet_first_draft(plan)

    assert accepted == [{"card_id": card["card_id"], "section": "evidence_cards", "canonicalized_source": True}]
    assert rejected == []
    assert "Outcome Study reports that Option A reduced flood losses by 25%" in draft
    assert "bundle_" not in draft


def test_reader_packet_verbalization_accepts_simple_source_alias_and_canonicalizes_it() -> None:
    reader_packet = {
        "evidence_cards": [
            {
                "card_id": "evidence_01",
                "statement": "A one-egg-per-day increase was not associated with cardiovascular disease.",
                "source": "Drouin-Chartier et al. 2020",
                "quantities": ["one", "2020"],
            }
        ],
        "source_trail": [{"source": "Drouin-Chartier et al. 2020"}],
    }

    verbalized, accepted, rejected = apply_reader_packet_verbalizations(
        reader_packet,
        {
            "verbalizations": [
                {
                    "card_id": "evidence_01",
                    "sentence": "A one-egg-per-day increase was not associated with cardiovascular disease [Drouin-Chartier 2020].",
                }
            ]
        },
    )

    assert accepted == [{"card_id": "evidence_01", "section": "evidence_cards", "canonicalized_source": True}]
    assert rejected == []
    assert verbalized["evidence_cards"][0]["prose"].endswith("[Drouin-Chartier et al. 2020].")


def test_reader_packet_verbalization_rejects_dropped_number_or_source() -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")
    reader_packet = build_packet_memo_plan(built["decision_briefing_packet"])["reader_facing_packet"]
    card = reader_packet["evidence_cards"][0]

    verbalized, accepted, rejected = apply_reader_packet_verbalizations(
        reader_packet,
        {
            "sentences": [
                {
                    "card_id": card["card_id"],
                    "sentence": "Option A reduced flood losses in comparable river cities.",
                }
            ]
        },
    )

    assert accepted == []
    assert rejected
    assert "prose" not in verbalized["evidence_cards"][0]
    assert any("missing accepted bracketed source label" in issue for issue in rejected[0]["issues"])
    assert any("missing protected number: 25%" in issue for issue in rejected[0]["issues"])


def test_reader_packet_source_aliases_are_canonicalized_after_memo_rewrite() -> None:
    reader_packet = {
        "source_trail": [
            {"source": "Drouin-Chartier et al. 2020"},
            {"source": "Nordic Nutrition Recommendations evidence review authors 2023"},
        ]
    }
    memo = "The main result is neutral [Drouin-Chartier 2020]. A scoping review adds dose nuance [NNR 2023]."

    canonicalized = canonicalize_reader_packet_source_aliases(memo, reader_packet)

    assert "[Drouin-Chartier et al. 2020]" in canonicalized
    assert "[Nordic Nutrition Recommendations evidence review authors 2023]" in canonicalized
    assert "[Drouin-Chartier 2020]" not in canonicalized
    assert "[NNR 2023]" not in canonicalized


def test_write_packet_first_artifacts_runs_reader_packet_verbalization_with_backend(tmp_path: Path, monkeypatch) -> None:
    built = build_decision_briefing_packet_bundle(_scaffold(), question="Should the city adopt option A for flood protection?")

    class FakeResult:
        prompt_only = False
        text = (
            '{"verbalizations":[{'
            '"card_id":"evidence_01",'
            '"sentence":"Outcome Study reports that Option A reduced flood losses by 25% in comparable river cities [Outcome Study]."'
            "}]}"
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_reader_packet_verbalization.run_model_backend", lambda *args, **kwargs: FakeResult())

    result = write_packet_first_artifacts(
        artifacts=tmp_path,
        packet=built["decision_briefing_packet"],
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["reader_packet_verbalization_status"] == "accepted"
    assert result["report"]["reader_packet_verbalization_accepted_count"] == 1
    assert "Outcome Study reports that Option A reduced flood losses by 25%" in result["draft"]
    assert result["reader_packet_verbalization_prompt_path"].exists()
    assert result["reader_packet_verbalization_raw_path"].exists()
    assert result["reader_packet_verbalization_report_path"].exists()
