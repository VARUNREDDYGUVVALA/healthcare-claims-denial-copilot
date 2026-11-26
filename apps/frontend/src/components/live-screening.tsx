import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

type Capability = {available: boolean; policy_mode: 'synthetic' | 'configured'}
export type Result = {
  recommendation: 'ready_for_review' | 'correct_before_submission' | 'needs_review'
  issues: {code: string; severity: 'review' | 'correct'; message: string}[]
  matched_policy: {policy_id: string; effective_start: string; effective_end: string; source_url: string | null} | null
  evaluated_at?: string
  policy_mode: Capability['policy_mode']
}
const route = import.meta.env.BASE_URL + 'api/screening'
export const decisions = {
  ready_for_review: 'Ready for analyst review',
  correct_before_submission: 'Correct before submission',
  needs_review: 'Needs manual review',
}

function Evidence({name, label}: {name: string; label: string}) {
  return <label>{label}<select name={name} defaultValue="unknown">
    <option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option>
  </select></label>
}

export function LiveScreening() {
  const [capability, setCapability] = useState<Capability>()
  const [connected, setConnected] = useState<boolean>()
  const [result, setResult] = useState<Result>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(route + '/capabilities', {signal: controller.signal})
      .then(response => {
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error()
        return response.json()
      })
      .then((value: Capability) => {setCapability(value); setConnected(true)})
      .catch(() => {if (!controller.signal.aborted) setConnected(false)})
    return () => controller.abort()
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const token = fields.get('token')
    fields.delete('token')
    setResult(undefined)
    setError('')
    setBusy(true)
    try {
      const response = await fetch(route, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + String(token).trim()},
        body: JSON.stringify(claimPayload(fields)),
      })
      if (response.status === 401) throw Error('Enter a valid API access token.')
      if (response.status === 422) throw Error('Check the claim fields. An approval date requires authorization marked Yes.')
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw Error(typeof body.detail === 'string' ? body.detail : 'The screening request failed.')
      }
      setResult(await response.json())
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Unable to screen this line.')
    } finally {
      setBusy(false)
    }
  }

  const sample = capability?.policy_mode === 'synthetic'
  return <>
    <h1>Live claim screening</h1>
    <p className="subtitle">Enter one claim line to check it against the server’s configured policy rules.</p>
    {connected === undefined ? <p role="status">Checking the screening API…</p> :
      !connected || !capability?.available ? <section className="panel section">
        <h2>{connected ? 'Configure API access' : 'A running API is required'}</h2>
        <p>{connected ? 'Set distinct analyst and supervisor tokens to enable screening.' : 'This static site cannot analyze a submitted line on a server. Run the local application to use live screening.'}</p>
        <a className="text-button" href="https://github.com/VARUNREDDYGUVVALA/healthcare-claims-denial-copilot/blob/main/docs/live_screening.md">Read setup and API instructions</a>
      </section> : <div className="detail-grid">
        <section className="panel section">
          <h2>Claim line details</h2>
          <p>{sample ? 'The server is using fictional payer policies.' : 'The server is using an operator-configured policy catalogue.'} Enter claim metadata only. Keep names, member identifiers, and medical notes out of this form.</p>
          <form className="batch-form" onSubmit={submit}>
            <label>API access token<input type="password" name="token" autoComplete="off" required/></label>
            <ClaimFields sample={sample}/>
            <button className="primary" disabled={busy}>{busy ? 'Analyzing…' : 'Analyze claim line'}</button>
          </form>
        </section>
        <section className="panel section" aria-label="Screening recommendation">
          <h2>Screening recommendation</h2>
          {error && <p className="notice" role="alert">{error}</p>}
          {!result && !error && <p>{busy ? 'Evaluating entered details on the server…' : 'Submit the form to see the policy match and checks.'}</p>}
          {result && <ScreeningResult result={result}/>}
        </section>
      </div>}
  </>
}

export function ClaimFields({sample}: {sample: boolean}) {
  return <>
    <label>Payer code<input name="payer_code" defaultValue={sample ? 'NORTHSTAR' : ''} required maxLength={30}/></label>
    <label>Plan code<input name="plan_code" defaultValue={sample ? 'DEMO' : ''} required maxLength={30}/></label>
    <label>Procedure code<input name="procedure_code" defaultValue={sample ? 'IMG-01' : ''} required maxLength={30}/></label>
    <label>Service date<input type="date" name="service_date" defaultValue={sample ? '2026-03-30' : ''} min="1900-01-01" max="2100-12-31" required/></label>
    <label>Units<input type="number" name="units" min={1} max={9999} defaultValue={1} required/></label>
    <Evidence name="coverage_active" label="Coverage active on service date"/>
    <Evidence name="duplicate_confirmed" label="Duplicate confirmed"/>
    <Evidence name="authorization_present" label="Authorization present"/>
    <label>Authorization approval date<input type="date" name="authorization_date" min="1900-01-01" max="2100-12-31"/></label>
  </>
}

export function claimPayload(fields: FormData) {
  const claim = Object.fromEntries(fields)
  return {
    ...claim,
    payer_code: String(claim.payer_code).trim().toUpperCase(),
    plan_code: String(claim.plan_code).trim().toUpperCase(),
    procedure_code: String(claim.procedure_code).trim().toUpperCase(),
    units: Number(claim.units),
    authorization_date: claim.authorization_date || null,
  }
}

export function ScreeningResult({result}: {result: Result}) {
  return <div aria-live="polite" className="question-answer">
            <h3>{decisions[result.recommendation]}</h3>
            <p>{result.policy_mode === 'synthetic' ? 'Fictional policy evaluation' : 'Configured policy evaluation'}{result.evaluated_at && ' · ' + new Date(result.evaluated_at).toLocaleString()}</p>
            {result.matched_policy && <p>Policy {result.matched_policy.policy_id} · {result.matched_policy.effective_start} to before {result.matched_policy.effective_end}.
              {result.matched_policy.source_url && <> <a className="text-button" href={result.matched_policy.source_url} target="_blank" rel="noreferrer">Open policy source</a></>}
            </p>}
            {result.issues.length ? <ul>{result.issues.map(issue => <li key={issue.code}>{issue.message}</li>)}</ul> :
              <p>The supplied details passed the configured checks.</p>}
            <p>An authorized reviewer makes the final submission decision.</p>
          </div>
}
