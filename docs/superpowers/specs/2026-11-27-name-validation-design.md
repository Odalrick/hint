# Refuse tag and attribute names that break out of the tag — design

## Intent

`render` passes tag and attribute names through `html.escape`, which handles quoting but not the characters that end a
name: `{"x href": "javascript:…"}` renders `<a x href="javascript:…">`, and `element("div onclick=alert(1)")` renders a
working `onclick`. No escaping of a name is meaningful, so such names are refused. In practice names come from code
literals, so the goal is quick feedback at the line that wrote the bad name.

## Goals, non-goals

- Goal: a bad tag or attribute name raises `ValueError` where the element is built.
- Non-goal: covering `Element(...)` built directly, or an attrs dict mutated after construction — nobody does either.
- Non-goal: dropping bad attributes silently — a bad name is the caller's bug, not data.

## Approaches

- **Check in the constructors (chosen, by the user):** `element` / `void_element` check the tag name when called (so
  built-in tags fail at `import hint`) and attribute names on each construction. Errors point at the code that wrote the
  name.
- Check at render, in `_walk` — rejected: complete, but late, possibly mid-stream, for coverage nobody needs.
- Drop bad attributes silently — rejected: hides a caller's bug.

## Design

- Refused in any name: empty, whitespace, `"`, `'`, `<`, `>`, `/`, `=`, control characters.
- A tag name must also start with an ASCII letter.
- `element(name)` and `void_element(name)` raise `ValueError` at once for a bad tag name.
- Their constructors raise `ValueError` for a bad attribute name, naming it and the tag:
  `invalid attribute name 'x href' on <a>`.
- `render` keeps escaping names, unchanged.
- Valid names keep passing: `data-x`, `aria-label`, `my-widget`, `xml:lang`.
- Docs: README Escaping and "Adding a tag" sections; the Escaping line in `CLAUDE.md`; remove the `BACKLOG.md` entry.
