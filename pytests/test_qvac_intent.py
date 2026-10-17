import pytest

from web.qvac_intent import (
    QvacIntent,
    QvacIntentError,
    apply_canonical_phrase_policy,
    parse_intent_output,
)


def test_qvac_output_accepts_only_frozen_five_dollar_intent():
    result = parse_intent_output(
        '{"intent":"LOAD_NOTE","amount_cents":500}',
        model="local-test",
        latency_ms=12,
        backend="gpu",
    )

    assert result.intent == "LOAD_NOTE"
    assert result.amount_cents == 500
    assert result.public()["local"] is True


def test_qvac_wrong_amount_fails_closed_to_unknown():
    result = parse_intent_output(
        '{"intent":"LOAD_NOTE","amount_cents":1000}', model="local-test"
    )

    assert result.intent == "UNKNOWN"
    assert result.amount_cents is None


def test_qvac_discards_amount_for_non_amount_intent():
    result = parse_intent_output(
        '{"intent":"PASS_NOTE","amount_cents":500}', model="local-test"
    )

    assert result.intent == "PASS_NOTE"
    assert result.amount_cents is None


@pytest.mark.parametrize("phrase", ["check my note", "Inspect note", "check my note’"])
def test_canonical_inspection_phrase_cannot_become_load_note(phrase):
    inferred = QvacIntent("LOAD_NOTE", 500, "local-test", 12, "cpu")

    result = apply_canonical_phrase_policy(phrase, inferred)

    assert result.intent == "INSPECT_NOTE"
    assert result.amount_cents is None
    assert result.model == inferred.model
    assert result.backend == inferred.backend


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '{"intent":"SPEND_NOW","amount_cents":500}',
        '{"intent":"LOAD_NOTE","amount_cents":500,"confirm":"yes"}',
    ],
)
def test_qvac_untrusted_output_is_rejected(payload):
    with pytest.raises(QvacIntentError):
        parse_intent_output(payload, model="local-test")
