/**
 * The issue format, mirrored from backend/scythe/issue_doc.py and markdown.py.
 * GitHub issues are the source of truth: a card issue's body is rendered Markdown for people plus a
 * hidden `<!-- scythe:v1 {...} -->` block holding the verbatim text, spans and links.
 */

export interface SpanRec {
  label: string; key: string; style: string; start_char: number; end_char: number; src: string
  start?: number; end?: number; score?: number
}
export interface LinkRec { rel: string; to: number }
export interface TopicRef { slug: string; event: string; season: string; period: string; resolution: string }
export interface CardMeta {
  kind: 'card'; text: string; cite: string; url: string; source: number | null; topic: TopicRef | null
  spans: SpanRec[]; links: LinkRec[]; processed?: { model: string; text_sha: string; tokens: number; sub_issue?: number }
}
export interface SourceMeta {
  kind: 'source'; url: string | null; title: string; publisher: string; published: string | null; authors: string[]
  cite: string; parts: number; length: number; text_sha: string
}
export interface TopicMeta extends TopicRef { kind: 'topic' }
export interface ConfigMeta { kind: 'config'; labels: LabelDef[] }
export interface LabelDef { name: string; key: string; style: string; hotkey: string | null }

export const KIND_LABELS = { card: 'scythe:card', source: 'scythe:source', topic: 'scythe:topic', config: 'scythe:config' } as const
export const DEFAULT_LABELS: LabelDef[] = [
  { name: 'underline', key: 'sc', style: 'underline', hotkey: '1' },
  { name: 'highlight', key: 'sc', style: 'highlight', hotkey: '2' },
  { name: 'emphasis', key: 'sc', style: 'emphasis', hotkey: '3' },
]
export const LINK_WORDS: Record<string, string> = {
  answers: 'Answers', supports: 'Supports', contradicts: 'Contradicts', elaborates: 'Elaborates',
  same_claim: 'Same claim as', quotes: 'Quotes', cites: 'Cites', derived_from: 'Derived from', related: 'Related to',
}
export const BODY_LIMIT = 65536
const PART_SIZE = 60000

const META_RE = /<!-- scythe:v1\n([\s\S]*?)\n-->/
const TEXT_RE = /<!-- scythe:text -->\n([\s\S]*?)\n<!-- \/scythe:text -->/
const PART_RE = /<!-- scythe:part (\d+) -->\n([\s\S]*?)\n<!-- \/scythe:part -->/g

export const normalize = (body: string | null | undefined) => (body ?? '').replace(/\r\n/g, '\n')

export function parseMeta<T = CardMeta>(body: string | null | undefined): T | null {
  const m = META_RE.exec(normalize(body))
  return m ? (JSON.parse(m[1]) as T) : null
}

export function metaBlock(meta: object): string {
  // Same escaping as Python: keeps the payload from ever closing the HTML comment.
  return '<!-- scythe:v1\n' + JSON.stringify(meta).replace(/</g, '\\u003c').replace(/>/g, '\\u003e') + '\n-->'
}

export async function textSha(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16)
}

// ---------------------------------------------------------------- Markdown (port of markdown.py)

const INLINE = /([\\`*_[\]<>=~|])/g
const URL_RE = /https?:\/\/[^\s<>\])]+/g
const BLOCK_START = /^(#+|[+-]|\d+\.)(?=\s)/gm
const ORDER = ['underline', 'highlight', 'emphasis'] as const
type Flavor = 'scythe' | 'github'
const MARKERS: Record<Flavor, [Record<string, string>, Record<string, string>]> = {
  scythe: [{ underline: '<u>', highlight: '==', emphasis: '**' }, { underline: '</u>', highlight: '==', emphasis: '**' }],
  github: [{ underline: '<ins>', highlight: '<mark>', emphasis: '**' }, { underline: '</ins>', highlight: '</mark>', emphasis: '**' }],
}

export function escapeMd(text: string): string {
  let out = ''
  let pos = 0
  for (const m of text.matchAll(URL_RE)) {
    out += text.slice(pos, m.index).replace(INLINE, '\\$1') + m[0]
    pos = m.index! + m[0].length
  }
  return out + text.slice(pos).replace(INLINE, '\\$1')
}

function flagsOf(text: string, spans: SpanRec[]): string[][] {
  const flags: Set<string>[] = Array.from({ length: text.length }, () => new Set())
  for (const s of spans) {
    if (s.key === 'ents' || !ORDER.includes(s.style as typeof ORDER[number])) continue
    for (let i = s.start_char; i < s.end_char && i < text.length; i++) flags[i].add(s.style)
  }
  return flags.map((f) => ORDER.filter((x) => f.has(x)))
}

function renderParagraph(segs: [string, string[]][], condensed: boolean, flavor: Flavor): string {
  const [OPEN, CLOSE] = MARKERS[flavor]
  const out: string[] = []
  const stack: string[] = []
  let pending = ''
  const closeTo = (k: number) => { while (stack.length > k) out.push(CLOSE[stack.pop()!]) }
  for (const [text, target] of segs) {
    if (condensed && target.length === 0) {
      closeTo(0)
      if (out.length && out[out.length - 1] !== ' … ') out.push(' … ')
      pending = ''
      continue
    }
    if (!text.trim()) { pending += text; continue }
    const core = text.trim()
    const lead = text.slice(0, text.length - text.trimStart().length)
    const trail = text.slice(text.trimEnd().length)
    pending += lead
    let k = 0
    while (k < Math.min(stack.length, target.length) && stack[k] === target[k]) k++
    closeTo(k)
    if (out.length && out[out.length - 1] === ' … ') pending = ''
    out.push(pending)
    for (const f of target.slice(k)) { out.push(OPEN[f]); stack.push(f) }
    out.push(escapeMd(core))
    pending = trail
  }
  closeTo(0)
  const joined = out.join('')
  return condensed ? joined.replace(/^[ …]+|[ …]+$/g, '') : joined.trim()
}

export function bodyMarkdown(text: string, spans: SpanRec[], { condensed = false, flavor = 'scythe' as Flavor } = {}): string {
  const flags = flagsOf(text, spans)
  const paras: string[] = []
  let pos = 0
  for (const line of text.split('\n')) {
    const segs: [string, string[]][] = []
    let i = pos
    const hi = pos + line.length
    while (i < hi) {
      let j = i
      while (j < hi && flags[j].join() === flags[i].join()) j++
      segs.push([text.slice(i, j), flags[i]])
      i = j
    }
    const rendered = renderParagraph(segs, condensed, flavor)
    if (rendered) paras.push(rendered)
    pos += line.length + 1
  }
  return paras.join('\n\n').replace(BLOCK_START, (m) => (m.endsWith('.') ? m.slice(0, -1) + '\\.' : '\\' + m))
}

export function citeMarkdown(cite: string): string {
  if (!cite) return ''
  const i = cite.indexOf(',')
  return i < 0 ? `**${escapeMd(cite.trim())}**` : `**${escapeMd(cite.slice(0, i).trim())}**${escapeMd(cite.slice(i))}`
}

/** Canonical card Markdown (print, copy-as-MD, chunking). */
export function cardMarkdown(title: string, meta: CardMeta, { condensed = false, level = 4 } = {}): string {
  return [`${'#'.repeat(level)} ${title ? escapeMd(title) : 'Untagged'}`, citeMarkdown(meta.cite),
    bodyMarkdown(meta.text, meta.spans, { condensed })].filter(Boolean).join('\n\n') + '\n'
}

// ---------------------------------------------------------------- issue bodies

export function cardBody(meta: CardMeta): string {
  const parts = [citeMarkdown(meta.cite), bodyMarkdown(meta.text, meta.spans, { flavor: 'github' })]
  if (meta.links.length) parts.push(meta.links.map((l) => `${LINK_WORDS[l.rel] ?? l.rel} #${l.to}`).join('\n'))
  parts.push(metaBlock(meta))
  const body = parts.filter(Boolean).join('\n\n') + '\n'
  if (body.length > BODY_LIMIT) throw new Error(`This card is too long for one GitHub issue (${body.length.toLocaleString()} characters).`)
  return body
}

export function cardLabels(o: { topic: string | null; file: string | null; block: string | null; approved: boolean }): string[] {
  const labels: string[] = [KIND_LABELS.card]
  if (o.topic) labels.push(`topic:${o.topic}`)
  if (o.file && o.block) labels.push(`file:${o.file}`.slice(0, 50), `block:${o.block}`.slice(0, 50))
  if (o.approved) labels.push('approved')
  return labels
}

export function splitText(text: string): string[] {
  const parts: string[] = []
  let cur = ''
  for (let para of text.split(/(?<=\n\n)/)) {
    if (cur && cur.length + para.length > PART_SIZE) { parts.push(cur); cur = '' }
    while (para.length > PART_SIZE) { parts.push(para.slice(0, PART_SIZE)); para = para.slice(PART_SIZE) }
    cur += para
  }
  if (cur || !parts.length) parts.push(cur)
  return parts
}

export const sourceBody = (meta: SourceMeta, firstPart: string) =>
  `${metaBlock(meta)}\n\n<!-- scythe:text -->\n${firstPart}\n<!-- /scythe:text -->\n`
export const partComment = (n: number, chunk: string) => `<!-- scythe:part ${n} -->\n${chunk}\n<!-- /scythe:part -->\n`

export function sourceText(body: string, comments: { body: string }[] = []): string {
  const parts = new Map<number, string>()
  const m = TEXT_RE.exec(normalize(body))
  if (m) parts.set(1, m[1])
  for (const c of comments) for (const p of normalize(c.body).matchAll(PART_RE)) parts.set(Number(p[1]), p[2])
  return [...parts.entries()].sort((a, b) => a[0] - b[0]).map(([, t]) => t).join('')
}

// ---------------------------------------------------------------- browser-side snapping

/** Word/punctuation tokens, close to spaCy's English tokenizer. The Action re-snaps with spaCy. */
export function roughTokens(text: string): [number, number][] {
  return [...text.matchAll(/[\p{L}\p{N}]+(?:['’][\p{L}]+)*|[^\s\p{L}\p{N}]/gu)].map((m) => [m.index!, m.index! + m[0].length])
}

export function snapChars(text: string, start: number, end: number): [number, number] | null {
  const toks = roughTokens(text).filter(([a, b]) => b > start && a < end)
  return toks.length ? [toks[0][0], toks[toks.length - 1][1]] : null
}

// ---------------------------------------------------------------- git files (mirror of issue_doc.py)

/** cards/<n>.md front matter: the record of a card. Every save is a commit of this file. */
export interface CardFile {
  issue: number | null; title: string; topic: TopicRef | null; file: string | null; block: string | null; approved: boolean
  cite: string; url: string; source: number | null; links: LinkRec[]; spans: SpanRec[]; text: string
}
export interface SourceHead {
  issue: number | null; title: string; url: string | null; publisher: string; published: string | null; authors: string[]
  cite: string; fetched: string | null
}
const CARD_FIELDS: (keyof CardFile)[] = ['issue', 'title', 'topic', 'file', 'block', 'approved', 'cite', 'url', 'source', 'links', 'spans', 'text']
const SOURCE_FIELDS: (keyof SourceHead)[] = ['issue', 'title', 'url', 'publisher', 'published', 'authors', 'cite', 'fetched']

/** One key per line, one span/link per line, so `git log -p` shows exactly what changed. Matches Python. */
export function diffableJson(obj: Record<string, unknown>): string {
  // Python's json.dumps spacing (", " and ": "), built structurally so string contents are untouched.
  const pyJson = (v: unknown): string => {
    if (Array.isArray(v)) return `[${v.map(pyJson).join(', ')}]`
    if (v && typeof v === 'object') return `{${Object.entries(v).map(([k, x]) => `${JSON.stringify(k)}: ${pyJson(x)}`).join(', ')}}`
    return JSON.stringify(v ?? null)
  }
  const entries = Object.entries(obj)
  const lines = entries.map(([k, v], i) => {
    const comma = i < entries.length - 1 ? ',' : ''
    if (Array.isArray(v) && v.length) {
      return `  ${JSON.stringify(k)}: [\n${v.map((x, j) => `    ${pyJson(x)}${j < v.length - 1 ? ',' : ''}`).join('\n')}\n  ]${comma}`
    }
    return `  ${JSON.stringify(k)}: ${pyJson(v)}${comma}`
  })
  return `{\n${lines.join('\n')}\n}`
}

function splitFront(content: string): [Record<string, unknown>, string] {
  const c = normalize(content)
  if (!c.startsWith('---\n')) throw new Error('missing front matter')
  const end = c.indexOf('\n---\n', 4)
  return [JSON.parse(c.slice(4, end)), c.slice(end + 5)]
}

export function cardFile(card: CardFile): string {
  const head = Object.fromEntries(CARD_FIELDS.map((k) => [k, card[k] ?? null]))
  head.links = card.links ?? []
  head.spans = card.spans ?? []
  const meta = { kind: 'card' as const, text: card.text, cite: card.cite, url: card.url, source: card.source, topic: card.topic, spans: head.spans as SpanRec[], links: [] }
  return `---\n${diffableJson(head)}\n---\n\n${cardMarkdown(card.title, meta)}`
}

export const parseCardFile = (content: string) => splitFront(content)[0] as unknown as CardFile

export function sourceFile(head: SourceHead, text: string): string {
  return `---\n${diffableJson(Object.fromEntries(SOURCE_FIELDS.map((k) => [k, head[k] ?? null])))}\n---\n\n${text}\n`
}

export function parseSourceFile(content: string): [SourceHead, string] {
  const [head, body] = splitFront(content)
  return [head as unknown as SourceHead, body.slice(1, -1)]
}
