import MarkdownIt from 'markdown-it'
import mark from 'markdown-it-mark'
import DOMPurify from 'dompurify'
import type { SpanRec } from './doc'
import type { CardDoc } from './store'

export interface Segment { start: number; end: number; text: string; spans: SpanRec[] }

/** Split a paragraph [lo, hi) at every visible span boundary. */
export function segments(text: string, spans: SpanRec[], lo: number, hi: number): Segment[] {
  const cuts = new Set([lo, hi])
  for (const s of spans) {
    if (s.end_char <= lo || s.start_char >= hi) continue
    cuts.add(Math.max(lo, s.start_char))
    cuts.add(Math.min(hi, s.end_char))
  }
  const points = [...cuts].sort((a, b) => a - b)
  const out: Segment[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]]
    out.push({ start: a, end: b, text: text.slice(a, b), spans: spans.filter((s) => s.start_char < b && s.end_char > a) })
  }
  return out
}

export function paragraphs(text: string): [number, number][] {
  const out: [number, number][] = []
  let pos = 0
  for (const line of text.split('\n')) {
    if (line.trim()) out.push([pos, pos + line.length])
    pos += line.length + 1
  }
  return out
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

/** Word-pasteable HTML (Verbatim conventions) + plain text for the clipboard. */
export async function copyCard(card: CardDoc) {
  const visible = card.meta.spans.filter((s) => s.key !== 'ents')
  const body = paragraphs(card.meta.text).map(([lo, hi]) => {
    const runs = segments(card.meta.text, visible, lo, hi).map((seg) => {
      const st = new Set(seg.spans.map((s) => s.style))
      const css: string[] = []
      if (st.has('underline') || st.has('emphasis')) css.push('text-decoration:underline')
      if (st.has('highlight')) css.push('background:#00ffff')
      if (st.has('emphasis')) css.push('font-weight:bold', 'border:1px solid #000')
      if (!st.size) css.push('font-size:8pt')
      return `<span style="${css.join(';')}">${esc(seg.text)}</span>`
    })
    return `<p style="font-family:Calibri,sans-serif;font-size:11pt">${runs.join('')}</p>`
  })
  const cite = card.meta.cite
  const i = cite.indexOf(',')
  const citeHtml = cite ? `<p style="font-family:Calibri,sans-serif;font-size:11pt"><b style="font-size:13pt">${esc(i < 0 ? cite : cite.slice(0, i))}</b>${esc(i < 0 ? '' : cite.slice(i))}</p>` : ''
  const html = `<h4 style="font-family:Calibri,sans-serif;font-size:13pt">${esc(card.title)}</h4>${citeHtml}${body.join('')}`
  const text = [card.title, cite, card.meta.text].filter(Boolean).join('\n\n')
  if ('ClipboardItem' in window) {
    await navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }),
    })])
  } else await navigator.clipboard.writeText(text)
}

const md = new MarkdownIt({ html: true, linkify: true }).use(mark)

export function renderMarkdown(source: string): string {
  return DOMPurify.sanitize(md.render(source), {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'u', 'ins', 'mark', 'strong', 'em', 'a', 'br', 'hr', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre'],
    ALLOWED_ATTR: ['href'],
  })
}

/** Character offset of a selection boundary in a tree annotated with data-start. */
export function domOffset(node: Node, offset: number): number | null {
  let el: HTMLElement | null = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as HTMLElement)
  if (node.nodeType !== Node.TEXT_NODE && el?.dataset.start === undefined) {
    const child = el?.childNodes[offset] as HTMLElement | undefined
    if (child?.dataset?.start !== undefined) return Number(child.dataset.start)
  }
  while (el && el.dataset.start === undefined) el = el.parentElement
  if (!el) return null
  const base = Number(el.dataset.start)
  return node.nodeType === Node.TEXT_NODE ? base + offset : base + (offset > 0 ? (el.textContent?.length ?? 0) : 0)
}

export function selectionRange(container: HTMLElement): [number, number] | null {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null
  const r = sel.getRangeAt(0)
  if (!container.contains(r.startContainer) || !container.contains(r.endContainer)) return null
  const a = domOffset(r.startContainer, r.startOffset)
  const b = domOffset(r.endContainer, r.endOffset)
  if (a === null || b === null || a === b) return null
  return [Math.min(a, b), Math.max(a, b)]
}
