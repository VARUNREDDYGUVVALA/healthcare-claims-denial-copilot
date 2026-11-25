import { useEffect, useState } from 'react'

type Score = {pr_auc: number; roc_auc: number; precision_at_capacity: number; recall_at_capacity: number; brier?: number}
type Report = {
  validation_start: string; test_start: string; review_capacity: number; dataset_sha256: string
  windows: Record<string, {lines: number; denials: number}>
  reference: string; recommended: string
  release: 'eligible_for_manual_review' | 'retain_reference'
  release_gates: {name: string; passed: boolean}[]
  validation: Record<string, Score>; test: Record<string, Score>
  gates: Record<string, {name: string; passed: boolean}[]>
  calibration: {lower: number; count: number; predicted: number; observed: number}[]
  test_slices: {dimension: string; value: string; count: number; denials: number; brier: number; denial_rate: number; mean_score: number}[]
  feature_drift: {feature: string; train_rate: number; test_rate: number; delta: number; alert: boolean}[]
}
const names: Record<string, string> = {logistic: 'Logistic regression', random_forest: 'Random forest', gradient_boosting: 'Gradient boosting', rules: 'Rules baseline'}
const formatPercent = (value: number) => (100 * value).toFixed(1) + '%'

export function ModelGovernance() {
  const [report, setReport] = useState<Report>()
  const [error, setError] = useState(false)
  const [window, setWindow] = useState<'validation' | 'test'>('test')

  useEffect(() => {
    const controller = new AbortController()
    fetch(import.meta.env.BASE_URL + 'model-governance.json', {signal: controller.signal})
      .then(response => {
        if (!response.ok) throw new Error('Report unavailable')
        return response.json()
      })
      .then(setReport)
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [])

  return <section className="panel section ledger-manager" aria-label="Model governance">
    <h2>Model governance</h2>
    {!report ? <p role={error ? 'alert' : 'status'}>{error ? 'The evaluation snapshot is unavailable.' : 'Loading the evaluation snapshot…'}</p> : <>
      <p><strong>Validation recommendation</strong> · {names[report.recommended]}. The evaluation does not promote a model to the live scorer.</p>
      <p><strong>Frozen-test decision</strong> · {report.release === 'retain_reference' ? 'Retain ' + names[report.reference] : 'Challenger eligible for manual review'}.</p>
      <p>Validation starts {report.validation_start}. Test starts {report.test_start}. Capacity is {report.review_capacity} lines per submission day.</p>
      <dl>{Object.entries(report.windows).map(([name, values]) =>
        <div className="model-window" key={name}><dt>{name}</dt><dd>{values.lines.toLocaleString('en-US')} lines · {values.denials.toLocaleString('en-US')} denials</dd></div>)}</dl>
      <details className="version-diff">
        <summary>Promotion gates</summary>
        {Object.entries(report.gates).map(([name, checks]) => <div className="model-gates" key={name}><h3>{names[name]} · Validation</h3>
          <ul>{checks.map(check => <li key={check.name}><strong>{check.passed ? 'Passed' : 'Failed'}</strong> · {check.name}</li>)}</ul>
        </div>)}
        {!!report.release_gates.length && <div className="model-gates"><h3>{names[report.recommended]} · Frozen test</h3>
          <ul>{report.release_gates.map(check => <li key={check.name}><strong>{check.passed ? 'Passed' : 'Failed'}</strong> · {check.name}</li>)}</ul>
        </div>}
      </details>
      <label className="ledger-control model-split">Evaluation split
        <select value={window} onChange={event => setWindow(event.target.value === 'test' ? 'test' : 'validation')}>
          <option value="test">Frozen test</option><option value="validation">Validation</option>
        </select>
      </label>
      <div className="scroll"><table>
        <thead><tr><th>Model</th><th>PR-AUC</th><th>ROC-AUC</th><th>Precision at capacity</th><th>Recall at capacity</th><th>Brier</th></tr></thead>
        <tbody>{Object.entries(report[window]).map(([name, score]) => <tr key={name}>
          <th scope="row">{names[name]}</th><td>{score.pr_auc.toFixed(4)}</td><td>{score.roc_auc.toFixed(4)}</td>
          <td>{formatPercent(score.precision_at_capacity)}</td><td>{formatPercent(score.recall_at_capacity)}</td><td>{score.brier?.toFixed(4) ?? '—'}</td>
        </tr>)}</tbody>
      </table></div>
      <details className="version-diff">
        <summary>Test calibration and payer/procedure slices</summary>
        <p>{names[report.recommended]} · Grouped predicted risk and observed denial rates.</p>
        <div className="scroll"><table>
          <thead><tr><th>Score bucket</th><th>Lines</th><th>Mean risk</th><th>Observed rate</th></tr></thead>
          <tbody>{report.calibration.map(bin => <tr key={bin.lower}>
            <td>{formatPercent(bin.lower)}–{formatPercent(bin.lower + .1)}</td><td>{bin.count}</td><td>{formatPercent(bin.predicted)}</td><td>{formatPercent(bin.observed)}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="scroll"><table>
          <thead><tr><th>Slice</th><th>Lines</th><th>Mean risk</th><th>Observed rate</th><th>Brier</th></tr></thead>
          <tbody>{report.test_slices.map(slice => <tr key={slice.dimension + slice.value}>
            <td>{slice.dimension} · {slice.value}</td><td>{slice.count}</td><td>{formatPercent(slice.mean_score)}</td>
            <td>{formatPercent(slice.denial_rate)}</td><td>{slice.brier.toFixed(4)}</td>
          </tr>)}</tbody>
        </table></div>
      </details>
      <details className="version-diff">
        <summary>Train-to-test feature drift</summary>
        <div className="scroll"><table>
          <thead><tr><th>Feature</th><th>Training</th><th>Test</th><th>Change</th><th>10-point alert</th></tr></thead>
          <tbody>{report.feature_drift.map(feature => <tr key={feature.feature}>
            <td>{feature.feature.replaceAll('_', ' ')}</td><td>{formatPercent(feature.train_rate)}</td><td>{formatPercent(feature.test_rate)}</td>
            <td>{(100 * feature.delta).toFixed(1)} pp</td><td>{feature.alert ? 'Triggered' : 'Clear'}</td>
          </tr>)}</tbody>
        </table></div>
      </details>
      <div className="guide-actions"><a href={import.meta.env.BASE_URL + 'model-governance.json'} download className="text-button">Download evaluation report</a><small>Dataset SHA-256 · {report.dataset_sha256.slice(0, 12)}…</small></div>
    </>}
  </section>
}
