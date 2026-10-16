/** Test-side GitHub and passthrough calls, as the token owner. Formats come from the app's own doc.ts. */
import nsda from '../backend/scythe/data/nsda_topics.json' with { type: 'json' }
import { cardFile, parseCardFile, parseMeta, parseSourceFile, sourceFile, type CardFile, type CardMeta, type SourceHead, type TopicRef } from '../frontend/src/lib/doc'
import { REPO } from './env'

const TOKEN = process.env.SCYTHE_TEST_TOKEN!
const SERVER = 'http://localhost:8082'
export const TOPICS = nsda as TopicRef[]
export const topic = (slug: string) => {
  const t = TOPICS.find((x) => x.slug === slug)
  if (!t) throw new Error(`no NSDA topic ${slug}`)
  return { slug: t.slug, event: t.event, season: t.season, period: t.period, resolution: t.resolution }
}
export const DEFAULT_TOPIC = 'cx-2025-26-exploration-development-arctic'

const headers = { Authorization: `Bearer ${TOKEN}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const url = path.startsWith('http') ? path : `https://api.github.com${path.replace('{repo}', REPO)}`
  const res = await fetch(url, { method, headers: { ...headers, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${await res.text()}`)
  return (res.status === 204 ? undefined : res.json()) as T
}

async function server<T = any>(method: string, path: string, body: unknown): Promise<T> {
  const res = await fetch(`${SERVER}/repos/${REPO}${path}`, { method, headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`passthrough ${method} ${path}: ${res.status} ${await res.text()}`)
  return res.json() as T
}

export async function readFile(path: string): Promise<{ text: string; sha: string } | null> {
  const res = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, { headers })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`)
  const data = await res.json()
  return { text: Buffer.from(data.content, 'base64').toString('utf8'), sha: data.sha }
}

export async function card(n: number): Promise<CardFile & { sha: string }> {
  const f = await readFile(`cards/${n}.md`)
  if (!f) throw new Error(`cards/${n}.md is missing`)
  return { ...parseCardFile(f.text), sha: f.sha }
}

export async function source(n: number): Promise<{ head: SourceHead; text: string }> {
  const f = await readFile(`sources/${n}.md`)
  if (!f) throw new Error(`sources/${n}.md is missing`)
  const [head, text] = parseSourceFile(f.text)
  return { head, text }
}

export async function commits(path: string): Promise<{ message: string; author: string }[]> {
  const list = await api<any[]>('GET', `/repos/{repo}/commits?path=${encodeURIComponent(path)}&per_page=20`)
  return list.map((c) => ({ message: c.commit.message.split('\n')[0], author: c.author?.login ?? c.commit.author.name }))
}

export async function issue(n: number) {
  const i = await api('GET', `/repos/{repo}/issues/${n}`)
  return { ...i, labelNames: i.labels.map((l: { name: string }) => l.name) as string[], meta: parseMeta<CardMeta & { processed?: { file_sha?: string } }>(i.body) }
}

export async function createSource(head: Partial<SourceHead> & { title: string }, text: string): Promise<number> {
  const h: SourceHead = { issue: null, url: null, publisher: '', published: null, authors: [], cite: '', fetched: null, ...head }
  return (await server<{ number: number }>('POST', '/sources', { title: h.title, content: sourceFile(h, text) })).number
}

export async function createCard(c: { title: string; text: string; source?: number | null; topic?: string; cite?: string }): Promise<number> {
  const t = topic(c.topic ?? DEFAULT_TOPIC)
  const record: CardFile = { issue: null, title: c.title, topic: t, file: null, block: null, approved: false, cite: c.cite ?? '',
    url: '', source: c.source ?? null, links: [], spans: [], text: c.text }
  return (await server<{ number: number }>('POST', '/cards', { title: c.title, labels: ['scythe:card', `topic:${t.slug}`], content: cardFile(record) })).number
}

const quote = (t: string) => `"${t.length > 40 ? t.slice(0, 40) + '…' : t}"`

/** Commit a change to cards/<n>.md the way the app does (read, change, PUT pinned to the sha). */
export async function changeCard(n: number, message: string, fn: (f: CardFile) => CardFile) {
  const { sha, ...f } = await card(n)
  const next = fn(f as CardFile)
  return server('PUT', `/cards/${n}`, { content: cardFile(next), sha, message: `${message} (#${n})` })
}

export const addSpan = (n: number, label: string, phrase: string) => changeCard(n, `${label}: ${quote(phrase)}`, (f) => {
  const a = f.text.indexOf(phrase)
  if (a < 0) throw new Error(`"${phrase}" is not in card ${n}`)
  const style = label
  f.spans.push({ label, key: 'sc', style, start_char: a, end_char: a + phrase.length, src: 'manual' })
  f.spans.sort((x, y) => x.start_char - y.start_char || y.end_char - x.end_char || x.label.localeCompare(y.label))
  return f
})

export const spanText = (f: { text: string }, s: { start_char: number; end_char: number }) => f.text.slice(s.start_char, s.end_char)
