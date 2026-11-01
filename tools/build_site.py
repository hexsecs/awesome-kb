#!/usr/bin/env python3
"""Build the composed static site for this OpenShelf KB and its imports.

Build-time federation (decided 2026-10-31): this KB renders itself, and
every KB pinned in .openshelf/kbs.lock is composed into the same static
site under kb/<kb-id>/, at exactly the locked commit. kb:// links
resolve to the local composed route when the target KB is imported,
and fall back to that KB's repository otherwise.

Reads:  kb.yaml, the pages dir + index from kb.yaml's layout,
        .openshelf/kbs.yaml / kbs.lock, .openshelf/cache/<kb-id>/
        (cloned and checked out at the pin when missing).
Writes: the output dir only (default _site/) — index.html per route,
        search-index.json, bundle.json, .nojekyll. Nothing is written
        into any KB's content files.

Sources may be public or private, on any host: github:<owner>/<repo>,
gitlab:<group>/<repo>, a full https/ssh git URL, or a local path.
Fetching is plain `git clone`, so authentication is whatever the
environment provides (SSH agent, credential helper, CI tokens) — this
script never handles credentials itself. A KB may declare
`visibility: private` in its kb.yaml; the bundle then marks the whole
composition private, because a composed site is only as private as its
most private member. Publish private compositions only to
access-controlled hosting — GitHub Pages URLs are public even for
private repos outside Enterprise.

Requires: pyyaml, markdown.  Usage: build_site.py [--out _site]
"""

import argparse
import html
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".openshelf" / "cache"

CSS = """
:root { --ink:#1a1d21; --muted:#5c6470; --line:#e2e6ea; --accent:#0b5cad;
        --chip:#eef2f5; --amber:#8a6100; --amberbg:#fdf3d7; }
* { box-sizing:border-box; }
body { margin:0; color:var(--ink); font:16px/1.6 system-ui,-apple-system,
       "Segoe UI",Roboto,sans-serif; background:#fff; }
header.site { border-bottom:1px solid var(--line); }
header.site .wrap { display:flex; gap:1rem; align-items:baseline;
  flex-wrap:wrap; padding:.7rem 1rem; }
header.site a { color:var(--ink); text-decoration:none; font-weight:600; }
header.site nav a { color:var(--accent); font-weight:400; margin-right:.9rem; }
main { max-width:880px; margin:0 auto; padding:1.2rem 1rem 3rem; }
footer { max-width:880px; margin:0 auto; padding:1rem; color:var(--muted);
  font-size:.85rem; border-top:1px solid var(--line); }
h1 { font-size:1.7rem; line-height:1.25; margin:.4rem 0 .6rem; }
a { color:var(--accent); }
.card { border:1px solid var(--line); border-radius:10px; padding:1rem 1.1rem;
  margin:0 0 1.2rem; background:#fbfcfd; }
.card p.summary { margin:.2rem 0 .7rem; font-size:1.05rem; }
.chips { display:flex; gap:.45rem; flex-wrap:wrap; margin:.4rem 0 .2rem; }
.chip { background:var(--chip); border-radius:999px; padding:.12rem .6rem;
  font-size:.8rem; color:var(--muted); }
.chip.status-active { color:#146c2e; } .chip.status-archived { color:#666; }
.chip.status-unknown { color:var(--amber); }
.prov { background:var(--amberbg); color:var(--amber); border-radius:8px;
  padding:.45rem .8rem; font-size:.87rem; margin:0 0 1rem; }
.prov code { font-size:.85em; }
a.resource { display:inline-block; margin-top:.5rem; font-weight:600; }
.related { border-top:1px solid var(--line); margin-top:2rem; padding-top:.6rem; }
.searchbox { position:relative; flex:1 1 240px; max-width:430px; }
#q { width:100%; padding:.45rem .7rem; font-size:.95rem; border:1px solid
  var(--line); border-radius:8px; }
#results { position:absolute; top:calc(100% + 4px); left:0; right:0;
  background:#fff; border:1px solid var(--line); border-radius:8px;
  list-style:none; padding:0; margin:0; z-index:20; max-height:62vh;
  overflow:auto; box-shadow:0 8px 30px rgba(20,25,30,.13); }
#results:empty { display:none; }
#results li { padding:.5rem .7rem; border-bottom:1px solid var(--line); }
#results li:last-child { border-bottom:none; }
#results .meta { color:var(--muted); font-size:.8rem; }
#results .snip { color:var(--muted); font-size:.85rem; }
.kbblock { border:1px solid var(--line); border-radius:10px;
  padding:1rem 1.1rem; margin:0 0 1rem; }
.kbblock h3 { margin:.1rem 0 .3rem; }
.kbblock p { margin:.2rem 0; color:var(--muted); }
code { background:var(--chip); padding:.05rem .3rem; border-radius:4px; }
pre code { display:block; padding:.8rem; overflow-x:auto; }
"""


def plain_text(md_text):
    """Rough plain-text extraction of a markdown body, for the search
    index. Search covers full page text, not just frontmatter."""
    t = re.sub(r"```.*?```", " ", md_text, flags=re.S)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[#>*_`~]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:6000]


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[4:end]) or {}
    return meta, text[end + 5:]


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


def clone_url(source):
    """Resolve an OpenShelf source to something `git clone` accepts."""
    if source.startswith("github:"):
        return f"https://github.com/{source.split(':', 1)[1]}.git"
    if source.startswith("gitlab:"):
        return f"https://gitlab.com/{source.split(':', 1)[1]}.git"
    return source  # full URL, ssh remote, or local path — used as-is


def web_url(source):
    """Best-effort browsable URL for a source, for kb:// fallbacks."""
    if source.startswith(("github:", "gitlab:")):
        host = "github.com" if source.startswith("github:") else "gitlab.com"
        return f"https://{host}/{source.split(':', 1)[1]}"
    if source.startswith(("https://", "http://")):
        return source[:-4] if source.endswith(".git") else source
    return None


def load_kb(root, kb_id, commit=None, source=None):
    manifest = yaml.safe_load((root / "kb.yaml").read_text())
    layout = manifest.get("layout") or {}
    pages_dir = root / (layout.get("pages") or "wiki")
    index_rel = layout.get("index") or "index.md"
    kb = {"id": kb_id or manifest["id"], "root": root,
          "title": manifest.get("title") or manifest["id"],
          "description": (manifest.get("description") or "").strip(),
          "version": manifest.get("version"),
          "visibility": manifest.get("visibility") or "public",
          "commit": commit, "source": source,
          "pages_dir": pages_dir, "index_rel": index_rel, "pages": []}
    for path in sorted(pages_dir.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        meta, body = parse_frontmatter(path.read_text())
        stem = path.stem
        if meta:
            kind = "concept" if meta.get("type") == "concept" else "entity"
        elif stem.startswith("index-"):
            kind, meta = "subindex", {}
        else:
            kind = "page"
        kb["pages"].append({"kb": kb["id"], "rel": rel, "meta": meta,
                            "body": body, "kind": kind, "stem": stem,
                            "subdir": path.parent.relative_to(pages_dir)
                            .as_posix()})
    home_meta, home_body = parse_frontmatter((root / index_rel).read_text())
    kb["home"] = {"kb": kb["id"], "rel": index_rel, "meta": home_meta,
                  "body": home_body, "kind": "home", "stem": "index",
                  "subdir": "."}
    return kb


def route_for(kb, page, host_id):
    prefix = "" if kb["id"] == host_id else f"kb/{kb['id']}/"
    if page["kind"] == "home":
        return prefix
    if page["subdir"] not in (".", ""):
        return f"{prefix}{page['subdir']}/{page['stem']}/"
    return f"{prefix}{page['stem']}/"


def rel_href(from_route, to_route):
    start = from_route.strip("/") or "."
    target = to_route.strip("/") or "."
    rel = posixpath.relpath(target, start)
    return "./" if rel == "." else rel + "/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    host_manifest = yaml.safe_load((ROOT / "kb.yaml").read_text())
    host_id = host_manifest["id"]
    try:
        host_commit = git("rev-parse", "HEAD", cwd=ROOT)
    except Exception:
        host_commit = None

    lock = yaml.safe_load((ROOT / ".openshelf" / "kbs.lock").read_text())
    locked = (lock or {}).get("kbs") or {}

    kbs = [load_kb(ROOT, host_id, commit=host_commit)]
    for kb_id, info in locked.items():
        source = info["source"]
        commit = info["commit"]
        url = clone_url(source)
        if url.startswith(("https://", "http://", "git@", "ssh://")) \
                or ":" in source:
            kb_root = CACHE / kb_id
            if not (kb_root / "kb.yaml").exists():
                # Auth, if any, comes from the environment (SSH agent,
                # credential helper, CI token) — never from this script.
                git("clone", "--quiet", url, str(kb_root))
            head = git("rev-parse", "HEAD", cwd=kb_root)
            if head != commit:
                git("checkout", "--quiet", commit, cwd=kb_root)
        else:  # local path source: used in place, pin checked loosely
            kb_root = (ROOT / source).resolve()
            if (kb_root / ".git").exists():
                head = git("rev-parse", "HEAD", cwd=kb_root)
                if head != commit:
                    print(f"warning: local KB {kb_id} is at {head[:7]}, "
                          f"lock pins {commit[:7]}; using it as-is",
                          file=sys.stderr)
        kbs.append(load_kb(kb_root, kb_id, commit=commit, source=source))

    # Route map: (kb id, source rel path) -> route; slug lookup for kb://.
    routes = {}
    slug_routes = {}
    for kb in kbs:
        for page in [kb["home"], *kb["pages"]]:
            route = route_for(kb, page, host_id)
            page["route"] = route
            routes[(kb["id"], page["rel"])] = route
            if page["kind"] in ("entity", "concept"):
                sub = "" if page["subdir"] in (".", "") \
                    else page["subdir"] + "/"
                slug_routes[(kb["id"], sub + page["stem"])] = route
    by_id = {kb["id"]: kb for kb in kbs}
    repo_url = {kb_id: url for kb_id, info in locked.items()
                if (url := web_url(info["source"]))}

    def resolve_md(kb, page, href):
        path, _, anchor = href.partition("#")
        base_dirs = [posixpath.dirname(page["rel"]), "",
                     (kb["pages_dir"].relative_to(kb["root"]).as_posix())]
        for base in base_dirs:
            cand = posixpath.normpath(posixpath.join(base, path))
            if (kb["id"], cand) in routes:
                rel = rel_href(page["route"], routes[(kb["id"], cand)])
                return rel + (f"#{anchor}" if anchor else "")
        return None

    def rewrite(page, html_text):
        kb = by_id[page["kb"]]

        def sub(m):
            href = m.group(1)
            if href.startswith("kb://"):
                rest = href[5:]
                kb_id, _, slug = rest.partition("/")
                if (kb_id, slug) in slug_routes:
                    return f'href="{rel_href(page["route"], slug_routes[(kb_id, slug)])}"'
                if kb_id in repo_url:
                    return f'href="{repo_url[kb_id]}"'
                return f'href="{href}" data-kb-unresolved="1"'
            if href.endswith(".md") or ".md#" in href:
                resolved = resolve_md(kb, page, href)
                if resolved:
                    return f'href="{resolved}"'
            return m.group(0)

        return re.sub(r'href="([^"]+)"', sub, html_text)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])

    def render_body(page):
        md.reset()
        return rewrite(page, md.convert(page["body"]))

    def shell(page, title, inner):
        kb = by_id[page["kb"]]
        root_rel = rel_href(page["route"], "")
        nav = [("Home", rel_href(page["route"], ""))]
        for other in kbs[1:]:
            nav.append((other["title"],
                        rel_href(page["route"], f"kb/{other['id']}/")))
        nav_html = "".join(
            f'<a href="{href}">{html.escape(label)}</a>'
            for label, href in nav)
        prov = ""
        if kb["id"] != host_id:
            prov = (f'<div class="prov">From <strong>{html.escape(kb["id"])}'
                    f'</strong> @ <code>{(kb["commit"] or "")[:7]}</code>'
                    f' — composed at the commit pinned in '
                    f'<code>.openshelf/kbs.lock</code></div>')
        foot_bits = [f'{host_id}@{((host_commit or "")[:7])}']
        for other in kbs[1:]:
            foot_bits.append(f'{other["id"]}@{(other["commit"] or "")[:7]}')
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><header class="site"><div class="wrap">
<a href="{rel_href(page['route'], '')}">{html.escape(by_id[host_id]['title'])}</a>
<nav>{nav_html}</nav>
<div class="searchbox"><input id="q" type="search"
placeholder="Search all composed KBs…" autocomplete="off">
<ul id="results"></ul></div></div></header>
<main>{prov}{inner}</main>
<footer>Built from OpenShelf knowledge bases · {' · '.join(foot_bits)} ·
markdown is the source of truth; this site is a rendered view.</footer>
<script>window.SEARCH_BASE="{root_rel}";</script>
<script src="{root_rel}search.js"></script>
</body></html>"""

    def write_page(page, title, inner):
        dest = out / page["route"] / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(shell(page, title, inner))

    search_index = []
    bundle = {"host": {"id": host_id, "title": by_id[host_id]["title"],
                       "description": by_id[host_id]["description"],
                       "commit": host_commit},
              "kbs": []}

    for kb in kbs:
        kb_bundle = {"id": kb["id"], "title": kb["title"],
                     "description": kb["description"],
                     "source": kb["source"], "commit": kb["commit"],
                     "visibility": kb["visibility"],
                     "pages": []}
        # KB home
        home = kb["home"]
        inner = render_body(home)
        search_index.append({
            "t": kb["title"], "s": kb["description"], "c": "",
            "kb": kb["id"], "p": home["route"],
            "x": plain_text(home["body"])})
        if kb["id"] == host_id:
            blocks = []
            for other in kbs[1:]:
                count = sum(1 for p in other["pages"]
                            if p["kind"] == "entity")
                blocks.append(
                    f'<div class="kbblock"><h3><a href="'
                    f'{rel_href("", "kb/" + other["id"] + "/")}">'
                    f'{html.escape(other["title"])}</a></h3>'
                    f'<p>{html.escape(other["description"])}</p>'
                    f'<p>{count} pages · composed @ '
                    f'{(other["commit"] or "")[:7]}</p></div>')
            if blocks:
                inner += "<h2>Composed knowledge bases</h2>" + "".join(blocks)
            write_page(home, kb["title"], inner)
        else:
            write_page(home, kb["title"], inner)
        kb_bundle["pages"].append({"slug": "", "path": home["route"],
                                   "kind": "home", "title": kb["title"]})
        for page in kb["pages"]:
            meta = page["meta"]
            title = str(meta.get("title") or page["stem"])
            if page["kind"] in ("entity", "concept"):
                chips = []
                for label, key in (("category", "category"),
                                   ("status", "status")):
                    if meta.get(key):
                        cls = f' class="chip status-{meta[key]}"' \
                            if key == "status" else ' class="chip"'
                        chips.append(f'<span{cls}>{label}: '
                                     f'{html.escape(str(meta[key]))}</span>')
                for key in ("last_checked", "updated", "depth"):
                    if meta.get(key):
                        chips.append(f'<span class="chip">{key}: '
                                     f'{html.escape(str(meta[key]))}</span>')
                card = (f'<div class="card"><p class="summary">'
                        f'{html.escape(str(meta.get("summary") or ""))}</p>'
                        f'<div class="chips">{"".join(chips)}</div>')
                if meta.get("url"):
                    card += (f'<a class="resource" href="'
                             f'{html.escape(str(meta["url"]))}">'
                             f'Open the resource ↗</a>')
                card += "</div>"
                body_html = render_body(page)
                related = meta.get("related") or []
                rel_links = []
                for slug in related:
                    target = None
                    for cand in (slug, f"concepts/{slug}"):
                        target = slug_routes.get((kb["id"], cand))
                        if target:
                            break
                    if target:
                        rel_links.append(
                            f'<li><a href="{rel_href(page["route"], target)}">'
                            f'{html.escape(slug)}</a></li>')
                    else:
                        rel_links.append(f'<li>{html.escape(slug)}</li>')
                rel_html = ""
                if rel_links:
                    rel_html = ('<div class="related"><h2>Related</h2><ul>'
                                + "".join(rel_links) + "</ul></div>")
                write_page(page, title,
                           f"<h1>{html.escape(title)}</h1>" + card
                           + body_html + rel_html)
                search_index.append({
                    "t": title, "s": str(meta.get("summary") or ""),
                    "c": str(meta.get("category") or ""), "kb": kb["id"],
                    "p": page["route"], "x": plain_text(page["body"])})
                kb_links = sorted({m.group(1) for m in re.finditer(
                    r"\]\((kb://[^)]+)\)", page["body"])})
                kb_bundle["pages"].append({
                    "slug": page["stem"], "path": page["route"],
                    "kind": page["kind"], "title": title,
                    "summary": str(meta.get("summary") or ""),
                    "category": str(meta.get("category") or ""),
                    "status": str(meta.get("status") or ""),
                    "updated": str(meta.get("updated")
                                   or meta.get("last_checked") or ""),
                    "url": str(meta.get("url") or ""),
                    "related": [str(r) for r in related],
                    "kb_links": kb_links})
            else:
                write_page(page, title, render_body(page))
                kb_bundle["pages"].append({"slug": page["stem"],
                                           "path": page["route"],
                                           "kind": page["kind"],
                                           "title": title})
        bundle["kbs"].append(kb_bundle)

    (out / "search-index.json").write_text(json.dumps(search_index))
    (out / "search.js").write_text(
        "let IDX=[];const B=window.SEARCH_BASE||'';"
        "fetch(B+'search-index.json').then(r=>r.json())"
        ".then(d=>IDX=d).catch(()=>{});"
        "const q=document.getElementById('q'),"
        "res=document.getElementById('results');"
        "q.addEventListener('input',()=>{"
        "const words=q.value.toLowerCase().trim().split(/\\s+/)"
        ".filter(Boolean);res.innerHTML='';"
        "if(!words.length||words.join('').length<2)return;"
        "const scored=[];"
        "for(const e of IDX){const T=e.t.toLowerCase(),"
        "S=(e.s||'').toLowerCase(),C=(e.c||'').toLowerCase(),"
        "X=(e.x||'').toLowerCase();let sc=0,ok=true;"
        "for(const w of words){let s=0;"
        "if(T.includes(w))s=5;else if(S.includes(w))s=3;"
        "else if(C.includes(w))s=2;else if(X.includes(w))s=1;"
        "else{ok=false;break;}sc+=s;}"
        "if(ok)scored.push([sc,e]);}"
        "scored.sort((a,b)=>b[0]-a[0]);"
        "for(const pair of scored.slice(0,20)){const e=pair[1];"
        "const li=document.createElement('li');"
        "let snip=e.s||'';"
        "if(pair[0]<=words.length&&e.x){"
        "const i=e.x.toLowerCase().indexOf(words[0]);"
        "if(i>=0)snip='…'+e.x.slice(Math.max(0,i-60),i+120)+'…';}"
        "li.innerHTML='<a></a><div class=\"meta\"></div>"
        "<div class=\"snip\"></div>';"
        "const a=li.querySelector('a');a.href=B+e.p;"
        "a.textContent=e.t;"
        "li.querySelector('.meta').textContent=e.kb"
        "+(e.c?' · '+e.c:'');"
        "li.querySelector('.snip').textContent=snip;"
        "res.appendChild(li);}});"
        "document.addEventListener('click',ev=>{"
        "if(!ev.target.closest('.searchbox'))res.innerHTML='';});")
    # A composition is only as private as its most private member.
    bundle["contains_private"] = any(kb["visibility"] == "private"
                                     for kb in kbs)
    if bundle["contains_private"]:
        print("warning: this composition includes a private KB — publish "
              "it only to access-controlled hosting (GitHub Pages URLs "
              "are public even for private repos outside Enterprise).",
              file=sys.stderr)
    (out / "bundle.json").write_text(json.dumps(bundle, indent=1))
    (out / ".nojekyll").write_text("")
    n = sum(1 for _ in out.rglob("index.html"))
    print(f"built {n} pages, {len(search_index)} searchable, "
          f"{len(kbs)} KBs -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
