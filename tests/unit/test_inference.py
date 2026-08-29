from core.kernel.inference.router import (
    extract_intent,
    select_model,
)

import pytest


def test_select_model_known_intent() -> None:
    assert select_model("code") == "openrouter/anthropic/claude-3.5-sonnet"


def test_select_model_default() -> None:
    assert select_model("nonsense") == select_model(None)


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        ("analyze the competitive landscape", "research"),
        ("fix this bug in the script", "code"),
        ("hi", "simple"),
        ("please review our entire go to market strategy document", "research"),
    ],
)
def test_extract_intent(msg: str, expected: str) -> None:
    assert extract_intent(msg) == expected
