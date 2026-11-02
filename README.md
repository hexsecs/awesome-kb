# Awesome KB

**Lists are so 2025.** Awesome KB is a network of living knowledge bases
grown from awesome lists: humans keep curating the inventory, while bots and
humans together add the depth, links, freshness checks, and machine-readable
structure that a flat list cannot carry.

This repository is the network's **registry**. It is also an
[OpenShelf](https://github.com/hexsecs/openkb) knowledge base about the
member KBs, with a machine-readable connection list that agents can sync.

**Browse the rendered site: [hexsecs.github.io/awesome-kb](https://hexsecs.github.io/awesome-kb/)** — the composed, searchable reading view of every registered KB.

## Registered knowledge bases

A KB is listed here only after its `kb.yaml` has been checked and
`openshelf lint` passes with no errors at the registered commit.

### Security

- **[Automotive Security](wiki/automotive-security.md)** — Knowledge base
  for automotive security, ingested from the curated awesome list
  [hexsecs/awesome-automotive-security](https://github.com/hexsecs/awesome-automotive-security).
  [Repository](https://github.com/hexsecs/awesome-kb-automotive-security) ·
  OpenShelf ID: `awesome-kb-automotive-security` · Profile: `awesome`
- **[Security](wiki/security.md)** — Knowledge base for security: tools,
  research, and practice across offensive and defensive security.
  [Repository](https://github.com/hexsecs/awesome-kb-security) ·
  OpenShelf ID: `awesome-kb-security` · Profile: `awesome`

### Artificial Intelligence

- **[AI and LLM Agents](wiki/ai-llm-agents.md)** — Knowledge base for AI
  and LLM agents: frameworks, tools, protocols, evaluations, and research
  on autonomous and agentic systems.
  [Repository](https://github.com/hexsecs/awesome-kb-ai-llm-agents) ·
  OpenShelf ID: `awesome-kb-ai-llm-agents` · Profile: `awesome`

## The format

Awesome KB uses **OpenShelf**, an open standard for the LLM Wiki pattern:
a small `kb.yaml` contract, progressive context from a one-line description
(L0) through an index (L1) and pages (L2) to raw sources (L3), and
`kb://` links between knowledge bases.

The format, schemas, CLI, lint tool, and MCP server live in
[hexsecs/openkb](https://github.com/hexsecs/openkb). This registry does not
define a competing format.

## Connect the registered KBs

The OpenShelf connection list is [`.openshelf/kbs.yaml`](.openshelf/kbs.yaml).
From a checkout of this repository:

```sh
openshelf sync --project .
```

Sync fetches each registered KB, verifies that its manifest ID matches the
registry entry, pins the resolved commits in `.openshelf/kbs.lock`, and
regenerates [`.openshelf/context.md`](.openshelf/context.md) for agents.

## Register a knowledge base

A registered KB must have a root `kb.yaml`, a unique OpenShelf ID, an L0
title and description, and a clean `openshelf lint` run at the commit being
registered. The full maintainer procedure and the distinction between
registered and planned KBs are in [AGENTS.md](AGENTS.md).

## Repository layout

- `kb.yaml` — this registry's OpenShelf manifest.
- `index.md` — the registry's L1 index.
- `wiki/` — one registry page per registered KB.
- `.openshelf/kbs.yaml` — the machine-readable connection list.
- `.openshelf/context.md` — generated L0 context for connected KBs.
- `AGENTS.md` — maintainer rules for registration, updates, and retirement.
- `log.md` — append-only registry activity log.

## License

Registry content is declared as CC-BY-4.0 in `kb.yaml`. Member knowledge
bases carry their own licenses, recorded on their registry pages.
