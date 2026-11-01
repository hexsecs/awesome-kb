# Themes for composed OpenShelf sites

A theme is the whole front-end of a composed site, and nothing else.
`tools/build_site.py` owns the data work — loading KBs, pinning
imports, resolving links, searching — and hands the theme *content and
context*. A theme never touches markdown, link resolution, or KB
files, and a KB never knows which theme renders it. Theme choice
belongs to the site build (`--theme`, a workflow input), never to
`kb.yaml`.

## What the builder emits before any theme runs

- `bundle.json` — the composition as data: per KB (id, title,
  description, source, commit, visibility) and per page (slug, path,
  kind, title, summary, category, status, dates, url, related,
  kb_links, **fragment**).
- `fragments/<route>.html` — each page's body as an HTML fragment,
  markdown converted and every link already resolved to composed
  routes. This fragment is the `content` a theme wraps.
- `search-index.json` + `search.js` — full-text search across the
  whole composition; themes opt in via the hooks below.

Another renderer can skip the bundled themes entirely and build
against `bundle.json` + fragments alone. That is the contract; the
themes here are two views of it.

## Theme layout

```
themes/<name>/
  theme.yaml          name, version, author, description
  templates/page.html the one Jinja2 template (autoescaping on;
                      `content` is passed pre-rendered, use |safe)
  assets/             copied verbatim to <out>/assets/
```

Select with `build_site.py --theme <name>` (looked up in `themes/`)
or `--theme <path-to-theme-dir>`.

## Template context

| Variable | Meaning |
|---|---|
| `title` | Page title (browser tab). |
| `page_title` | Title for an in-page H1 — set on entity/concept pages only; other pages carry their own headings in `content`. |
| `site_title` | The host KB's title. |
| `home_href` | Relative href to the composed site's home. |
| `nav` | `[{label, href}]` — Home plus each composed KB's home. |
| `root_rel` | Relative path from this page to the site root (`./`, `../`, …). Prefix root-level files with it (`assets/…`, `search.js`). |
| `provenance` | `{kb_id, commit, commit_short}` on imported pages, else `None`. |
| `card` | Entity/concept pages: `{summary, chips: [{text, cls}], resource_url}`; else `None`. `cls` is a ready class attribute value (e.g. `chip status-active`). |
| `content` | The page's fragment HTML (links resolved). Render with `{{ content \| safe }}`. |
| `composed` | Host home only: `[{title, description, pages, commit_short, href}]` for each imported KB. |
| `related` | `[{slug, href}]` — `href` is `None` when the slug doesn't resolve in this composition. |
| `footer` | Pre-joined build line (`host@sha · import@sha`). |

## Required hooks for search

To keep site search working, a template must include:

- an element with class `searchbox` containing
  `<input id="q" type="search">` and `<ul id="results"></ul>`;
- before `</body>`: `<script>window.SEARCH_BASE="{{ root_rel }}";</script>`
  followed by `<script src="{{ root_rel }}search.js"></script>`.

Style `#q` / `#results` (`.meta`, `.snip`) in the theme's CSS as it
pleases. A theme that omits the hooks simply has no search box.
