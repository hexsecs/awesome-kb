#!/usr/bin/env python3
"""Build the composed static site for this OpenShelf KB and its imports.

Build-time federation (decided 2026-10-31): this KB renders itself, and
every KB pinned in .openshelf/kbs.lock is composed into the same static
site under kb/<kb-id>/, at exactly the locked commit. kb:// links
resolve to the local composed route when the target KB is imported,
and fall back to that KB's repository otherwise.

Data and front-end are separate. This script owns the data work —
loading KBs, pinning imports, converting markdown, resolving links —
and emits it theme-free: bundle.json (the composition as data),
fragments/<route>.html (each page's body, links resolved), and a
full-text search-index.json. A theme (themes/<name>/, selected with
--theme) supplies all presentation: one Jinja2 template plus assets,
fed the context documented in themes/README.md. A KB never knows which
theme renders it, and theme choice never goes in kb.yaml.

Reads:  kb.yaml, the pages dir + index from kb.yaml's layout,
        .openshelf/kbs.yaml / kbs.lock, .openshelf/cache/<kb-id>/
        (cloned and checked out at the pin when missing),
        themes/<name>/ (theme.yaml, templates/, assets/).
Writes: the output dir only (default _site/) — index.html per route,
        fragments, search-index.json, bundle.json, assets/, .nojekyll.
        Nothing is written into any KB's content files.

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

Requires: pyyaml, markdown, jinja2.
Usage: build_site.py [--out _site] [--theme default|<name>|<path>]
"""

import argparse
import json
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

import jinja2
import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".openshelf" / "cache"


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


def fragment_rel(route):
    """Output-relative path of a route's theme-free content fragment."""
    stem = route.rstrip("/") or "index"
    return f"fragments/{stem}.html"


def rel_href(from_route, to_route):
    start = from_route.strip("/") or "."
    target = to_route.strip("/") or "."
    rel = posixpath.relpath(target, start)
    return "./" if rel == "." else rel + "/"


def load_theme(name_or_path):
    cand = Path(name_or_path)
    theme_dir = cand if cand.is_dir() else ROOT / "themes" / name_or_path
    if not (theme_dir / "theme.yaml").exists():
        sys.exit(f"theme not found: {theme_dir} "
                 f"(no theme.yaml) — see themes/README.md")
    meta = yaml.safe_load((theme_dir / "theme.yaml").read_text()) or {}
    templates = theme_dir / (meta.get("templates") or "templates")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates)), autoescape=True,
        trim_blocks=True, lstrip_blocks=True)
    return {"dir": theme_dir, "meta": meta,
            "assets": theme_dir / (meta.get("assets") or "assets"),
            "template": env.get_template("page.html")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--theme", default="default",
                    help="theme name under themes/, or a theme dir path")
    args = ap.parse_args()
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    theme = load_theme(args.theme)

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

    foot_bits = [f'{host_id}@{((host_commit or "")[:7])}']
    for other in kbs[1:]:
        foot_bits.append(f'{other["id"]}@{(other["commit"] or "")[:7]}')
    footer = " · ".join(foot_bits)

    def write_fragment(page):
        rel = fragment_rel(page["route"])
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = render_body(page)
        dest.write_text(content)
        return rel, content

    def render_page(page, title, content, card=None, composed=(),
                    related=()):
        kb = by_id[page["kb"]]
        root_rel = rel_href(page["route"], "")
        nav = [{"label": "Home", "href": root_rel}]
        for other in kbs[1:]:
            nav.append({"label": other["title"],
                        "href": rel_href(page["route"],
                                          f"kb/{other['id']}/")})
        provenance = None
        if kb["id"] != host_id:
            provenance = {"kb_id": kb["id"], "commit": kb["commit"],
                          "commit_short": (kb["commit"] or "")[:7]}
        ctx = {"title": title,
               "page_title": title if page["kind"] in ("entity", "concept")
               else None,
               "site_title": by_id[host_id]["title"],
               "home_href": root_rel, "nav": nav, "root_rel": root_rel,
               "provenance": provenance, "card": card, "content": content,
               "composed": list(composed), "related": list(related),
               "footer": footer}
        dest = out / page["route"] / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(theme["template"].render(**ctx))

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
        # KB home: fragment is the body; the host home also gets the
        # composed-KB blocks, which the theme renders from context.
        home = kb["home"]
        home_frag, home_content = write_fragment(home)
        search_index.append({
            "t": kb["title"], "s": kb["description"], "c": "",
            "kb": kb["id"], "p": home["route"],
            "x": plain_text(home["body"])})
        composed = []
        if kb["id"] == host_id:
            for other in kbs[1:]:
                composed.append({
                    "title": other["title"],
                    "description": other["description"],
                    "pages": sum(1 for p in other["pages"]
                                 if p["kind"] == "entity"),
                    "commit_short": (other["commit"] or "")[:7],
                    "href": rel_href(home["route"], f"kb/{other['id']}/")})
        render_page(home, kb["title"], home_content, composed=composed)
        kb_bundle["pages"].append({"slug": "", "path": home["route"],
                                   "kind": "home", "title": kb["title"],
                                   "fragment": home_frag})
        for page in kb["pages"]:
            meta = page["meta"]
            title = str(meta.get("title") or page["stem"])
            frag, content = write_fragment(page)
            if page["kind"] in ("entity", "concept"):
                chips = []
                for label, key in (("category", "category"),
                                   ("status", "status")):
                    if meta.get(key):
                        cls = f"chip status-{meta[key]}" \
                            if key == "status" else "chip"
                        chips.append({"text": f"{label}: {meta[key]}",
                                      "cls": cls})
                for key in ("last_checked", "updated", "depth"):
                    if meta.get(key):
                        chips.append({"text": f"{key}: {meta[key]}",
                                      "cls": "chip"})
                card = {"summary": str(meta.get("summary") or ""),
                        "chips": chips,
                        "resource_url": str(meta["url"])
                        if meta.get("url") else None}
                related = []
                for slug in [str(r) for r in (meta.get("related") or [])]:
                    target = None
                    for cand in (slug, f"concepts/{slug}"):
                        target = slug_routes.get((kb["id"], cand))
                        if target:
                            break
                    related.append({
                        "slug": slug,
                        "href": rel_href(page["route"], target)
                        if target else None})
                render_page(page, title, content, card=card,
                            related=related)
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
                    "last_checked": str(meta.get("last_checked") or ""),
                    "depth": str(meta.get("depth") or ""),
                    "url": str(meta.get("url") or ""),
                    "related": [str(r)
                                for r in (meta.get("related") or [])],
                    "kb_links": kb_links, "fragment": frag})
            else:
                render_page(page, title, content)
                kb_bundle["pages"].append({"slug": page["stem"],
                                           "path": page["route"],
                                           "kind": page["kind"],
                                           "title": title,
                                           "fragment": frag})
        bundle["kbs"].append(kb_bundle)

    if theme["assets"].is_dir():
        shutil.copytree(theme["assets"], out / "assets",
                        dirs_exist_ok=True)
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
    pages = sum(1 for kb in bundle["kbs"] for _ in kb["pages"])
    print(f"built {pages} pages, {len(search_index)} searchable, "
          f"{len(kbs)} KBs, theme {theme['meta'].get('name', '?')} "
          f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
