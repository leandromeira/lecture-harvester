import csv
import threading
from datetime import datetime
from pathlib import Path

_WRITE_LOCK = threading.Lock()
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_COST_LOG_PATH = _PROJECT_ROOT / "logs" / "cost_tracker.csv"

_MODEL_PRICING_USD_PER_1K = {
    "openai": {
        "gpt-4o": (0.0050, 0.0150),
        "gpt-4o-mini": (0.00015, 0.00060),
        "gpt-4.1": (0.0020, 0.0080),
        "gpt-4.1-mini": (0.00040, 0.00160),
        "gpt-4.1-nano": (0.00010, 0.00040),
    },
    "anthropic": {
        "claude-3-5-sonnet": (0.0030, 0.0150),
        "claude-3-7-sonnet": (0.0030, 0.0150),
        "claude-3-5-haiku": (0.0008, 0.0040),
    },
    "gemini": {
        "gemini-1.5-pro": (0.0035, 0.0105),
        "gemini-1.5-flash": (0.00035, 0.00105),
        "gemini-2.0-flash": (0.00010, 0.00040),
    },
}
_OPENAI_COMPATIBLE_USAGE_PROVIDERS = {"openai", "openrouter"}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_field(obj, field: str, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(field, default)

    value = getattr(obj, field, None)
    if value is not None:
        return value

    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(field, default)

    return default


def _resolve_pricing(provider: str, model: str):
    provider_key = (provider or "").lower()
    model_key = (model or "").lower()
    provider_prices = _MODEL_PRICING_USD_PER_1K.get(provider_key, {})

    if model_key in provider_prices:
        return provider_prices[model_key]

    for key, prices in sorted(provider_prices.items(), key=lambda item: len(item[0]), reverse=True):
        if model_key.startswith(key):
            return prices

    return 0.0, 0.0


def _extract_usage(provider: str, response):
    if not response:
        return 0, 0, 0

    provider_key = (provider or "").lower()
    usage = getattr(response, "usage", None)

    if provider_key in _OPENAI_COMPATIBLE_USAGE_PROVIDERS:
        input_tokens = _as_int(_read_field(usage, "prompt_tokens", 0))
        output_tokens = _as_int(_read_field(usage, "completion_tokens", 0))
        total_tokens = _as_int(_read_field(usage, "total_tokens", input_tokens + output_tokens))
        return input_tokens, output_tokens, total_tokens

    if provider_key == "anthropic":
        input_tokens = _as_int(_read_field(usage, "input_tokens", 0))
        output_tokens = _as_int(_read_field(usage, "output_tokens", 0))
        total_tokens = input_tokens + output_tokens
        return input_tokens, output_tokens, total_tokens

    if provider_key == "gemini":
        usage_meta = getattr(response, "usage_metadata", None)
        input_tokens = _as_int(_read_field(usage_meta, "prompt_token_count", 0))
        output_tokens = _as_int(_read_field(usage_meta, "candidates_token_count", 0))
        total_tokens = _as_int(_read_field(usage_meta, "total_token_count", input_tokens + output_tokens))
        return input_tokens, output_tokens, total_tokens

    return 0, 0, 0


def _extract_openrouter_costs(response):
    usage = getattr(response, "usage", None)
    if not usage:
        return 0.0, 0.0, 0.0

    cost_details = _read_field(usage, "cost_details", None)
    input_cost = _as_float(_read_field(cost_details, "upstream_inference_prompt_cost", 0.0))
    output_cost = _as_float(_read_field(cost_details, "upstream_inference_completions_cost", 0.0))
    total_cost = _as_float(_read_field(usage, "cost", input_cost + output_cost))

    if total_cost and not (input_cost or output_cost):
        return 0.0, 0.0, total_cost

    return input_cost, output_cost, total_cost


def log_cost_event(provider: str, model: str, call_context: str, response=None, status: str = "success", error_message: str = ""):
    input_tokens, output_tokens, total_tokens = _extract_usage(provider, response)
    provider_key = (provider or "").lower()

    if provider_key == "openrouter":
        input_cost, output_cost, total_cost = _extract_openrouter_costs(response)
    else:
        input_price, output_price = _resolve_pricing(provider, model)
        input_cost = (input_tokens / 1000.0) * input_price
        output_cost = (output_tokens / 1000.0) * output_price
        total_cost = input_cost + output_cost

    row = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "provider": provider or "",
        "model": model or "",
        "call_context": call_context or "unknown",
        "status": status,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": f"{input_cost:.8f}",
        "output_cost_usd": f"{output_cost:.8f}",
        "total_cost_usd": f"{total_cost:.8f}",
        "error_message": (error_message or "")[:500],
    }

    _COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    headers = list(row.keys())

    with _WRITE_LOCK:
        write_header = not _COST_LOG_PATH.exists()
        with open(_COST_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    return row
