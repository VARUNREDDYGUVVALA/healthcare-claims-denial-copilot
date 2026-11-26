import {useState} from 'react'
import {BookOpen, ClipboardCheck, Files, ShieldCheck} from 'lucide-react'
import {evaluate} from './batch'
import type {BatchPolicy, ClaimInput, Evidence} from './batch'

const example: ClaimInput = {
  id: 'LAB-IMAGING', payer: 'Northstar Health', procedure: 'IMG-01', service: '2026-03-31',
  eligible: 'yes', duplicate: 'no', authorization: 'yes', authorizationDate: '2026-04-02',
}
const examples = [
  {label: 'March 31 service', service: '2026-03-31'},
  {label: 'April 1 service', service: '2026-04-01'},
]
const labels = {
  'Recommend approval': 'Ready for review',
  'Recommend denial': 'Correct before submission',
  'Needs review': 'Needs manual review',
}
const workspaces = [
  {title: 'Claim Check', description: 'Check an entered line and track a review request.'},
  {title: 'Analyst Review', description: 'Verify evidence, record a recommendation, and escalate exceptions.'},
  {title: 'Manager Dashboard', description: 'Assign cases and track the review workload.'},
]

function EvidenceSelect({label, value, onChange}: {label: string; value: Evidence; onChange: (value: Evidence) => void}) {
  return <label>{label}<select value={value} onChange={event => onChange(event.target.value as Evidence)}>
    <option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option>
  </select></label>
}

export function ClaimLab({policies, openGuided, openArchive, openWorkspace}: {
  policies: BatchPolicy[]; openGuided: () => void; openArchive: () => void; openWorkspace: () => void
}) {
  const [claim, setClaim] = useState(example)
  const result = claim.service ? evaluate(claim, policies) : undefined
  function edit<K extends keyof ClaimInput>(field: K, value: ClaimInput[K]) {
    setClaim(current => ({...current, [field]: value}))
  }
  return <div className="claim-lab">
    <section className="lab-intro">
      <div>
        <p className="lab-kicker"><ShieldCheck size={16}/> Ledger · Claims denial copilot</p>
        <h1>Check a claim before you submit it</h1>
        <p>Try a fictional MRI claim. Change the service date or evidence and see which payer policy applies and what to do next.</p>
      </div>
      <button className="primary" onClick={openWorkspace}>Open account workspace</button>
    </section>

    <div className="detail-grid lab-grid">
      <section className="panel section" aria-labelledby="lab-evidence">
        <h2 id="lab-evidence">Claim evidence</h2>
        <p>Northstar Health · MRI, knee · IMG-01</p>
        <div className="lab-scenarios" role="group" aria-label="Compare policy versions">
          {examples.map(item => <button type="button" key={item.service} className="lab-scenario"
            aria-pressed={claim.service === item.service} onClick={() => setClaim({...example, service: item.service})}>
            {item.label}
          </button>)}
        </div>
        <div className="batch-form">
          <label>Service date<input type="date" value={claim.service} onChange={event => edit('service', event.target.value)}/></label>
          <EvidenceSelect label="Coverage active" value={claim.eligible} onChange={value => edit('eligible', value)}/>
          <EvidenceSelect label="Duplicate confirmed" value={claim.duplicate} onChange={value => edit('duplicate', value)}/>
          <EvidenceSelect label="Authorization on file" value={claim.authorization} onChange={value => edit('authorization', value)}/>
          <label>Authorization approval date<input type="date" value={claim.authorizationDate}
            disabled={claim.authorization !== 'yes'} onChange={event => edit('authorizationDate', event.target.value)}/></label>
        </div>
      </section>

      <section className="panel section lab-result" aria-labelledby="lab-result" aria-live="polite">
        <h2 id="lab-result">Screening recommendation</h2>
        {result ? <>
          <p className="lab-verdict" data-recommendation={result.recommendation}>{labels[result.recommendation]}</p>
          <ul>{result.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
          {result.policy && <figure className="lab-policy">
            <figcaption>{result.policy.section} <span>{result.policy.starts} to before {result.policy.ends}</span></figcaption>
            <blockquote>{result.policy.excerpt}</blockquote>
          </figure>}
          <p><strong>Next step.</strong> {result.recommendation === 'Recommend approval' ?
            'Send the supporting records to a reviewer before submission.' : result.recommendation === 'Recommend denial' ?
            'Reconcile the flagged evidence before submitting the claim.' : 'Verify the missing evidence or locate the applicable policy.'}</p>
        </> : <p>Enter a service date to find the applicable rule.</p>}
      </section>
    </div>
    <p className="lab-context">This browser exercise applies fictional payer rules. The ranked queue uses a model trained on synthetic claim data. The payer makes the final decision.</p>

    <section className="panel section lab-workflow" aria-labelledby="lab-workflow">
      <h2 id="lab-workflow">Follow the claim through review</h2>
      <div className="lab-roles">{workspaces.map(workspace => <article key={workspace.title}>
        <h3>{workspace.title}</h3><p>{workspace.description}</p>
      </article>)}</div>
      <div className="guide-actions">
        <button className="text-button" onClick={openGuided}><BookOpen size={16}/> Open the guided denial case</button>
        <button className="text-button" onClick={openArchive}><Files size={16}/> Browse the claim archive</button>
        <button className="text-button" onClick={openWorkspace}><ClipboardCheck size={16}/> Sign in to review claims</button>
      </div>
    </section>
  </div>
}
