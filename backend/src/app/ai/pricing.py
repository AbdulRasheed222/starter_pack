"""Model prices in USD per million tokens, used to cost every call in the usage ledger.

Claude prices are from Anthropic's pricing page as of 2026-10-25. Cache writes use the
5-minute rate of 1.25 times input. Update this table when prices change, or set
AI_PRICE_INPUT_PER_MTOK and AI_PRICE_OUTPUT_PER_MTOK for a model that isn't in it.
"""

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20, 5.00),
    "claude-opus-5": Price(5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-8": Price(5.00, 25.00, 0.50, 6.25),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.20, 2.50),
    # Haiku 5.5's cache-read price is assumed at a tenth of input; not checked.
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01, 0.125),
}

# A model missing from the table is costed at the most expensive known price, so the cap
# errs on the side of stopping early rather than overspending.
_FALLBACK = Price(
    max(p.input for p in PRICES.values()),
    max(p.output for p in PRICES.values()),
    max(p.cache_read for p in PRICES.values()),
    max(p.cache_write for p in PRICES.values()),
)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def price_for(model: str, settings: Settings) -> Price:
    if (
        settings.ai_price_input_per_mtok is not None
        and settings.ai_price_output_per_mtok is not None
    ):
        i, o = settings.ai_price_input_per_mtok, settings.ai_price_output_per_mtok
        return Price(i, o, i, i)
    return PRICES.get(model, _FALLBACK)


def cost_usd(model: str, usage: Usage, settings: Settings) -> float:
    price = price_for(model, settings)
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    )
    return total / 1_000_000
