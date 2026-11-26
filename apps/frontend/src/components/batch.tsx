import { useState } from 'react'
import type { FormEvent } from 'react'

export type BatchPolicy = { id: string; payer: string; procedure: string; starts: string; ends: string; section: string; excerpt: string }
export type Evidence = 'yes' | 'no' | 'unknown'
export type ClaimInput = {
  id: string; payer: string; procedure: string; service: string
  eligible: Evidence; duplicate: Evidence; authorization: Evidence; authorizationDate: string
}
type Recommendation = 'Recommend approval' | 'Recommend denial' | 'Needs review'
type Result = { line: ClaimInput; recommendation: Recommendation; reasons: string[]; policy?: BatchPolicy }
const limit = 5000
const verdicts: Recommendation[] = ['Recommend approval', 'Recommend denial', 'Needs review']
const isoDate = (date: Date) => date.toISOString().slice(0, 10)

function isDate(value: string) {
  const date = new Date(value)
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(+date) && isoDate(date) === value
}

export function evaluate(line: ClaimInput, policies: BatchPolicy[]): Result {
  const matches = policies.filter(policy => policy.payer === line.payer && policy.procedure === line.procedure &&
    policy.starts <= line.service && line.service < policy.ends)
  const denied: string[] = []
  const review: string[] = []
  const policy = matches.length === 1 ? matches[0] : undefined
  if (!policy) review.push(matches.length ? 'Multiple policies match the service date.' : 'No demo policy matches this payer, procedure and service date.')
  if (line.eligible === 'no') denied.push('Coverage was confirmed inactive on the service date.')
  if (line.eligible === 'unknown') review.push('Verify coverage on the service date.')
  if (line.duplicate === 'yes') denied.push('The line was confirmed to be a duplicate.')
  if (line.duplicate === 'unknown') review.push('Verify whether the line is a duplicate.')
  if (policy?.id.startsWith('NS-IMG-')) {
    if (line.authorization === 'no') denied.push('Authorization was confirmed absent.')
    if (line.authorization === 'unknown' || (line.authorization === 'yes' && !line.authorizationDate)) {
      review.push('Verify the authorization and its approval date.')
    }
    if (line.authorization === 'yes' && line.authorizationDate) {
      if (policy.id.endsWith('-v1')) {
        const deadline = new Date(line.service)
        let businessDays = 0
        while (businessDays < 2) {
          deadline.setUTCDate(deadline.getUTCDate() + 1)
          if (![0, 6].includes(deadline.getUTCDay())) businessDays += 1
        }
        if (line.authorizationDate > isoDate(deadline)) denied.push('Authorization was approved after the two-business-day window.')
      }
      if (policy.id.endsWith('-v2') && line.authorizationDate >= line.service) {
        if (line.authorizationDate === line.service) review.push('Verify that authorization preceded the service time. Only dates were supplied.')
        else denied.push('Authorization was approved after the service date.')
      }
    }
  }
  if (!policy) return { line, recommendation: 'Needs review', reasons: [...review, ...denied] }
  if (denied.length) return { line, recommendation: 'Recommend denial', reasons: [...denied, ...review], policy }
  if (review.length) return { line, recommendation: 'Needs review', reasons: review, policy }
  return { line, recommendation: 'Recommend approval', reasons: ['The supplied evidence meets the demo checks for coverage, duplicates and applicable authorization.'], policy }
}

function readClaim(value: unknown, index: number): ClaimInput {
  const record = value as Partial<ClaimInput> | null
  const invalid = (field: string) => new Error(`Record ${index + 1}: invalid or missing ${field}.`)
  if (!record || typeof record !== 'object' || Array.isArray(value)) throw invalid('claim object')
  for (const field of ['id', 'payer', 'procedure'] as const) {
    if (typeof record[field] !== 'string' || !record[field].trim() || record[field].length > 100) throw invalid(field)
  }
  if (typeof record.service !== 'string' || !isDate(record.service)) throw invalid('service date (YYYY-MM-DD)')
  for (const field of ['eligible', 'duplicate', 'authorization'] as const) {
    if (record[field] !== undefined && !['yes', 'no', 'unknown'].includes(record[field])) throw invalid(field)
  }
  const authorizationDate = record.authorizationDate ?? ''
  if (typeof authorizationDate !== 'string' || (authorizationDate && !isDate(authorizationDate))) {
    throw invalid('authorizationDate (YYYY-MM-DD)')
  }
  if (authorizationDate && record.authorization !== 'yes') throw invalid('authorization (use yes when supplying an approval date)')
  return {
    id: record.id!.trim(), payer: record.payer!.trim(), procedure: record.procedure!.trim(), service: record.service,
    eligible: record.eligible ?? 'unknown', duplicate: record.duplicate ?? 'unknown',
    authorization: record.authorization ?? 'unknown', authorizationDate,
  }
}

function examples(count: number): ClaimInput[] {
  const boundary: Omit<ClaimInput, 'id' | 'payer' | 'procedure' | 'eligible' | 'duplicate'>[] = [
    {service: '2025-06-30', authorization: 'yes', authorizationDate: '2025-07-01'},
    {service: '2025-07-01', authorization: 'no', authorizationDate: ''},
    {service: '2025-06-30', authorization: 'unknown', authorizationDate: ''},
    {service: '2025-07-01', authorization: 'yes', authorizationDate: '2025-06-30'},
  ]
  return Array.from({length: count}, (_, index) => {
    const id = `TEST-${String(index + 1).padStart(4, '0')}`
    if (index < boundary.length) {
      return {id, payer: 'Northstar Health', procedure: 'IMG-01', eligible: 'yes', duplicate: 'no', ...boundary[index]}
    }
    const service = new Date(Date.UTC(2025, 0, 1 + ((index * 73) % 365)))
    const approved = new Date(service)
    approved.setUTCDate(service.getUTCDate() + (index % 5) - 2)
    const authorization = index % 11 === 0 ? 'unknown' : index % 7 === 0 ? 'no' : 'yes'
    return {
      id, payer: index % 17 === 0 ? 'Juniper Mutual' : 'Northstar Health',
      procedure: index % 3 ? 'IMG-01' : 'VIS-03', service: isoDate(service),
      eligible: index % 13 === 0 ? 'no' : index % 19 === 0 ? 'unknown' : 'yes',
      duplicate: index % 23 === 0 ? 'yes' : index % 29 === 0 ? 'unknown' : 'no',
      authorization, authorizationDate: authorization === 'yes' ? isoDate(approved) : '',
    }
  })
}

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function BatchReview({ policies }: { policies: BatchPolicy[] }) {
  const [results, setResults] = useState<Result[]>([])
  const [filter, setFilter] = useState<Recommendation | 'All'>('All')
  const [page, setPage] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function analyze(records: unknown[]) {
    if (!records.length || records.length > limit) throw new Error('Provide 1 to 5,000 claim records.')
    const lines = records.map(readClaim)
    if (new Set(lines.map(line => line.id)).size !== lines.length) throw new Error('Each line must have a unique ID.')
    setResults(lines.map(line => evaluate(line, policies)))
    setFilter('All')
    setPage(0)
    setError('')
  }

  async function upload(files: File[]) {
    if (!files.length) return
    setBusy(true)
    setError('')
    try {
      if (files.length > limit || files.reduce((size, file) => size + file.size, 0) > 10_000_000) {
        throw new Error('Select up to 5,000 JSON files with a total size of 10 MB or less.')
      }
      const records: unknown[] = []
      for (const file of files) {
        let document: unknown
        try { document = JSON.parse(await file.text()) }
        catch { throw new Error(`${file.name}: expected valid JSON.`) }
        const lines = Array.isArray(document) ? document : [document]
        if (records.length + lines.length > limit) throw new Error('Provide no more than 5,000 claim records.')
        for (const line of lines) records.push(line)
      }
      analyze(records)
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not read the claims.')
    } finally {
      setBusy(false)
    }
  }

  function manual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try { analyze([Object.fromEntries(new FormData(event.currentTarget))]) }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Could not analyze the line.') }
  }

  const visible = filter === 'All' ? results : results.filter(result => result.recommendation === filter)
  return <>
    <h1>Batch claim review</h1>
    <p className="subtitle">Analyze up to 5,000 fictional claim lines in this browser. Recommendations are for analyst review. Use synthetic records only.</p>
    <div className="detail-grid">
      <section className="panel section">
        <h2>Claim documents</h2>
        <p>Upload JSON files containing claim objects or arrays of claim objects. Use the sample to see the schema.</p>
        <label className="batch-upload">Upload claim documents<input type="file" accept=".json,application/json" multiple disabled={busy}
          onChange={event => { void upload(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }}/></label>
        <div className="guide-actions">
          <button className="primary" disabled={busy} onClick={() => analyze(examples(limit))}>Analyze 5,000 sample lines</button>
          <button className="text-button" onClick={() => download('sample-claim-lines.json', examples(limit))}>Download sample JSON</button>
        </div>
      </section>
      <section className="panel section">
        <h2>Enter one claim line</h2>
        <form className="batch-form" onSubmit={manual}>
          <label>Line ID<input name="id" required maxLength={100}/></label>
          <label>Payer<input name="payer" defaultValue="Northstar Health" required maxLength={100}/></label>
          <label>Procedure<input name="procedure" defaultValue="IMG-01" required maxLength={100}/></label>
          <label>Service date<input name="service" type="date" required/></label>
          <label>Coverage active<select name="eligible"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
          <label>Confirmed duplicate<select name="duplicate"><option value="unknown">Unknown</option><option value="no">No</option><option value="yes">Yes</option></select></label>
          <label>Authorization present<select name="authorization"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
          <label>Authorization approval date<input name="authorizationDate" type="date"/></label>
          <button className="primary" disabled={busy}>Analyze line</button>
        </form>
      </section>
    </div>
    {(busy || results.length > 0) && <p className="batch-status" role="status">{busy ? 'Reading claim documents…' : `${results.length.toLocaleString('en-US')} ${results.length === 1 ? 'line' : 'lines'} analyzed`}</p>}
    {error && <p className="notice" role="alert">{error}</p>}
    {results.length > 0 && <section className="panel section decision">
      <h2>Recommendations</h2>
      <p>{verdicts.map(verdict => `${verdict} · ${results.filter(result => result.recommendation === verdict).length.toLocaleString('en-US')}`).join(' | ')}</p>
      <div className="guide-actions">
        <select aria-label="Filter recommendations" value={filter} onChange={event => {setFilter(event.target.value as typeof filter); setPage(0)}}>
          <option>All</option>{verdicts.map(verdict => <option key={verdict}>{verdict}</option>)}
        </select>
        <button className="text-button" onClick={() => download('claim-recommendations.json', results)}>Export recommendations</button>
      </div>
      <div className="scroll batch-results"><table>
        <thead><tr><th>Line</th><th>Recommendation</th><th>Evidence</th><th>Policy</th></tr></thead>
        <tbody>{visible.slice(page * 25, (page + 1) * 25).map(result => <tr key={result.line.id}>
          <td>{result.line.id}</td><td>{result.recommendation}</td><td>{result.reasons.join(' ')}</td>
          <td>{result.policy && <details><summary>{result.policy.id}</summary><p>{result.policy.excerpt}</p></details>}</td>
        </tr>)}</tbody>
      </table></div>
      {!visible.length && <p>No recommendations match this filter.</p>}
      {visible.length > 25 && <div className="guide-actions">
        <button className="text-button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
        <span>Page {page + 1} of {Math.ceil(visible.length / 25)}</span>
        <button className="text-button" disabled={(page + 1) * 25 >= visible.length} onClick={() => setPage(page + 1)}>Next</button>
      </div>}
    </section>}
  </>
}
