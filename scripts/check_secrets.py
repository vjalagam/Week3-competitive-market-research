from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ydc-sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:OPENROUTER_API_KEY|YDC_API_KEY)\s*=\s*(?!your_|$|#)[^\s#]+"),
)
ALLOWED_FILES = {".env.example"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    findings: list[tuple[Path, int]] = []
    for path in tracked_files():
        if path.name in ALLOWED_FILES or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append((path.relative_to(ROOT), line_number))

    if findings:
        print("Potential secret found in tracked files:")
        for path, line_number in findings:
            print(f"- {path}:{line_number}")
        print("Remove the credential, rotate it if exposed, and keep secrets in local .env files.")
        return 1

    print("Secret scan passed: no credential patterns found in tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())