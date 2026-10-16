# Features

Eighteen Gherkin features describe Scythe from a debater's side: cards and the words in them first, then what Scythe reads in the language, then sources, then organizing and team work. They are the spec the app is built and tested against.

## Two registers

- **The steps are technical.** They name what really happens:
  - spaCy tokens and `char_span(alignment_mode="expand")`
  - span labels and offsets
  - `cards/<n>.md` front matter and the blob sha a save is pinned to
  - the 409 and `theirs`
  - issue labels such as `scythe:fetch-failed`, and NSDA topic slugs
  An engineer can test against every line.
- **The screens speak debate.** Any text a debater sees, quoted in a `see` / `sees` step, must be plain debate language. `npm run voice` (in `e2e/`) fails if a quoted on-screen string uses repo, commit, issue, spaCy, sha, API, server, rebase, main, markdown, token or entities.

| Today on screen | Production copy |
| --- | --- |
| repository / repo | the team's evidence (on GitHub) |
| commit / save | saved, with "who changed what" in the card's history |
| issue #n | card 12, source 4 |
| spaCy processing / up to date | checking words / words checked |
| entities (PERSON, ORG…) | names, organizations, places, dates |
| condensed / "read" mode | read-aloud |
| md mode | plain text |
| diverged | your partner saved this card first |
| rebase / keep theirs / force | add my change to theirs / keep theirs / keep mine |
| fine-grained token | a GitHub sign-in key |

## Status tags

Each scenario carries exactly one status tag. An outline can tag its Examples tables separately.

| Tag | Meaning | In the test run |
| --- | --- | --- |
| `@built` | Works today, as written. | Must pass. |
| `@partly` | The behavior exists only in part: wrong copy, a known bug, or only on the local API. A `# today:` comment says what happens now. | Must fail. |
| `@missing` | Not built. | Must fail. |

`@partly` and `@missing` scenarios still run, driving the debate-language screen they describe, and are marked as expected failures. When one starts passing, the run reports it as "unexpectedly passed": retag it `@built`.

Other tags:
- `@signed-in`: the scenario needs a signed-in debater.
- `@two-debaters`: two browsers on the same card.
- `@slow`: waits on the GitHub Actions (the spaCy worker, the article fetcher) or on GitHub search, usually 1–5 minutes.

## Where things stand

Regenerate this table with `node e2e/gaps.mjs`.

| Feature | Built | Partly | Missing |
| --- | ---: | ---: | ---: |
| `01_cutting_a_card.feature` | 3 | 1 | 2 |
| `02_marking_up_words.feature` | 5 | 2 | 1 |
| `03_tag_and_cite.feature` | 5 | 2 | 1 |
| `04_reading_a_card.feature` | 3 | 1 | 1 |
| `05_signing_in_and_teams.feature` | 6 | 2 | 1 |
| `06_scythe_reads_the_card.feature` | 2 | 3 | 0 |
| `07_names_places_and_dates.feature` | 1 | 1 | 2 |
| `08_suggested_highlights.feature` | 0 | 2 | 3 |
| `09_opening_an_article_by_link.feature` | 1 | 2 | 2 |
| `10_pasting_an_article.feature` | 2 | 2 | 1 |
| `11_finding_a_copied_passage.feature` | 2 | 1 | 1 |
| `12_the_source_shelf.feature` | 3 | 1 | 1 |
| `13_choosing_the_resolution.feature` | 5 | 3 | 0 |
| `14_files_blocks_and_approval.feature` | 3 | 2 | 1 |
| `15_answering_and_linking_cards.feature` | 3 | 3 | 1 |
| `16_card_history_and_removing.feature` | 1 | 2 | 2 |
| `17_two_debaters_one_card.feature` | 4 | 2 | 0 |
| `18_searching_printing_and_copying.feature` | 3 | 3 | 0 |
| **All 18** | **52** | **35** | **20** |

## Running them

The tests run in a real browser against real GitHub, using the public test repo [joegr/scythe-test](https://github.com/joegr/scythe-test). That repo has Scythe's worker and fetcher Actions and nothing else.

```bash
make e2e
```

```bash
make e2e-all
```

`make e2e` runs everything but `@slow`. `make e2e-all` adds `@slow`. Both use `gh auth token` for the test repo.

The harness is in `e2e/`, built on playwright-bdd. It starts its own app on :5174 and passthrough on :8082, so it never touches the dev servers on :5173 and :8081. Steps are grouped by area:
- `cards.ts`, `sources.ts`, `organize.ts`, `debaters.ts`: steps for scenarios that work today.
- `gaps.ts`: steps for the `@partly` and `@missing` scenarios.

The Pages workflow runs every feature, slow ones included, and deploys the site only when they all come out as expected. It needs the `SCYTHE_TEST_TOKEN` secret: a fine-grained token with Contents and Issues write on `joegr/scythe-test` only.
