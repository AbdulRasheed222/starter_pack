"""Documents, answers with citations, the usage ledger and spending caps, and the providers.

Answers here come from FakeProvider or from the real SDKs talking to a mock transport, so no
test needs a network or a key. Embeddings are the word-matching HashingEmbedder: good enough to
test plumbing and isolation, useless for judging search quality (see scripts/eval_retrieval.py).
"""

import io
import json

import anthropic
import docx
import httpx
import httpx2
import pytest

from app.ai.ask import provider, verified_cites
from app.ai.parsing import ParseError, parse_file
from app.ai.pricing import Usage, cost_usd
from app.ai.providers import (
    AskRequest,
    Block,
    Cite,
    ClaudeProvider,
    Delta,
    Finish,
    OpenAICompatibleProvider,
    Passage,
    ProviderError,
)
from app.api import app
from app.config import Settings, get_settings
from app.models import Workspace
from tests.support import as_user, create_workspace, join

HOURS = b"""# Opening hours

The studio opens at 9:00 on weekdays and is closed on Sundays.

# Prices

A day pass costs 25 lira. Monthly membership is 400 lira.
"""


def upload(client, workspace_id, name="hours.md", data=HOURS, user="user_alice"):
    return client.post(
        f"/workspaces/{workspace_id}/documents",
        files={"file": (name, data)},
        headers=as_user(user),
    )


def events(response) -> list[tuple[str, dict | list]]:
    """Parse a server-sent event stream into (event, data) pairs."""
    parsed = []
    for chunk in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def ask(client, workspace_id, question="When do you open?", user="user_alice", **body):
    return client.post(
        f"/workspaces/{workspace_id}/ask",
        json={"question": question, **body},
        headers=as_user(user),
    )


@pytest.fixture
def override():
    yield app.dependency_overrides
    app.dependency_overrides.clear()


class Scripted:
    """A provider that replays the events it is given."""

    def __init__(self, *items):
        self.items = items
        self.requests: list[AskRequest] = []

    def stream(self, request):
        self.requests.append(request)
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item


# --- documents ------------------------------------------------------------------------------


def test_upload_list_and_delete(client):
    workspace_id = create_workspace(client)
    created = upload(client, workspace_id)
    assert created.status_code == 201, created.text
    document = created.json()
    assert (document["title"], document["kind"], document["chunks"]) == ("hours", "markdown", 2)

    listed = client.get(f"/workspaces/{workspace_id}/documents", headers=as_user()).json()
    assert [d["id"] for d in listed] == [document["id"]]

    path = f"/workspaces/{workspace_id}/documents/{document['id']}"
    assert client.delete(path, headers=as_user()).status_code == 204
    assert client.get(f"/workspaces/{workspace_id}/documents", headers=as_user()).json() == []


def test_upload_rejects_bad_files(client, monkeypatch):
    workspace_id = create_workspace(client)
    assert upload(client, workspace_id, name="virus.exe").status_code == 422
    assert upload(client, workspace_id, name="empty.txt", data=b"   ").status_code == 422
    assert upload(client, workspace_id, name="broken.pdf", data=b"not a pdf").status_code == 422
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert upload(client, workspace_id).status_code == 413


def test_only_admins_manage_documents(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob")
    assert upload(client, workspace_id, user="user_bob").status_code == 403
    document_id = upload(client, workspace_id).json()["id"]
    path = f"/workspaces/{workspace_id}/documents/{document_id}"
    assert client.delete(path, headers=as_user("user_bob")).status_code == 403
    # Members can still read and ask.
    assert client.get(f"/workspaces/{workspace_id}/documents", headers=as_user("user_bob")).json()
    assert ask(client, workspace_id, user="user_bob").status_code == 200


def test_parses_pdf_and_word():
    pdf = parse_file("menu.pdf", _pdf("Lunch is served from noon."))
    assert (pdf.kind, pdf.pages, pdf.sections[0].page) == ("pdf", 1, 1)
    assert "Lunch is served from noon." in pdf.sections[0].text

    document = docx.Document()
    document.add_heading("Parking", level=1)
    document.add_paragraph("Park behind the building.")
    buffer = io.BytesIO()
    document.save(buffer)
    word = parse_file("guide.docx", buffer.getvalue())
    assert (word.sections[0].heading, word.sections[0].text) == (
        "Parking",
        "Park behind the building.",
    )

    with pytest.raises(ParseError):
        parse_file("scan.pdf", _pdf(""))


def test_turkish_text_files_decode():
    parsed = parse_file("notlar.txt", "Pazar günleri kapalıyız.".encode("cp1254"))
    assert parsed.sections[0].text == "Pazar günleri kapalıyız."


# --- asking ---------------------------------------------------------------------------------


def test_ask_streams_a_cited_answer_and_records_its_cost(client):
    workspace_id = create_workspace(client)
    upload(client, workspace_id)
    response = ask(client, workspace_id, "When does the studio open on weekdays?")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    stream = events(response)
    names = [name for name, _ in stream]
    assert names[0] == "sources" and names[-1] == "done" and "delta" in names
    sources = stream[0][1]
    assert sources[0]["title"] == "hours"
    assert "9:00" in sources[0]["text"]
    done = stream[-1][1]
    assert done["grounded"] and not done["refused"]
    assert done["answer"][0]["cites"] == [1]
    assert done["cost_usd"] > 0

    usage = client.get(f"/workspaces/{workspace_id}/usage", headers=as_user()).json()
    assert usage["calls"] == 1
    assert usage["spent_usd"] == pytest.approx(done["cost_usd"])
    assert usage["budget_usd"] == 5
    assert len(usage["days"]) == 30 and usage["days"][-1]["calls"] == 1


def test_ask_needs_documents(client):
    workspace_id = create_workspace(client)
    assert ask(client, workspace_id).status_code == 409


def test_spending_cap_stops_calls(client, session):
    workspace_id = create_workspace(client)
    upload(client, workspace_id)
    workspace = session.get(Workspace, workspace_id)
    workspace.ai_monthly_budget_usd = 0.0001
    session.commit()

    assert ask(client, workspace_id).status_code == 200  # spends past the cap
    response = ask(client, workspace_id)
    assert response.status_code == 429
    assert "budget" in response.json()["detail"]


def test_search_never_crosses_workspaces(client):
    """Bob asks, in his own workspace, about words that only Alice's document contains."""
    alpha = create_workspace(client, "user_alice", "Alpha")
    beta = create_workspace(client, "user_bob", "Beta")
    upload(client, alpha, data=b"# Vault\n\nThe vault code is 4512 and the safe is blue.")
    upload(client, beta, name="beta.md", data=b"# Beta\n\nBeta sells bicycles.", user="user_bob")

    response = ask(client, beta, "What is the vault code of the safe?", user="user_bob")
    sources = events(response)[0][1]
    assert {s["title"] for s in sources} == {"beta"}
    assert "4512" not in response.text


def test_refusals_withdraw_the_answer(client, override):
    override[provider] = lambda: Scripted(
        Delta("Partial"), Block("Partial", []), Finish("m", "refusal", Usage(10, 2))
    )
    workspace_id = create_workspace(client)
    upload(client, workspace_id)
    done = events(ask(client, workspace_id))[-1][1]
    assert done["refused"] and done["answer"] == [] and not done["grounded"]


def test_provider_errors_become_an_error_event(client, override):
    override[provider] = lambda: Scripted(Delta("Hel"), ProviderError("The model is down."))
    workspace_id = create_workspace(client)
    upload(client, workspace_id)
    stream = events(ask(client, workspace_id))
    assert stream[-1] == ("error", {"message": "The model is down."})
    assert client.get(f"/workspaces/{workspace_id}/usage", headers=as_user()).json()["calls"] == 0


def test_history_is_passed_on_and_starts_with_the_user(client, override):
    scripted = Scripted(Block("Yes.", []), Finish("m", "end_turn", Usage(1, 1)))
    override[provider] = lambda: scripted
    workspace_id = create_workspace(client)
    upload(client, workspace_id)
    history = [
        {"role": "assistant", "text": "Hello! Ask me anything."},
        {"role": "user", "text": "When do you open?"},
        {"role": "assistant", "text": "At 9:00."},
    ]
    ask(client, workspace_id, "And on Sundays?", history=history)
    sent = scripted.requests[0]
    assert [t.role for t in sent.history] == ["user", "assistant"]
    assert sent.question == "And on Sundays?"
    assert "Alpha" not in sent.system and "Acme" in sent.system


def test_citations_are_verified():
    passages = [Passage("a", "Closed on Sundays."), Passage("b", "Open at 9.")]
    block = Block(
        "x",
        [
            Cite(0, "closed  on sundays."),  # whitespace and case differ: still the same text
            Cite(1, "Open at 10."),  # not in the passage
            Cite(5, None),  # no such passage
            Cite(0, None),  # duplicate
        ],
    )
    assert verified_cites(block, passages) == [1]


def test_unknown_models_cost_the_most_and_prices_can_be_overridden():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    settings = Settings()
    assert cost_usd("claude-opus-5-5", usage, settings) == pytest.approx(24.0)
    assert cost_usd("some-local-model", usage, settings) == pytest.approx(30.0)
    local = Settings(ai_price_input_per_mtok=0, ai_price_output_per_mtok=0)
    assert cost_usd("some-local-model", usage, local) == 0


# --- providers against their real wire formats ----------------------------------------------

CLAUDE_STREAM = [
    {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 900, "output_tokens": 1},
        },
    },
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "Closed on Sundays."},
    },
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {
            "type": "citations_delta",
            "citation": {
                "type": "char_location",
                "cited_text": "closed on Sundays.",
                "document_index": 0,
                "document_title": "hours",
                "start_char_index": 41,
                "end_char_index": 59,
            },
        },
    },
    {"type": "content_block_stop", "index": 0},
    {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 40},
    },
    {"type": "message_stop"},
]


def _sse(items) -> str:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in items)


def test_claude_request_and_stream():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(CLAUDE_STREAM)
        )

    client = anthropic.Anthropic(
        api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    claude = ClaudeProvider(Settings(), client=client)
    request = AskRequest(
        "rules",
        [Passage("hours", "The studio opens at 9:00 on weekdays and is closed on Sundays.")],
        "Open on Sunday?",
    )
    items = list(claude.stream(request))

    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["beta"]
    assert "temperature" not in body
    content = body["messages"][-1]["content"]
    assert content[0]["citations"] == {"enabled": True}
    assert content[-1] == {"type": "text", "text": "Open on Sunday?"}

    delta, block, finish = items
    assert delta == Delta("Closed on Sundays.")
    assert block.cites == [Cite(0, "closed on Sundays.")]
    assert finish.stop_reason == "end_turn"
    assert (finish.usage.input_tokens, finish.usage.output_tokens) == (900, 40)


def test_claude_errors_are_wrapped():
    def handler(request):
        return httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error"}})

    client = anthropic.Anthropic(
        api_key="test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    claude = ClaudeProvider(Settings(), client=client)
    with pytest.raises(ProviderError):
        list(claude.stream(AskRequest("rules", [Passage("a", "b")], "q")))


def test_openai_compatible_request_and_stream():
    seen = {}
    chunks = [
        {"model": "llama3", "choices": [{"delta": {"content": "Opens at 9 [1]"}}]},
        {"model": "llama3", "choices": [{"delta": {"content": ". Closed Sundays [2]."}}]},
        {"model": "llama3", "choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"model": "llama3", "choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 9}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        lines = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=lines)

    settings = Settings(
        ai_provider="openai",
        ai_model="llama3",
        openai_base_url="http://localhost:11434/v1/",
        openai_api_key="key",
    )
    model = OpenAICompatibleProvider(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    passages = [Passage("hours", "Opens at 9."), Passage("days", "Closed Sundays.")]
    items = list(model.stream(AskRequest("rules", passages, "When?")))

    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["auth"] == "Bearer key"
    assert "[1]" in seen["body"]["messages"][0]["content"]
    assert '<document number="2" title="days">' in seen["body"]["messages"][-1]["content"]

    blocks = [i for i in items if isinstance(i, Block)]
    assert [(b.text.strip(), [c.passage for c in b.cites]) for b in blocks] == [
        ("Opens at 9.", [0]),
        ("Closed Sundays.", [1]),
    ]
    finish = items[-1]
    assert (finish.model, finish.stop_reason) == ("llama3", "stop")
    assert (finish.usage.input_tokens, finish.usage.output_tokens) == (50, 9)


def _pdf(text: str) -> bytes:
    """A one-page PDF with `text` on it, built by hand so tests need no PDF writer."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
