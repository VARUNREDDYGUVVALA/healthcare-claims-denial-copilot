import { useState } from 'react'
import type { FormEvent } from 'react'

type Run = {
  id: string
  line_id: string
  status: 'awaiting_review' | 'approved' | 'rejected'
  recorded_reason: string
  findings: string[]
  suggested_action: string
  policy: {id: string; section: string; excerpt: string} | null
  appeal_draft: string | null
  trace: string[]
  audit: {role: string; event: string; note: string | null; at: string}[]
}

export function Investigation({lineId}: {lineId: string}) {
  const [token, setToken] = useState('')
  const [runId, setRunId] = useState('')
  const [run, setRun] = useState<Run>()
  const [decision, setDecision] = useState('approve')
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  function request(event: FormEvent<HTMLFormElement>, mode: 'start' | 'resume' | 'review') {
    event.preventDefault()
    if (busy || !token.trim()) return
    const id = encodeURIComponent(mode === 'review' ? run?.id ?? '' : runId.trim())
    const path = import.meta.env.BASE_URL + 'api/investigations'
    const body = mode === 'start' ? {line_id: lineId} : {decision, note}
    setBusy(true)
    setMessage('')
    fetch(mode === 'start' ? path : path + '/' + id + (mode === 'review' ? '/decision' : ''), {
      method: mode === 'resume' ? 'GET' : 'POST',
      headers: {Authorization: 'Bearer ' + token.trim(), 'Content-Type': 'application/json'},
      body: mode === 'resume' ? undefined : JSON.stringify(body),
    }).then(async response => {
      if (response.status === 401) throw Error('Check the bearer token and try again.')
      if (response.status === 403) throw Error('A supervisor token is required to record a final review.')
      if (response.status === 503) throw Error('The local API or its tokens are not configured. See the README.')
      if (!response.ok) {
        const result = await response.json().catch(() => ({}))
        throw Error(typeof result.detail === 'string' ? result.detail : 'The request could not be completed.')
      }
      const result: Run = await response.json()
      setRun(result)
      setRunId(result.id)
      if (mode === 'review') setNote('')
    }).catch(error => setMessage(error instanceof Error ? error.message : 'The request failed.'))
      .finally(() => setBusy(false))
  }

  return <section className="panel section decision" aria-label="Local investigation">
    <h2>Local investigation</h2>
    <p>Run the workflow against the local API. Approval records a review decision for this investigation.</p>
    <form onSubmit={event => request(event, 'start')}>
      <label>Local API token<input name="copilot-investigation-token" autoComplete="off" type="password" required value={token} onChange={event => setToken(event.target.value)}/></label>
      <button className="primary" disabled={busy || !token.trim()}>Start investigation</button>
    </form>
    <details className="question-history"><summary>Reopen a saved investigation</summary>
      <form onSubmit={event => request(event, 'resume')}>
        <label>Investigation ID<input value={runId} onChange={event => setRunId(event.target.value)} required/></label>
        <button className="primary" disabled={busy || !token.trim()}>Open investigation</button>
      </form>
    </details>
    {message && <p className="notice" role="alert">{message}</p>}
    {run && <div className="question-answer">
      <h3>{run.line_id} · {run.status.replaceAll('_', ' ')}</h3>
      <p>Investigation ID <code>{run.id}</code></p>
      <p>Recorded payer reason · {run.recorded_reason}</p>
      {run.policy && <blockquote><strong>{run.policy.id} · {run.policy.section}</strong><p>{run.policy.excerpt}</p></blockquote>}
      <ul>{run.findings.map(finding => <li key={finding}>{finding}</li>)}</ul>
      <p>Suggested action · {run.suggested_action}</p>
      {run.appeal_draft && <details open><summary>Appeal draft</summary><p>{run.appeal_draft}</p></details>}
      <h3>Workflow trace</h3>
      <ol>{run.trace.map(step => <li key={step}>{step}</li>)}</ol>
      <h3>Audit history</h3>
      <ul>{run.audit.map(event => <li key={event.event}>{event.event.replaceAll('_', ' ')} · {event.role} · {new Date(event.at).toLocaleString()}{event.note && <> · {event.note}</>}</li>)}</ul>
      {run.status === 'awaiting_review' && <form onSubmit={event => request(event, 'review')}>
        <label>Supervisor decision<select value={decision} onChange={event => setDecision(event.target.value)}>
          <option value="approve">Approve investigation</option><option value="reject">Reject investigation</option>
        </select></label>
        <label>Supervisor note<textarea required maxLength={2000} value={note} onChange={event => setNote(event.target.value)}/></label>
        <button className="primary" disabled={busy || !token.trim() || !note.trim()}>Record supervisor decision</button>
      </form>}
    </div>}
  </section>
}
