# Name validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `element` and `void_element` raise `ValueError` for a tag or attribute name that could break out of the tag.

**Architecture:** Two private predicates in `hint/_core.py`, called by `element(name)` / `void_element(name)` on the tag
name and by their returned constructors on each attribute name.

**Tech Stack:** Python 3.14, `unicodedata` for control characters, pytest.

**Spec:** `docs/superpowers/specs/2026-11-27-name-validation-design.md`

## Global Constraints

- Refused in any name: empty, whitespace (`str.isspace`), `"`, `'`, `<`, `>`, `/`, `=`, control characters (Unicode
  category `Cc`).
- A tag name must also start with an ASCII letter.
- Tag-name errors raise when `element(name)` / `void_element(name)` is called; attribute-name errors when the
  constructor is called.
- Messages: `invalid tag name 'div onclick=x'`, `invalid attribute name 'x href' on <a>`.
- `render` unchanged. No change to `Element`.
- Commits: `fix(core): …`; `make check` before push.

## Review Focus

- Non-ASCII whitespace or C1 controls in a name (`"x y"`, `"x\x85y"`, `"x\x7fy"`) — refused.
- Non-ASCII but otherwise valid attribute name (`"données"`) — accepted; HTML allows it.
- Upper-case tag name (`"DIV"`) — accepted.
- Every built-in tag in `hint/__init__.py` — still imports (covered by the whole suite importing `hint`).
- `markdown`'s fallback and `style()` build `Element` directly — unaffected, still render.

---

### Task 1: Refuse bad names in `element` and `void_element`

**Files:**

- Modify: `src/hint/_core.py` (`element`, `void_element`, two private predicates)
- Test: `src/hint/element_test.py`
- Modify: `README.md` (Escaping, Adding a tag), `CLAUDE.md` (Escaping line), `BACKLOG.md` (remove the attribute-name
  entry)

**Interfaces:**

- Produces: `element(name: str) -> Node` and `void_element(name: str) -> VoidNode`, unchanged signatures, now raising
  `ValueError`.

- [ ] **Step 1: Write the failing tests** in `src/hint/element_test.py` (`void_element` from `hint._core`, the test's
      one internal import):

```python
BAD = ["", "x y", "x\ty", "x y", 'x"y', "x'y", "x<y", "x>y", "x/y", "x=y", "x\x00y", "x\x7fy", "x\x85y"]

@pytest.mark.parametrize("name", [*BAD, "1x", "-x", "écrit"])
def test_element_refuses_a_bad_tag_name(name: str) -> None:
    with pytest.raises(ValueError, match="invalid tag name"):
        element(name)
# same for void_element

@pytest.mark.parametrize("name", BAD)
def test_element_refuses_a_bad_attribute_name(name: str) -> None:
    with pytest.raises(ValueError, match=r"invalid attribute name .* on <a>"):
        element("a")([], {name: "v"})
# same for void_element("img")({name: "v"}) with "on <img>"

@pytest.mark.parametrize("name", ["data-x", "aria-label", "xml:lang", "données", "onclick"])
def test_element_accepts_a_sensible_attribute_name(name: str) -> None: ...  # renders name="v"

@pytest.mark.parametrize("name", ["div", "DIV", "my-widget", "h1"])
def test_element_accepts_a_sensible_tag_name(name: str) -> None: ...
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest src/hint/element_test.py -q` Expected: the refuse tests FAIL with `DID NOT RAISE`; accept tests
pass.

- [ ] **Step 3: Implement** in `src/hint/_core.py`: `_is_sensible_name(name: str) -> bool` and
      `_is_sensible_tag_name(name: str) -> bool`; `element`/`void_element` check the tag name before returning
      `construct`, `construct` checks each attr key.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest src/hint/element_test.py -q` → all pass. Break each predicate clause in turn and confirm a test
fails.

- [ ] **Step 5: Docs** — README Escaping: names are checked at construction and a bad one raises; Adding a tag: a bad
      name fails at once. `CLAUDE.md` Escaping line likewise. Remove the `BACKLOG.md` entry.

- [ ] **Step 6: Gates** — `make check` → all pass.

- [ ] **Step 7: Commit** `fix(core): refuse tag and attribute names that break out of the tag` (stage, check
      `git diff --cached` after reflow, commit separately).
