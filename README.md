# Scythe

*spaCy, but cleaner: a Prodigy for les terminales.*

Scythe is a debate card cutter that doubles as a span-labeling tool. Plain git keeps every save, and GitHub provides the rest:

- **GitHub Pages** serves the app, a static site published from this public repo.
- **Git is the record.** Each card is `cards/<n>.md` and each source is `sources/<n>.md`.
  - Every label, link or edit is a commit, made through a tiny passthrough on Fly (`server/`).
  - A save is pinned to the file version you opened. If someone else committed first, GitHub refuses it like a non-fast-forward push, and the app shows the divergence: *rebase mine onto theirs*, *keep theirs*, or *force mine*.
- **Issues are the view.** On every push, `scythe.yml` runs spaCy and rewrites each card's issue: rendered card, labels, token offsets, entities, and the card as a sub-issue of its source. You get lists, search, backlinks and discussion on GitHub. The worker never commits.
- **Articles by link.** `fetch.yml` opens the page in headless Chromium, strips it with Readability to clean HTML and text, and commits `sources/<n>.md` (plus `.html`).
- **No LLMs anywhere.** The NLP is spaCy (`en_core_web_sm`) and nothing else.
- **The local API is optional.** Run it for the Postgres search index, spaCy exports and spancat training.

```
Pages app ──PUT {content, sha}──▶ Fly passthrough ──▶ git: cards/<n>.md   (409 = diverged)
                                                          │ push
                                                          ▼
                                        scythe.yml (spaCy) ──▶ issue #n (view, search, backlinks)
```

### Sign in

On the Pages site, click **sign in**. It opens GitHub's pre-filled token page: a fine-grained token named `scythe` with Contents and Issues read & write and a 30-day expiry. Choose your repo under *Repository access* (GitHub can't pre-fill that field), generate the token, and paste it into Scythe. Only that browser keeps it. Reading the site needs no token at all.

### Setup (once, when you're ready to publish)

1. Push this repo to GitHub as a **public** repository.
2. Set **Settings → Pages → Source** to **GitHub Actions**. `pages.yml` deploys the site at `https://<owner>.github.io/<repo>/`, and the app detects the repo from that URL.
3. Nothing else: `scythe.yml` runs on issue events with the built-in `GITHUB_TOKEN`. To process and snapshot existing issues, run it manually (`workflow_dispatch`).

### More than one repo

Any public repo can hold cards: copy `.github/workflows/` and `.github/fetcher/` into it, enable Pages or not, and pick it under **settings → Repository** in the app. The passthrough takes the repo from the request (`/repos/<owner>/<repo>/cards`) and writes as whoever's token it carries, so GitHub decides who can write where. Set `SCYTHE_REPOS=owner/a,owner/b` on the server to limit it to specific repos.

### Local development

Everything runs against the real GitHub API; there is no offline mode. `make web` (Vite) defaults to the passthrough on `localhost:8081` (`make server`) and the local API on `localhost:8000`. The Pages build has no local API unless a user adds one in settings.

## Run it

Requires Docker, [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
make install
make db      # Postgres 16 + pgvector on localhost:5544 (also creates scythe_test)
make api     # migrations + FastAPI on :8000 (optional: index, exports, training)
make server  # the passthrough on :8081, committing to real GitHub
make web     # Vite on :5173
make test    # pytest + tsc + eslint
```

### Optional: GitHub App sign-in for the local API

The local API also accepts the same fine-grained token the browser uses. Its older GitHub App OAuth flow still works if you prefer it: create a GitHub App (Settings → Developer settings → GitHub Apps) with these settings:

- **Callback URL:** `http://localhost:8000/api/auth/callback`, i.e. `{SCYTHE_API_URL}/api/auth/callback`
- **Expire user authorization tokens:** on
- **Repository permissions:** Issues read & write, Contents read & write, Metadata read
- **Where it can be installed:** only on this account

Install the App on the repo that will hold your cards, then add its credentials to `.env`:

```
SCYTHE_GITHUB_CLIENT_ID=...
SCYTHE_GITHUB_CLIENT_SECRET=...
SCYTHE_GITHUB_APP_SLUG=your-app-name
```

The tests run against an in-process fake GitHub (`SCYTHE_GITHUB_FAKE=1`, set by `backend/tests/conftest.py`); nothing else uses it.

### How a card is stored

| Scythe | GitHub |
| --- | --- |
| Card | An issue. The title is the tag, and the body holds the cite and text (`<ins>` for underline, `<mark>` for highlight, `**` for emphasis), followed by `Answers #12`-style link lines. |
| Card data | A hidden `<!-- scythe:v1 {...} -->` block: the verbatim text, spans (character offsets, plus token offsets once the Action has run), links, topic, and a `processed` stamp. |
| Source | An issue labelled `scythe:source`. Its verbatim text sits between `<!-- scythe:text -->` markers, with overflow in `scythe:part N` comments. Cards are attached as its sub-issues. |
| Topic, file, block, approval | The labels `topic:<slug>`, `file:…`, `block:…` and `approved`. |
| Custom topics, label set | Issues labelled `scythe:topic` and `scythe:config`. |
| Archive | The issue is closed as not planned; its snapshot keeps `"state": "closed"`. |
| History | `archive/**.md`. The front matter is JSON with one span or link per line, so `git log -p` shows each label change. |

The format lives in `backend/scythe/issue_doc.py` and is mirrored in `frontend/src/lib/doc.ts`; the two renderers produce identical output. The worker is `backend/scythe/action.py`, which needs only the standard library and spaCy.

### Topics

Every card is filed under a debate topic. When you create a card without one, Scythe asks you to choose one and remembers it for the next card. `backend/scythe/data/nsda_topics.json` holds 542 past NSDA national topics (Policy, LD, PF, Big Questions), parsed from speechanddebate.org/topics by `python -m scythe.topics_nsda topics.html`. They're re-seeded at startup, and you can add your own topics alongside them.

## How it fits together

| Area | Where |
| --- | --- |
| spaCy core: shared pipeline, token storage, `char_span(expand)`-equivalent snapping | `backend/scythe/nlp.py` |
| DocBin / Doc JSON / Prodigy import and export (span groups, ents, `user_data`) | `backend/scythe/spacy_io.py` |
| Canonical card Markdown ("Scythe MD"), used for the MD view, print preview and chunkers | `backend/scythe/markdown.py` |
| Reader mode: sanitize, locate pasted passages, default cites | `backend/scythe/reader.py` |
| Knowledge graph schema and relation vocabulary | `backend/scythe/graph_models.py` |
| Graph operations: upserts, chunk trees, traversal CTEs | `backend/scythe/graph.py` |
| Background enrichment (NER, graph indexing, chunk summaries) | `backend/scythe/jobs.py`, `enrich.py` |
| Spancat training and suggestions | `backend/scythe/train.py`, `suggest.py` |
| GitHub App auth, issue format, two-way sync | `backend/scythe/auth.py`, `issues.py`, `gh_sync.py`, `github.py` |
| Topics (seed, required on every card) | `backend/scythe/topics.py`, `topics_nsda.py` |
| The single card renderer (text-first, underline-only) | `frontend/src/components/CardView.tsx` |

**Cutting.** In the reader, open a link, or paste text or page HTML (for paywalled articles, add the link, authors and publication yourself). Then select a passage, or paste a copied passage to locate it. The cut card is an exact substring of `Source.full_text`, and an `excerpt_of` edge records its character offsets. The card shows up immediately after tokenizing. A background job then runs NER, links entities and chunks, and summarizes the source.

**Labeling.** Select text in the editor; the selection snaps to tokens. Press `1`–`5` (or a custom label's hotkey) to apply a label. Click a span to select it, `⌫` removes it, and `Enter` accepts a model suggestion. Labels belong to a `spans_key`, so custom ML labels can live in their own span groups.

**Training.** Run `make train` (or use the Data page) to fit a `spancat` model on gold spans (`manual` and `import`). Then click **Suggest** on a card. Accepted suggestions become gold, which closes the active-learning loop.

**Graph relations.** The graph has three families of relations:
- **Structural:** `part_of`, `excerpt_of`, `derived_from`
- **Provenance:** `authored_by`, `published_in`, `cites`, `quotes`
- **Semantic:** `mentions`, `supports`, `contradicts`, `answers`, `elaborates`, `same_claim`, `related`

Edges carry optional character anchors on both ends. Agentic chunkers write nested chunk trees with `PUT /api/sources/{id}/chunks`, which takes `{strategy, chunks: [{start_char, end_char, title, summary, propositions, children}]}`.
