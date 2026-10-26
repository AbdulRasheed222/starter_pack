"""Measure search quality: for each question in eval/questions.yaml, is a passage containing
its evidence phrase among the top k results?

Uses the same parsing, chunking and embedding code as uploads, with the embedder from your
settings (EMBEDDER, EMBEDDING_MODEL). Run it with the real model; the hashing embedder only
matches words. Exits with status 1 when recall@k is below --min-recall, so CI can gate on it.

    uv run python scripts/eval_retrieval.py --k 5 --min-recall 0.9
"""

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from app.ai.chunking import chunk_sections
from app.ai.embeddings import get_embedder
from app.ai.parsing import parse_file
from app.config import get_settings

EVAL = Path(__file__).resolve().parents[2] / "eval"


def load_passages(settings) -> list[tuple[str, str, str]]:
    """(document, text, embedding text) for every passage of every evaluation document."""
    passages = []
    for path in sorted((EVAL / "documents").iterdir()):
        parsed = parse_file(path.name, path.read_bytes())
        for p in chunk_sections(
            parsed.sections, settings.chunk_words, settings.chunk_overlap_words
        ):
            passages.append((path.name, p.text, p.embedding_text()))
    return passages


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.0)
    args = parser.parse_args()

    settings = get_settings()
    embedder = get_embedder(settings)
    passages = load_passages(settings)
    vectors = embedder.embed_documents([p[2] for p in passages])
    questions = yaml.safe_load((EVAL / "questions.yaml").read_text(encoding="utf-8"))

    ks = sorted({1, 3, args.k})
    # For each k: hits per language.
    found: dict[int, dict[str, list[bool]]] = {k: defaultdict(list) for k in ks}
    misses = []
    for item in questions:
        query = embedder.embed_query(item["question"])
        ranked = sorted(range(len(passages)), key=lambda i: -cosine(query, vectors[i]))
        for k in ks:
            hit = any(item["evidence"] in passages[i][1] for i in ranked[:k])
            found[k][item.get("language", "en")].append(hit)
            if k == args.k and not hit:
                misses.append(item["question"])

    model = settings.embedding_model if settings.embedder == "fastembed" else "(words only)"
    print(f"Embedder: {settings.embedder} {model}")
    print(f"Passages: {len(passages)}, questions: {len(questions)}")
    recall = 0.0
    for k in ks:
        every = [hit for hits in found[k].values() for hit in hits]
        by_language = ", ".join(
            f"{language} {sum(hits)}/{len(hits)}" for language, hits in sorted(found[k].items())
        )
        print(f"recall@{k}: {sum(every) / len(every):.3f} ({by_language})")
        if k == args.k:
            recall = sum(every) / len(every)
    for question in misses:
        print(f"  missed at {args.k}: {question}")
    if recall < args.min_recall:
        print(f"recall@{args.k} is below the minimum of {args.min_recall}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
