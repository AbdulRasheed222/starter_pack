"""Model providers behind one small interface, so the rest of the app never imports an SDK.

A provider takes passages and a question and yields events: text as it is written (`Delta`),
each finished block of the answer with the passages it cites (`Block`), then one `Finish` with
the model's name, why it stopped, and the tokens used.

- `ClaudeProvider` uses the Anthropic SDK with native citations: every passage is sent as a
  document, and Claude returns the exact sentences it relied on.
- `OpenAICompatibleProvider` talks to any server with OpenAI's chat completions API (OpenAI,
  Ollama, vLLM, LM Studio). It has no native citations, so the model is asked to write [n]
  after each claim, and those markers become the citations.
- `FakeProvider` quotes the best passage without a network call, for tests and for trying the
  app without a key.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.ai.pricing import Usage
from app.config import Settings


@dataclass
class Passage:
    title: str
    text: str


@dataclass
class Turn:
    role: str  # "user" or "assistant"
    text: str


@dataclass
class AskRequest:
    system: str
    passages: list[Passage]
    question: str
    # Earlier turns, oldest first. Passages go with the latest question only.
    history: list[Turn] = field(default_factory=list)


@dataclass
class Delta:
    text: str


@dataclass
class Cite:
    passage: int  # index into AskRequest.passages
    quote: str | None = None  # the exact text relied on, when the provider gives it


@dataclass
class Block:
    text: str
    cites: list[Cite] = field(default_factory=list)


@dataclass
class Finish:
    model: str
    stop_reason: str | None
    usage: Usage


Event = Delta | Block | Finish


class Provider(Protocol):
    def stream(self, request: AskRequest) -> Iterator[Event]: ...


class ProviderError(RuntimeError):
    """The model call failed. The message is safe to show to the user."""


# ---------------------------------------------------------------------------------------------


class ClaudeProvider:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic  # imported lazily so the app starts without an API key

            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def params(self, request: AskRequest) -> dict:
        s = self.settings
        documents = [
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": p.text},
                "title": p.title,
                "citations": {"enabled": True},
            }
            for p in request.passages
        ]
        params: dict = {
            "model": s.ai_model,
            "max_tokens": s.ai_max_tokens,
            "system": request.system,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": s.ai_effort},
            "messages": [
                *({"role": t.role, "content": t.text} for t in request.history),
                {
                    "role": "user",
                    "content": [*documents, {"type": "text", "text": request.question}],
                },
            ],
        }
        if s.ai_fallbacks:
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def stream(self, request: AskRequest) -> Iterator[Event]:
        import anthropic

        try:
            with self.client.beta.messages.stream(**self.params(request)) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield Delta(event.delta.text)
                    elif event.type == "content_block_stop" and event.content_block.type == "text":
                        block = event.content_block
                        yield Block(
                            text=block.text,
                            cites=[
                                Cite(c.document_index, c.cited_text)
                                for c in block.citations or []
                                if hasattr(c, "document_index")
                            ],
                        )
                message = stream.get_final_message()
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"The model returned an error ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("The model could not be reached.") from exc

        u = message.usage
        yield Finish(
            model=message.model,
            stop_reason=message.stop_reason,
            usage=Usage(
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_read_tokens=u.cache_read_input_tokens or 0,
                cache_write_tokens=u.cache_creation_input_tokens or 0,
            ),
        )


# ---------------------------------------------------------------------------------------------

_MARKER = re.compile(r"\[(\d+)\]")
_LEADING_PUNCTUATION = re.compile(r"^[.,;:!?)]+")

CITE_RULE = (
    "\n\nThe documents are numbered. After each statement, write the number of the document "
    "that supports it in square brackets, like [1]."
)


def split_markers(text: str, passages: int) -> list[Block]:
    """Turn "Open at 9 [1]. Closed Sundays [2]." into blocks that each cite their passages.
    Numbers outside 1..passages are dropped: the model cited something it wasn't given."""
    blocks: list[Block] = [Block("")]

    def add(segment: str) -> None:
        # Punctuation right after a marker ends the sentence the marker belongs to.
        punctuation = _LEADING_PUNCTUATION.match(segment)
        if punctuation:
            blocks[-1].text += punctuation.group(0)
            segment = segment[punctuation.end() :]
        if blocks[-1].cites and segment.strip():
            blocks.append(Block(segment))
        else:
            blocks[-1].text += segment

    position = 0
    for match in _MARKER.finditer(text):
        add(text[position : match.start()])
        blocks[-1].text = blocks[-1].text.rstrip()
        number = int(match.group(1))
        if 1 <= number <= passages and all(c.passage != number - 1 for c in blocks[-1].cites):
            blocks[-1].cites.append(Cite(number - 1))
        position = match.end()
    add(text[position:])
    return [b for b in blocks if b.text.strip()]


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))

    def body(self, request: AskRequest) -> dict:
        documents = "\n\n".join(
            f'<document number="{n}" title="{p.title}">\n{p.text}\n</document>'
            for n, p in enumerate(request.passages, start=1)
        )
        return {
            "model": self.settings.ai_model,
            "max_tokens": self.settings.ai_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {"role": "system", "content": request.system + CITE_RULE},
                *({"role": t.role, "content": t.text} for t in request.history),
                {"role": "user", "content": f"{documents}\n\n{request.question}"},
            ],
        }

    def stream(self, request: AskRequest) -> Iterator[Event]:
        s = self.settings
        headers = {"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {}
        url = s.openai_base_url.rstrip("/") + "/chat/completions"
        parts: list[str] = []
        model, stop_reason, usage = s.ai_model, None, Usage()
        try:
            with self.client.stream("POST", url, json=self.body(request), headers=headers) as r:
                if r.status_code != 200:
                    raise ProviderError(f"The model returned an error ({r.status_code}).")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    model = chunk.get("model") or model
                    if chunk.get("usage"):
                        usage = Usage(
                            input_tokens=chunk["usage"].get("prompt_tokens") or 0,
                            output_tokens=chunk["usage"].get("completion_tokens") or 0,
                        )
                    for choice in chunk.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            parts.append(text)
                            yield Delta(text)
                        stop_reason = choice.get("finish_reason") or stop_reason
        except httpx.HTTPError as exc:
            raise ProviderError("The model could not be reached.") from exc
        yield from split_markers("".join(parts), len(request.passages))
        yield Finish(model=model, stop_reason=stop_reason, usage=usage)


# ---------------------------------------------------------------------------------------------


class FakeProvider:
    """Answers with the first sentence of the best passage, cited. Token counts are words."""

    def stream(self, request: AskRequest) -> Iterator[Event]:
        text = request.passages[0].text
        sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
        yield Delta(sentence)
        yield Block(sentence, [Cite(0, sentence)])
        words = sum(len(p.text.split()) for p in request.passages) + len(request.question.split())
        yield Finish("fake", "end_turn", Usage(input_tokens=words, output_tokens=len(sentence)))


_providers: dict[str, Provider] = {}


def get_provider(settings: Settings) -> Provider:
    """One provider per process, so HTTP connections are reused."""
    name = settings.ai_provider
    if name not in _providers:
        if name == "anthropic":
            _providers[name] = ClaudeProvider(settings)
        elif name == "openai":
            _providers[name] = OpenAICompatibleProvider(settings)
        elif name == "fake":
            _providers[name] = FakeProvider()
        else:
            raise ValueError(f"Unknown AI_PROVIDER: {name}")
    return _providers[name]
