#!/usr/bin/env python3
"""Turn this starter into your project: name it and remove the modules you don't need.

    python3 setup_project.py                       # asks
    python3 setup_project.py --name Acme --without billing --without notes

Modules:
    ai       documents, cited answers, model providers, usage and spending caps
    billing  Stripe plans, checkout, customer portal and webhook
    notes    the example feature

Code that belongs to a module sits between `[module:NAME]` and `[/module:NAME]` comments, and
its own files are listed in MODULE_FILES below. A removed module's code is deleted; for kept
modules only the marker lines go. A single line can end with `<!-- [only:NAME] -->` instead,
for Markdown tables, which a marker line would break. Run it once, on a fresh copy, then commit
the result.

Each module has its own migration; a removed module's is deleted and the rest are relinked.

Uses only the standard library. Needs `uv` on the PATH to update the lock file and tidy imports.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = {
    "ai": "documents, cited answers, model providers, usage and spending caps",
    "billing": "Stripe plans, checkout, customer portal and webhook",
    "notes": "the example feature",
}
MODULE_FILES = {
    "ai": [
        "backend/src/app/ai",
        "backend/tests/test_ai.py",
        "backend/tests/test_eval_data.py",
        "backend/scripts/eval_retrieval.py",
        "backend/migrations/versions/20261026_0003_ai.py",
        "eval",
        "docs/ai.md",
        "web/components/Ask.tsx",
        "web/components/Documents.tsx",
        "web/components/Usage.tsx",
        "web/app/(signed-in)/app/[workspaceId]/ask",
        "web/app/(signed-in)/app/[workspaceId]/documents",
        "web/app/(signed-in)/app/[workspaceId]/usage",
    ],
    "billing": [
        "backend/src/app/billing.py",
        "backend/tests/test_billing.py",
        "backend/migrations/versions/20261026_0004_billing.py",
        "docs/billing.md",
        "web/components/Billing.tsx",
        "web/app/(signed-in)/app/[workspaceId]/billing",
    ],
    "notes": [
        "backend/src/app/notes.py",
        "backend/tests/test_notes.py",
        "backend/migrations/versions/20261026_0002_notes.py",
        "web/components/Notes.tsx",
    ],
}
# Message keys (web/messages/*.json) that only a module uses, by prefix.
MODULE_MESSAGES = {
    "ai": ["nav.ask", "nav.documents", "nav.usage", "documents.", "ask.", "usage.",
           "admin.documents", "admin.spent", "admin.budget", "admin.usePlan", "billing.budget"],
    "billing": ["nav.billing", "billing.", "admin.plan"],
    # billing.budget is only shown with ai; listed under ai too, below.
    "notes": ["nav.notes", "notes."],
}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".md", ".toml", ".yml", ".yaml", ".example",
                 ".mjs", ".json", ".sql"}
TEXT_NAMES = {"Dockerfile", ".env.example"}
SKIP_DIRS = {".git", "node_modules", ".venv", ".next", "__pycache__", ".models", ".ruff_cache",
             ".pytest_cache"}
MARKER = re.compile(r"\[(/?)module:(\w+)\]")
ONLY = re.compile(r"\s*<!-- \[only:(\w+)\] -->\s*$")


def strip_markers(text: str, removed: set[str]) -> str:
    out: list[str] = []
    dropping: list[str] = []
    for line in text.splitlines(keepends=True):
        match = MARKER.search(line)
        if match:
            closing, name = match.group(1) == "/", match.group(2)
            if closing:
                if dropping and dropping[-1] == name:
                    dropping.pop()
            elif name in removed:
                dropping.append(name)
            continue  # marker lines never survive
        only = ONLY.search(line)
        if only:
            if only.group(1) in removed:
                continue
            line = line[: only.start()] + "\n"
        if not dropping:
            out.append(line)
    return "".join(out)


def text_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES):
            if path.name in ("package-lock.json", "uv.lock") or path == Path(__file__).resolve():
                continue
            yield path


def relink_migrations() -> None:
    """Each module has its own migration. With some deleted, chain the rest in file order."""
    previous = None
    for path in sorted((ROOT / "backend/migrations/versions").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^down_revision = .*$", f"down_revision = {previous!r}", text, flags=re.M)
        text = re.sub(r"^Revises:.*$", f"Revises: {previous or ''}", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
        previous = re.search(r'^revision = "(\w+)"', text, flags=re.M).group(1)


def ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--name", help="your product's name, shown in the app")
    parser.add_argument("--without", action="append", choices=sorted(MODULES), default=[])
    parser.add_argument("--yes", action="store_true", help="don't ask, use the arguments")
    args = parser.parse_args()

    name = args.name
    removed = set(args.without)
    if not args.yes and sys.stdin.isatty():
        name = ask("Product name", name or "Starter")
        for module, description in MODULES.items():
            keep = ask(f"Keep {module} ({description})? y/n", "n" if module in removed else "y")
            if keep.lower().startswith("n"):
                removed.add(module)
            else:
                removed.discard(module)

    for module in sorted(removed):
        for relative in MODULE_FILES[module]:
            path = ROOT / relative
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    for path in text_files():
        text = path.read_text(encoding="utf-8")
        if "module:" not in text and "[only:" not in text:
            continue
        # "setup" marks what only this template needs, such as CI for this script.
        new = strip_markers(text, removed | {"setup"})
        if path.suffix in {".ts", ".tsx", ".css", ".md", ".yml"}:
            new = re.sub(r"\n{3,}", "\n\n", new)
        path.write_text(new, encoding="utf-8")

    for messages in (ROOT / "web/messages").glob("*.json"):
        data = json.loads(messages.read_text(encoding="utf-8"))
        prefixes = [p for m in removed for p in MODULE_MESSAGES[m]]
        data = {k: v for k, v in data.items() if not any(k.startswith(p) for p in prefixes)}
        if name:
            data["brand"] = name
        messages.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")

    if "notes" in removed:
        # The workspace's home page was the notes list: send people somewhere that exists.
        home = "ask" if "ai" not in removed else "members"
        (ROOT / "web/app/(signed-in)/app/[workspaceId]/page.tsx").write_text(
            'import { redirect } from "next/navigation";\n\n'
            "export default async function WorkspaceHome({\n"
            "  params,\n"
            "}: {\n"
            "  params: Promise<{ workspaceId: string }>;\n"
            "}) {\n"
            "  const { workspaceId } = await params;\n"
            f"  redirect(`/app/${{workspaceId}}/{home}`);\n"
            "}\n",
            encoding="utf-8",
        )

    if name:
        readme = ROOT / "README.md"
        readme.write_text(readme.read_text().replace("# starter_pack", f"# {name}", 1))
        api = ROOT / "backend/src/app/api.py"
        api.write_text(api.read_text().replace('"Starter API"', json.dumps(f"{name} API")))

    relink_migrations()

    backend = ROOT / "backend"
    if shutil.which("uv"):
        subprocess.run(["uv", "lock"], cwd=backend, check=True)
        subprocess.run(["uv", "run", "ruff", "check", "--fix", "-q", "."], cwd=backend)
        subprocess.run(["uv", "run", "ruff", "format", "-q", "."], cwd=backend, check=True)
    else:
        print("uv was not found: run `uv lock` and `uv run ruff check --fix .` in backend/.")

    Path(__file__).resolve().unlink()

    kept = [m for m in MODULES if m not in removed]
    print(f"\nDone. Kept: {', '.join(kept) or 'none'}. Removed: {', '.join(sorted(removed)) or 'none'}.")
    print("\nThen: cd backend && uv run pytest, and cd web && npm run build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
