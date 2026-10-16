import { useCallback, useEffect, useState } from 'react'
import { config } from '../lib/gh'
import { local, localDownload } from '../lib/local'

interface ModelRun { name: string; ready: boolean; status?: string; n_train?: number; n_dev?: number; performance?: Record<string, number> }

/** spaCy training and exports run on the local Scythe API, which indexes the repo's card issues. */
export default function DataPage() {
  const [model, setModel] = useState<{ base_model: string; active: ModelRun | null; runs: ModelRun[]; training: boolean } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [down, setDown] = useState<string | null>(null)

  const reload = useCallback(() => {
    local<typeof model>('GET', '/model').then((m) => { setModel(m); setDown(null) }).catch((e) => setDown(e.message))
  }, [])
  useEffect(reload, [reload])

  const act = (fn: () => Promise<unknown>, done: string) => fn().then(() => setMessage(done)).catch((e) => setMessage(e.message))
  const score = (r: ModelRun, k: string) => {
    const v = Object.entries(r.performance ?? {}).find(([key]) => key.endsWith(`_${k}`))?.[1]
    return v != null ? v.toFixed(2) : 'n/a'
  }

  return (
    <div className="stack">
      <section className="gap">
        <h1>Training data</h1>
        <p>
          Every card issue is also snapshotted to <code>archive/</code> in the repo by the GitHub Action, with spaCy token offsets.
          The local API ({config.localApi()}) indexes the issues for spaCy exports and training.
        </p>
        {down && <p className="note">{down}</p>}
        {message && <p className="note">{message}</p>}
      </section>
      {!down && (
        <>
          <section className="gap">
            <h2>Index</h2>
            <button className="link" onClick={() => act(() => local('PUT', '/github/repo', { repo: config.repo() }).then(() => local('POST', '/github/sync')), 'Syncing the index from GitHub issues.')}>
              sync from {config.repo()}
            </button>
          </section>
          <section className="gap">
            <h2>Export</h2>
            <ul className="list">
              <li><button className="link" onClick={() => localDownload('/spacy/export.spacy', 'scythe.spacy')}>DocBin (.spacy)</button></li>
              <li><button className="link" onClick={() => localDownload('/spacy/export.jsonl?format=docjson', 'scythe-docjson.jsonl')}>spaCy Doc JSON lines</button></li>
              <li><button className="link" onClick={() => localDownload('/spacy/export.jsonl?format=prodigy', 'scythe-prodigy.jsonl')}>Prodigy JSONL</button></li>
              <li><button className="link" onClick={() => localDownload('/spacy/training-bundle.zip', 'scythe-train.zip')}>Training bundle</button></li>
            </ul>
          </section>
          {model && (
            <section className="gap">
              <h2>Span categorizer</h2>
              <p>Base pipeline {model.base_model}. Active model: {model.active ? model.active.name : 'none yet'}.</p>
              <button className="link" disabled={model.training} onClick={() => act(() => local('POST', '/model/train?max_steps=2000').then(reload), 'Training started.')}>
                {model.training ? 'training…' : 'train'}
              </button>
              <ul className="list">
                {model.runs.map((r) => <li key={r.name}>{r.name}, {r.status ?? (r.ready ? 'done' : '…')}, F {score(r, 'f')}, P {score(r, 'p')}, R {score(r, 'r')}</li>)}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}
