"""Grounding tests — claim extraction + ground-truth matching."""

from __future__ import annotations

from zeststream_voice import BrandVoiceEnforcer


def test_96_workflows_matches(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    g = e.ground("I run 96 production workflows.")
    matched_ids = [gt_id for _, gt_id in g.matched]
    assert "n8n_workflow_count_2026_04_19" in matched_ids


def test_12_years_matches(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    g = e.ground("12 years at ZIRKEL before the acquisition.")
    matched_ids = [gt_id for _, gt_id in g.matched]
    assert "joshua_years_zirkel" in matched_ids


def test_unsourced_number_unmatched(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    g = e.ground("I've helped 10,000 clients.")
    unmatched_values = [c.value for c in g.unmatched]
    joined = " ".join(unmatched_values)
    assert "10,000" in joined


def test_empty_text_has_no_claims(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    g = e.ground("")
    assert g.matched == []
    assert g.unmatched == []


def test_grounding_result_to_dict(zeststream_brand):
    import json

    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    g = e.ground("I run 96 workflows and nobody helped 10,000 others.")
    payload = g.to_dict()
    assert json.loads(json.dumps(payload))  # json-serializable
    assert any(m["id"] == "n8n_workflow_count_2026_04_19" for m in payload["matched"])
