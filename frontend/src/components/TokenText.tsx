import { useMemo, type MouseEvent } from 'react'
import type { SpanRec } from '../lib/doc'
import { paragraphs, segments, selectionRange } from '../lib/render'
import { spanKey } from '../lib/store'

interface Props {
  text: string
  spans: SpanRec[]
  condensed?: boolean
  editable?: boolean
  showEntities?: boolean
  activeKey?: string | null
  onSelect?: (range: [number, number] | null) => void
  onSpanClick?: (spans: SpanRec[], e: MouseEvent) => void
  mark?: [number, number] | null
}

const STYLE_CLASS: Record<string, string> = { underline: 't-u', highlight: 't-hl', emphasis: 't-em' }

/** Card text with formatting drawn as underlines only (thin / heavy / double). */
export default function TokenText({ text, spans, condensed, editable, showEntities, activeKey, onSelect, onSpanClick, mark }: Props) {
  const visible = useMemo(() => spans.filter((s) => s.key !== 'ents' || showEntities), [spans, showEntities])
  const all = useMemo(() => (mark ? [...visible, { key: '_mark', label: '', style: '', src: '', start_char: mark[0], end_char: mark[1] }] : visible), [visible, mark])

  return (
    <div className={`token-text${editable ? ' editable' : ''}`}
      onMouseUp={editable && onSelect ? (e) => onSelect(selectionRange(e.currentTarget)) : undefined}>
      {paragraphs(text).map(([lo, hi]) => {
        const children: React.ReactNode[] = []
        let elided = false
        let shown = 0
        for (const seg of segments(text, all, lo, hi)) {
          const real = seg.spans.filter((s) => s.key !== '_mark')
          const formatted = real.some((s) => s.key !== 'ents')
          if (condensed && !formatted) {
            if (!elided) children.push(<span key={seg.start}> … </span>)
            elided = true
            continue
          }
          elided = false
          shown++
          const cls = new Set<string>()
          const titles: string[] = []
          for (const s of real) {
            if (s.key === 'ents') { cls.add('t-ner'); titles.push(s.label) } else {
              cls.add(STYLE_CLASS[s.style] ?? 't-custom')
              if (!STYLE_CLASS[s.style]) titles.push(s.label)
            }
          }
          if (activeKey && real.some((s) => spanKey(s) === activeKey)) cls.add('t-active')
          if (seg.spans.some((s) => s.key === '_mark')) cls.add('t-mark')
          children.push(
            <span key={seg.start} data-start={seg.start} data-span={real.length && onSpanClick ? '' : undefined}
              className={[...cls].join(' ') || undefined} title={titles.join(' · ') || undefined}
              onClick={real.length && onSpanClick ? (e) => onSpanClick(real, e) : undefined}>
              {seg.text}
            </span>,
          )
        }
        return condensed && shown === 0 ? null : <p key={lo}>{children}</p>
      })}
    </div>
  )
}
