import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LINK_WORDS } from '../lib/doc'
import { useDebounced } from '../lib/hooks'
import { backlinks, ops, searchCards, type CardDoc, type Op } from '../lib/store'

const RELATIONS = ['answers', 'supports', 'contradicts', 'elaborates', 'same_claim', 'quotes', 'cites', 'derived_from', 'related']

/** A card's typed links (committed in its file, "Answers #12" in its issue) and the cards linking to it. */
export default function Links({ card, commit, canEdit }: { card: CardDoc; commit: (op: Op) => void; canEdit: boolean }) {
  const [incoming, setIncoming] = useState<{ rel: string; card: CardDoc }[]>([])
  const [relation, setRelation] = useState('answers')
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<CardDoc[]>([])
  const dq = useDebounced(q, 300)

  useEffect(() => { backlinks(card.number).then(setIncoming).catch(() => setIncoming([])) }, [card.number])
  useEffect(() => {
    if (!dq.trim()) { setHits([]); return }
    searchCards(dq).then((h) => setHits(h.filter((c) => c.number !== card.number).slice(0, 6))).catch(() => setHits([]))
  }, [dq, card.number])

  return (
    <section className="gap">
      <h3>Links</h3>
      {card.meta.links.length === 0 && incoming.length === 0 && <p>Nothing linked yet.</p>}
      <ul className="list">
        {card.meta.links.map((l) => (
          <li key={`${l.rel}-${l.to}`} className="row">
            <span>{LINK_WORDS[l.rel] ?? l.rel}</span><Link to={`/cards/${l.to}`}>#{l.to}</Link>
            {canEdit && <button className="link spacer" onClick={() => commit(ops.unlink(l))}>unlink</button>}
          </li>
        ))}
        {incoming.map((i) => (
          <li key={`in-${i.card.number}-${i.rel}`} className="row">
            <Link to={`/cards/${i.card.number}`}>{i.card.title}</Link><span>{(LINK_WORDS[i.rel] ?? i.rel).toLowerCase()} this card</span>
          </li>
        ))}
      </ul>
      {canEdit && (
        <>
          <div className="row">
            <select className="field" style={{ width: 'auto' }} value={relation} onChange={(e) => setRelation(e.target.value)}>
              {RELATIONS.map((r) => <option key={r} value={r}>{LINK_WORDS[r]}</option>)}
            </select>
            <input className="field" style={{ flex: 1, minWidth: '12rem' }} placeholder="Search cards to link…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {hits.length > 0 && (
            <ul className="list">
              {hits.map((h) => (
                <li key={h.number}><button className="link" onClick={() => { commit(ops.link(relation, h.number)); setQ('') }}>
                  {LINK_WORDS[relation]} #{h.number} {h.title}</button></li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
