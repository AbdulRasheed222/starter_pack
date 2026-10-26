"""The evaluation questions must stay answerable: every evidence phrase is copied exactly from
the documents, so a typo can't turn into a silent miss."""

from pathlib import Path

import yaml

EVAL = Path(__file__).resolve().parents[2] / "eval"


def test_evidence_is_quoted_exactly():
    documents = " ".join(p.read_text(encoding="utf-8") for p in (EVAL / "documents").iterdir())
    questions = yaml.safe_load((EVAL / "questions.yaml").read_text(encoding="utf-8"))
    assert len(questions) >= 20
    missing = [q["evidence"] for q in questions if q["evidence"] not in documents]
    assert missing == []
