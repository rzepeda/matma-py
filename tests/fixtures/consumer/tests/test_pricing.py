import pytest

from example_app import PriceCalculator, discounted_price


def test_discounted_price() -> None:
    assert discounted_price(100, 0.2) == 80


def test_total() -> None:
    assert PriceCalculator().total(100, 0.15) == pytest.approx(115)
