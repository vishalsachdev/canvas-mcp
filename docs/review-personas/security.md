---
type: review-persona
domain: security+quality+deployment
repo: canvas-mcp
version: 1.0.0
source: GEPA-distilled from 37 real Claude Code session bugfixes (claude-mem, Mar–Jun 2026)
---

# Canvas MCP — Review Persona: Security, Quality, Deployment

Use this checklist when reviewing any PR touching `src/`, `Dockerfile`, `pyproject.toml`, or deployment config.
An LLM-as-judge should flag any item below that the PR violates or fails to address.

---

## Security

- [ ] **Path confinement uses `Path.is_relative_to()`**, not `str.startswith()`.
  Why: `str.startswith("/app/src/canvas_mcp/code_api")` is bypassed by `/app/src/canvas_mcp/code_api_evil/` (CWE-22).
- [ ] **Symlinks resolved before confinement check**: `Path(p).resolve()` called before `is_relative_to()`.
  Why: Symlinks at `local_maps/` can redirect PII writes to arbitrary locations.
- [ ] **User-supplied filenames stripped of directory components**: `Path(filename).name` used, not raw filename.
  Why: Filenames like `../../etc/passwd` pass naive checks.
- [ ] **Auth fails closed at startup**: server calls `sys.exit(1)` if `MCP_ACCESS_KEYS` unset and `MCP_ALLOW_UNAUTHENTICATED` is false.
  Why: Previous behaviour logged a warning but started an ungated endpoint exposing Canvas gradebook read/write.
- [ ] **No PII in logs**: `X-MS-CLIENT-PRINCIPAL-NAME` (user UPN/email) never logged. Only opaque identifiers: OID, scope, client app ID.
  Why: `entra_upn` key was not in `_PII_KEYS`, causing UPN to leak on every request.
- [ ] **Entra auth guard present**: `MCP_ALLOW_UNAUTHENTICATED=true` required as explicit opt-in when `ENTRA_AUTH_ENABLED=true`.
  Why: Prevents header spoofing in misconfigured deployments where App Service auth is not properly set up.
- [ ] **Code execution disabled in network-facing containers**: `EXECUTE_TYPESCRIPT_ENABLED=false` in `Dockerfile ENV`.
  Why: Network callers could execute TypeScript with a dummy auth header.
- [ ] **Canvas URL validation allows institution vanity domains (CNAMEs)**, not just `*.instructure.com` regex.
  Why: `canvas.illinois.edu` is a CNAME to `illinoisedu-vanity.instructure.com` — strict regex rejects valid institutional URLs.

---

## Code Quality

- [ ] **No blocking I/O in async functions**: `await fs.promises.readFile` / `await fs.promises.writeFile`, not `readFileSync`.
  Why: Blocking I/O in async functions stalls the event loop.
- [ ] **Windows tsx resolution**: `shutil.which('tsx')` checked first with `os.path.realpath()`, explicit error if not found — no `npx` fallback.
  Why: `npx` fallback on Windows caused issue #83 (wrong tsx version resolved through shims).
- [ ] **Config validation mutates invalid values back to defaults**, not just logs a warning.
  Why: `validate_config()` warned about invalid `CANVAS_ROLE` but never reset it, causing silent failures in `register_all_tools()`.
- [ ] **Test import paths use `canvas_mcp.tools.X`**, not `src.canvas_mcp.tools.X`.
  Why: `src.` prefix doesn't match installed package layout and breaks test mocks.

---

## Deployment

- [ ] **SCM basic auth enabled on both production and staging slots** before deploying.
  Why: Auth disabled on one slot caused deployment authentication failures after publish profile refresh.
- [ ] **MCP registry submission includes a PyPI propagation wait** after publish.
  Why: Registry validation hits PyPI; immediate submission gets 404 if package not yet discoverable.
- [ ] **Dependency version bumps are isolated commits**, not bundled with feature/fix changes.
  Why: `pytest-asyncio` version bump was accidentally included in an unrelated commit, requiring a revert.
