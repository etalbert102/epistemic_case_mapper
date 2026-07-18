from __future__ import annotations

from pathlib import Path

from scripts.build_eggs_large_source_case import build_case_payload, extract_article_record
from scripts.validate_large_source_case import validate_large_source_case


PMC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmc">1234567</article-id>
      <title-group>
        <article-title>Egg consumption and cardiovascular risk in adults</article-title>
      </title-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name><surname>Smith</surname><given-names>Jane A</given-names></name>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Jones</surname><given-names>Pat</given-names></name>
        </contrib>
      </contrib-group>
      <pub-date><year>2020</year><month>7</month><day>3</day></pub-date>
      <abstract><p>Eggs were evaluated in relation to lipid outcomes.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Higher egg intake changed LDL-C and HDL-C in this trial.</p>
      <caption><p>Table 1 shows lipid concentrations.</p></caption>
    </sec>
  </body>
</article>
"""


def test_extract_article_record_from_pmc_xml() -> None:
    record = extract_article_record(PMC_XML, fallback_uid="999", acquisition_query='"egg consumption"')

    assert record.pmc_uid == "1234567"
    assert record.source_id == "pmc1234567"
    assert record.url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/"
    assert record.title == "Egg consumption and cardiovascular risk in adults"
    assert record.authors == "Smith JA, Jones P"
    assert record.publication_date == "2020-07-03"
    assert "Higher egg intake changed LDL-C" in record.text
    assert record.word_count > 10
    assert record.raw_xml == PMC_XML


def test_build_case_payload_uses_stable_source_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    record = extract_article_record(PMC_XML, fallback_uid="999", acquisition_query='"egg consumption"')

    payload = build_case_payload("eggs_large_source_stress", [record], root, "2026-07-18")

    assert payload["case_id"] == "eggs_large_source_stress"
    assert payload["question"].startswith("For generally healthy adults")
    assert payload["sources"][0]["source_id"] == "pmc1234567"
    assert payload["sources"][0]["path"] == "data/cases/eggs_large_source_stress/sources/text/pmc1234567.txt"
    assert payload["sources"][0]["retrieval_date"] == "2026-07-18"


def test_validate_large_source_case_checks_paths_and_provenance(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    case_dir = root / "data/cases/eggs_large_source_stress"
    text_dir = case_dir / "sources/text"
    raw_dir = case_dir / "sources/raw"
    text_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    text = " ".join(["egg cardiovascular evidence"] * 20)
    (text_dir / "pmc1234567.txt").write_text(text, encoding="utf-8")
    (raw_dir / "pmc1234567.xml").write_text(PMC_XML, encoding="utf-8")
    record = extract_article_record(PMC_XML, fallback_uid="999", acquisition_query='"egg consumption"')
    payload = build_case_payload("eggs_large_source_stress", [record], root, "2026-07-18")
    case_path = case_dir / "case.yaml"
    case_path.write_text(
        "case_id: eggs_large_source_stress\n"
        "title: Eggs and Health\n"
        "question: For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial?\n"
        "case_type: large noisy source stress case\n"
        "evidence_mode: source_grounded\n"
        "review_status: draft\n"
        "status: in_progress\n"
        "sources:\n"
        f"  - source_id: {payload['sources'][0]['source_id']}\n"
        f"    title: {payload['sources'][0]['title']}\n"
        f"    url: {payload['sources'][0]['url']}\n"
        "    retrieval_date: '2026-07-18'\n"
        "    source_type: peer_reviewed_article\n"
        f"    path: {payload['sources'][0]['path']}\n"
        "    provenance_level: peer_reviewed\n"
        "    evidence_role: broad_acquired_source\n"
        "    notes: 'PMC full-text XML acquired from query: \"egg consumption\"'\n",
        encoding="utf-8",
    )

    errors = validate_large_source_case(
        case_path,
        min_sources=1,
        min_words=10,
        min_estimated_tokens=10,
        min_queries=1,
    )

    assert errors == []
