import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'

type SummaryRow = {
  claims: number; claim_lines: number; denied_lines: number; pending_lines: number
  denial_pct_of_finalized: number; billed_cents: number; paid_cents: number
}
type Annual = SummaryRow & {service_year: number}
type Monthly = SummaryRow & {service_month: string}
type Analysis = {
  claims: number; claim_lines: number; members: number; months: number; start: string; end_exclusive: string
  feeds: Record<string, string>; source_year_summary: (Annual & {source_feed: string})[]
  annual_summary: Annual[]; monthly_summary: Monthly[]
  annual_denial_reasons: {service_year: number; reason_code: string; denied_lines: number; denied_billed_cents: number}[]
}

const count = new Intl.NumberFormat('en-US')
const dollars = new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 0})
const monthLabel = new Intl.DateTimeFormat('en-US', {month: 'short', year: 'numeric', timeZone: 'UTC'})
const risk = (rate: number) => rate.toFixed(2) + '%'
const reasonLabels: Record<string, string> = {AUTH: 'Authorization', DUP: 'Duplicate', ELIG: 'Eligibility'}
const archiveName = 'claims-2023-2025-extra-large.zip'
const archiveLink = location.hostname.endsWith('.github.io')
  ? import.meta.env.BASE_URL + archiveName
  : 'https://varunreddyguvvala.github.io/healthcare-claims-denial-copilot/' + archiveName

export function ThreeYearAnalysis() {
  const [data, setData] = useState<Analysis>()
  const [selectedYear, setSelectedYear] = useState<number>()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(import.meta.env.BASE_URL + 'three-year-analysis.json', {signal: controller.signal})
      .then(response => {
        if (!response.ok) throw Error('Analysis unavailable')
        return response.json()
      })
      .then((report: Analysis) => {
        setSelectedYear(report.annual_summary.at(-1)?.service_year)
        setData(report)
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [])

  if (!data) return <>
    <h1>Three-year analysis</h1>
    <p role={failed ? 'alert' : 'status'}>{failed ? 'The dataset summary could not be loaded.' : 'Loading dataset summary…'}</p>
  </>

  const monthly = data.monthly_summary.filter(row => Number(row.service_month.slice(0, 4)) === selectedYear)
  const reasons = data.annual_denial_reasons.filter(row => row.service_year === selectedYear)
  const maxRate = Math.max(1, ...data.monthly_summary.map(row => row.denial_pct_of_finalized))
  const end = new Date(Date.parse(data.end_exclusive) - 86400000)
  return <>
    <div className="page-heading analysis-heading"><div>
      <h1>Three-year analysis</h1>
      <p>{monthLabel.format(new Date(data.start))}–{monthLabel.format(end)} · Synthetic service-date cohorts</p>
    </div><a className="primary" href={archiveLink} download><Download size={17}/> Download full dataset</a></div>
    <div className="stats analysis-stats">
      {[[data.claims, 'Distinct claims'], [data.claim_lines, 'Claim lines'], [data.members, 'Fictional members'], [data.months, 'Service months']].map(([total, label]) =>
        <div className="stat" key={label}><span>{label}</span><strong>{count.format(Number(total))}</strong></div>)}
    </div>
    <section className="panel section">
      <h2>Annual outcomes</h2>
      <p>Denial rate uses finalized lines. Pending lines are excluded.</p>
      <div className="scroll"><table>
        <thead><tr><th>Service year</th><th>Claims</th><th>Claim lines</th><th>Denied</th><th>Pending</th><th>Denial rate</th><th>Billed</th><th>Simulated paid</th></tr></thead>
        <tbody>{data.annual_summary.map(row => <tr key={row.service_year}>
          <th scope="row">{row.service_year}</th><td>{count.format(row.claims)}</td><td>{count.format(row.claim_lines)}</td>
          <td>{count.format(row.denied_lines)}</td><td>{count.format(row.pending_lines)}</td><td>{risk(row.denial_pct_of_finalized)}</td>
          <td>{dollars.format(row.billed_cents / 100)}</td><td>{dollars.format(row.paid_cents / 100)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel section ledger-manager" aria-label="Monthly denial trend">
      <h2>Monthly denial trend</h2>
      <label className="ledger-control model-split">Service year
        <select value={selectedYear} onChange={event => setSelectedYear(Number(event.target.value))}>
          {data.annual_summary.map(row => <option key={row.service_year}>{row.service_year}</option>)}
        </select>
      </label>
      <div className="analysis-months" role="list" aria-label={`Denial rates by month in ${selectedYear}`}>
        {monthly.map(row => <div key={row.service_month} role="listitem" className="analysis-month">
          <span>{monthLabel.format(new Date(row.service_month))}</span>
          <div aria-hidden="true"><i style={{width: `${row.denial_pct_of_finalized / maxRate * 100}%`}}/></div>
          <strong>{risk(row.denial_pct_of_finalized)}</strong>
          <span>{count.format(row.denied_lines)} denied</span>
        </div>)}
      </div>
    </section>
    <section className="panel section ledger-manager">
      <h2>Source feeds · {selectedYear}</h2>
      <p>Source feeds are fictional provider groups in the same synthetic dataset.</p>
      <div className="scroll"><table>
        <thead><tr><th>Feed</th><th>Claims</th><th>Claim lines</th><th>Denied</th><th>Denial rate</th></tr></thead>
        <tbody>{data.source_year_summary.filter(row => row.service_year === selectedYear).map(row => <tr key={row.source_feed}>
          <th scope="row">{data.feeds[row.source_feed]}</th><td>{count.format(row.claims)}</td><td>{count.format(row.claim_lines)}</td>
          <td>{count.format(row.denied_lines)}</td><td>{risk(row.denial_pct_of_finalized)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel section ledger-manager">
      <h2>Denied lines by reason · {selectedYear}</h2>
      <div className="scroll"><table>
        <thead><tr><th>Reason</th><th>Denied lines</th><th>Billed on denied lines</th></tr></thead>
        <tbody>{reasons.map(row => <tr key={row.reason_code}>
          <th scope="row">{reasonLabels[row.reason_code] ?? row.reason_code}</th><td>{count.format(row.denied_lines)}</td>
          <td>{dollars.format(row.denied_billed_cents / 100)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
  </>
}
