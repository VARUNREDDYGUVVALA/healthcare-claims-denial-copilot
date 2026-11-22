import { useEffect, useId, useMemo, useState } from 'react'
import type { BatchPolicy } from './batch'

const DAY = 86_400_000
const dateAt = (day: number) => new Date(day * DAY).toISOString().slice(0, 10)
const dayOf = (iso: string) => Date.parse(iso) / DAY
export const daysBetween = (from: string, to: string) => dayOf(to) - dayOf(from)
function localToday() {
  const now = new Date()
  return dateAt(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY)
}
const shortDate = (iso: string) => new Date(iso).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'})

export type LedgerLine = {
  id: string; payer: string; procedure: string; service: string; submitted: string; received: string
  rules_score: number; risk: number; holdout: boolean; status: string
  amount: number; reason: string; staged: boolean
  authorizations: {recorded: string}[]
}

export function rankDaily(lines: LedgerLine[], capacity: number) {
  const days = new Map<string, LedgerLine[]>()
  for (const line of lines) {
    if (!line.holdout) continue
    const day = days.get(line.submitted) ?? []
    day.push(line)
    days.set(line.submitted, day)
  }
  const by = (key: 'risk' | 'rules_score') => (a: LedgerLine, b: LedgerLine) => b[key] - a[key] || a.id.localeCompare(b.id)
  return Array.from(days, ([date, records]) => {
    const ranked = [...records].sort(by('risk')).slice(0, capacity)
    const denied = records.filter(line => line.status === 'denied').length
    const caught = ranked.filter(line => line.status === 'denied').length
    const rulesCaught = [...records].sort(by('rules_score')).slice(0, capacity).filter(line => line.status === 'denied').length
    return {date, caught, missed: denied - caught, approved: ranked.length - caught, rulesCaught}
  }).sort((a, b) => a.date.localeCompare(b.date))
}

function changedWords(left: string, right: string) {
  const a = left.split(/\s+/)
  const b = right.split(/\s+/)
  const score = Array.from({length: a.length + 1}, () => Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      score[i][j] = a[i] === b[j] ? 1 + score[i + 1][j + 1] : Math.max(score[i + 1][j], score[i][j + 1])
    }
  }
  const sharedA = new Set<number>()
  const sharedB = new Set<number>()
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {sharedA.add(i++); sharedB.add(j++)}
    else if (score[i + 1][j] >= score[i][j + 1]) i++
    else j++
  }
  return [a.map((word, index) => ({word, changed: !sharedA.has(index)})),
          b.map((word, index) => ({word, changed: !sharedB.has(index)}))]
}

export function PolicyRuler({line, policies, showResponse}: {line: LedgerLine; policies: BatchPolicy[]; showResponse: boolean}) {
  const [selectedDay, setSelectedDay] = useState(dayOf(line.service))
  const id = useId()
  const year = line.service.slice(0, 4)
  const versions = policies.filter(policy => policy.payer === line.payer && policy.procedure === line.procedure && policy.starts.slice(0, 4) === year)
    .sort((a, b) => a.starts.localeCompare(b.starts))
  const lower = dayOf(year + '-01-01')
  const endDate = line.service < year + '-07-01' && versions.every(policy => policy.ends <= year + '-07-01')
    ? year + '-07-01' : Number(year) + 1 + '-01-01'
  const upper = dayOf(endDate)
  const service = dateAt(selectedDay)
  const resolved = versions.find(policy => policy.starts <= service && service < policy.ends)
  const position = (day: number) => 30 + 740 * (day - lower) / (upper - lower)
  const x = (iso: string) => position(dayOf(iso))
  const months = Array.from({length: endDate.startsWith(year) ? 6 : 12}, (_, i) => new Date(Date.UTC(Number(year), i, 1)))
  const pins = [
    ...(line.authorizations[0] ? [{date: line.authorizations[0].recorded, label: 'Authorization recorded', y: 50, dx: 7, anchor: 'start'}] : []),
    {date: service, label: 'Service date', y: 89, dx: x(service) < 140 ? 8 : -9, anchor: x(service) < 140 ? 'start' : 'end'},
    {date: line.submitted, label: 'Submitted', y: 187, dx: 6, anchor: 'start'},
    ...(showResponse ? [{date: line.received, label: 'Payer response', y: 210, dx: 6, anchor: 'start'}] : []),
  ].filter(pin => dayOf(pin.date) >= lower && dayOf(pin.date) < upper)
  const comparison = versions.length === 2 ? changedWords(versions[0].excerpt, versions[1].excerpt) : null
  const target = resolved ? (x(resolved.starts) + x(resolved.ends)) / 2 : 0
  return <section className="panel section ledger-ruler">
    <h2>Policy time ruler</h2>
    <p>{showResponse ? 'The recorded service date determines the original policy. Scrub to explore another date.' : 'Explore the policy by service date before revealing the payer response.'}</p>
    <div className="scroll ruler-scroll" tabIndex={0} aria-label="Scrollable policy timeline">
      <svg viewBox="0 0 800 225" role="img" aria-label={`Policy timeline for ${year}. Selected service date ${service}.`}>
        <defs><marker id={id} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="none" stroke="currentColor"/></marker></defs>
        <line x1="30" x2="770" y1="145" y2="145" className="ruler-tick"/>
        {Array.from({length: Math.ceil((upper - lower) / 7)}, (_, i) => position(lower + 7 * i)).map(point =>
          <line key={point} x1={point} x2={point} y1="145" y2="152" className="ruler-tick"/>)}
        {months.map(month => <g key={month.toISOString()}><line x1={x(month.toISOString().slice(0, 10))} x2={x(month.toISOString().slice(0, 10))} y1="145" y2="158" className="ruler-tick"/><text x={x(month.toISOString().slice(0, 10)) + 4} y="171">{month.toLocaleDateString('en', {month: 'short', timeZone: 'UTC'})}</text></g>)}
        {versions.map(policy => <g key={policy.id}>
          <rect x={x(policy.starts)} y="112" width={x(policy.ends) - x(policy.starts)} height="33" className={policy.id.endsWith('-v1') ? 'version-one' : 'version-two'}/>
          <text x={(x(policy.starts) + x(policy.ends)) / 2} y="133" textAnchor="middle">{policy.id.endsWith('-v1') ? 'Version 1' : 'Version 2'}</text>
        </g>)}
        {resolved && <path key={service} d={`M ${x(service)} 108 Q ${(x(service) + target) / 2} 20 ${target} 110`} markerEnd={`url(#${id})`} className="ruler-arc"/>}
        {pins.map(pin => <g key={pin.label} className={pin.label === 'Service date' ? 'ruler-pin service-pin' : 'ruler-pin'}>
          <line x1={x(pin.date)} x2={x(pin.date)} y1={pin.y < 112 ? pin.y + 5 : 145} y2={pin.y < 112 ? 112 : pin.y - 4}/>
          <text x={x(pin.date) + pin.dx} y={pin.y} textAnchor={pin.anchor as 'start' | 'end'}>{shortDate(pin.date)} · {pin.label}</text>
        </g>)}
      </svg>
    </div>
    <label className="ledger-control">Explore service date <input aria-label="Explore service date" type="range" min={lower} max={upper - 1} value={selectedDay} onChange={event => setSelectedDay(Number(event.target.value))}/></label>
    <p aria-live="polite">{shortDate(service)} {year} · {resolved ? `${resolved.id} · ${resolved.section}` : 'No policy section covers this date.'}
      {service !== line.service && <> · Hypothetical <button type="button" className="text-button" onClick={() => setSelectedDay(dayOf(line.service))}>Reset service date</button></>}</p>
    {service !== line.service && resolved && <blockquote><p>{resolved.excerpt}</p><small>{resolved.payer} · {resolved.id} · {resolved.starts} to before {resolved.ends}</small></blockquote>}
    {comparison && <details className="version-diff" open={line.id === 'CLM-LEDGER-1' || undefined}>
      <summary>Compare policy versions</summary>
      <div className="detail-grid">{versions.map((policy, index) => <blockquote key={policy.id}>
        <strong>{policy.id}</strong><p>{comparison[index].map(({word, changed}, wordIndex) =>
          <span key={wordIndex}>{changed ? <mark>{word}</mark> : word}{' '}</span>)}</p>
      </blockquote>)}</div>
    </details>}
  </section>
}

const reasonLabels: Record<string, string> = {AUTH: 'Authorization', ELIG: 'Eligibility', DUP: 'Duplicate'}
const money = (amount: number) => amount.toLocaleString('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 0})

export function ManagerLedger({lines, days, reviewed, capacity, unmatched}: {
  lines: LedgerLine[]; days: ReturnType<typeof rankDaily>; reviewed: {line_id: string}[]; capacity: number; unmatched: number
}) {
  const counts = useMemo(() => {
    const totals = new Map<string, number>()
    const activity = new Map<string, number>()
    const byId = new Map(lines.map(line => [line.id, line]))
    for (const line of lines) {
      if (!line.staged && line.status === 'denied') totals.set(line.reason, (totals.get(line.reason) ?? 0) + line.amount)
    }
    for (const decision of reviewed) {
      const line = byId.get(decision.line_id)
      if (line) activity.set(line.submitted, (activity.get(line.submitted) ?? 0) + 1)
    }
    return {totals, activity}
  }, [lines, reviewed])
  const [today, setToday] = useState(localToday)
  useEffect(() => {
    const timer = window.setInterval(() => setToday(localToday()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const matchingDay = days.findIndex(day => day.date === today)
  const chartEnd = matchingDay === -1 ? days.length : matchingDay + 1
  const chartDays = days.slice(Math.max(0, chartEnd - 21), chartEnd)
  const max = Math.max(capacity, ...chartDays.map(day => day.caught + day.missed + day.approved), 1)
  const maxAmount = Math.max(1, ...counts.totals.values())
  const first = counts.activity.size ? Math.min(...Array.from(counts.activity.keys(), dayOf)) : dayOf(today)
  const last = counts.activity.size ? Math.max(...Array.from(counts.activity.keys(), dayOf)) : first
  const grid = Array.from({length: last - first + 1}, (_, index) => dateAt(first + index))
  return <>
    <section className="panel section ledger-manager">
      <h2>Daily review capacity</h2>
      <p>Holdout simulation by submission date. Denied and reviewed · Denied and missed · Reviewed and approved</p>
      <p>Today: {today}{matchingDay < 0 ? ' · Outside this dataset’s holdout dates' : ''}</p>
      <div className="daily-chart scroll" role="list" aria-label="Daily holdout results">
        <div className="daily-columns">
          <div className="daily-cut" style={{bottom: `calc(1.65rem + (100% - 1.65rem) * ${capacity / max})`}}><span>{capacity} / day</span></div>
          {chartDays.map(day => <div key={day.date} className={day.date === today ? 'daily-day today' : 'daily-day'} role="listitem" title={`${day.date}: ${day.caught} denied and reviewed, ${day.missed} missed, ${day.approved} reviewed and approved`}>
            <div className="daily-bars"><i style={{height: `${100 * day.caught / max}%`}}/><i style={{height: `${100 * day.missed / max}%`}}/><i style={{height: `${100 * day.approved / max}%`}}/></div>
            <small>{shortDate(day.date)}</small>
          </div>)}
        </div>
      </div>
    </section>
    <div className="detail-grid ledger-manager">
      <section className="panel section"><h2>Denial reasons by billed amount</h2>
        {Array.from(counts.totals, ([code, amount]) => <div className="reason-bar" key={code}>
          <span>{reasonLabels[code] ?? code}</span><i style={{width: `${100 * amount / maxAmount}%`}}/><strong>{money(amount)}</strong>
        </div>)}
      </section>
      <section className="panel section"><h2>Review activity</h2><p>Saved reviews grouped by claim submission date</p>
        <div className="heat-grid" role="img" aria-label={`${reviewed.length} reviews. ${first === last ? dateAt(first) : dateAt(first) + ' to ' + dateAt(last)}.`}>
          {grid.map(date => <span key={date} className={date === today ? 'heat-cell today' : 'heat-cell'} title={`${date}: ${counts.activity.get(date) ?? 0} reviews`} style={{opacity: Math.min(.95, .24 + (counts.activity.get(date) ?? 0) * .36)}}/>)}
        </div>
      </section>
    </div>
    <section className="panel section unmatched-tray"><h2>Unmatched response tray</h2><p>{unmatched} payer response{unmatched === 1 ? '' : 's'} without a matching claim line. Open Unmatched responses in the sidebar to review.</p></section>
  </>
}
