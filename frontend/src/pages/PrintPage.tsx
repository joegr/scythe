import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { cardMarkdown } from '../lib/doc'
import { renderMarkdown } from '../lib/render'
import { getCard, listCards, type CardDoc } from '../lib/store'

/** Print preview from canonical card Markdown: one card (/print/12) or a file (/print/file/Name). */
export default function PrintPage() {
  const { id, file } = useParams()
  const [cards, setCards] = useState<CardDoc[]>([])
  const [condensed, setCondensed] = useState(false)
  const [raw, setRaw] = useState(false)

  useEffect(() => {
    if (file) listCards({ labels: [`file:${file}`] }).then((cs) => setCards(cs.sort((a, b) => (a.block ?? '').localeCompare(b.block ?? '') || a.number - b.number)))
    else if (id) getCard(Number(id)).then((c) => setCards([c]))
  }, [id, file])

  let source = file ? `# ${file}\n\n` : ''
  let block: string | null | undefined
  for (const c of cards) {
    if (file && c.block !== block) { block = c.block; source += `### ${block ?? 'Unfiled'}\n\n` }
    source += cardMarkdown(c.title, c.meta, { condensed }) + '\n'
  }

  return (
    <div className="stack">
      <div className="row no-print">
        <button className={`link ${!raw ? 'on' : ''}`} onClick={() => setRaw(false)}>preview</button>
        <button className={`link ${raw ? 'on' : ''}`} onClick={() => setRaw(true)}>markdown</button>
        <button className={`link ${condensed ? 'on' : ''}`} onClick={() => setCondensed(!condensed)}>read only</button>
        <button className="link spacer" onClick={() => window.print()}>print</button>
      </div>
      {raw ? <pre className="md">{source}</pre> : <article className="print-sheet" dangerouslySetInnerHTML={{ __html: renderMarkdown(source) }} />}
    </div>
  )
}
