/**
 * Cards and sources are files in git; every save is a commit through the passthrough, pinned to the
 * file version it started from (a stale save comes back as a divergence). Issues are the mirror the
 * spaCy Action keeps current, used for lists, search and backlinks.
 */
import nsdaTopics from '../../../backend/scythe/data/nsda_topics.json'
import {
  DEFAULT_LABELS, KIND_LABELS, cardFile, cardLabels, parseCardFile, parseMeta, parseSourceFile, snapChars, sourceFile,
  type CardFile, type CardMeta, type LabelDef, type LinkRec, type SourceHead, type SpanRec, type TopicRef,
} from './doc'
import { Diverged, gh, pages, readFile, repoPath, server, writeFile, type Theirs } from './gh'

export interface Issue {
  id: number; number: number; title: string; body: string | null; state: 'open' | 'closed'
  labels: { name: string }[]; html_url: string; updated_at: string; comments: number; user?: { login: string }
}

export interface CardDoc {
  number: number; title: string; state: 'open' | 'closed'; url: string; updated_at: string; author: string
  /** Spans from the file, plus spaCy entities once the Action has processed this exact version. */
  meta: CardMeta
  topic: string | null; file: string | null; block: string | null; approved: boolean
  /** The card's file as last read from git, and its blob sha (what the next save builds on). */
  record: CardFile | null; sha: string | null
  processed: boolean
}

export interface SourceDoc { number: number; title: string; url: string; head: SourceHead; text: string }
export interface Topic extends TopicRef { origin: 'nsda' | 'custom' }

const labelNames = (i: Issue) => i.labels.map((l) => (typeof l === 'string' ? l : l.name))
const prefixed = (labels: string[], p: string) => labels.find((l) => l.startsWith(p + ':'))?.slice(p.length + 1) ?? null
const metaOf = (f: CardFile, ents: SpanRec[] = []): CardMeta => ({
  kind: 'card', text: f.text, cite: f.cite, url: f.url, source: f.source, topic: f.topic, spans: [...f.spans, ...ents], links: f.links,
})

/** From the issue mirror only (lists, search). */
export function fromIssue(i: Issue): CardDoc | null {
  const labels = labelNames(i)
  const meta = parseMeta<CardMeta & { processed?: { file_sha?: string } }>(i.body)
  if (!labels.includes(KIND_LABELS.card) || !meta || meta.kind !== 'card') return null
  meta.spans ??= []
  meta.links ??= []
  return {
    number: i.number, title: i.title, state: i.state, url: i.html_url, updated_at: i.updated_at, author: i.user?.login ?? '',
    meta, topic: prefixed(labels, 'topic'), file: prefixed(labels, 'file'), block: prefixed(labels, 'block'),
    approved: labels.includes('approved'), record: null, sha: null, processed: !!meta.processed,
  }
}

const fromIssues = (issues: Issue[]) => issues.map(fromIssue).filter((c): c is CardDoc => c !== null)

// ---------------------------------------------------------------- reading

export async function listCards({ labels = [] as string[], state = 'open', limit = 100 } = {}): Promise<CardDoc[]> {
  const q = new URLSearchParams({ labels: [KIND_LABELS.card, ...labels].join(','), state, sort: 'updated', direction: 'desc', per_page: String(Math.min(limit, 100)) })
  return fromIssues((await gh<Issue[]>('GET', repoPath(`/issues?${q}`))).data)
}

const quoteLabel = (l: string) => `label:"${l.replace(/"/g, '')}"`

export async function searchCards(text: string, labels: string[] = [], state: 'open' | 'closed' = 'open'): Promise<CardDoc[]> {
  const q = [`repo:${repoPath().slice(7)}`, 'is:issue', `is:${state}`, quoteLabel(KIND_LABELS.card), ...labels.map(quoteLabel), text.trim()].filter(Boolean).join(' ')
  const { data } = await gh<{ items: Issue[] }>('GET', `/search/issues?${new URLSearchParams({ q, per_page: '50' })}`)
  return fromIssues(data.items)
}

/** The card as recorded in git (truth), joined with its issue (state, link, spaCy results). */
export async function getCard(n: number, ref?: string): Promise<CardDoc> {
  const [file, issue] = await Promise.all([readFile(`cards/${n}.md`, ref), gh<Issue>('GET', repoPath(`/issues/${n}`)).then((r) => r.data)])
  if (!file) throw new Error(`cards/${n}.md isn't in the repo`)
  const record = parseCardFile(file.text)
  const mirror = parseMeta<CardMeta & { processed?: { file_sha?: string } }>(issue.body)
  const processed = mirror?.processed?.file_sha === file.sha
  const labels = labelNames(issue)
  return {
    number: n, title: record.title, state: issue.state, url: issue.html_url, updated_at: issue.updated_at, author: issue.user?.login ?? '',
    meta: metaOf(record, processed ? (mirror?.spans ?? []).filter((s) => s.key === 'ents') : []),
    topic: record.topic?.slug ?? prefixed(labels, 'topic'), file: record.file, block: record.block, approved: record.approved,
    record, sha: file.sha, processed,
  }
}

// ---------------------------------------------------------------- saving (git)

/** A change to a card, described for the commit message and re-appliable on someone else's version. */
export interface Op { message: string; apply: (f: CardFile) => CardFile }

export interface Divergence { op: Op; mine: CardFile; theirs: CardFile; theirsSha: string; commit: Theirs['commit'] }

/** Commit `op` on top of the version this card was loaded at. Resolves with the new card, or throws
 *  `DivergedSave` when main moved: their version, and mine, are in the error for the user to settle. */
export async function save(card: CardDoc, op: Op): Promise<CardDoc> {
  if (!card.record || !card.sha) throw new Error('load the card from git before editing')
  const next = op.apply(structuredClone(card.record))
  try {
    await server('PUT', `/cards/${card.number}`, { content: cardFile(next), sha: card.sha, message: `${op.message} (#${card.number})` })
  } catch (e) {
    if (e instanceof Diverged) {
      throw new DivergedSave({ op, mine: next, theirs: parseCardFile(e.theirs.content), theirsSha: e.theirs.sha, commit: e.theirs.commit })
    }
    throw e
  }
  return getCard(card.number)
}

export class DivergedSave extends Error {
  d: Divergence
  constructor(d: Divergence) { super('diverged'); this.d = d }
}

/** git rebase: replay my change on their version. May diverge again if main moved once more. */
export async function rebase(n: number, d: Divergence): Promise<CardDoc> {
  const base = await getCard(n)
  return save(base, d.op)
}

/** git push --force-with-lease: my version replaces theirs (still refused if main moved again). */
export async function force(n: number, d: Divergence): Promise<CardDoc> {
  try {
    await server('PUT', `/cards/${n}`, { content: cardFile(d.mine), sha: d.theirsSha, message: `${d.op.message}, replacing ${d.commit.sha?.slice(0, 7) ?? 'their save'} (#${n})` })
  } catch (e) {
    if (e instanceof Diverged) throw new DivergedSave({ ...d, theirs: parseCardFile(e.theirs.content), theirsSha: e.theirs.sha, commit: e.theirs.commit })
    throw e
  }
  return getCard(n)
}

export const spanKey = (s: Pick<SpanRec, 'key' | 'label' | 'start_char' | 'end_char'>) => `${s.key}|${s.label}|${s.start_char}|${s.end_char}`
const quote = (t: string) => `"${t.length > 40 ? t.slice(0, 40) + '…' : t}"`

export const ops = {
  addSpan: (text: string, label: LabelDef, start: number, end: number): Op => {
    const snapped = snapChars(text, start, end)
    if (!snapped) throw new Error('That selection has no words in it.')
    const [a, b] = snapped
    return {
      message: `${label.name}: ${quote(text.slice(a, b))}`,
      apply: (f) => {
        if (!f.spans.some((s) => s.label === label.name && s.key === label.key && s.start_char === a && s.end_char === b)) {
          f.spans.push({ label: label.name, key: label.key, style: label.style, start_char: a, end_char: b, src: 'manual' })
          f.spans.sort((x, y) => x.start_char - y.start_char || y.end_char - x.end_char || x.label.localeCompare(y.label))
        }
        return f
      },
    }
  },
  removeSpan: (text: string, span: SpanRec): Op => ({
    message: `remove ${span.label}: ${quote(text.slice(span.start_char, span.end_char))}`,
    // Match by label and characters (not token offsets): those are what both versions share.
    apply: (f) => ({ ...f, spans: f.spans.filter((s) => !(s.label === span.label && s.key === span.key && s.start_char === span.start_char && s.end_char === span.end_char)) }),
  }),
  set: <K extends 'title' | 'cite'>(field: K, value: string): Op => ({ message: `${field}: ${quote(value)}`, apply: (f) => ({ ...f, [field]: value }) }),
  topic: (t: TopicRef): Op => ({ message: `topic: ${t.slug}`, apply: (f) => ({ ...f, topic: t }) }),
  place: (file: string | null, block: string | null): Op => ({ message: file ? `file: ${file} / ${block ?? ''}` : 'unfile', apply: (f) => ({ ...f, file, block }) }),
  approve: (on: boolean): Op => ({ message: on ? 'approve' : 'unapprove', apply: (f) => ({ ...f, approved: on }) }),
  link: (rel: string, to: number): Op => ({ message: `${rel.replace('_', ' ')} #${to}`, apply: (f) => ({ ...f, links: [...f.links.filter((l) => !(l.rel === rel && l.to === to)), { rel, to }] }) }),
  unlink: (l: LinkRec): Op => ({ message: `unlink ${l.rel.replace('_', ' ')} #${l.to}`, apply: (f) => ({ ...f, links: f.links.filter((x) => !(x.rel === l.rel && x.to === l.to)) }) }),
}

export interface NewCard { text: string; title: string; cite: string; url?: string; source?: number | null; topic: Topic; file?: string | null; block?: string | null }

export async function createCard(c: NewCard): Promise<number> {
  const topic: TopicRef = { slug: c.topic.slug, event: c.topic.event, season: c.topic.season, period: c.topic.period, resolution: c.topic.resolution }
  const record: CardFile = { issue: null, title: c.title || c.text.slice(0, 80), topic, file: c.file ?? null, block: c.block ?? null, approved: false,
    cite: c.cite, url: c.url ?? '', source: c.source ?? null, links: [], spans: [], text: c.text }
  const labels = cardLabels({ topic: topic.slug, file: record.file, block: record.block, approved: false })
  return (await server<{ number: number }>('POST', '/cards', { title: record.title, labels, content: cardFile(record) })).number
}

/** Archive = delete the file (the Action closes the issue); history keeps every version. */
export async function archiveCard(card: CardDoc) {
  if (!card.sha) throw new Error('load the card first')
  await gh('DELETE', repoPath(`/contents/cards/${card.number}.md`), { message: `archive: ${card.title} (#${card.number})`, sha: card.sha })
}

/** Cards whose links point at #n (GitHub records each `Answers #n` line as a cross-reference). */
export async function backlinks(n: number): Promise<{ rel: string; card: CardDoc }[]> {
  const events = await pages<{ event: string; source?: { issue?: Issue } }>(repoPath(`/issues/${n}/timeline`), {}, 3)
  const out: { rel: string; card: CardDoc }[] = []
  const seen = new Set<number>()
  for (const e of events) {
    const issue = e.event === 'cross-referenced' ? e.source?.issue : undefined
    if (!issue || seen.has(issue.number)) continue
    seen.add(issue.number)
    const card = fromIssue(issue)
    for (const l of card?.meta.links ?? []) if (l.to === n) out.push({ rel: l.rel, card: card! })
  }
  return out
}

// ---------------------------------------------------------------- sources

export interface NewSource { text: string; title: string; url?: string | null; publisher?: string; published?: string | null; authors?: string[]; cite?: string }

export async function createSource(s: NewSource): Promise<number> {
  const head: SourceHead = { issue: null, title: s.title, url: s.url || null, publisher: s.publisher ?? '', published: s.published ?? null,
    authors: s.authors ?? [], cite: s.cite ?? '', fetched: null }
  return (await server<{ number: number }>('POST', '/sources', { title: s.title || s.url || 'Untitled source', content: sourceFile(head, s.text) })).number
}

/** Ask the fetcher Action to read a link; resolves when sources/<n>.md lands (or the fetch fails). */
export async function fetchSource(url: string, onWait?: (seconds: number) => void): Promise<number> {
  const { number } = await server<{ number: number }>('POST', '/sources', { title: '', url })
  const started = Date.now()
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000))
    onWait?.(Math.round((Date.now() - started) / 1000))
    if (await readFile(`sources/${number}.md`)) return number
    const { data } = await gh<Issue>('GET', repoPath(`/issues/${number}`))
    if (labelNames(data).includes('scythe:fetch-failed')) throw new Error(`GitHub couldn't read that page (see issue #${number}). Paste the text instead.`)
    if (Date.now() - started > 5 * 60 * 1000) throw new Error(`Still fetching after 5 minutes; check issue #${number}.`)
  }
}

export async function getSource(n: number): Promise<SourceDoc> {
  const [file, issue] = await Promise.all([readFile(`sources/${n}.md`), gh<Issue>('GET', repoPath(`/issues/${n}`)).then((r) => r.data)])
  if (!file) throw new Error(`sources/${n}.md isn't in the repo yet`)
  const [head, text] = parseSourceFile(file.text)
  return { number: n, title: head.title || issue.title, url: issue.html_url, head, text }
}

export async function listSources(): Promise<{ number: number; title: string }[]> {
  const { data } = await gh<Issue[]>('GET', repoPath(`/issues?labels=${KIND_LABELS.source}&state=open&sort=updated&per_page=30`))
  return data.map((i) => ({ number: i.number, title: i.title }))
}

export async function cardsFromSource(n: number): Promise<CardDoc[]> {
  try { return fromIssues((await gh<Issue[]>('GET', repoPath(`/issues/${n}/sub_issues`))).data) } catch { return [] }
}

const LOOSE: Record<string, string> = { "'": "['‘’]", '‘': "['‘’]", '’': "['‘’]", '"': '["“”]', '“': '["“”]', '”': '["“”]', '-': '[-‐-―]', '–': '[-‐-―]', '—': '[-‐-―]' }

/** Find a copied passage in source text: exact, then whitespace- and quote-insensitive. */
export function locate(full: string, passage: string): [number, number] | null {
  const p = passage.trim()
  if (!p) return null
  const i = full.indexOf(p)
  if (i >= 0) return [i, i + p.length]
  const pattern = p.split(/\s+/).filter(Boolean).map((w) => [...w].map((ch) => LOOSE[ch] ?? ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('')).join('\\s+')
  const m = new RegExp(pattern).exec(full)
  return m ? [m.index, m.index + m[0].length] : null
}

export function defaultCite(s: { title: string; authors: string[]; publisher: string; published: string | null; url: string | null }): string {
  const year = s.published?.slice(2, 4)
  const date = s.published ? (() => { const [y, m, d] = s.published!.split('-').map(Number); return `${m}-${d}-${y}` })() : ''
  const head = s.authors.length ? `${s.authors[0].split(/\s+/).pop()}${year ? ` ${year}` : ''}` : year ? `${(s.publisher || 'Unknown').split(',')[0]} ${year}` : ''
  return [head, s.authors.join(', '), s.title ? `"${s.title}"` : '', s.publisher, date, s.url ?? ''].filter(Boolean).join(', ')
}

// ---------------------------------------------------------------- shared settings: scythe.json

export interface Settings { labels: LabelDef[]; topics: TopicRef[] }

export async function readSettings(): Promise<{ settings: Settings; sha: string | null }> {
  const f = await readFile('scythe.json')
  const s = f ? (JSON.parse(f.text) as Partial<Settings>) : {}
  return { settings: { labels: s.labels?.length ? s.labels : DEFAULT_LABELS, topics: s.topics ?? [] }, sha: f?.sha ?? null }
}

/** Read-modify-commit scythe.json; on a race, re-read and re-apply once more. */
export async function updateSettings(message: string, fn: (s: Settings) => Settings) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const { settings, sha } = await readSettings()
    try {
      return await writeFile('scythe.json', JSON.stringify(fn(settings), null, 2) + '\n', message, sha ?? undefined)
    } catch (e) {
      if (!(e instanceof Error && 'status' in e && (e as { status: number }).status === 409)) throw e
    }
  }
  throw new Error('scythe.json kept changing; try again')
}

export const NSDA_TOPICS: Topic[] = (nsdaTopics as TopicRef[]).map((t) => ({ ...t, origin: 'nsda' as const }))

export async function customTopics(): Promise<Topic[]> {
  return (await readSettings()).settings.topics.map((t) => ({ ...t, origin: 'custom' as const }))
}

export async function createTopic(resolution: string, season = ''): Promise<Topic> {
  const res = /^resolved/i.test(resolution.trim()) ? resolution.trim() : `Resolved: ${resolution.trim()}`
  const words = res.toLowerCase().replace(/^resolved:?/, '').match(/[a-z0-9]+/g) ?? []
  let slug = 'custom'
  for (const w of words.filter((x) => !['the', 'a', 'an', 'of', 'should'].includes(x))) { if (slug.length + w.length + 1 > 38) break; slug += `-${w}` }
  slug += `-${Date.now().toString(36).slice(-5)}`
  const topic: TopicRef = { slug, event: 'custom', season, period: '', resolution: res }
  await updateSettings(`topic: ${slug}`, (s) => ({ ...s, topics: [...s.topics, topic] }))
  return { ...topic, origin: 'custom' }
}

export async function repoLabels(): Promise<string[]> {
  return (await pages<{ name: string }>(repoPath('/labels'), {}, 5)).map((l) => l.name)
}
