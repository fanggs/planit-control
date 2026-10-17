// Keep one refresh running and at most one follow-up. Events received during a
// fetch still need a later fetch, but a burst does not need one fetch per event.
export function createRefreshQueue(task) {
  let current, pending;
  function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
  }
  function finish(batch, failed, value) {
    // Advance state before notifying callers, so a new request cannot be lost
    // between a completed fetch and its promise callbacks.
    current = pending;
    pending = undefined;
    if (current) run(current);
    if (failed) batch.reject(value);
    else batch.resolve(value);
  }
  function run(batch) {
    Promise.resolve().then(task).then(
      value => finish(batch, false, value),
      error => finish(batch, true, error));
  }
  return function refresh() {
    if (!current) {
      current = deferred();
      run(current);
      return current.promise;
    }
    pending ??= deferred();
    return pending.promise;
  };
}
