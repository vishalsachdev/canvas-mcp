# Release Checklist

When bumping the version in `pyproject.toml`, also update:

- [ ] `src/canvas_mcp/__init__.py` - Update `__version__`
- [ ] `server.json` - Update both `version` fields (top-level and packages[0]) for MCP Registry
- [ ] `tools/TOOL_MANIFEST.json` - Update `version` field to match new version
- [ ] `README.md` - Update "Latest Release" section with new version, date, and changelog
- [ ] `docs/index.html` - Update version badge, tool count, and meta descriptions (GitHub Pages site)
- [ ] Create git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`

> `manifest.json` (Desktop Extension) does **not** need a manual bump — `create-release.yml` stamps the tag version into it and attaches `canvas-mcp.mcpb` to the GitHub Release automatically. The committed `manifest.json` version is just a default.

## Gotchas

- A blanket `s/1.3.0/1.4.0/` also hits dep constraints (e.g. `pytest-asyncio>=1.3.0`) — verify `git diff` shows ONLY the package version before committing.
- `docs/index.html` has both a `softwareVersion` field and a `vX.Y.Z`-style banner; a `\b`-anchored regex misses the `v`-prefixed banner — bump `v`-prefixed refs separately.
- **Publish race:** the MCP Registry job validates the version on PyPI and 404s before PyPI's CDN propagates. Wait until `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/canvas-mcp/<ver>/json` returns 200, THEN `gh run rerun <id> --failed`.
