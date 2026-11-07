"""Intentionally contains both a function and a class in one source module."""


def discounted_price(price: float, rate: float) -> float:
    return price * (1 - rate)


class PriceCalculator:
    def total(self, base: float, tax_rate: float) -> float:
        return base * (1 + tax_rate)
