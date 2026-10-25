// Preloaded with --import when execute_typescript runs under the local sandbox.
//
// The sandbox runs the caller's script with plain Node, under its permission
// model, instead of tsx: tsx transpiles through an esbuild child process, and
// the permission model exists here precisely to refuse child processes. Node
// strips TypeScript types itself, but it does not map the `./client.js` style
// specifiers that this API documents onto the `.ts` files that exist. This
// in-thread hook does that one mapping, and nothing else.
//
// registerHooks runs on the main thread, so the hook needs no worker thread,
// which the sandbox does not grant.
import { registerHooks } from 'node:module';

registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (error) {
      const relative = specifier.startsWith('./') || specifier.startsWith('../');
      if (error?.code === 'ERR_MODULE_NOT_FOUND' && relative && specifier.endsWith('.js')) {
        return nextResolve(`${specifier.slice(0, -3)}.ts`, context);
      }
      throw error;
    }
  },
});
