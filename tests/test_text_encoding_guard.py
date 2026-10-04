"""Guard: every text read and write names its encoding.

``Path.read_text()``, ``Path.write_text()`` and ``open()`` with no ``encoding=``
resolve to ``locale.getpreferredencoding(False)``. That is UTF-8 on this
repository's CI (ubuntu-latest) and on macOS, and the host code page on Windows:
cp1252 in Western Europe and the US, cp932 in Japan, cp936 in China. The same
source file is then decoded differently depending on who runs the suite.

This already shipped once as a user-visible bug. ``code_api_search`` and
``code_api_signatures`` read repository sources with a bare ``read_text()``
under ``except Exception: continue``, so on a cp932 host the two files holding
``"✓"``/``"✗"`` were silently dropped from search results and a signature read
failed outright; the fix pinned UTF-8 at those three call sites. The file
writers were already explicit -- ``admin_tools.py`` and
``peer_review_comments.py`` both pass ``encoding='utf-8'`` -- so what was left
was the test suite, which read those UTF-8 files back with whatever the host
offered.

The reason this is a source scan and not a behavioral test: the defect is
invisible on a UTF-8 host, so a behavioral test cannot fail on this
repository's CI. An AST guard fails there on the day the call site is
written. ``test_an_encoding_less_read_is_decoded_by_the_host_code_page`` below
forces a non-UTF-8 default to show what the guard is protecting against.

Binary modes carry no encoding, so ``open(p, "rb")``, ``os.open`` and
``os.fdopen(fd, "wb")`` are not flagged.

This is a source heuristic for common direct calls and literal import aliases,
not a proof of dynamic bindings or forwarded keyword arguments.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("src/canvas_mcp", "tests")

# "path/to/file.py:function" -> why exactly one site may stay encoding-less.
# Add an entry only with the reason the host code page is the right answer
# there, which for repository-owned text is essentially never.
ENCODING_LESS_ALLOWED: dict[str, str] = {
    "tests/test_text_encoding_guard.py:"
    "test_an_encoding_less_read_is_decoded_by_the_host_code_page": (
        "the control below, which must stay encoding-less to show what a bare "
        "read does on a non-UTF-8 host"
    ),
}

TEXT_READ_WRITE_METHODS = frozenset({"read_text", "write_text"})


@dataclass(frozen=True)
class TextIOSite:
    file: str
    line: int
    function: str
    call: str

    @property
    def key(self) -> str:
        return f"{self.file}:{self.function}"


def _has_encoding(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "encoding":
            return not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
    # **kwargs forwarding: the caller decides, so do not second-guess it.
    return any(kw.arg is None for kw in node.keywords)


def _mode_of(node: ast.Call, mode_arg: int, default: str = "r") -> str | None:
    """The mode of an ``open()`` call, or None when it is not a literal.

    ``mode_arg`` differs by receiver: ``open(path, mode)`` carries it second,
    ``Path.open(mode)`` first.
    """
    for kw in node.keywords:
        if kw.arg == "mode":
            return kw.value.value if isinstance(kw.value, ast.Constant) else None
    if len(node.args) > mode_arg:
        positional = node.args[mode_arg]
        return positional.value if isinstance(positional, ast.Constant) else None
    return default


def _is_binary(node: ast.Call, mode_arg: int, default: str = "r") -> bool:
    mode = _mode_of(node, mode_arg, default)
    return mode is not None and "b" in mode


def scan_source(source: str, filename: str) -> list[TextIOSite]:
    """Recognized text I/O calls that do not name an encoding."""
    sites: list[TextIOSite] = []
    tree = ast.parse(source)

    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    enclosing: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                enclosing.setdefault(id(child), node.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _has_encoding(node):
            continue

        qualified = ""
        if isinstance(node.func, ast.Name):
            qualified = imports.get(node.func.id, node.func.id)
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = node.func.value.id
            qualified = f"{imports.get(owner, owner)}.{node.func.attr}"

        if qualified == "os.open":
            continue
        if qualified in {"io.open", "builtins.open", "gzip.open", "bz2.open", "lzma.open"}:
            compressed = qualified.split(".")[0] in {"gzip", "bz2", "lzma"}
            mode = _mode_of(node, mode_arg=1, default="rb" if compressed else "r")
            if mode is not None and ("t" not in mode if compressed else "b" in mode):
                continue
            call = f"open({mode!r})"
        elif qualified == "os.fdopen":
            if _is_binary(node, mode_arg=1):
                continue
            call = f"fdopen({_mode_of(node, mode_arg=1)!r})"
        elif qualified.rsplit(".", 1)[-1] == "NamedTemporaryFile":
            if _is_binary(node, mode_arg=0, default="w+b"):
                continue
            call = f"NamedTemporaryFile({_mode_of(node, mode_arg=0, default='w+b')!r})"
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in TEXT_READ_WRITE_METHODS:
                call = f"{attr}()"
            elif attr == "open":
                # Path.open() / p.open(); known module functions were handled above.
                mode = _mode_of(node, mode_arg=0)
                if mode is not None and "b" in mode:
                    continue
                call = f"open({mode!r})"
            else:
                continue
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            if _is_binary(node, mode_arg=1):
                continue
            call = f"open({_mode_of(node, mode_arg=1)!r})"
        else:
            continue

        sites.append(
            TextIOSite(
                file=filename,
                line=node.lineno,
                function=enclosing.get(id(node), "<module>"),
                call=call,
            )
        )
    return sites


def scan_repository() -> list[TextIOSite]:
    sites: list[TextIOSite] = []
    for rel in SCANNED_DIRS:
        root = REPO_ROOT / rel
        for path in sorted(root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            name = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            sites.extend(scan_source(source, name))
    return sites


# --- The guard -------------------------------------------------------------


def test_no_encoding_less_text_io_in_src_or_tests() -> None:
    problems = [
        f"{s.file}:{s.line} in {s.function}(): {s.call} with no encoding="
        for s in scan_repository()
        if s.key not in ENCODING_LESS_ALLOWED
    ]
    assert not problems, (
        "A text read or write with no encoding= uses the host code page, so the "
        "same file decodes differently on cp1252/cp932 than on CI's UTF-8. Pass "
        'encoding="utf-8", or open the file in binary mode, or add the call site '
        "to ENCODING_LESS_ALLOWED with the reason.\n" + "\n".join(problems)
    )


def test_every_allowlisted_site_still_exists() -> None:
    """Each exception must cover exactly one call, never another future call."""
    present = Counter(s.key for s in scan_repository())
    invalid = {key: present[key] for key in ENCODING_LESS_ALLOWED if present[key] != 1}
    assert not invalid, f"ENCODING_LESS_ALLOWED requires exactly one site per entry: {invalid}"


# --- Controls: prove the scanner sees what it claims to police --------------


def test_guard_flags_explicit_locale_encoding() -> None:
    source = '''
def locale_io(p, **kwargs):
    p.read_text(encoding=None)
    p.write_text("x", encoding=None)
    open(p, encoding=None)
    p.open(encoding=None)
    p.read_text(encoding=None, **kwargs)
'''
    assert [s.call for s in scan_source(source, "sample.py")] == [
        "read_text()", "write_text()", "open('r')", "open('r')", "read_text()",
    ]


def test_guard_checks_text_mode_fdopen() -> None:
    source = '''
import os
os.fdopen(fd)
os.fdopen(fd, "w")
os.fdopen(fd, mode="r", encoding=None)
os.fdopen(fd, "w", encoding="utf-8")
os.fdopen(fd, "wb")
'''
    assert [s.call for s in scan_source(source, "sample.py")] == [
        "fdopen('r')", "fdopen('w')", "fdopen('r')",
    ]


def test_guard_checks_text_mode_named_temporary_files() -> None:
    source = '''
import tempfile
tempfile.NamedTemporaryFile(mode="w")
NamedTemporaryFile("w", encoding=None)
tempfile.NamedTemporaryFile(mode="w", encoding="utf-8")
tempfile.NamedTemporaryFile()
tempfile.NamedTemporaryFile(mode="wb")
'''
    assert [s.call for s in scan_source(source, "sample.py")] == [
        "NamedTemporaryFile('w')", "NamedTemporaryFile('w')",
    ]


def test_guard_uses_module_open_mode_not_filename() -> None:
    source = '''
import io
import gzip
io.open("blob.txt", "w")
io.open("alpha.txt", "rb")
gzip.open("blob.gz", "wt")
gzip.open("alpha.gz", "rb")
gzip.open("blob.gz")
gzip.open("blob.gz", "r")
'''
    assert [s.call for s in scan_source(source, "sample.py")] == [
        "open('w')", "open('wt')",
    ]


def test_guard_resolves_imported_text_io_aliases() -> None:
    source = '''
import gzip as gz
import io as streamio
from gzip import open as gzopen
from tempfile import NamedTemporaryFile as temporary
gz.open("blob.gz", "wt")
streamio.open("blob.txt", "w")
gzopen("blob.gz", "wt")
temporary(mode="w")
gz.open("blob.gz", "rb")
gzopen("blob.gz")
temporary()
'''
    assert [s.call for s in scan_source(source, "sample.py")] == [
        "open('wt')", "open('w')", "open('wt')", "NamedTemporaryFile('w')",
    ]


@pytest.mark.parametrize("count", [0, 1, 2])
def test_allowlist_permits_exactly_one_site(count: int, monkeypatch) -> None:
    source = "def control(p):\n    pass\n" + "    p.read_text()\n" * count
    sites = scan_source(source, "sample.py")
    monkeypatch.setattr(sys.modules[__name__], "scan_repository", lambda: sites)
    monkeypatch.setattr(
        sys.modules[__name__], "ENCODING_LESS_ALLOWED", {"sample.py:control": "control"}
    )
    if count == 1:
        test_every_allowlisted_site_still_exists()
    else:
        with pytest.raises(AssertionError):
            test_every_allowlisted_site_still_exists()


def test_scanner_reaches_the_real_tree() -> None:
    """An empty walk would make the guard above pass without inspecting anything."""
    encoded = 0
    for rel in SCANNED_DIRS:
        for path in sorted((REPO_ROOT / rel).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            encoded += sum(
                1
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Call) and _has_encoding(node)
            )
    assert encoded > 20, (
        f"only {encoded} calls naming an encoding were found across "
        f"{SCANNED_DIRS}; the walk is broken, so the guard proves nothing"
    )


def test_guard_flags_each_encoding_less_form() -> None:
    source = """
from pathlib import Path

def read_it(p: Path) -> str:
    return p.read_text()

def write_it(p: Path) -> None:
    p.write_text("x")

def open_it(p: Path) -> str:
    with open(p) as handle:
        return handle.read()

def path_open_it(p: Path) -> str:
    with p.open("r") as handle:
        return handle.read()
"""
    found = {(s.function, s.call) for s in scan_source(source, "sample.py")}
    assert found == {
        ("read_it", "read_text()"),
        ("write_it", "write_text()"),
        ("open_it", "open('r')"),
        ("path_open_it", "open('r')"),
    }, found


def test_guard_ignores_what_carries_no_encoding() -> None:
    source = """
import os
from pathlib import Path

def explicit(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def binary_read(p: Path) -> bytes:
    with open(p, "rb") as handle:
        return handle.read()

def binary_write(p: Path, data: bytes) -> None:
    with p.open("wb") as handle:
        handle.write(data)

def low_level(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)

def forwarded(p: Path, **kwargs: object) -> str:
    return p.read_text(**kwargs)
"""
    assert scan_source(source, "sample.py") == []


def test_an_encoding_less_read_is_decoded_by_the_host_code_page(
    tmp_path: Path, monkeypatch
) -> None:
    """What the guard is protecting against, shown on a forced cp932 default."""
    target = tmp_path / "checkmark.py"
    target.write_bytes('STATUS = "✓"\n'.encode())

    real_read_text = Path.read_text

    def shim(self, encoding=None, errors=None, *args, **kwargs):
        return real_read_text(self, encoding=encoding or "cp932", errors=errors)

    monkeypatch.setattr(Path, "read_text", shim)

    assert target.read_text(encoding="utf-8") == 'STATUS = "✓"\n'
    try:
        decoded = target.read_text()
    except UnicodeDecodeError:
        return
    assert decoded != 'STATUS = "✓"\n', (
        "cp932 decoded the UTF-8 bytes without error and without mangling them, "
        "so this control proves nothing on this host"
    )
