import os
import re
import mimetypes
from pathlib import Path
from typing import Iterable

from flask import Flask, jsonify, render_template, request, send_file, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
SEARCH_ROOT = Path(os.environ.get("SEARCH_ROOT", BASE_DIR / "search_root")).expanduser().resolve()
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "dev-token-change-me")

DEFAULT_EXTENSIONS = [".html", ".py", ".txt", ".js", ".css", ".json"]
URL_REGEX = re.compile(r"https?://[^\s\"'>]+", re.IGNORECASE)

# Prevent scanning huge files by default. User can lower/raise in the UI.
DEFAULT_MAX_FILE_SIZE_MB = 10
DEFAULT_MAX_RESULTS = 1000


def require_token() -> None:
    """Small token gate so a public Render URL is not an open file browser."""
    supplied = (
        request.headers.get("X-Auth-Token")
        or request.args.get("token")
        or request.form.get("token")
    )
    if supplied != AUTH_TOKEN:
        abort(401, description="Missing or invalid AUTH_TOKEN")


def safe_join_root(relative_path: str | None = None) -> Path:
    """Resolve a user-supplied path but keep it inside SEARCH_ROOT."""
    rel = (relative_path or "").strip().strip("/").strip("\\")
    target = (SEARCH_ROOT / rel).resolve()
    if target != SEARCH_ROOT and SEARCH_ROOT not in target.parents:
        abort(400, description="Path is outside SEARCH_ROOT")
    return target


def parse_extensions(raw) -> set[str]:
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.split(",")]
    elif isinstance(raw, list):
        parts = [str(x).strip() for x in raw]
    else:
        parts = DEFAULT_EXTENSIONS

    result = set()
    for ext in parts:
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        result.add(ext.lower())
    return result


def file_is_probably_text(path: Path) -> bool:
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        return path.suffix.lower() in parse_extensions(DEFAULT_EXTENSIONS)
    return mime.startswith("text/") or mime in {
        "application/json",
        "application/javascript",
        "application/xml",
        "application/x-python-code",
    }


def match_line(line: str, pattern: str, mode: str, case_sensitive: bool) -> bool:
    if mode == "Regex":
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.search(pattern, line, flags) is not None
        except re.error:
            return False

    if mode == "URL":
        needle = pattern if case_sensitive else pattern.lower()
        for url in URL_REGEX.findall(line):
            candidate = url if case_sensitive else url.lower()
            if needle in candidate:
                return True
        return False

    # Exact Text mode
    haystack = line if case_sensitive else line.lower()
    needle = pattern if case_sensitive else pattern.lower()
    return needle in haystack


def iter_files(start_dir: Path, extensions: set[str], max_file_size: int) -> Iterable[Path]:
    for root, dirs, files in os.walk(start_dir):
        # Skip common heavy/private folders. Add/remove as needed.
        dirs[:] = [
            d for d in dirs
            if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}
        ]
        for name in files:
            path = Path(root) / name
            if extensions and path.suffix.lower() not in extensions:
                continue
            try:
                if path.stat().st_size > max_file_size:
                    continue
            except OSError:
                continue
            if file_is_probably_text(path):
                yield path


@app.get("/")
def index():
    return render_template(
        "index.html",
        search_root=str(SEARCH_ROOT),
        default_token="" if AUTH_TOKEN != "dev-token-change-me" else AUTH_TOKEN,
        default_extensions=",".join(DEFAULT_EXTENSIONS),
    )


@app.get("/health")
def health():
    return jsonify({"ok": True, "search_root": str(SEARCH_ROOT)})


@app.get("/api/list")
def list_dir():
    require_token()
    subdir = request.args.get("dir", "")
    directory = safe_join_root(subdir)
    if not directory.exists() or not directory.is_dir():
        abort(404, description="Directory not found")

    items = []
    for child in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        try:
            stat = child.stat()
        except OSError:
            continue
        items.append({
            "name": child.name,
            "relative_path": str(child.relative_to(SEARCH_ROOT)).replace("\\", "/"),
            "is_dir": child.is_dir(),
            "size": stat.st_size,
        })
    return jsonify({"root": str(SEARCH_ROOT), "dir": subdir, "items": items})


@app.post("/api/search")
def search():
    require_token()
    data = request.get_json(force=True, silent=True) or {}

    pattern = str(data.get("pattern", "")).strip()
    if not pattern:
        abort(400, description="Search pattern is required")

    mode = data.get("mode", "Exact Text")
    if mode not in {"Exact Text", "Regex", "URL"}:
        abort(400, description="Invalid mode")

    case_sensitive = bool(data.get("case_sensitive", False))
    extensions = parse_extensions(data.get("extensions", DEFAULT_EXTENSIONS))
    subdir = str(data.get("directory", "")).strip()

    max_results = int(data.get("max_results", DEFAULT_MAX_RESULTS) or DEFAULT_MAX_RESULTS)
    max_results = max(1, min(max_results, 10000))

    max_file_size_mb = float(data.get("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB) or DEFAULT_MAX_FILE_SIZE_MB)
    max_file_size = int(max(0.1, min(max_file_size_mb, 200)) * 1024 * 1024)

    start_dir = safe_join_root(subdir)
    if not start_dir.exists() or not start_dir.is_dir():
        abort(404, description="Search directory not found")

    results = []
    scanned_files = 0
    matched_files = set()

    for path in iter_files(start_dir, extensions, max_file_size):
        scanned_files += 1
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line_number, line in enumerate(f, start=1):
                    if match_line(line, pattern, mode, case_sensitive):
                        rel = str(path.relative_to(SEARCH_ROOT)).replace("\\", "/")
                        matched_files.add(rel)
                        results.append({
                            "file": rel,
                            "line": line_number,
                            "match": line.strip()[:1000],
                        })
                        if len(results) >= max_results:
                            return jsonify({
                                "truncated": True,
                                "scanned_files": scanned_files,
                                "matched_file_count": len(matched_files),
                                "result_count": len(results),
                                "results": results,
                            })
        except OSError as exc:
            rel = str(path.relative_to(SEARCH_ROOT)).replace("\\", "/")
            results.append({"file": rel, "line": 0, "match": f"ERROR reading file: {exc}"})

    return jsonify({
        "truncated": False,
        "scanned_files": scanned_files,
        "matched_file_count": len(matched_files),
        "result_count": len(results),
        "results": results,
    })


@app.get("/download")
def download():
    require_token()
    rel_path = request.args.get("path", "")
    path = safe_join_root(rel_path)
    if not path.exists() or not path.is_file():
        abort(404, description="File not found")
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    SEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
