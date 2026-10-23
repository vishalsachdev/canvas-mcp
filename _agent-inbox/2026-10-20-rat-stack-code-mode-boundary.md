# Evaluate rat-stack's code-mode boundary as a design option for execute_typescript (#157)

**Repo:** canvas-mcp
**File:** src/canvas_mcp/tools/code_execution.py, src/canvas_mcp/code_api/ (design only; no change proposed yet)
**Priority:** normal
**Requested by:** Xplorer for Vishal, 2026-10-20
**Updated:** 2026-10-22 (added Pi codemode reference)
**Authored and committed by:** [Xplorer]

## What to change

This is a design idea for the host session to evaluate. It is not an order. Nothing here needs to ship, and any code change goes through a PR with Vishal's approval.

rat-stack ([ratstack.sh](https://ratstack.sh/), [github.com/joelhooks/rat-stack](https://github.com/joelhooks/rat-stack)) runs a code-mode endpoint like `execute_typescript`. Its sandbox boundary is built the other way round from ours:

- **Our model today.** AGENTS.md says the sandbox "holds `CANVAS_API_TOKEN` and can reach the Canvas API directly". The in-process guard can be bypassed (#157), and an `execute_typescript` run "voids the confirmation-token and untrusted-content fencing guarantees." The container path can already add `--network=none`, but only when there is no allowlist. Code that calls Canvas needs the network and the token.
- **rat-stack's model.** The sandbox gets no network and no credentials. Every `tools.x(input)` call returns to host code, which decodes the input with the tool's schema, runs the same handler that the HTTP and MCP surfaces use, and encodes the result. Project law in [AGENTS.md](https://ratstack.sh/AGENTS.md): "The sandbox is a surface, not a bypass. Anything reachable from a code-mode program must be a capability and goes through that capability's schemas and handler." Write-type actions can be left out of the sandbox list. Its signup action `joinInterest` is excluded this way.
- **Its limits.** [apps/site/src/sandbox-worker-loader.ts](https://github.com/joelhooks/rat-stack/blob/main/apps/site/src/sandbox-worker-loader.ts) loads a fresh Dynamic Worker with `globalOutbound: null`, a 100 ms CPU limit, five subrequests and a ten-second timeout. The catalog and TypeScript declarations are generated from the same contracts in [packages/capability/src/to-code-mode.ts](https://github.com/joelhooks/rat-stack/blob/main/packages/capability/src/to-code-mode.ts). Rate limits are 6 calls per IP and 300 total per minute. See [/lore/one-program-can-replace-several-tool-calls](https://ratstack.sh/lore/one-program-can-replace-several-tool-calls) and [/lore/one-capability-every-surface](https://ratstack.sh/lore/one-capability-every-surface).

The option to evaluate for #157:
1. Run `execute_typescript` with `--network=none` always, and give the container no Canvas token.
2. Expose the code API operations as a host-side bridge (stdin/stdout RPC) to the existing tool handlers. Confirmation tokens, role filtering and untrusted-content fencing then apply to code-mode calls too.
3. Start with read operations only. Add write operations later, each behind the same preview/confirm step as the MCP tool.
4. Generate the code-API catalog from the registered tools, so the two lists cannot drift.

Measure the cost first. Bulk jobs make many calls, and a bridge adds a round trip per call. Batching operations may be needed to keep the token savings that justify `execute_typescript`.

## Pi codemode reference (earendil-works/pi)

Pi's `codemode` tool is a second piece of prior art. Source: [packages/coding-agent/docs/codemode.md](https://github.com/earendil-works/pi/blob/16f5f0af4d85ca583d045ceb5ed6d646fcaf7761/packages/coding-agent/docs/codemode.md) at commit 16f5f0a. Points that apply to canvas-mcp:

1. **Same boundary.** Scripts run in a QuickJS sandbox that "has no Node APIs, file system, network, or timers; scripts reach the outside world only through tools and `models`." Every outside call is `tools.<name>(args)`. This matches the boundary proposed above. Cite it as prior art in #157.
2. **No rollback.** "Tool calls are real: calls made before a failure are not undone." Calls still running when the script ends are cancelled. A half-failed script can leave partial writes. So keep Canvas write tools (grades, submissions, announcements, messages) out of the code-mode path by default. If they are added later, each one needs an explicit confirm step.
3. **Deferred tool exposure.** Pi does not list MCP tools in the `codemode` description. Scripts find them with `searchTools()` (BM25 ranking, default limit 8), `describeTool()`, `describeNamespace()` or `ALL_TOOLS`. Listed declarations share a budget of about 3000 tokens (`codemode.inlineBudget`). canvas-mcp has a large tool list, so the code-API catalog could work the same way: a short inline list plus search and describe helpers.
4. **Output filtering.** Only the script's output reaches the model. It is capped by `max_output_tokens` (default 10000). Longer output keeps its start and end, and the full text goes to a temp file. This suits large roster and submission listings. Filtering must happen inside the script, before output, so learner PII is not echoed to the model. The overflow temp file also holds full output, so it needs the same care.
5. **Small persistent store.** `store(key, value)` and `load(key)` keep small JSON values across calls. Writes are kept only when the script succeeds. Pi means it for IDs, cursors and summaries. It is optional prior art for course IDs or pagination cursors. Do not store learner data there.
6. **Optional `mode: only`.** With `codemode.mode: only`, Pi hides the normal tools so the model must call them through scripts. This could be a later option for canvas-mcp. It should not be the default.

## Why

#157 ("Harden execute_typescript sandbox: container-level egress control, non-root user, prebuilt tsx image") is open, and CLAUDE.md says "sandbox egress is mitigated, not closed." Egress control limits where the token can go. The bridge design removes the token from the sandbox, so the guarantees in AGENTS.md hold again. It changes the threat model instead of patching the guard.

## Notes

- **Learner data.** This note does not route learner data anywhere new. Data stays in the same server process and goes through the same handlers. Grading flows and their review rules stay as they are. Any test of a bridge prototype should use a sandbox course with synthetic data.
- **Caveats on the source.** rat-stack is a prerelease reference (Alchemy beta, XState alpha). Its sandbox runs on Cloudflare Dynamic Workers, and canvas-mcp's runs in a local container, so copy the boundary, not the runtime. On 2026-10-20 its live sandbox listed 16 tools while its lore page names 6, so its docs drift too.
- canvas-mcp already serves `docs/llms.txt`. rat-stack's agent guide is at [ratstack.sh/llms.txt](https://ratstack.sh/llms.txt) for comparison. No change is suggested there.
- This is a public repo. This note has no secrets, tokens or student data.
- Related fleet-wide note (hook and escape-ledger ideas from the same research): claude-config/_agent-inbox/2026-10-20-rat-stack-fence-patterns.md.
