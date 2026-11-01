"""Thin wrapper around the Claude Messages API for one structured comment."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .pricing import cost_usd
from .prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT

log = logging.getLogger(__name__)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class LlmResult:
    data: dict[str, Any] | None
    model: str
    served_model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None
    request_id: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None


class ClaudeCommentator:
    def __init__(
        self,
        api_key: str,
        model: str,
        effort: str = "low",
        max_tokens: int = 2500,
        fallbacks: bool = True,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.fallbacks = fallbacks
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0, max_retries=1)

    def request_kwargs(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": "Markedsdata (JSON):\n"
                    + json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                }
            ],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
        }

    async def comment(self, snapshot: dict[str, Any]) -> LlmResult:
        kwargs = self.request_kwargs(snapshot)
        try:
            if self.fallbacks:
                resp = await self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs
                )
            else:
                resp = await self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError:
            return LlmResult(
                None, self.model, error="Ugyldig Anthropic API-nøkkel (sjekk ANTHROPIC_API_KEY i .env)."
            )
        except anthropic.PermissionDeniedError:
            return LlmResult(None, self.model, error="API-nøkkelen mangler tilgang til denne modellen.")
        except anthropic.RateLimitError:
            return LlmResult(
                None, self.model, error="Anthropic: for mange forespørsler akkurat nå, prøver senere."
            )
        except anthropic.BadRequestError as exc:
            return LlmResult(None, self.model, error=f"Anthropic avviste forespørselen: {exc.message}")
        except anthropic.APIStatusError as exc:
            return LlmResult(None, self.model, error=f"Anthropic-feil {exc.status_code}, prøver senere.")
        except anthropic.APIConnectionError:
            return LlmResult(None, self.model, error="Får ikke kontakt med Anthropic (internett?).")

        u = resp.usage
        served = getattr(resp, "model", None) or self.model
        res = LlmResult(
            data=None,
            model=self.model,
            served_model=served,
            input_tokens=int(u.input_tokens or 0),
            output_tokens=int(u.output_tokens or 0),
            cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            stop_reason=resp.stop_reason,
            request_id=getattr(resp, "_request_id", None),
        )
        # Price at the more expensive of requested/served model (a fallback may have run).
        res.cost_usd = max(
            cost_usd(m, res.input_tokens, res.output_tokens, res.cache_read_tokens, res.cache_write_tokens)
            for m in {self.model, served}
        )
        if resp.stop_reason == "refusal":
            res.error = "Modellen avslo å svare på denne oppdateringen."
            return res
        if resp.stop_reason == "max_tokens":
            res.error = "Svaret ble kuttet (max_tokens). Øk COPILOT_AI_MAX_TOKENS eller senk effort."
            return res
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
        try:
            res.data = json.loads(text) if text else None
        except json.JSONDecodeError:
            res.data = None
        if res.data is None:
            res.error = "Kunne ikke lese svaret fra modellen."
        return res
