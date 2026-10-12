"""The language model. Which one is a setting. The key is never in the code or in settings.toml: it comes from
the environment, or on your own machine from a .env file that git ignores."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import anthropic
from dotenv import load_dotenv
from sqlalchemy import Connection, func, select

from common.db import model_calls

MAX_TOKENS = 16000

# On a PC the key can sit in a .env file beside the code. A key already in the environment wins, which is how
# a hosted run (GitHub Actions) supplies it from its secret store.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class ModelError(Exception):
    """A request to the model failed or gave no usable answer. The message says why."""


@dataclass
class Reply:
    data: dict
    model: str
    tokens_in: int
    tokens_out: int
    cost: float  # US dollars


# What every step calls: (model settings, instructions, the material, the shape of the answer) -> Reply
Ask = Callable[[dict, str, str, dict], Reply]


def configured(settings: dict) -> bool:
    return bool(settings.get("provider") and settings.get("name"))


def chosen(run_settings: dict, root: Path) -> dict:
    """The model settings a step should use: the run's frozen ones, or, for a run started before a model
    was chosen, the ones in settings.toml as it is now, so that the run can pick the model up."""
    if configured(run_settings["model"]):
        return run_settings["model"]
    from common.settings import load  # imported here: common.settings is read before this module is needed

    return load(root)["model"]


def check(settings: dict) -> str | None:
    """Returns None when the model can be reached with the credentials present, else what is wrong.

    Nothing is sent to the model: this only looks for credentials.
    """
    if not configured(settings):
        return None
    # The client is built without complaint when there are no credentials, so they are looked for here:
    # a key or token in the environment, or a profile saved by `ant auth login`.
    in_environment = any(os.environ.get(name) for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    if not in_environment and not (Path.home() / ".config" / "anthropic").exists():
        return f"no key for {settings['provider']}: put ANTHROPIC_API_KEY in the .env file, or set it in the environment"
    return None


def ask(settings: dict, system: str, user: str, schema: dict) -> Reply:
    """One request, one answer, in the shape the schema describes."""
    if not configured(settings):
        raise ModelError("No model is chosen. Set provider and name under [model] in settings.toml.")
    try:
        response = anthropic.Anthropic().messages.create(
            model=settings["name"],
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            # The answer's shape is fixed by the schema; the thinking effort is sent only when one is set.
            output_config={"format": {"type": "json_schema", "schema": schema}, **({"effort": settings["effort"]} if settings.get("effort") else {})},
        )
    except anthropic.AuthenticationError as exc:
        raise ModelError(f"The model key was rejected: {exc.message}") from exc
    except anthropic.RateLimitError as exc:
        raise ModelError(f"The model's rate limit was reached: {exc.message}") from exc
    except anthropic.APIStatusError as exc:
        raise ModelError(f"The model returned an error ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ModelError(f"The model could not be reached: {exc}") from exc
    except anthropic.AnthropicError as exc:
        raise ModelError(f"The model could not be used: {exc}") from exc

    if response.stop_reason in ("refusal", "max_tokens"):
        raise ModelError(f"The model stopped without a full answer ({response.stop_reason}).")
    text = next((block.text for block in response.content if block.type == "text"), None)
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError as exc:
        raise ModelError(f"The model's answer was not in the agreed format: {exc}") from exc

    tokens_in, tokens_out = response.usage.input_tokens, response.usage.output_tokens
    cost = (tokens_in * settings.get("price_in", 0) + tokens_out * settings.get("price_out", 0)) / 1_000_000
    return Reply(data, response.model, tokens_in, tokens_out, cost)


def record(conn: Connection, run_id: int, step: int, purpose: str, reply: Reply, story_id: int | None = None) -> None:
    conn.execute(
        model_calls.insert().values(
            run_id=run_id, step=step, purpose=purpose, story_id=story_id,
            model=reply.model, tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, cost=reply.cost,
        )
    )


def spent(conn: Connection, run_id: int, step: int | None = None) -> tuple[int, int, int, float]:
    """Requests, tokens in, tokens out and dollars for a run, or for one step of it."""
    where = model_calls.c.run_id == run_id
    if step is not None:
        where &= model_calls.c.step == step
    row = conn.execute(
        select(
            func.count(), func.coalesce(func.sum(model_calls.c.tokens_in), 0),
            func.coalesce(func.sum(model_calls.c.tokens_out), 0), func.coalesce(func.sum(model_calls.c.cost), 0.0),
        ).where(where)
    ).one()
    return row[0], row[1], row[2], float(row[3])
