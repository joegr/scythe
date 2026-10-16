/** The optional local Scythe API (Postgres search index, spaCy exports, training). Uses the same GitHub token. */
import { config } from './gh'

export async function local<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = config.token()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(`${config.localApi()}/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new Error(`The local Scythe API at ${config.localApi()} isn't running. Start it with make api.`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const type = res.headers.get('content-type') ?? ''
  return (res.status === 204 ? undefined : type.includes('json') ? res.json() : res.text()) as Promise<T>
}

export async function localDownload(path: string, name: string) {
  const headers: Record<string, string> = {}
  const token = config.token()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${config.localApi()}/api${path}`, { headers })
  if (!res.ok) throw new Error(`Download failed: ${res.status}`)
  const url = URL.createObjectURL(await res.blob())
  Object.assign(document.createElement('a'), { href: url, download: name }).click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export interface Extracted { url: string; title: string; publisher: string; published: string | null; authors: string[]; text: string; default_cite: string }
export const extract = (url: string) => local<Extracted>('POST', '/reader/extract', { url })

/** Same rules as backend reader.sanitize_text: NFC, no invisible characters, one blank line between paragraphs. */
export function sanitizeText(text: string): string {
  return text.normalize('NFC').replace(/\u00ad|\u200b|\u200c|\u200d|\u2060|\ufeff/g, '').replace(/\r\n?/g, '\n')
    .split(/\n\s*\n/).map((b) => b.split('\n').map((l) => l.replace(/[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+/g, ' ').trim()).filter(Boolean).join(' '))
    .filter(Boolean).join('\n\n')
}

/** Pasted page HTML -> paragraphs, without a server. */
export function htmlToText(html: string): { title: string; text: string } {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  doc.querySelectorAll('script, style, nav, header, footer, aside, form, noscript').forEach((n) => n.remove())
  const root = doc.querySelector('article') ?? doc.querySelector('main') ?? doc.body
  const paras = [...root.querySelectorAll('p, h1, h2, h3, li, blockquote')].map((p) => p.textContent ?? '').filter((t) => t.trim())
  return { title: doc.title.trim(), text: sanitizeText(paras.join('\n\n') || root.textContent || '') }
}
