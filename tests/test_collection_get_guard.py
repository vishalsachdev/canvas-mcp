"""Guard: no single-request GET on a Canvas collection endpoint in tool code (issue 420).

A single ``make_canvas_request("get", ...)`` returns Canvas's first page and
silently drops the rest. On a collection endpoint that is a truncated list
presented as complete, and in ``assign_peer_review`` it once became a write: a
reviewee past page 1 got a placeholder submission POSTed on their behalf.

Collections must be read with ``fetch_all_paginated_results``. A tool that reads
one page on purpose passes ``_pagination=`` so it can see Canvas's next link and
must tell the caller more exists. Passing ``_pagination=`` proves only that the
link is read, not that it is reported, so such readers are exempt only when
listed in ``DISCLOSING_SINGLE_PAGE_READERS`` with the behavioral test that
proves they report ``more_available``.

This test walks the AST of every module under ``src/canvas_mcp/tools`` and
fails when a GET's path template ends in a literal segment (a collection name)
rather than an identifier, unless the template is a known single-object path
listed below with the reason it is single, or the call is a listed
disclosing single-page reader.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "canvas_mcp" / "tools"

# Path templates (each interpolation shown as "{}") that end in a literal
# segment yet return one object, not a list. Checked by hand against the call
# sites when this guard was written; add to it only with the same evidence.
SINGLE_OBJECT_PATHS: dict[str, str] = {
    "/courses/{}/front_page": "the course's one front page",
    "/users/self": "the caller's own user object",
    "/users/self/profile": "the caller's own profile object",
    "/courses/{}/assignments/{}/submissions/self": "the caller's own submission",
    # {prefix} is /courses/{id} or /groups/{id} since group discussions (#433).
    "{}/discussion_topics/{}/view": "the full-topic view: one object holding the whole tree",
    "{}/discussion_topics/{}/entry_list": "ID-filtered by ids[]: returns exactly the entries asked for",
    "/conversations/unread_count": "one count object",
    "/courses/{}/permissions": "one permissions map",
}

# (file under tools/, function) -> "test file::test name" proving the reader
# reports more_available when Canvas sends a next link. Only listed readers may
# use a single-page collection GET with _pagination=; every named test must
# exist (checked below).
DISCLOSING_SINGLE_PAGE_READERS: dict[tuple[str, str], str] = {
    ("messaging.py", "list_conversations"): (
        "tests/tools/test_truncation_disclosure.py::"
        "test_list_conversations_reports_more_available_without_fetching_more"
    ),
}

REPO_ROOT = TOOLS_DIR.parents[2]


@dataclass(frozen=True)
class GetSite:
    file: str
    line: int
    function: str
    path: str | None  # None when the endpoint expression could not be resolved
    reads_next_link: bool


def _template(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _arg(call: ast.Call, index: int, keyword: str) -> ast.AST | None:
    if len(call.args) > index:
        return call.args[index]
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _local_string_assignments(function: ast.AST) -> dict[str, str | None]:
    """Map local names to the string template assigned to them, if unambiguous."""
    found: dict[str, str | None] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                value = _template(node.value)
                # A name assigned two different templates is ambiguous.
                if target.id in found and found[target.id] != value:
                    found[target.id] = None
                else:
                    found[target.id] = value
    return found


def scan_source(source: str, filename: str) -> list[GetSite]:
    """Return every single-request GET in ``source``, keyed to its innermost function."""
    tree = ast.parse(source)
    sites: dict[tuple[int, int], GetSite] = {}
    functions = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    # Outer functions first, so an inner function's entry overwrites them.
    functions.sort(key=lambda f: (f.lineno, -(f.end_lineno or f.lineno)))
    for function in functions:
        locals_ = _local_string_assignments(function)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or _call_name(node) != "make_canvas_request":
                continue
            method = _arg(node, 0, "method")
            if not (isinstance(method, ast.Constant) and str(method.value).lower() == "get"):
                continue
            endpoint = _arg(node, 1, "endpoint")
            path = _template(endpoint)
            if path is None and isinstance(endpoint, ast.Name):
                path = locals_.get(endpoint.id)
            reads_next = any(kw.arg == "_pagination" for kw in node.keywords)
            key = (node.lineno, node.col_offset)
            sites[key] = GetSite(filename, node.lineno, function.name, path, reads_next)
    return sorted(sites.values(), key=lambda s: s.line)


def is_collection_path(path: str) -> bool:
    """True when the template ends in a literal segment that is not a known single object."""
    bare = path.split("?", 1)[0].rstrip("/")
    if bare in SINGLE_OBJECT_PATHS:
        return False
    last = bare.rsplit("/", 1)[-1]
    return "{}" not in last


def violations(sites: list[GetSite]) -> list[str]:
    problems = []
    for site in sites:
        where = f"{site.file}:{site.line} in {site.function}()"
        if site.reads_next_link and (site.file, site.function) in DISCLOSING_SINGLE_PAGE_READERS:
            continue
        if site.path is None:
            problems.append(f"{where}: GET endpoint could not be resolved to a path template")
        elif is_collection_path(site.path):
            if site.reads_next_link:
                problems.append(
                    f"{where}: single-page GET on collection {site.path!r} reads the next "
                    "link but is not a listed disclosing reader (DISCLOSING_SINGLE_PAGE_READERS)"
                )
            else:
                problems.append(f"{where}: single-request GET on collection {site.path!r}")
    return problems


def scan_tools() -> list[GetSite]:
    sites: list[GetSite] = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        sites.extend(scan_source(path.read_text(encoding="utf-8"), str(path.relative_to(TOOLS_DIR))))
    return sites


# --- The guard -------------------------------------------------------------


def test_no_single_request_get_on_a_collection_endpoint():
    problems = violations(scan_tools())
    assert not problems, (
        "Single-request GET on a collection endpoint returns only Canvas's first page "
        "(issue 420). Use fetch_all_paginated_results, or pass _pagination=, report "
        "more_available, and list the reader in DISCLOSING_SINGLE_PAGE_READERS with "
        "the test proving it. If the path really returns one object, add it to "
        "SINGLE_OBJECT_PATHS with the reason.\n" + "\n".join(problems)
    )


# --- Controls: prove the scanner sees what it claims to police --------------


def test_scanner_finds_known_single_request_gets():
    """Positive control on the real tree: an empty scan must not pass the guard."""
    sites = scan_tools()
    paths = {s.path for s in sites}
    assert len(sites) > 50, f"scanner found only {len(sites)} GET sites; the walk is broken"
    assert "/courses/{}/front_page" in paths
    assert "/courses/{}/assignments/{}/submissions/self" in paths
    # Resolved through a local variable, not a literal argument.
    assert "/courses/{}/modules/{}/items/{}" in paths


def test_every_allowlisted_path_is_still_used():
    """A stale allowlist entry would silently permit a future collection read."""
    paths = {s.path for s in scan_tools()}
    unused = sorted(set(SINGLE_OBJECT_PATHS) - paths)
    assert not unused, f"SINGLE_OBJECT_PATHS entries no longer used: {unused}"


def test_list_conversations_reads_next_link():
    """The one deliberate single-page collection read must carry _pagination."""
    convo = [s for s in scan_tools() if s.path == "/conversations"]
    assert convo and all(s.reads_next_link for s in convo)


def test_every_disclosing_reader_is_used_and_backed_by_an_existing_test():
    """Each exemption must match a real _pagination reader and name a real test."""
    readers = {(s.file, s.function) for s in scan_tools() if s.reads_next_link}
    unused = sorted(set(DISCLOSING_SINGLE_PAGE_READERS) - readers)
    assert not unused, f"DISCLOSING_SINGLE_PAGE_READERS entries no longer used: {unused}"

    for reader, test_ref in DISCLOSING_SINGLE_PAGE_READERS.items():
        test_file, test_name = test_ref.split("::")
        tree = ast.parse((REPO_ROOT / test_file).read_text(encoding="utf-8"))
        names = {
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert test_name in names, f"{reader}: behavioral test {test_ref} does not exist"


def test_guard_flags_an_unlisted_pagination_reader():
    """_pagination= alone proves the link is read, not that truncation is reported."""
    source = '''
async def list_everyone():
    return await make_canvas_request("get", "/courses/1/users", _pagination={})
'''
    problems = violations(scan_source(source, "synthetic.py"))
    assert len(problems) == 1
    assert "not a listed disclosing reader" in problems[0]


def test_guard_flags_listed_function_name_in_another_file():
    """The exemption is keyed to (file, function), not the function name alone."""
    source = '''
async def list_conversations():
    return await make_canvas_request("get", "/conversations", _pagination={})
'''
    assert len(violations(scan_source(source, "other.py"))) == 1
    assert violations(scan_source(source, "messaging.py")) == []


def test_guard_flags_a_reintroduced_truncated_lookup():
    """The pre-fix assign_peer_review call shape must be reported."""
    source = '''
async def assign_peer_review(course_id, assignment_id):
    submissions = await make_canvas_request(
        "get",
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        params={"per_page": 100},
    )
'''
    problems = violations(scan_source(source, "synthetic.py"))
    assert len(problems) == 1
    assert "submissions" in problems[0]


def test_guard_flags_collection_via_variable_and_keyword_method():
    source = '''
async def tool(course_id):
    endpoint = f"/courses/{course_id}/users"
    return await client.make_canvas_request(method="GET", endpoint=endpoint)
'''
    problems = violations(scan_source(source, "synthetic.py"))
    assert len(problems) == 1
    assert "/courses/{}/users" in problems[0]


def test_guard_flags_unresolvable_endpoint():
    source = '''
async def tool(course_id, suffix):
    return await make_canvas_request("get", "/courses/" + suffix)
'''
    problems = violations(scan_source(source, "synthetic.py"))
    assert len(problems) == 1
    assert "could not be resolved" in problems[0]


def test_guard_passes_single_object_and_paginated_reads():
    source = '''
async def tool(course_id, page_id):
    a = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_id}")
    b = await make_canvas_request("get", f"/courses/{course_id}/front_page")
    c = await make_canvas_request("post", f"/courses/{course_id}/pages")
    d = await fetch_all_paginated_results(f"/courses/{course_id}/pages")
'''
    assert violations(scan_source(source, "synthetic.py")) == []
