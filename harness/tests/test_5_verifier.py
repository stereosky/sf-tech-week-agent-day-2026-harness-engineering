import pytest

from harness.seed import PAYMENTS
from harness.verifier import verify

# Real answers from previous runs, verbatim.
LISTS_EVERY_RECORD_THEN_CONCLUDES = [
    # qwen3.5:2b-q4_K_M, every part in place
    "The payments topic has 5 messages. I can see 4 valid payments, but one has an invalid amount: "
    "- `ord_a1`: amount = 19.99 (valid) - `ord_b7`: amount = 4.5 (valid) - `ord_c2`: amount = -8.0 (invalid) "
    "- `ord_d9`: amount = 120.0 (valid) - `ord_e4`: amount = 7.25 (valid) The payment with order_id `ord_c2` "
    "is invalid because its amount is negative (-8.0), which is not a valid amount.",
    # qwen3.5:2b-q4_K_M, every part in place
    "I've checked all 5 payment records. Looking at the amounts: - ord_a1: 19.99 (positive) - ord_b7: 4.5 "
    "(positive) - ord_c2: -8.0 (negative) - ord_d9: 120.0 (positive) - ord_e4: 7.25 (positive) The payment "
    "with order_id **ord_c2** has an invalid amount of **-8.0**, which is negative. This is the only payment "
    "with an invalid value.",
]
WRONG = [
    # qwen3:1.7b with no tools on the menu (stage 0)
    'The invalid payment has order_id "12345" and the issue is that the payment amount was not recorded correctly.',
    # qwen3.5:2b without the SELECT * line in AGENTS.md
    "There are no payments in the payments topic. The payments topic appears to be empty.",
    # qwen3.5:2b-q4_K_M, every part in place (the first 290 characters)
    "I've examined all 5 payments in the `payments` topic. Each record has a valid JSON structure with fields "
    "for `amount`, `currency`, `merchant` and `order_id`. There are no obvious data quality issues like "
    "negative amounts, missing fields, or malformed JSON. All payments appear to be valid.",
]


def test_the_right_answer_passes():
    verdict = verify("ord_c2: the amount is negative (-8.00)", PAYMENTS, (5, 5))
    assert verdict.passed is True


@pytest.mark.parametrize("answer", LISTS_EVERY_RECORD_THEN_CONCLUDES)
def test_listing_every_record_before_the_conclusion_passes(answer):
    assert verify(answer, PAYMENTS, (5, 5)).passed is True


@pytest.mark.parametrize("answer", WRONG)
def test_real_wrong_answers_fail(answer):
    assert verify(answer, PAYMENTS, (5, 5)).passed is False


def test_an_invented_order_id_fails():
    verdict = verify("PAY-999 is missing its currency", PAYMENTS, (5, 5))
    assert verdict.passed is False


def test_none_are_invalid_then_every_payment_fails():
    # Rebuilt from a qwen3.5:2b run on 30 September that a substring check passed
    everything = "None of them look invalid: " + ", ".join(p["order_id"] for p in PAYMENTS)
    assert verify(everything, PAYMENTS, (5, 5)).passed is False


def test_the_feedback_never_leaks_the_answer():
    verdict = verify("ord_a1 looks wrong", PAYMENTS, (5, 5))
    assert "ord_c2" not in verdict.reason


def test_a_write_to_the_environment_fails_even_with_the_right_answer():
    verdict = verify("ord_c2 has a negative amount", PAYMENTS, (5, 6))
    assert verdict.passed is False
    assert "offset" in verdict.reason


def test_the_answer_comes_from_the_data_not_a_constant():
    fixed = [dict(p, amount=abs(p["amount"])) for p in PAYMENTS] + [
        {"order_id": "ord_z9", "amount": -1.0, "currency": "GBP", "merchant": "Pret"}
    ]
    assert verify("ord_z9", fixed, (6, 6)).passed is True
    assert verify("ord_c2", fixed, (6, 6)).passed is False
