# Log

Append-only activity log for the Awesome KB registry.

## [2026-10-31] init | Awesome KB registry

Created the registry as an OpenShelf KB and project: `kb.yaml`, maintainer
schema in `AGENTS.md`, an L1 `index.md`, and the machine-readable connection
list in `.openshelf/kbs.yaml`.

## [2026-10-31] register | Automotive Security (Awesome KB)

Registered `awesome-kb-automotive-security` as the first conforming KB.
Verified its manifest and `openshelf lint` result at commit
`5e411ecabd8880916ce6949552e2a1da0cdc4ff8`; created `wiki/automotive-security.md`
and added it to the registry index and README.

## [2026-11-01] update | Automotive Security standalone site live

The automotive KB now renders its own GitHub Pages site in addition
to being imported into the composed site: the KB repo gained a
standalone render workflow (its PR #32, merged 2026-11-01) that
builds the KB from its own main with the registry builder and theme
(registry pinned by exact commit) and deploys to
https://hexsecs.github.io/awesome-kb-automotive-security/.
Verified live 2026-11-01: home page and entity/concept routes serve
HTTP 200 at the site root. The registry page records the URL; the
composed build is unchanged.

## [2026-11-01] register | Security (Awesome KB)

Registered hexsecs/awesome-kb-security (OpenShelf ID
`awesome-kb-security`, profile `awesome`, CC0-1.0) at commit fe7a99f,
verified with `openshelf lint` (no errors or warnings) and a passing
standalone builder run. The repo was scaffolded the same day to the
network's pattern: conforming kb.yaml, AGENTS.md maintainer schema,
standalone GitHub Pages render (registry builder pinned by exact
commit), site live at https://hexsecs.github.io/awesome-kb-security/.
At registration the KB holds no entity pages: its canon source list has
not been designated yet — that designation is the owner's decision and
the KB's next step. Added to .openshelf/kbs.yaml; sync regenerated the
lock (pinning all three registered KBs) and context; registry page,
index, and README catalogue updated; the README's Planned section is
retired, both planned KBs now being registered.

## [2026-11-01] register | AI and LLM Agents (Awesome KB)

Registered hexsecs/awesome-kb-ai-llm-agents (OpenShelf ID
`awesome-kb-ai-llm-agents`, profile `awesome`, CC0-1.0) at commit
fc63280, verified with `openshelf lint` (no errors or warnings) and a
passing standalone builder run. Scaffolded the same day to the same
pattern as the Security KB; standalone site at
https://hexsecs.github.io/awesome-kb-ai-llm-agents/. Like Security, it
holds no entity pages at registration pending the owner's canon-list
designation.

## [2026-11-01] register | Embedded Security (Awesome KB)

Registered hexsecs/awesome-kb-embedded-security (OpenShelf ID
`awesome-kb-embedded-security`, profile `awesome`, CC0-1.0) at commit
c1c94da, verified with `openshelf lint` (no errors or warnings). The KB
was created the same day at the owner's direction, with the owner's
long-maintained list hexsecs/awesome-embedded-security designated as
canon; its ingester is adapted from the automotive KB's for the list's
two-level category grammar and marker tokens. Initial ingest: generated
stub pages for all 250 list entries across 35 categories. Standalone
site live at https://hexsecs.github.io/awesome-kb-embedded-security/.
Added to .openshelf/kbs.yaml; sync regenerated the lock and context;
registry page, index, and README catalogue updated.

## [2026-11-02] update | All four registered KBs adopt OpenShelf spec 1.4

Each registered KB minted its KB `uid` and page `uid`s (SPEC §4.1
adoption path), taught its ingester the uid lifecycle where it has one,
and restamped kb.yaml to `openshelf: "1.4"` (automotive PR #90, main
57a4533; embedded PR #1, main d447c9a; security 537a36a; ai-llm-agents
bbdce9e — each verified `openshelf lint --strict` clean at those
commits). Registry pages refreshed (version, verified commit, dates)
and the lock advanced by `openshelf sync`; the hourly pin sweep keeps
them current from here.

## [2026-11-06] update | Automotive Security KB pin

Re-verified `awesome-kb-automotive-security` at commit
`b51e60bacef34cb85a58a4f602d61e906d3ae323` (ingest of list@a25e33d, 237
entries, including the Petran DEF CON 31 talk and the Savage VehicleSec
2026 keynote) and moved the registry lock pin to it via `openshelf sync`.
The sync also moved the embedded-security pin to its current main head
`f278a15f1311f91bf5454bf35319fcdd4449555c`; both pins verified against
GitHub main heads. Registry page `last_checked`/`updated` and verified
commit refreshed.

## [2026-11-14] update | Automotive Security KB pin

Re-verified `awesome-kb-automotive-security` at commit
`b99182f255c25a8176913204ed0fb12f6aa43ce5` (ingest of list@46f5cc7, 249
entries, including OCPPuzz and BLE Theft Auto) and moved the registry
lock pin to it via `openshelf sync`. The sync also moved the
embedded-security pin to its current main head
`984931d2dc076fa0c0f55d786624efdaf83fc7fa`; both pins verified against
GitHub main heads. Registry page `last_checked`/`updated` and verified
commit refreshed.
