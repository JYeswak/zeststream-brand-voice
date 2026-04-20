"""Layer 1 (banned-words + operator-variant) regression tests."""

from __future__ import annotations

from zeststream_voice import BrandVoiceEnforcer


def test_banned_word_triggers_veto(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    r = e.score("our platform helps you synergize")
    layer = r.layers["layer1_banned_words"]
    assert layer.vetoed is True
    assert r.passed is False
    assert r.composite == 0.0


def test_clean_text_passes_layer1(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    r = e.score("I build things that work.")
    layer = r.layers["layer1_banned_words"]
    assert layer.vetoed is False
    assert layer.score == 100.0


def test_josh_variant_caught(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    r = e.score("I'm Josh and I build things.")
    hits = r.layers["layer1_banned_words"].details["hits"]
    assert any(h.get("word") == "Josh" for h in hits)
    assert r.layers["layer1_banned_words"].vetoed is True


def test_joshua_canonical_is_NOT_banned(zeststream_brand):
    """Regression: the trauma memo says 'Joshua' was accidentally in the ban list."""
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    r = e.score("I'm Joshua and I build things that work.")
    hits = r.layers["layer1_banned_words"].details["hits"]
    # Joshua alone must NOT be flagged
    assert not any(h.get("word") == "Joshua" for h in hits)


def test_banned_phrase_caught(zeststream_brand):
    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    # "empower" is a banned phrase (verb form)
    r = e.score("Tools that empower your team.")
    assert r.layers["layer1_banned_words"].vetoed is True


def test_score_result_to_dict_is_json_safe(zeststream_brand):
    import json

    e = BrandVoiceEnforcer(brand_path=zeststream_brand)
    r = e.score("our platform synergizes at scale")
    payload = r.to_dict()
    # round-trip through json to confirm no non-serializable types
    assert json.loads(json.dumps(payload))["composite"] == 0.0
