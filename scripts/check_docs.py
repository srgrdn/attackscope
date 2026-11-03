"""Check wiki links and screenshot integrity without network or extra packages."""

import hashlib
import json
import re
import struct
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "THIRD_PARTY_NOTICES.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]


def main():
    errors = []
    links = 0
    for document in DOCUMENTS:
        text = document.read_text()
        # The wiki uses inline Markdown links without nested URL parentheses.
        for target in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("//"):
                continue
            if not parsed.path:
                continue
            path = (document.parent / unquote(parsed.path)).resolve()
            links += 1
            if not path.is_relative_to(ROOT) or not path.is_file():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")
    manifest_path = ROOT / "docs/images/manifest.json"
    if not manifest_path.exists():
        errors.append("Missing screenshot manifest")
    else:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("synthetic") is not True or manifest.get("events") != 2093:
            errors.append("Screenshot data must be the expected synthetic scenario")
        if manifest.get("application_origin") != "http://127.0.0.1:18182":
            errors.append("Unexpected screenshot origin")
        images = manifest.get("screenshots", [])
        if len(images) != 12 or len({item["file"] for item in images}) != 12:
            errors.append("Expected 12 distinct documented screenshots")
        for item in images:
            filename = item["file"]
            if Path(filename).name != filename or not filename.endswith(".png"):
                errors.append("Unsafe screenshot filename")
                continue
            path = manifest_path.parent / filename
            if not path.exists():
                errors.append("Missing screenshot: " + filename)
                continue
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                errors.append("Screenshot checksum mismatch: " + filename)
            if content[:8] != b"\x89PNG\r\n\x1a\n" or content[12:16] != b"IHDR":
                errors.append("Invalid PNG: " + filename)
                continue
            width, height = struct.unpack(">II", content[16:24])
            if width < 300 or height < 150:
                errors.append("Unexpectedly small screenshot: " + filename)
        simulated = [item["file"] for item in images if item["simulated_api_error"]]
        if simulated != ["11-api-error.png"]:
            errors.append("API error simulation must be explicitly and uniquely labelled")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Documentation: {len(DOCUMENTS)} Markdown files, {links} local links, "
        "12 PNG checksums passed"
    )


if __name__ == "__main__":
    main()
