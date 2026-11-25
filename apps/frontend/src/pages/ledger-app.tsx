import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, BookOpen, ChartNoAxesCombined, ChevronRight, CircleHelp, ClipboardList, FileCheck2, Files, FlaskConical, Layers3, ListFilter, Search } from 'lucide-react'
import { BatchReview } from '../components/batch'
import type { BatchPolicy } from '../components/batch'
import { Investigation } from '../components/investigation'
import { ModelGovernance } from '../components/model-governance'
import { VoiceQuestion } from '../components/voice-question'
import { daysBetween, ManagerLedger, PolicyRuler, rankDaily } from '../components/ledger'
import '../style.css'
import '../ledger.css'

type Outcome = 'approved' | 'denied' | 'pending'
type Decision = { id: string; line_id: string; action: string; note: string }
type Policy = { id: string; section: string; excerpt: string; starts: string; ends: string }
type EvidenceRecord = { id: string; starts: string; ends: string; recorded: string }
type Line = {
  id: string; claim_id: string; description: string; procedure: string; payer: string; member: string
  service: string; submitted: string; amount: number; risk: number; staged: boolean; rules_score: number; holdout: boolean; reason: string
  status: Outcome; claim_status: string; received: string
  eligibility: EvidenceRecord[]; authorizations: EvidenceRecord[]; duplicates: string[] | null
  explanation: { reason: string; code: string; policy: Policy | null; action: string } | null
}
type Score = { pr_auc: number; precision_at_capacity: number; recall_at_capacity: number; roc_auc: number; brier_score?: number }
type Demo = {
  lines: Line[]; decisions: Decision[]
  policies: BatchPolicy[]
  months: { month: string; finalized: number; denied: number; reviews: number }[]
  unmatched: { id: string; line_id: string; reason: string; status: string; received: string }[]
  metrics: { model: Score; rules: Score; capacity: number; cutoff: string; holdout_lines: number }
}
type Local = { revealed: string[]; decisions: Decision[] }
const viewLabels = {queue: 'Claim queue', dashboard: 'Manager dashboard', unmatched: 'Unmatched responses', batch: 'Batch claim review'}
type View = keyof typeof viewLabels
type QueueFilter = 'all' | 'pre-submission' | Outcome
const queuePageSize = 25
const localApiMode = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) &&
  new URLSearchParams(location.search).get('mode') === 'api'
const formatCount = (value: number) => value.toLocaleString('en-US')
const key = 'claims-copilot-v1'
const guide = 'CLM-GUIDE-1'
const early = 'CLM-EARLY-1'
const ledgerCase = 'CLM-LEDGER-1'
const actions = ['Verify authorization', 'Verify coverage', 'Check for duplicate', 'Request payer clarification', 'Close review']
const percent = (n: number, digits = 0) => new Intl.NumberFormat('en', {style:'percent', maximumFractionDigits: digits}).format(n)
const currency = (n: number) => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0}).format(n)
const prettyDate = (value: string) => new Date(value + 'T00:00:00Z').toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric', timeZone:'UTC'})
const reasonName: Record<string, string> = {AUTH:'Prior authorization required', ELIG:'Coverage inactive on service date', DUP:'Duplicate service'}

function readLocal(): Local {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? 'null') as Local | null
    if (value && Array.isArray(value.revealed) && Array.isArray(value.decisions)) return value
  } catch { /* Start fresh if storage is unavailable or unreadable. */ }
  return {revealed: [], decisions: []}
}

function App() {
  const [demo, setDemo] = useState<Demo>()
  const [error, setError] = useState('')
  const [storageError, setStorageError] = useState(false)
  const [local, setLocal] = useState<Local>(readLocal)
  const [view, setView] = useState<View>('queue')
  const [selected, setSelected] = useState('')
  const [search, setSearch] = useState('')
  const [queuePage, setQueuePage] = useState(0)
  const [capacity, setCapacity] = useState(3)
  const [deferred, setDeferred] = useState<string[]>([])
  const [filter, setFilter] = useState<QueueFilter>('all')
  useEffect(() => {
    fetch(import.meta.env.BASE_URL + 'demo.json')
      .then(response => { if (!response.ok) throw Error(); return response.json() })
      .then(setDemo).catch(() => setError('Could not load the demo data. Reload the page to retry.'))
  }, [])
  function persist(next: Local) {
    setLocal(next)
    try { localStorage.setItem(key, JSON.stringify(next)); setStorageError(false) }
    catch { setStorageError(true) }
  }
  function navigate(next: View) {
    setView(next); setSelected('')
    window.scrollTo(0, 0)
  }
  function open(id: string) {
    setView('queue'); setSelected(id)
    window.scrollTo(0, 0)
  }
  const status = (line: Line) => line.staged && !local.revealed.includes(line.claim_id) ? 'pre-submission' : line.status
  const lines = demo?.lines ?? []
  const daily = useMemo(() => rankDaily(demo?.lines ?? [], capacity), [demo, capacity])
  const line = lines.find(item => item.id === selected)
  const queue = lines.filter(item => (filter === 'all' || status(item) === filter) &&
    [item.id, item.payer, item.procedure, item.description].join(' ').toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => b.risk - a.risk || a.id.localeCompare(b.id))
  const pageCount = Math.ceil(queue.length / queuePageSize)
  const currentPage = Math.min(queuePage, Math.max(0, pageCount - 1))
  const pageStart = currentPage * queuePageSize
  const pageRows = queue.slice(pageStart, pageStart + queuePageSize)
  const activeRanks = new Set(queue.filter(item => !deferred.includes(item.id)).slice(0, capacity).map(item => item.id))
  const cutAfter = queue.findIndex((item, index) => index >= capacity && !deferred.includes(item.id) && !activeRanks.has(item.id))
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><Activity size={23}/></div><div>Ledger<small>Claims denial copilot</small></div></div>
      <div className="workspace"><div className="workspace-icon"><Layers3 size={16}/></div><div>Willow Creek Health<small>Fictional provider</small></div></div>
      <div className="nav-label">Workspace</div>
      <nav aria-label="Main navigation">
        <button className={view === 'batch' ? 'active' : ''} onClick={() => navigate('batch')}><FileCheck2 size={18}/> Batch claim review</button>
        <button className={view === 'queue' ? 'active' : ''} onClick={() => navigate('queue')}><ClipboardList size={18}/> Claim queue</button>
        <button className={view === 'dashboard' ? 'active' : ''} onClick={() => navigate('dashboard')}><ChartNoAxesCombined size={18}/> Manager dashboard</button>
        <button className={view === 'unmatched' ? 'active' : ''} onClick={() => navigate('unmatched')}><Files size={18}/> Unmatched responses</button>
      </nav>
      <div className="sidebar-bottom"><FlaskConical size={17}/><div>Portfolio demo<small>Synthetic data only</small></div></div>
    </aside>
    <div className="content">
      <header className="topbar"><span>Workspace <ChevronRight size={14}/> <strong>{viewLabels[view]}</strong></span><span className="simulation"><i/> Single-browser simulation</span></header>
      <main>
        {storageError && <p className="notice" role="alert">Browser storage is unavailable. Changes will last until this page reloads.</p>}
        {!demo && <p role={error ? 'alert' : 'status'}>{error || 'Loading claims…'}</p>}
        {demo && view === 'queue' && (line ?
          <Detail key={line.id} line={line} status={status(line)} policies={demo.policies}
            decisions={[...demo.decisions, ...local.decisions].filter(item => item.line_id === line.id)}
            back={() => navigate('queue')} earlyCase={() => open(line.claim_id === 'CLM-GUIDE' ? early : guide)}
            reveal={() => persist({...local, revealed: [...local.revealed, line.claim_id]})}
            save={(action, note) => persist({...local, decisions: [...local.decisions, {id: crypto.randomUUID(), line_id: line.id, action, note}]})}/> :
          <>
            <div className="page-heading"><div><h1>Claim queue</h1><p>Prioritize claim lines by denial risk and review payer responses.</p></div></div>
            <section className="guide">
              <div className="guide-content">
                <div className="guide-label"><BookOpen size={15}/> Guided walkthrough</div>
                <h2>Follow an imaging claim</h2>
                <p>Start with a flagged MRI line, simulate the payer response, and review the policy in effect on the service date.</p>
                <div className="guide-actions"><button className="primary" onClick={() => open(guide)}>Start guided case <ArrowRight size={16}/></button><button className="text-button" onClick={() => open(early)}>Open earlier policy case <ArrowUpRight size={15}/></button><button className="text-button" onClick={() => open(ledgerCase)}>Review March 2026 case <ArrowUpRight size={15}/></button></div>
              </div>
            </section>
            <div className="stats">
              <Stat icon={<ClipboardList size={19}/>} label="Claim lines" value={formatCount(lines.length)} detail="In this demo queue"/>
              <Stat icon={<Activity size={19}/>} label="High-risk lines" value={formatCount(lines.filter(item => item.risk >= .65).length)} detail="Predicted risk ≥ 65%"/>
              <Stat icon={<FileCheck2 size={19}/>} label="Reviews saved" value={local.decisions.length} detail="In this browser"/>
            </div>
            <section className="panel">
              <div className="panel-heading"><div><h2>Ranked claim lines</h2><p>{formatCount(queue.length)} of {formatCount(lines.length)} lines</p></div><div className="filters"><label className="search"><Search size={16}/><input aria-label="Search claim lines" placeholder="Search claims" value={search} onChange={e => {setSearch(e.target.value); setQueuePage(0)}} onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}/></label><label className="search"><ListFilter size={16}/><select aria-label="Filter by status" value={filter} onChange={e => {setFilter(e.target.value as QueueFilter); setQueuePage(0)}}><option value="all">All statuses</option><option value="pre-submission">Pre-submission</option><option value="denied">Denied</option><option value="approved">Approved</option><option value="pending">Pending</option></select></label></div></div>
              <div className="queue-capacity">
                <label className="ledger-control">Daily review capacity <input type="range" aria-label="Daily review capacity" min={1} max={20} value={capacity} onChange={event => setCapacity(Number(event.target.value))}/> <output>{capacity} lines</output></label>
                <p aria-live="polite">Holdout denials caught · Model {daily.reduce((sum, day) => sum + day.caught, 0)} · Rules {daily.reduce((sum, day) => sum + day.rulesCaught, 0)}</p>
              </div>
              {pageCount > 1 && <div className="queue-pagination" role="group" aria-label="Claim queue pagination">
                <span aria-live="polite">Page {currentPage + 1} of {pageCount} · Lines {formatCount(pageStart + 1)}–{formatCount(pageStart + pageRows.length)}</span>
                <div>
                  <button className="text-button" disabled={currentPage === 0} onClick={() => setQueuePage(currentPage - 1)}>Previous page</button>
                  <button className="text-button" disabled={currentPage + 1 === pageCount} onClick={() => setQueuePage(currentPage + 1)}>Next page</button>
                </div>
              </div>}
              <div className="scroll queue-scroll"><table><thead><tr><th>Claim line</th><th>Payer</th><th>Service date</th><th>Denial risk <ArrowDown size={13}/></th><th>Line status</th><th><span className="sr-only">Open line</span></th></tr></thead>
              <tbody>{pageRows.map((item, index) => <tr key={item.id}
                className={`ledger-row ${item.risk >= .65 ? 'high-risk' : ''} ${index + pageStart === cutAfter ? 'capacity-cut' : ''}`}>
                <td><button className="table-link" onClick={() => open(item.id)}>{item.id}</button><small>{item.description} · {item.procedure}</small>
                  <small className="evidence-chip">{item.authorizations[0] ? `Authorization recorded ${Math.max(0, daysBetween(item.authorizations[0].recorded, item.service))} days before service` : item.procedure === 'IMG-01' ? 'Authorization absent from extract' : item.duplicates?.length ? 'Possible duplicate' : 'Check coverage evidence'}</small>
                </td><td>{item.payer}</td><td>{prettyDate(item.service)}</td><td><Risk risk={item.risk}/></td><td><Status value={status(item)}/></td>
                <td><div className="row-actions"><button className="text-button" aria-label={'Open ' + item.id} onClick={() => open(item.id)}>Review</button>
                  <button className="text-button" onClick={() => setDeferred(items => items.includes(item.id) ? items.filter(id => id !== item.id) : [...items, item.id])}>{deferred.includes(item.id) ? 'Restore' : 'Defer'}</button></div></td>
              </tr>)}</tbody></table></div>
              {!queue.length && <p className="empty">No claim lines match your filters.</p>}
            </section>
          </>)}
        {demo && view === 'batch' && <BatchReview policies={demo.policies}/>}
        {demo && view === 'dashboard' && <Dashboard demo={demo} reviews={local.decisions.length}/>}
        {demo && view === 'dashboard' && <ManagerLedger lines={lines} days={daily} reviewed={[...demo.decisions, ...local.decisions]} capacity={capacity} unmatched={demo.unmatched.length}/>}
        {demo && view === 'dashboard' && <ModelGovernance/>}
        {demo && view === 'unmatched' && <>
          <h1>Unmatched responses</h1><p className="subtitle">Payer responses whose claim line is absent from the billing extract.</p>
          <div className="panel scroll"><table><thead><tr><th>Response ID</th><th>Referenced line</th><th>Received</th><th>Status</th><th>Recorded reason</th></tr></thead><tbody>
            {demo.unmatched.map(item => <tr key={item.id}><td>{item.id}</td><td>{item.line_id}</td><td>{prettyDate(item.received)}</td><td><Status value={item.status}/></td><td>{reasonName[item.reason] || item.reason || '—'}</td></tr>)}
          </tbody></table></div>
        </>}
      </main>
    </div>
  </div>
}

function Stat({icon, label, value, detail}: {icon: React.ReactNode; label: string; value: number | string; detail: string}) {
  return <div className="stat"><div className="stat-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>
}
function Status({value}: {value: string}) {
  return <span className={'status ' + value.replaceAll(' ', '-')}><i/>{value}</span>
}
function Risk({risk}: {risk: number}) {
  return <span className={'risk ' + (risk >= .65 ? 'high' : risk >= .35 ? 'medium' : 'low')}><span className="risk-track"><span style={{width:percent(risk)}}/></span>{percent(risk, 1)}</span>
}

function Records({records, fallback}: {records: EvidenceRecord[]; fallback: string}) {
  if (!records.length) return fallback
  return records.map(record => <div className="evidence-record" key={record.id}><strong>{record.id}</strong>
    <small>{prettyDate(record.starts)} to before {prettyDate(record.ends)} · recorded {prettyDate(record.recorded)}</small>
  </div>)
}

function Detail({line, status, policies, decisions, back, reveal, save, earlyCase}: {
  line: Line; status: string; policies: BatchPolicy[]; decisions: Decision[]; back: () => void; reveal: () => void
  save: (action: string, note: string) => void; earlyCase: () => void
}) {
  const response = status === 'denied' ? line.explanation : null
  const [action, setAction] = useState('')
  const [note, setNote] = useState('')
  const [saved, setSaved] = useState(0)
  const hasConflictingAuthorization = response?.code === 'AUTH' && response.policy && line.authorizations.some(record =>
    record.starts <= line.service && line.service < record.ends && record.recorded < line.service)
  return <>
    <button className="text-button back" onClick={back}>← Back to claim queue</button>
    <div className="page-heading"><div><h1>{line.id}</h1><p>{line.description} · {line.procedure} · {line.payer}</p></div><Status value={status}/></div>
    {line.staged && <div className="notice guided-notice"><BookOpen size={18}/><div><strong>{line.claim_id === 'CLM-GUIDE' ? 'Guided imaging case' : 'Earlier policy case'}</strong><p>{status === 'pre-submission' ? (line.procedure === 'IMG-01' ? 'The MRI is flagged for review. Check the authorization evidence before simulating the payer response.' : 'Review the companion line before simulating the payer response.') : 'Compare the authorization policy in effect on each service date.'}</p></div><button className="text-button" onClick={earlyCase}>{line.claim_id === 'CLM-GUIDE' ? 'Open earlier policy case' : 'Open guided case'} <ArrowUpRight size={15}/></button></div>}
    <PolicyRuler line={line} policies={policies} showResponse={status !== 'pre-submission'}/>
    <div className="detail-grid">
      <section className="panel section"><h2><ClipboardList size={19}/> Claim evidence</h2>
        <dl><dt>Member</dt><dd>{line.member}</dd><dt>Service date</dt><dd>{prettyDate(line.service)}</dd><dt>Billed amount</dt><dd>{currency(line.amount)}</dd><dt>Denial risk</dt><dd><Risk risk={line.risk}/></dd>
        <dt>Eligibility extract</dt><dd>{<Records records={line.eligibility} fallback="No matching record in extract"/>}</dd>
        <dt>Authorization age</dt><dd>{line.authorizations[0] ? daysBetween(line.authorizations[0].recorded, line.service) + ' days at service' : 'Unknown'}</dd>
        <dt>Authorization extract</dt><dd>{<Records records={line.authorizations} fallback={line.procedure === 'IMG-01' ? 'No matching record in extract' : 'Not tracked for this procedure'}/>}</dd>
        <dt>Possible duplicate lines</dt><dd>{line.duplicates?.join(', ') || 'None in extract'}</dd>
        {status !== 'pre-submission' && <><dt>Overall claim</dt><dd><Status value={line.claim_status}/></dd></>}</dl>
      </section>
      <div className="case-response"><section className="panel section"><h2><Activity size={19}/> Payer response</h2>
        {status === 'pre-submission' ? <><p>No response has been recorded in this simulation.</p><button className="primary" onClick={reveal}>Simulate payer response <ArrowRight size={16}/></button></> :
          <><p>Recorded {prettyDate(line.received)}</p>{response ? <>
            <div className="reason"><strong>{response.reason}</strong><span>{response.code}</span></div>
            {hasConflictingAuthorization && <p className="notice">The recorded denial appears to conflict with the applicable policy and the authorization in the extract. Verify the authorization with the payer.</p>}
            <h3>Applicable payer policy</h3>
            {response.policy ? <blockquote><strong>{response.policy.section}</strong><p><mark>{response.policy.excerpt.split(/(?<=\.) /)[0]}</mark>{response.policy.excerpt.includes('. ') && ' ' + response.policy.excerpt.split(/(?<=\.) /).slice(1).join(' ')}</p><small>{line.payer} · {response.policy.id} · Effective {prettyDate(response.policy.starts)} to before {prettyDate(response.policy.ends)}</small></blockquote> : <p className="notice"><CircleHelp size={15}/> No matching policy passage was found for this payer, procedure, and service date.</p>}
            <h3>Suggested next step</h3><p>{response.action}</p>
          </> : <p><Status value={status}/></p>}</>}
      </section>
    {response && <section className="panel section decision"><h2><FileCheck2 size={19}/> Analyst decision</h2>
      <form onSubmit={e => {e.preventDefault(); save(action || response.action, note.trim()); setNote(''); setSaved(value => value + 1)}}>
        <label>Decision<select value={action || response.action} onChange={e => {setAction(e.target.value); setSaved(0)}}>{actions.map(item => <option key={item}>{item}</option>)}</select></label>
        <label>Review note<textarea value={note} maxLength={2000} onChange={e => {setNote(e.target.value); setSaved(0)}} placeholder="Optional review notes"/></label>
        <button className="primary" type="submit">Save decision</button>{saved > 0 && <span key={saved} className="saved decision-stamp" role="status">Decision saved</span>}
      </form>
      {decisions.length > 0 && <div className="history"><h3>Review history</h3>{decisions.map(item => <div key={item.id}><strong>{item.action}</strong>{item.note && <p>{item.note}</p>}</div>)}</div>}
    </section>}
    </div></div>
    <ClaimQuestions line={line} status={status} decisions={decisions}/>
    {response && localApiMode && <Investigation lineId={line.id}/>}
  </>
}

const sampleQuestions = [
  'What is the predicted denial risk?',
  'Why was this line denied?',
  'Which policy applied on the service date?',
  'Is there an authorization record?',
  'What should I do next?',
]

function answerClaimQuestion(question: string, line: Line, status: string, decisions: Decision[]): string {
  const query = question.toLowerCase().trim()
  const response = status === 'denied' ? line.explanation : null
  const unrevealed = status === 'pre-submission'
  const responseGap = unrevealed
    ? 'Simulate the payer response to see the recorded outcome and policy review.'
    : `The line is ${status}. There is no recorded denial reason.`
  const otherLine = query.match(/\bclm-[\w-]+/g)?.some(id => id !== line.id.toLowerCase() && id !== line.claim_id.toLowerCase())
  if (otherLine) return 'Open the claim line you want to ask about, then ask your question there.'

  const policy = response?.policy
  const details = {
    claim: `${line.id} is a ${line.description} line (${line.procedure}) on claim ${line.claim_id} for ${line.member}.`,
    payer: `The payer is ${line.payer}.`,
    amount: `The billed amount for this line is ${currency(line.amount)}.`,
    service: `The service date was ${prettyDate(line.service)}.`,
    submission: `The claim record lists ${prettyDate(line.submitted)} as the submission date.`,
    received: unrevealed ? responseGap : `The payer response was recorded on ${prettyDate(line.received)}.`,
    risk: `The model estimated a ${percent(line.risk, 1)} denial risk before submission based on the billing extract.`,
    outcome: response ? `The payer recorded “${response.reason}” (${response.code}) for ${line.id}.` : responseGap,
    claimStatus: unrevealed ? responseGap : `The overall claim status is ${line.claim_status}. This line is ${status}.`,
    policy: policy
      ? `${policy.id}, ${policy.section}, applied on ${prettyDate(line.service)}. It was effective from ${prettyDate(policy.starts)} to before ${prettyDate(policy.ends)}. “${policy.excerpt}”`
      : response
        ? `No matching policy passage was found for ${line.payer}, ${line.procedure}, and ${prettyDate(line.service)}. The payer recorded “${response.reason}” (${response.code}).`
        : responseGap,
    action: response ? `Suggested next step: ${response.action}.` : responseGap,
    auth: describeEvidence('authorization', line.authorizations),
    coverage: describeEvidence('eligibility', line.eligibility),
    duplicates: line.duplicates?.length
      ? `Possible duplicate lines: ${line.duplicates.join(', ')}.`
      : 'The billing extract has no possible duplicate lines.',
    reviews: !unrevealed && decisions.length
      ? `Saved review decisions: ${decisions.map(item => item.note ? `${item.action} (${item.note})` : item.action).join('; ')}.`
      : 'No review decisions are visible for this line.',
  }
  if (/\b(?:summari[sz]e|summary|overview|tell me about|what happened)\b/.test(query)) {
    return [details.claim, details.payer, details.service, details.amount, details.risk, details.outcome].join(' ')
  }

  const topics: [RegExp, keyof typeof details][] = [
    [/\b(?:billed|billing amount|amount|charge[ds]?|cost|how much)\b/, 'amount'],
    [/\b(?:service date|date of service|when (?:was|did) .*?(?:service|performed|visit|mri))\b/, 'service'],
    [/\b(?:submission date|date submitted|when .*submit)\b/, 'submission'],
    [/\b(?:when .*respond|when .*response|response date|date .*response|received)\b/, 'received'],
    [/\b(?:who (?:is|was) the payer|which payer|payer name|insurance company|insurer|payer)\b(?!\s+(?:response|record|reason|policy|denied))/, 'payer'],
    [/\b(?:procedure|cpt|member|patient|claim id|line id|what service)\b/, 'claim'],
    [/\b(?:risk|score|probability|flagged|chance)\b/, 'risk'],
    [/\b(?:why .*deni\w*|denial reason|denial code|recorded reason|payer response|approved|denied|outcome|line status)\b/, 'outcome'],
    [/\b(?:claim status|overall status|status of (?:the|this) claim|partially denied)\b/, 'claimStatus'],
    [/\b(?:policy|policies|requirement|requirements|rule|version|effective date)\b/, 'policy'],
    [/\b(?:next step|recommend\w*|suggest\w*|what should|resubmit|can i appeal)\b/, 'action'],
    [/\b(?:auth|authorization|preauthorization|approval record)\b/, 'auth'],
    [/\b(?:eligibility|coverage|covered)\b/, 'coverage'],
    [/\bduplicates?\b/, 'duplicates'],
    [/\b(?:review history|saved (?:decision|review)|review note|analyst decision)\b/, 'reviews'],
  ]
  const matches = topics.filter(([pattern]) => pattern.test(query)).map(([, topic]) => topic)
  if (/\b(?:paid|payment|reimbursed|reimbursement|appeal deadline|phone number|address|date of birth)\b/.test(query)) {
    return 'The demo records do not include that information. They include billed charges, payer outcomes, policy excerpts, and review decisions.'
  }
  return matches.length
    ? [...new Set(matches.map(topic => details[topic]))].join(' ')
    : 'I couldn’t find an answer in the selected claim records. Ask about the billed amount, dates, payer, denial reason, policy, billing evidence, or next step. Try one of the sample questions.'
}

function describeEvidence(kind: string, records: EvidenceRecord[]): string {
  if (!records.length) return `The billing extract has no matching ${kind} record.`
  const evidence = records.map(record =>
    `${record.id} (from ${prettyDate(record.starts)} to before ${prettyDate(record.ends)}, recorded ${prettyDate(record.recorded)})`)
  return `Matching ${kind} records: ${evidence.join(', ')}.`
}

function ClaimQuestions({line, status, decisions}: {line: Line; status: string; decisions: Decision[]}) {
  const [question, setQuestion] = useState('')
  const [asked, setAsked] = useState('')
  const [history, setHistory] = useState<{question: string; answer: string}[]>([])
  function ask(value: string) {
    const next = value.trim()
    if (!next) return
    if (asked) setHistory(items => [...items, {question: asked, answer: answerClaimQuestion(asked, line, status, decisions)}])
    setQuestion('')
    setAsked(next)
  }
  return <section className="panel section decision"><h2><CircleHelp size={19}/> Ask about this claim</h2>
    <p>Type or speak your own question, or choose an example. Answers use the selected line’s synthetic records.</p>
    <div className="question-samples" aria-label="Sample questions">
      {sampleQuestions.map(sample => <button type="button" key={sample} onClick={() => ask(sample)}>{sample}</button>)}
    </div>
    <form onSubmit={event => {event.preventDefault(); ask(question)}}>
      <label>Your question<input value={question} maxLength={1000} onChange={event => setQuestion(event.target.value)} placeholder="Ask about this claim line"/></label>
      <VoiceQuestion onTranscript={value => setQuestion(value.slice(0, 1000))}/>
      <button className="primary" type="submit" disabled={!question.trim()}>Ask</button>
    </form>
    {history.length > 0 && <details className="question-history"><summary>Earlier questions ({history.length})</summary>
      {history.map((item, index) => <div className="question-answer" key={index}><strong>{item.question}</strong><p>{item.answer}</p></div>)}
    </details>}
    <div aria-live="polite">{asked && <div className="question-answer"><strong>{asked}</strong><p>{answerClaimQuestion(asked, line, status, decisions)}</p></div>}</div>
  </section>
}

function Dashboard({demo, reviews}: {demo: Demo; reviews: number}) {
  const finalized = demo.months.reduce((sum, item) => sum + item.finalized, 0)
  const denied = demo.months.reduce((sum, item) => sum + item.denied, 0)
  const historical = demo.months.reduce((sum, item) => sum + item.reviews, 0)
  return <>
    <h1>Manager dashboard</h1><p className="subtitle">Denial outcomes and review activity across the synthetic dataset.</p>
    <div className="stats">
      <Stat icon={<ClipboardList size={19}/>} label="Finalized lines" value={finalized.toLocaleString()} detail="Approved and denied"/>
      <Stat icon={<Activity size={19}/>} label="Denial rate" value={percent(denied / finalized, 1)} detail={denied + ' denied lines'}/>
      <Stat icon={<FileCheck2 size={19}/>} label="Review volume" value={historical + reviews} detail={historical + ' historical · ' + reviews + ' in this browser'}/>
    </div>
    <div className="detail-grid">
      <section className="panel section"><h2>Monthly denial trends</h2><p>Finalized lines grouped by submission month</p>
        <div className="trend" role="list">{demo.months.map(item => <div role="listitem" key={item.month}><span>{new Date(item.month + '-01T00:00:00Z').toLocaleDateString('en-US', {month:'short', timeZone:'UTC'})}</span><span className="trend-track"><i style={{width:percent(item.denied / item.finalized)}}/></span><strong>{percent(item.denied / item.finalized, 1)}</strong><small>{item.reviews} reviews</small></div>)}</div>
      </section>
      <section className="panel section"><h2>Risk model evaluation</h2><p>{demo.metrics.holdout_lines} finalized holdout lines from {prettyDate(demo.metrics.cutoff)} onward.</p>
        <div className="scroll"><table><thead><tr><th>Method</th><th>PR-AUC</th><th>ROC-AUC</th><th>Precision @ {demo.metrics.capacity}/day</th><th>Recall @ {demo.metrics.capacity}/day</th></tr></thead><tbody>
          <tr><td>Logistic regression</td><td>{demo.metrics.model.pr_auc.toFixed(4)}</td><td>{demo.metrics.model.roc_auc.toFixed(4)}</td><td>{percent(demo.metrics.model.precision_at_capacity, 2)}</td><td>{percent(demo.metrics.model.recall_at_capacity, 2)}</td></tr>
          <tr><td>Rules baseline</td><td>{demo.metrics.rules.pr_auc.toFixed(4)}</td><td>{demo.metrics.rules.roc_auc.toFixed(4)}</td><td>{percent(demo.metrics.rules.precision_at_capacity, 2)}</td><td>{percent(demo.metrics.rules.recall_at_capacity, 2)}</td></tr>
        </tbody></table></div>
      </section>
    </div>
  </>
}
createRoot(document.getElementById('root')!).render(<App/>)
