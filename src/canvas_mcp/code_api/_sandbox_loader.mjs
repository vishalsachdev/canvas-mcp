// Preloaded with --import when execute_typescript runs under the local sandbox.
//
// The sandbox runs the caller's script with plain Node, under its permission
// model, instead of tsx: tsx transpiles through an esbuild child process, and
// the permission model exists here precisely to refuse child processes. Node
// strips TypeScript types itself, but it resolves imports the ESM way, which
// is stricter than tsx. This in-thread hook restores the relative forms that
// this API documents and tsx accepted, and nothing else:
//   './client.js'      -> './client.ts'
//   './client'         -> './client.ts'
//   './canvas/grading' -> './canvas/grading/index.ts'
//
// registerHooks runs on the main thread, so the hook needs no worker thread,
// which the sandbox does not grant.
import { registerHooks } from 'node:module';

const RETRY_CODES = new Set(['ERR_MODULE_NOT_FOUND', 'ERR_UNSUPPORTED_DIR_IMPORT']);
const HAS_EXTENSION = /\.[A-Za-z0-9]+$/;

function typescriptCandidates(specifier) {
  if (specifier.endsWith('.js')) {
    return [`${specifier.slice(0, -3)}.ts`];
  }
  const lastSegment = specifier.slice(specifier.lastIndexOf('/') + 1);
  if (HAS_EXTENSION.test(lastSegment)) {
    return [];
  }
  return [`${specifier}.ts`, `${specifier}/index.ts`];
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (error) {
      const relative = specifier.startsWith('./') || specifier.startsWith('../');
      if (!relative || !RETRY_CODES.has(error?.code)) {
        throw error;
      }
      for (const candidate of typescriptCandidates(specifier)) {
        try {
          return nextResolve(candidate, context);
        } catch (candidateError) {
          if (!RETRY_CODES.has(candidateError?.code)) {
            throw candidateError;
          }
        }
      }
      throw error;
    }
  },
});
