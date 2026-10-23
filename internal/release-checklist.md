# Release Checklist

> Paths, workflow behavior and version-field counts verified 2026-09-30 against v1.13.0.

When bumping the version in `pyproject.toml`, also update:

- [ ] `src/canvas_mcp/__init__.py` - Update `__version__`
- [ ] `server.json` - Update both `version` fields (top-level and packages[0]) for MCP Registry
- [ ] `tools/TOOL_MANIFEST.json` - Update `version` field to match new version
- [ ] `README.md` - Update "Latest Release" section with new version, date, and changelog
- [ ] `docs/index.html` - Update version badge, tool count, and meta descriptions (Cloudflare Pages site; deploy by hand with `npx wrangler pages deploy docs/ --project-name=canvas-mcp --branch=main`)
- [ ] `uv.lock` - Run `uv lock` after bumping `pyproject.toml`; the lock records the project version and drifts otherwise
- [ ] Create git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
- [ ] Confirm the production deploy ran: the tag push also triggers `deploy-prod.yml`. Merges to `main` do not deploy production; between releases, ship `main` with a manual `deploy-prod.yml` run from `main`.

> `manifest.json` (Desktop Extension) does **not** need a manual bump — `create-release.yml` stamps the tag version into it and attaches `canvas-mcp.mcpb` to the GitHub Release automatically. The committed `manifest.json` version is just a default.

## Pending for the next release

- Nothing flagged as of 2026-09-30. (v1.13.0 shipped 2026-09-27; see `CHANGELOG.md`.)

## Gotchas

- A blanket `s/1.3.0/1.4.0/` also hits dep constraints (e.g. `pytest-asyncio>=1.3.0`) — verify `git diff` shows ONLY the package version before committing.
- `docs/index.html` has both a `softwareVersion` field and a `vX.Y.Z`-style banner; a `\b`-anchored regex misses the `v`-prefixed banner — bump `v`-prefixed refs separately.
- **`Installing mcp-publisher version: null` (first seen v1.11.0):** NOT the publish race. The
  registry job resolved the mcp-publisher tag via an *unauthenticated* `api.github.com` call,
  hit the per-runner-IP rate limit, and `jq` returned the string `null`. The download URL then
  404'd into a 9-byte body and the step died on `gzip: stdin: not in gzip format` — three steps
  from the real cause. A plain `gh run rerun --failed` succeeded. Hardened afterwards: the call
  is authenticated with `github.token`, the tag is checked for null/empty, and `curl --fail`
  stops an error page reaching `tar`. **Tell the two apart by checking PyPI first:** if
  `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/canvas-mcp/<ver>/json` already
  returns 200, it is not the propagation race.
- **Publish race:** the MCP Registry job validates the version on PyPI and 404s before PyPI's CDN propagates. Wait until `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/canvas-mcp/<ver>/json` returns 200, THEN `gh run rerun <id> --failed`.


## Maintaining the MCP publisher pin

The repository maintainer owns the version and Linux amd64 SHA-256 pin in
`.github/workflows/publish-mcp.yml`. The `v1.11.0` incident above refers to a
canvas-mcp release, not the publisher binary. On 2026-10-21 the pinned publisher
v1.8.1 passed `validate server.json` against the live Registry and advertised
`login github-oidc`. This is compatibility evidence, not a completed release.

Before tagging, install the pinned binary with `scripts/install_mcp_publisher.py`,
run `mcp-publisher --version`, `mcp-publisher login --help`, and
`mcp-publisher validate server.json`. Validation does not publish. Recheck after
a schema change or Registry migration. If an update is needed, select an explicit
official Registry release, verify its published Linux amd64 asset digest, update
version and checksum together, rerun installer regressions and live validation,
and review the change through a PR. Never restore an unpinned `latest` download.

Actual OIDC login needs the Actions publishing job. Review protected tags,
publishing environments and OIDC audiences before authorizing a release.
Old tags predating #515 lack the new helper scripts: do not use the revised
manual workflow to republish them. Canvas HTML readback still needs a separately
authorized real-page check before relying on the accessibility `applied` field.
