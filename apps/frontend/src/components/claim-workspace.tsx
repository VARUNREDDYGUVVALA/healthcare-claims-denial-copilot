import {useEffect, useState} from 'react'
import type {FormEvent} from 'react'
import {ClaimFields, ScreeningResult, claimPayload, decisions} from './live-screening'
import type {Result} from './live-screening'

type Role = 'customer' | 'analyst' | 'manager'
type Session = {username: string; role: Role; token: string}
type Outcome = keyof typeof decisions
type Status = 'submitted' | 'assigned' | 'escalated' | 'reviewed'
type Summary = {id: string; status: Status; analyst: string | null; outcome: Outcome | null; procedure: string; recommendation: Outcome}
type Case = Pick<Summary, 'id' | 'status' | 'outcome'> & {
  claim: Record<string, string | number | null>
  screening: Result
  events: {action: string; occurred_at: string; actor?: string; value?: string | null}[]
}
type Queue = {cases: Summary[]; analysts: string[]}
const route = import.meta.env.BASE_URL + 'api/workspace/'
const titles = {customer: 'Claim Check', analyst: 'Analyst Review', manager: 'Manager Dashboard'}
const states = {submitted: 'Awaiting assignment', assigned: 'Assigned', escalated: 'Escalated', reviewed: 'Reviewed'}
const fieldLabels: Record<string, string> = {
  payer_code: 'Payer code', plan_code: 'Plan code', procedure_code: 'Procedure code',
  service_date: 'Service date', units: 'Units', coverage_active: 'Coverage active',
  duplicate_confirmed: 'Duplicate confirmed', authorization_present: 'Authorization present',
  authorization_date: 'Authorization approval date',
}

export function ClaimWorkspace() {
  const [mode, setMode] = useState<string>()
  const [session, setSession] = useState<Session>()
  const [queue, setQueue] = useState<Queue>({cases: [], analysts: []})
  const [selected, setSelected] = useState<Case>()
  const [preview, setPreview] = useState<Result>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(route + 'capabilities', {signal: controller.signal})
      .then(response => response.json())
      .then(data => setMode(data.available ? data.policy_mode : 'unavailable'))
      .catch(() => {if (!controller.signal.aborted) setMode('unavailable')})
    return () => controller.abort()
  }, [])

  async function request<T>(path: string, method = 'GET', data?: object, token = session?.token): Promise<T> {
    const headers = new Headers()
    if (token) headers.set('Authorization', 'Bearer ' + token)
    if (data) headers.set('Content-Type', 'application/json')
    const response = await fetch(route + path, {method, headers, body: data && JSON.stringify(data), cache: 'no-store'})
    if (!response.ok) {
      if (response.status === 401 && token) clearSession()
      const body = await response.json().catch(() => ({}))
      throw Error(typeof body.detail === 'string' ? body.detail : 'Check the entered fields and try again.')
    }
    return response.status === 204 ? undefined as T : response.json()
  }

  function clearSession() {
    setSession(undefined)
    setPreview(undefined)
    setSelected(undefined)
    setQueue({cases: [], analysts: []})
  }

  async function run(work: () => Promise<void>) {
    setBusy(true)
    setError('')
    try { await work() }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'The workspace request failed.') }
    finally { setBusy(false) }
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    await run(async () => {
      const account = await request<Session>('sessions', 'POST', fields)
      setQueue(await request<Queue>('cases', 'GET', undefined, account.token))
      setSession(account)
    })
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const input = claimPayload(new FormData(event.currentTarget))
    const action = (event.nativeEvent as SubmitEvent).submitter
    const shouldSubmit = action instanceof HTMLButtonElement && action.value === 'submit'
    await run(async () => {
      if (!shouldSubmit) {
        setPreview(await request<Result>('screening', 'POST', input))
        return
      }
      setPreview(undefined)
      const {id} = await request<{id: string}>('cases', 'POST', input)
      setSelected(await request<Case>('cases/' + id))
      setQueue(await request<Queue>('cases'))
    })
  }

  async function update(action: string, data?: object) {
    if (!selected) return
    const path = 'cases/' + selected.id
    await run(async () => {
      await request(path + '/' + action, 'POST', data)
      setSelected(await request<Case>(path))
      setQueue(await request<Queue>('cases'))
    })
  }

  return <>
    <div className="page-heading"><div><h1>{session ? titles[session.role] : 'Claim workspace'}</h1>
      <p>{session ? 'Signed in as ' + session.username : 'Submit a claim line, verify the evidence, and track the review.'}</p></div>
      {session && <button className="text-button" disabled={busy} onClick={() => run(async () => {
        await request('sessions/current', 'DELETE')
        clearSession()
      })}>Sign out</button>}
    </div>
    {error && <p role="alert" className="notice">{error}</p>}
    {!mode && <p role="status">Checking workspace availability…</p>}
    {mode === 'unavailable' && <section className="panel section">
      <h2>Connect to the full-stack app</h2>
      <p>Customer, analyst, and manager accounts are available on a configured Ledger server.</p>
      <a className="text-button" href="https://github.com/VARUNREDDYGUVVALA/healthcare-claims-denial-copilot/blob/main/docs/live_screening.md#enable-the-three-workspaces">Workspace setup</a>
    </section>}
    {mode && mode !== 'unavailable' && !session && <section className="panel section">
      <h2>Sign in</h2>
      <form className="batch-form" onSubmit={signIn}>
        <label>Username<input name="username" autoComplete="username" required maxLength={64}/></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required maxLength={128}/></label>
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </section>}
    {session && <>
      {session.role === 'customer' && <section className="panel section">
        <h2>Check and submit a claim line</h2>
        <p>Use fictional claim details for this pilot. Submit codes and evidence flags only.</p>
        <form className="batch-form" onSubmit={submit} onChange={() => setPreview(undefined)}>
          <ClaimFields sample={mode === 'synthetic'}/>
          <button className="primary" disabled={busy}>Analyze claim line</button>
          <button className="text-button" value="submit" disabled={busy || !preview}>Request analyst review</button>
        </form>
        {preview && <ScreeningResult result={preview}/>}
      </section>}
      {session.role === 'manager' && <section className="panel section">
        <h2>Review workload</h2>
        <p>{Object.entries(states).map(([status, label]) =>
          label + ' ' + queue.cases.filter(item => item.status === status).length).join(' · ')}</p>
        <h3>Activate an analyst account</h3>
        <form className="batch-form" onSubmit={event => {
          event.preventDefault()
          const form = event.currentTarget
          const fields = Object.fromEntries(new FormData(form))
          void run(async () => {
            await request('analysts', 'POST', fields)
            form.reset()
            setQueue(await request<Queue>('cases'))
          })
        }}>
          <label>Analyst username<input name="username" required pattern="[a-z0-9_.\-]{3,64}" maxLength={64}/></label>
          <label>Initial password<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label>
          <button className="primary" disabled={busy}>Activate analyst</button>
        </form>
        {queue.analysts.length > 0 && <p>Active analysts · {queue.analysts.join(', ')}</p>}
      </section>}
      <section className="panel section">
        <h2>{session.role === 'customer' ? 'Your submissions' : 'Review queue'}</h2>
        <button className="text-button" disabled={busy} onClick={() => run(async () => {
          setQueue(await request<Queue>('cases'))
          setSelected(undefined)
        })}>Refresh queue</button>
        {!queue.cases.length ? <p>No claims in this queue.</p> : <div className="scroll"><table>
          <thead><tr><th>Claim reference</th><th>Procedure</th><th>Status</th><th>Screening</th>
            {session.role === 'manager' && <th>Assigned analyst</th>}</tr></thead>
          <tbody>{queue.cases.map(item => <tr key={item.id}>
            <td><button className="table-link" disabled={busy} onClick={() => run(async () =>
              setSelected(await request<Case>('cases/' + item.id)))}>{item.id.slice(0, 8)}</button></td>
            <td>{item.procedure}</td><td>{states[item.status]}</td><td>{decisions[item.outcome ?? item.recommendation]}</td>
            {session.role === 'manager' && <td>{item.analyst ?? 'Unassigned'}</td>}
          </tr>)}</tbody>
        </table></div>}
      </section>
      {selected && <section className="panel section" aria-label="Claim review detail">
        <h2>Claim {selected.id.slice(0, 8)}</h2>
        <p>{states[selected.status]}{selected.outcome && ' · ' + decisions[selected.outcome]}</p>
        <div className="detail-grid">
          <div><h3>Submitted evidence</h3>
            <dl>{Object.entries(selected.claim).map(([field, value]) => <div key={field}>
              <dt>{fieldLabels[field] ?? field}</dt><dd>{value ?? 'Not provided'}</dd>
            </div>)}</dl>
          </div>
          <div><h3>Screening recommendation</h3><ScreeningResult result={selected.screening}/></div>
        </div>
        {session.role === 'manager' && ['submitted', 'assigned'].includes(selected.status) &&
          <form className="batch-form" onSubmit={event => {
            event.preventDefault()
            void update('assignment', {analyst: new FormData(event.currentTarget).get('analyst')})
          }}>
            <label>Assign analyst<select name="analyst" required defaultValue="">
              <option value="">Select analyst</option>{queue.analysts.map(name => <option key={name}>{name}</option>)}
            </select></label>
            <button className="primary" disabled={busy || !queue.analysts.length}>Save assignment</button>
          </form>}
        {((session.role === 'analyst' && selected.status === 'assigned') ||
          (session.role === 'manager' && selected.status === 'escalated')) &&
          <form className="batch-form" onSubmit={event => {
            event.preventDefault()
            void update(session.role === 'analyst' ? 'review' : 'resolution', {
              outcome: new FormData(event.currentTarget).get('outcome'),
            })
          }}>
            <label>Review outcome<select name="outcome" defaultValue={selected.screening.recommendation}>
              {Object.entries(decisions).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select></label>
            <button className="primary" disabled={busy}>Save review</button>
            {session.role === 'analyst' && <button type="button" className="text-button" disabled={busy}
              onClick={() => update('escalation')}>Escalate to manager</button>}
          </form>}
        <h3>Review history</h3>
        <ul>{selected.events.map((event, index) => <li key={index}>
          {event.action} · {new Date(event.occurred_at).toLocaleString()}{event.actor ? ' · ' + event.actor : ''}
        </li>)}</ul>
      </section>}
    </>}
  </>
}
