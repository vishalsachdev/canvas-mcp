/** Validate once, before callers perform reads, and own per-invocation batching. */
export function createBatchRunner(controls: {maxConcurrent?: number; rateLimitDelay?: number}) {
  const maxConcurrent = controls.maxConcurrent ?? 5;
  const rateLimitDelay = controls.rateLimitDelay ?? 1000;
  if (!Number.isSafeInteger(maxConcurrent) || maxConcurrent < 1) {
    throw new Error('maxConcurrent must be a positive safe integer');
  }
  // Node clamps overflowing/negative timers to roughly 1ms; reject them.
  if (!Number.isInteger(rateLimitDelay) || rateLimitDelay < 0 || rateLimitDelay > 2147483647) {
    throw new Error('rateLimitDelay must be an integer from 0 to 2147483647 milliseconds');
  }

  return async function runBatches<T, R>(
    items: readonly T[], process: (item: T) => Promise<R>
  ): Promise<PromiseSettledResult<R>[]> {
    const results: PromiseSettledResult<R>[] = [];
    for (let i = 0; i < items.length; i += maxConcurrent) {
      // A rejection must not open the next batch while other writes remain active.
      const batchResults = await Promise.allSettled(
        items.slice(i, i + maxConcurrent).map(async item => process(item))
      );
      for (const result of batchResults) results.push(result);
      if (rateLimitDelay > 0 && i + maxConcurrent < items.length) {
        await new Promise(resolve => setTimeout(resolve, rateLimitDelay));
      }
    }
    return results;
  };
}
