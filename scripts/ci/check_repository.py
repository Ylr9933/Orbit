"""Check policy parity and local Markdown file links (not remote URLs or anchors)."""

import re
from pathlib import Path
from urllib.parse import unquote


def check(root: Path) -> list[str]:
    errors = []
    if (root / "AGENTS.md").read_bytes() != (root / "CLAUDE.md").read_bytes():
        errors.append("AGENTS.md and CLAUDE.md differ")
    documents = [*root.glob("*.md"), *(root / "docs").rglob("*.md")]
    for document in documents:
        content = document.read_text()
        # Examples inside fenced blocks are not actual navigation links.
        content = re.sub(r"^```.*?^```[^\n]*", "", content, flags=re.M | re.S)
        for match in re.finditer(r"\]\(([^)\n]+)\)", content):
            target = match[1].split(' "', 1)[0].strip("<>")
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0])
            if target and not (document.parent / target).exists():
                errors.append(f"{document.relative_to(root)}: missing {target}")
    return errors


if __name__ == "__main__":
    problems = check(Path(__file__).resolve().parents[2])
    if problems:
        raise SystemExit("\n".join(problems))
    print("Policy mirrors and local Markdown file links passed.")
