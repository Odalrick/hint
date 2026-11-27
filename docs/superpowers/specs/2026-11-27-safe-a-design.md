# `safe_a` — design

## Intent

`a` escapes its attributes but takes any address, so a `javascript:` URL from stored data renders as a working link.
Pages that link to a recorded address — one possibly written by a malicious actor — must each remember a scheme check.
`safe_a` makes forgetting impossible wherever it is used. Prompted by the game library in `notes-jubilant-guacamole`,
which needed the same check in its route and again in its page.

## Goals, non-goals

- Goal: an anchor that only ever links to a web page, whatever the stored value.
- Non-goal: a configurable allow-list, `mailto:`, relative links, or checking `img src` / `form action`. Stored
  addresses from untrusted writers have no legitimate relative form.
- Anti-goal: a stored bad value taking the page down.

## Approaches

- **Fixed check, degrade to text (chosen).** One rule, no options; a refused address renders the children without a
  link.
- Raise `ValueError` on a refused address — rejected: one bad row in stored data fails the whole page, and every caller
  must catch it, which is the remembering this was meant to remove.
- Configurable schemes (`safe_a(schemes=...)`) — rejected: a keyword argument breaks the calling convention, and nobody
  needs another scheme yet.

## Design

- `safe_a([children], {attrs})`, same shape as `a`. Lives in `hint/_helper.py`, re-exported flat from `hint`.
- Parse `attrs["href"]` with `urlsplit`. Allowed only if the scheme is `http` or `https` and the netloc is non-empty.
- **The stored value is never emitted.** An allowed address renders as `urlunsplit(urlsplit(href))` — the
  parsed-and-rebuilt form, so what reaches the page is what the check judged (lowercased scheme, leading control
  characters and embedded tabs/newlines stripped).
- Allowed → `a(children, {**attrs, "href": rebuilt})`.
- Refused, or no `href` → `span(children, attrs without "href")`: the text and other attributes stay, nothing is
  clickable.

## Tests (first, watched red)

Refused: `javascript:`, mixed case `JaVaScRiPt:`, a leading control character, a tab inside the scheme, `data:`, `ftp:`,
`https:` with no host, a relative path, `//host`, missing `href`. Allowed: plain `http` and `https`; the rendered `href`
is the rebuilt form, not the raw input (e.g. `HTTPS://example.com` renders `https://example.com`). Other attributes
survive a refusal.

## Left to the builder

README section placement and wording; removing the `BACKLOG.md` entry.
