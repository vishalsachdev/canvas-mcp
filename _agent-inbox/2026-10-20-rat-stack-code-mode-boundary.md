# Evaluate rat-stack's code-mode boundary as a design option for execute_typescript (#157)

**Repo:** canvas-mcp
**File:** src/canvas_mcp/tools/code_execution.py, src/canvas_mcp/code_api/ (design only; no change proposed yet)
**Priority:** normal
**Requested by:** Xplorer for Vishal, 2026-10-20
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

## Why

#157 ("Harden execute_typescript sandbox: container-level egress control, non-root user, prebuilt tsx image") is open, and CLAUDE.md says "sandbox egress is mitigated, not closed." Egress control limits where the token can go. The bridge design removes the token from the sandbox, so the guarantees in AGENTS.md hold again. It changes the threat model instead of patching the guard.

## Notes

- **Learner data.** This note does not route learner data anywhere new. Data stays in the same server process and goes through the same handlers. Grading flows and their review rules stay as they are. Any test of a bridge prototype should use a sandbox course with synthetic data.
- **Caveats on the source.** rat-stack is a prerelease reference (Alchemy beta, XState alpha). Its sandbox runs on Cloudflare Dynamic Workers, and canvas-mcp's runs in a local container, so copy the boundary, not the runtime. On 2026-10-20 its live sandbox listed 16 tools while its lore page names 6, so its docs drift too.
- canvas-mcp already serves `docs/llms.txt`. rat-stack's agent guide is at [ratstack.sh/llms.txt](https://ratstack.sh/llms.txt) for comparison. No change is suggested there.
- This is a public repo. This note has no secrets, tokens or student data.
- Related fleet-wide note (hook and escape-ledger ideas from the same research): claude-config/_agent-inbox/2026-10-20-rat-stack-fence-patterns.md.
