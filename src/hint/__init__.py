# ruff: noqa: A001
# The tag constructors are named for their HTML tags; `input`, `map`, and `object`
# deliberately shadow builtins. Every use site is qualified (`hint.input`), so
# nothing is actually shadowed — the one file-scoped suppression (see the design spec).
"""hint — build HTML as a tree of description values and render it once.

hint is not templating. HTML is built in code as a tree of plain description
values (:class:`Element`, :class:`RawHtml`, :class:`str`) by a constructor per tag,
and a single :func:`render` step converts the tree to a string at the edge.

A constructor is exported for every element in the current HTML Living Standard. Add
a new one in a single line — ``figure: Node = element("figure")`` — with no class and
no registry. Obsolete elements and the SVG/MathML vocabularies are out of scope.
"""

from hint._core import (
    Element as Element,
    ElementOrStr as ElementOrStr,
    Hole as Hole,
    Node as Node,
    RawHtml as RawHtml,
    VoidNode as VoidNode,
    element as element,
    hole as hole,
    render as render,
    render_html as render_html,
    style as style,
    void_element as _void_element,
)
from hint._markdown import markdown as markdown

# The HTML Living Standard element vocabulary, one constructor per tag, by category.
# `<style>` is intentionally absent — use the `style` re-export above, which emits its
# content verbatim. `<del>` is exported as `del_` because `del` is a Python keyword.

# Main root
html: Node = element("html")

# Document metadata
base: VoidNode = _void_element("base")
head: Node = element("head")
link: VoidNode = _void_element("link")
meta: VoidNode = _void_element("meta")
title: Node = element("title")

# Sectioning root
body: Node = element("body")

# Content sectioning
address: Node = element("address")
article: Node = element("article")
aside: Node = element("aside")
footer: Node = element("footer")
header: Node = element("header")
h1: Node = element("h1")
h2: Node = element("h2")
h3: Node = element("h3")
h4: Node = element("h4")
h5: Node = element("h5")
h6: Node = element("h6")
hgroup: Node = element("hgroup")
main: Node = element("main")
nav: Node = element("nav")
section: Node = element("section")
search: Node = element("search")

# Text content
blockquote: Node = element("blockquote")
dd: Node = element("dd")
div: Node = element("div")
dl: Node = element("dl")
dt: Node = element("dt")
figcaption: Node = element("figcaption")
figure: Node = element("figure")
hr: VoidNode = _void_element("hr")
li: Node = element("li")
menu: Node = element("menu")
ol: Node = element("ol")
p: Node = element("p")
pre: Node = element("pre")
ul: Node = element("ul")

# Inline text semantics
a: Node = element("a")
abbr: Node = element("abbr")
b: Node = element("b")
bdi: Node = element("bdi")
bdo: Node = element("bdo")
br: VoidNode = _void_element("br")
cite: Node = element("cite")
code: Node = element("code")
data: Node = element("data")
dfn: Node = element("dfn")
em: Node = element("em")
i: Node = element("i")
kbd: Node = element("kbd")
mark: Node = element("mark")
q: Node = element("q")
rp: Node = element("rp")
rt: Node = element("rt")
ruby: Node = element("ruby")
s: Node = element("s")
samp: Node = element("samp")
small: Node = element("small")
span: Node = element("span")
strong: Node = element("strong")
sub: Node = element("sub")
sup: Node = element("sup")
time: Node = element("time")
u: Node = element("u")
var: Node = element("var")
wbr: VoidNode = _void_element("wbr")

# Image and multimedia
area: VoidNode = _void_element("area")
audio: Node = element("audio")
img: VoidNode = _void_element("img")
map: Node = element("map")
track: VoidNode = _void_element("track")
video: Node = element("video")

# Embedded content
embed: VoidNode = _void_element("embed")
iframe: Node = element("iframe")
object: Node = element("object")
picture: Node = element("picture")
source: VoidNode = _void_element("source")

# Scripting
canvas: Node = element("canvas")
noscript: Node = element("noscript")
script: Node = element("script")

# Demarcating edits
del_: Node = element("del")
ins: Node = element("ins")

# Table content
caption: Node = element("caption")
col: VoidNode = _void_element("col")
colgroup: Node = element("colgroup")
table: Node = element("table")
tbody: Node = element("tbody")
td: Node = element("td")
tfoot: Node = element("tfoot")
th: Node = element("th")
thead: Node = element("thead")
tr: Node = element("tr")

# Forms
button: Node = element("button")
datalist: Node = element("datalist")
fieldset: Node = element("fieldset")
form: Node = element("form")
input: VoidNode = _void_element("input")
label: Node = element("label")
legend: Node = element("legend")
meter: Node = element("meter")
optgroup: Node = element("optgroup")
option: Node = element("option")
output: Node = element("output")
progress: Node = element("progress")
select: Node = element("select")
textarea: Node = element("textarea")

# Interactive elements
details: Node = element("details")
dialog: Node = element("dialog")
summary: Node = element("summary")

# Web components
slot: Node = element("slot")
template: Node = element("template")
