# `hint` — Async streaming driver — Design

*hint is not templating.* This is the design for the "Async streaming driver" backlog item
(`BACKLOG.md`), a follow-up to the 1.1.0 streaming feature
(`docs/superpowers/specs/2026-07-14-hint-streaming-render-design.md`).

The 1.1.0 spec left the parallel-dispatch async consumer as an explicit non-goal: *"The real
expected usage dispatches all hole fetches up front as parallel tasks (so total latency is `max`
not `sum`), then drives the generator and `await`s each hole's task when the walk reaches it …
This is general and worth building, but it is a follow-up."* This is that follow-up.

The status of the item is deliberately exploratory: we are building it to find out whether it is
a clean helper or something gnarly. If the implementation turns up something non-obvious — the
task-cancellation / `aclose()` hygiene, or awaitable-reuse semantics — we abort and keep this doc
plus a short reflection rather than shipping something we do not understand.

## The idea: an async driver over the sync co-generator

`render_stream` is a synchronous co-generator (see the 1.1.0 spec): it yields HTML `str` chunks and
yields a `Hole` when it reaches a placeholder, and the consumer `.send()`s a `list[ElementOrStr]`
back to fill it. Driving it is the consumer's job, and the *high-value* way to drive it fires every
hole's slow fetch **up front, in parallel**, so total latency is `max(fetch)` not `sum(fetch)`,
while emission stays in strict document order.

This driver encapsulates that loop. Given a tree and a `name -> awaitable` mapping, it:

1. Dispatches every awaitable **known at start** as a task (parallel).
2. Drives `render_stream`; on each hole it `await`s that hole's result and `send`s it back.
3. Yields the `str` chunks straight through, in document order.

`hint`'s core stays synchronous. This helper is a consumer-side convenience that lives *outside*
the pure core, in its own module.

```python
async def render_stream_async(
    node: ElementOrStr,
    fills: Mapping[str, Awaitable[list[ElementOrStr]]],
) -> AsyncGenerator[str, None]:
    ...

async def render_html_stream_async(
    root: Element,
    fills: Mapping[str, Awaitable[list[ElementOrStr]]],
) -> AsyncGenerator[str, None]:
    ...
```

Usage sketch (the payoff — three slow fetches overlap; output is in document order):

```python
fills = {
    "header": fetch_header(),   # coroutines; the driver wraps them into tasks up front
    "rows": fetch_rows(),
    "footer": fetch_footer(),
}
async for chunk in hint.render_html_stream_async(page, fills):
    await response.write(chunk)
```

## Goals

- Encapsulate the parallel-dispatch drive loop as `render_stream_async` /
  `render_html_stream_async`, async generators yielding `str`.
- `max`-latency for holes known at start: dispatch all up front.
- Strict document-order emission (no out-of-order / client-side slot filling).
- A documented **caching guarantee**: equal hole names resolve to the exact same fill data.
- Support **dynamic holes**: a completing fill may invent new holes and add them to `fills`.
- No new runtime dependencies (stdlib `asyncio` only); pure-core and boundary invariants
  (import-linter) untouched.

## Non-goals

- Trio / `anyio` portability. `asyncio` (stdlib) only, documented as such. A structured-concurrency
  version can come later if a consumer needs it; nothing here forecloses it.
- Out-of-order / client-side slot filling (React-Suspense style). Holes emit in **document order**,
  same as the sync path — and this is a deliberate feature, not a limitation. A single HTTP response
  body is an in-order byte stream in every version of the protocol (HTTP/2 and HTTP/3 multiplex
  *across* responses, not *within* one), so document-order maps 1:1 onto what the wire actually
  delivers, with no client-side runtime. React-Suspense "out-of-order streaming" is a client-side
  DOM trick layered over an in-order stream (placeholders emitted in order, then `<script>` chunks
  relocate content) — a different product that ships and owns JS. `hint` stays on the protocol.
- Coalescing / buffering of chunks — inherited from the sync co-generator's granularity.
- A public `holes(node)` enumerator. See "Deferred: `holes()`".

## The two data structures

The driver keeps two dicts, with distinct roles:

- `tasks: dict[str, asyncio.Future[list[ElementOrStr]]]` — the **in-flight dispatches**. Populated
  up front from `fills` and lazily for dynamic holes. This is where the parallelism lives.
- `results: dict[str, list[ElementOrStr]]` — the **value cache**, populated by a resolved `await`.
  This is the caching guarantee: a repeat hole is a plain value read, never a second `await`.

### Why `ensure_future`, and the coroutine-reuse trap

`fills` values are typed `Awaitable`, which in practice is usually a bare **coroutine**. A Python
coroutine is *single-shot*: `await`ing it twice raises `RuntimeError: cannot reuse already awaited
coroutine` (unlike a JS Promise, which is re-awaitable). `asyncio.ensure_future(aw)`:

1. schedules the work to start **immediately** (this is the parallelism), and
2. returns a `Task`/`Future`, which *is* re-awaitable —

and, unlike `asyncio.create_task`, it accepts something that is *already* a Future/Task and returns
it unchanged. So `ensure_future` is the correct wrapper: it handles both coroutines and
already-started futures (the latter matters for dynamic holes — see below).

## The drive loop

Both public functions delegate to one internal async generator, `_drive(gen, fills)`, where `gen`
is a sync `StreamItem` generator: `render_stream(node)` for `render_stream_async`, and
`render_html_stream(root)` for `render_html_stream_async`. This reuses the sync twins wholesale —
the `<html>`-root validation and the leading doctype come from `render_html_stream` for free, and
there is exactly one drive loop (mirrors the sync side's "one walk" ethos). The non-`<html>` root
`ValueError` therefore surfaces when the underlying sync generator is first advanced.

```
# _drive(gen, fills):
tasks   = {name: ensure_future(aw) for name, aw in fills.items()}   # dispatch up front
results = {}
to_send = None
try:
    while True:
        try:
            item = gen.send(to_send)          # first call primes with None
        except StopIteration:
            break
        to_send = None
        if isinstance(item, Hole):
            to_send = await _resolve(item.name, fills, tasks, results)   # a list
        else:
            yield item                        # str chunk, document order
finally:
    for task in tasks.values():
        if not task.done():
            task.cancel()
```

`_resolve(name, fills, tasks, results)`:

```
if name in results:                # cache hit — no await (the caching guarantee)
    return results[name]
if name in tasks:                  # dispatched up front
    task = tasks[name]
elif name in fills:                # dynamic hole added since start
    task = tasks[name] = ensure_future(fills[name])
else:                              # caller error — see "Missing fills"
    raise ValueError(f"render_stream_async: no fill for hole {name!r}")
fill = await task
results[name] = fill
return fill
```

## Caching guarantee

Equal hole names resolve to the **exact same fill data**. The first occurrence of a name `await`s
its task and stores the result in `results`; every later occurrence reads `results` directly (no
second `await`). This is a documented API guarantee consumers may rely on, not an accident of
timing.

Corollary (the supported/unsupported line): mutating or removing an *already-provided* name in
`fills` after it may have been consumed is **unsupported** — the value cache wins and the change is
silently ignored. We do not enforce this; the docs state it. *Adding* new names is supported (see
next).

## Dynamic holes and the arrow of time

`fills` is read **live**, not snapshotted. A completing fill may splice in content containing a
*new* hole and add that hole's awaitable to `fills`. When the walk reaches the new hole, `_resolve`
finds it via the `elif name in fills` branch, wraps it, awaits it, and caches it. Without live reads
this would be impossible, and dynamic holes are most of why nested holes are worth having.

The inventor of a dynamic hole **is expected to start its fetch itself** (add an already-running
future, or a coroutine that is cheap to start late). The driver's `ensure_future` on a dynamic hole
is a *correctness* fallback (it runs at all), **not** a parallelism feature: by the time the walk
reaches a dynamic hole its siblings are already emitted, so parallelism there is only achievable by
pre-starting the fetch. The driver cannot buy back time that has already passed — this is dictated
by the arrow of time, not a limitation we could design away.

## Missing fills — a deliberate divergence from the sync path

The sync `render_stream` renders an *unfilled* hole as empty. That is **not** a chosen "empty is a
fill" semantic — it is fallout from the generator protocol: `None` is the priming/advance artifact
on the send channel (`list[ElementOrStr] | None`), so `None` is structurally unavailable as a
meaningful fill, and advancing past a hole without sending a list therefore renders it empty.

The async driver is **stricter**: it always decides what to send, so it never uses the advance-`None`
path. A hole with **no entry in `fills`** is caller error and raises `ValueError` naming the hole
(consistent with eager `render`'s own unresolved-hole `ValueError`). "Deliberately empty" is spelled
`fills[name] = _resolved([])` — an awaitable resolving to `[]` — not omission. Rationale: at this
layer the caller owns the hole, so a missing fill is a bug, not a silent empty region. The low-level
co-generator stays lenient; the convenience driver has opinions.

## Error handling and cancellation

- If an awaited fill **raises**, the exception propagates out of the async generator. The `finally`
  cancels every still-pending task, so a failure in one fetch does not orphan the others.
- If the consumer stops early (`break` out of the `async for`, i.e. `aclose()`), `GeneratorExit` is
  thrown into the generator; the same `finally` cancels outstanding tasks.
- Cancellation scope is **only tasks the driver created** (everything in `tasks`). Awaitables the
  caller kept references to elsewhere are the caller's concern.

This cancellation/`aclose()` hygiene is the part with real risk. If it turns gnarly (e.g. cancelled
tasks needing to be awaited to suppress "Task was destroyed but it is pending" warnings, or
interaction with the caller's own task group), that is a candidate abort trigger — we stop, keep
this doc, and write a short reflection.

## Placement and boundary

- New internal module `hint/_async.py`. It imports `hint._core` only (never the package boundary),
  so import-linter's boundary and pure-core-stays-sync invariants hold: `_core` gains no `asyncio`.
- The boundary `hint/__init__.py` re-exports `render_stream_async` and `render_html_stream_async`.
- import-linter contracts extended so `_async` is an allowed internal module importing `_core`.

## Deferred: `holes()`

The backlog floats a `holes(node)` name-enumerator "possibly alongside" the driver, for discovering
which names a tree contains so a consumer can build `fills`. It is deferred (YAGNI): it is a pure
sync tree walk, easy to add later, and it fundamentally *cannot* see dynamic holes (names hidden
inside not-yet-resolved awaitable results), so it is a partial tool. We build the driver — the real
value — first, and add `holes()` only if it earns its place against a concrete consumer need.

## Testing

- Colocated `src/hint/async_test.py` (project convention: `*_test.py` under `src`).
- Tests use `asyncio.run(...)` to drive an async collector, so **no `pytest-asyncio` dependency** is
  added. A small helper collects an async generator into a `list[str]`.
- Cases:
  - **Happy path / parallelism:** two holes whose fetches, driven concurrently, complete with total
    latency `max` not `sum` (assert via awaited-order / a shared timeline, not wall-clock sleeps
    where avoidable).
  - **Document order:** chunks emit in tree order regardless of which fetch finishes first.
  - **Caching guarantee:** a name appearing twice `await`s once and yields identical data (assert the
    underlying coroutine ran once).
  - **List fill / empty fill:** `[]` renders empty; multi-element list splices with no wrapper.
  - **Nested/dynamic hole:** a fill that adds a new name to `fills` is resolved and spliced.
  - **Missing fill raises:** a hole absent from `fills` raises `ValueError` naming it.
  - **Fetch raises → propagates and cancels others:** one failing fill propagates; siblings are
    cancelled (assert cancellation, no orphaned-task warning).
  - **Early stop (`aclose`)/break:** outstanding tasks are cancelled.
  - **`render_html_stream_async`:** doctype first; non-`<html>` root raises (mirrors the sync twin).

Internal helpers (`_resolve`, the collector) are covered through the public surface (project
convention).

## Docs and backlog

- README "Streaming" section: replace the "left to the consumer for now … planned" note with a
  short subsection showing `render_stream_async` / `render_html_stream_async` and the parallel-fetch
  payoff, the caching guarantee, dynamic holes, and the strict missing-fill behaviour.
- `BACKLOG.md`: remove the "Async streaming driver" item (or, if we abort, replace it with the
  reflection).
- `CLAUDE.md`: note `hint/_async.py` in the package-structure section; add `async` reasoning to any
  suppressions if they arise.

## Versioning

Additive, backward-compatible public surface → **minor** bump (`feat(render):`). release-please
drives it from the conventional-commit type; no manual version edit.
