import { expect, test } from '@playwright/test'

test('reviews a flagged line, saves the decision and compares policy dates', async ({ page }) => {
  await page.goto('./?queue=guided')
  await expect(page.getByText('Single-browser simulation')).toBeVisible()
  await page.getByLabel('Filter by status').selectOption('pre-submission')
  await expect(page.getByRole('row')).toHaveCount(6)
  const scores = await page.locator('tbody .risk').allTextContents()
  expect(scores.map(Number.parseFloat)).toEqual(scores.map(Number.parseFloat).sort((a, b) => b - a))
  await page.getByRole('button', { name: 'Start guided case' }).click()
  await expect(page.getByRole('heading', { name: 'CLM-GUIDE-1' })).toBeVisible()
  await expect(page.getByText('No matching record in extract')).toBeVisible()
  const payerResponse = page.getByRole('heading', {name: 'Payer response'}).locator('..')
  await expect(payerResponse.getByText('Prior authorization required')).toHaveCount(0)
  await page.getByRole('button', { name: 'Simulate payer response' }).click()
  await expect(page.getByText('Prior authorization required')).toBeVisible()
  await expect(page.getByText('partially denied', { exact: true })).toBeVisible()
  await expect(payerResponse.getByText('Imaging § 4.2 · v2')).toBeVisible()
  await expect(payerResponse.getByText(/must be on file before the service/)).toBeVisible()
  await page.getByLabel('Review note').fill('Verify against the payer portal.')
  await page.getByRole('button', { name: 'Save decision' }).click()
  await expect(page.getByRole('status')).toHaveText('Decision saved')
  await page.reload()
  await page.getByRole('button', { name: 'Start guided case' }).click()
  await expect(page.getByText('Verify against the payer portal.')).toBeVisible()
  await expect(payerResponse.getByText('Imaging § 4.2 · v2')).toBeVisible()
  await page.getByRole('button', { name: 'Open earlier policy case' }).click()
  await page.getByRole('button', { name: 'Simulate payer response' }).click()
  await expect(payerResponse.getByText('Imaging § 4.2 · v1')).toBeVisible()
  await expect(payerResponse.getByText(/two business days after service/)).toBeVisible()
  await page.getByRole('button', { name: 'Manager dashboard' }).click()
  await expect(page.getByText(/historical · 1 in this browser/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Monthly denial trends' })).toBeVisible()
  await page.getByRole('button', { name: 'Unmatched responses' }).click()
  await expect(page.getByText('R-UNMATCHED')).toBeVisible()
})

test('keeps the recorded reason when policy evidence is missing', async ({ page }) => {
  await page.goto('./?queue=guided')
  const demo = await page.request.get('./demo.json').then(response => response.json())
  const line = demo.lines.find((item: { explanation: { policy: unknown } | null }) => item.explanation && !item.explanation.policy)
  await page.getByLabel('Search claim lines').fill(line.id)
  await page.getByLabel('Search claim lines').press('Enter')
  await page.getByRole('button', { name: line.id, exact: true }).click()
  await expect(page.getByText(line.explanation.reason, { exact: true })).toBeVisible()
  await expect(page.getByText(/No matching policy passage was found/)).toBeVisible()
  await expect(page.getByText('Request payer clarification', { exact: true }).first()).toBeVisible()
})

test('answers sample and typed questions from the selected claim evidence', async ({ page }) => {
  await page.goto('./?queue=guided')
  await page.getByRole('button', { name: 'Start guided case' }).click()
  const answer = page.locator('[aria-live] .question-answer')
  await page.getByRole('button', { name: 'Why was this line denied?' }).click()
  await expect(answer).toContainText('Simulate the payer response')
  await page.getByRole('button', { name: 'Simulate payer response' }).click()
  await expect(answer).toContainText('Prior authorization required')
  await page.getByLabel('Your question').fill('Which policy version applies?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(answer).toContainText('NS-IMG-v2')
  await page.getByLabel('Your question').fill('How much was billed and who is the payer?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(answer).toContainText('Northstar Health')
  await expect(answer).toContainText('$1,250')
  await page.getByLabel('Your question').fill('How much was paid?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(answer).toContainText('do not include that information')
  await page.getByText('Earlier questions (3)').click()
  await expect(page.locator('.question-history')).toContainText('NS-IMG-v2')
  await page.getByRole('button', { name: 'Open earlier policy case' }).click()
  await page.getByRole('button', { name: 'Simulate payer response' }).click()
  await page.getByRole('button', { name: 'Which policy applied on the service date?' }).click()
  await expect(answer).toContainText('NS-IMG-v1')
  await page.getByLabel('Your question').fill('What is the weather?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(answer).toContainText('Try one of the sample questions')
})

test('paginates the full queue and searches beyond the current page', async ({ page }) => {
  await page.goto('./?queue=guided')
  const demo = await page.request.get('./demo.json').then(response => response.json())
  expect(demo.lines.length).toBeGreaterThan(4000)
  const line = demo.lines.at(-1)
  const pagination = page.getByRole('group', {name: 'Claim queue pagination'})
  await expect(pagination).toContainText('Lines 1–25')
  await expect(page.getByRole('row')).toHaveCount(26)
  await page.getByRole('button', {name: 'Next page'}).click()
  await expect(pagination).toContainText('Lines 26–50')
  await page.getByLabel('Search claim lines').fill(line.id)
  await expect(page.getByRole('row')).toHaveCount(2)
  await expect(page.getByRole('button', {name: line.id, exact: true})).toBeVisible()
  await expect(pagination).toHaveCount(0)
  await page.getByLabel('Search claim lines').clear()
  await expect(pagination).toContainText('Lines 1–25')
})

test('transcribes a complete spoken question and lets the user submit it', async ({ page }) => {
  await page.addInitScript(() => {
    class MockRecognition {
      onresult?: (event: {results: {transcript: string}[][]}) => void
      onend?: () => void
      start() {}
      stop() {
        this.onresult?.({results: [[{transcript: 'How much was billed'}], [{transcript: 'and who is the payer?'}]]})
        this.onend?.()
      }
      abort() {}
    }
    Object.defineProperty(window, 'SpeechRecognition', {value: MockRecognition})
  })
  await page.goto('./?queue=guided')
  await page.getByRole('button', {name: 'Start guided case'}).click()
  await page.getByRole('button', {name: 'Use microphone'}).click()
  await expect(page.getByText('Listening. Speak your question, then stop the microphone.')).toBeVisible()
  await page.getByRole('button', {name: 'Stop microphone'}).click()
  await expect(page.getByLabel('Your question')).toHaveValue('How much was billed and who is the payer?')
  const answer = page.locator('[aria-live] .question-answer')
  await expect(answer).toHaveCount(0)
  await page.getByRole('button', {name: 'Ask', exact: true}).click()
  await expect(answer).toContainText('$1,250')
  await expect(answer).toContainText('Northstar Health')
})

test('keeps text questions available when speech recognition is unsupported', async ({ page }) => {
  await page.addInitScript(() => {
    for (const key of ['SpeechRecognition', 'webkitSpeechRecognition']) {
      Object.defineProperty(window, key, {value: undefined})
    }
  })
  await page.goto('./?queue=guided')
  await page.getByRole('button', {name: 'Start guided case'}).click()
  await expect(page.getByText('Voice input is unavailable in this browser.')).toBeVisible()
  await page.getByLabel('Your question').fill('How much was billed?')
  await page.getByRole('button', {name: 'Ask', exact: true}).click()
  await expect(page.locator('[aria-live] .question-answer')).toContainText('$1,250')
})

test('Ledger compares policy editions and previews a hypothetical service date', async ({ page }) => {
  await page.goto('./?queue=guided')
  const comparison = page.getByText(/Holdout denials caught/)
  const initial = await comparison.textContent()
  await page.getByRole('slider', {name: 'Daily review capacity'}).press('End')
  await expect(comparison).not.toHaveText(initial ?? '')
  await page.getByRole('button', {name: 'Review March 2026 case'}).click()
  const ruler = page.getByRole('heading', {name: 'Policy time ruler'}).locator('..')
  await expect(ruler).toContainText('30 Mar 2026 · NS-IMG-2026-v1')
  await expect(ruler).toContainText('9 Jan · Authorization recorded')
  await expect(ruler).not.toContainText('13 Apr · Payer response')
  await page.getByRole('button', {name: 'Simulate payer response'}).click()
  await expect(ruler).toContainText('13 Apr · Payer response')
  await expect(page.getByText(/denial appears to conflict/)).toBeVisible()
  await expect(ruler.locator('.version-diff mark').first()).toBeVisible()
  const scrubber = page.getByRole('slider', {name: 'Explore service date'})
  await scrubber.press('ArrowRight')
  await scrubber.press('ArrowRight')
  await expect(ruler).toContainText('1 Apr 2026 · NS-IMG-2026-v2')
  await expect(page.getByText(/Effective Jan 1, 2026/)).toBeVisible()
  await page.getByRole('button', {name: 'Reset service date'}).click()
  await expect(ruler).toContainText('30 Mar 2026 · NS-IMG-2026-v1')
  await page.getByRole('button', {name: 'Manager dashboard'}).click()
  await expect(page.getByRole('heading', {name: 'Daily review capacity'})).toBeVisible()
  await expect(page.getByRole('heading', {name: 'Review activity'})).toBeVisible()
})

test('local investigation displays verified evidence and submits a supervisor review', async ({ page }) => {
  const id = '11111111-1111-4111-8111-111111111111'
  const run = {
    id, line_id: 'CLM-LEDGER-1', status: 'awaiting_review',
    recorded_reason: 'Prior authorization required',
    findings: ['Verify the authorization record.'],
    suggested_action: 'Verify authorization',
    policy: {id: 'NS-IMG-2026-v1', section: 'Imaging', excerpt: 'An authorization clause.'},
    appeal_draft: 'Review this draft alongside the verified record.',
    trace: ['Policy and evidence verification', 'Awaiting human review'],
    audit: [],
  }
  await page.route('**/api/investigations', async route => {
    expect(route.request().headers().authorization).toBe('Bearer analyst-test')
    expect(route.request().postDataJSON()).toEqual({line_id: 'CLM-LEDGER-1'})
    await route.fulfill({status: 201, json: run})
  })
  await page.route('**/api/investigations/' + id + '/decision', async route => {
    expect(route.request().headers().authorization).toBe('Bearer supervisor-test')
    expect(route.request().postDataJSON()).toEqual({decision: 'approve', note: 'Verified synthetic evidence.'})
    await route.fulfill({json: {...run, status: 'approved', audit: [{role: 'supervisor', event: 'review_approved', note: null, at: '2026-04-13T12:00:00Z'}]}})
  })
  await page.goto('./?mode=api')
  await page.getByRole('button', {name: 'Review March 2026 case'}).click()
  await page.getByRole('button', {name: 'Simulate payer response'}).click()
  const investigation = page.getByRole('region', {name: 'Local investigation'})
  await investigation.getByLabel('Local API token').fill('analyst-test')
  await investigation.getByRole('button', {name: 'Start investigation'}).click()
  await expect(investigation).toContainText('NS-IMG-2026-v1')
  await expect(investigation).toContainText('Awaiting human review')
  await investigation.getByLabel('Local API token').fill('supervisor-test')
  await investigation.getByLabel('Supervisor note').fill('Verified synthetic evidence.')
  await investigation.getByRole('button', {name: 'Record supervisor decision'}).click()
  await expect(investigation).toContainText('review approved · supervisor')
})

test('Model governance separates validation recommendations from the frozen-test release decision', async ({ page }) => {
  await page.goto('./')
  await page.getByRole('button', {name: 'Manager dashboard'}).click()
  const governance = page.getByRole('region', {name: 'Model governance'})
  await expect(governance.getByText('Validation recommendation')).toBeVisible()
  await expect(governance.getByText(/Frozen-test decision/)).toBeVisible()
  await expect(governance.getByRole('row', {name: /Gradient boosting/})).toContainText('0.7727')
  await governance.getByText('Promotion gates').click()
  await expect(governance.getByText(/Frozen-test PR-AUC does not decline/)).toContainText('Failed')
  await governance.getByLabel('Evaluation split').selectOption('validation')
  await expect(governance.getByRole('row', {name: /Gradient boosting/})).toContainText('0.7885')
  await expect(governance.getByRole('link', {name: 'Download evaluation report'})).toHaveAttribute('href', './model-governance.json')
})

test('three-year analysis shows expanded counts and browses service years', async ({ page }) => {
  await page.goto('./')
  await page.getByRole('button', {name: 'Three-year analysis'}).click()
  await expect(page.getByRole('heading', {name: 'Three-year analysis'})).toBeVisible()
  await expect(page.getByText('500,000', {exact: true})).toBeVisible()
  await expect(page.getByText('2,000,000', {exact: true})).toBeVisible()
  await expect(page.getByRole('row', {name: /^2025/})).toContainText('9.06%')
  await expect(page.getByRole('list', {name: 'Denial rates by month in 2025'}).getByRole('listitem')).toHaveCount(12)
  await page.getByLabel('Service year').selectOption('2023')
  await expect(page.getByRole('list', {name: 'Denial rates by month in 2023'})).toContainText('Jan 2023')
  await expect(page.getByRole('heading', {name: 'Denied lines by reason · 2023'})).toBeVisible()
  await expect(page.getByRole('link', {name: 'Download full dataset'})).toHaveAttribute('href', /claims-2023-2025-extra-large\.zip$/)
})

test('claim archive browses actual source and year partitions', async ({ page }) => {
  await page.goto('./?queue=archive')
  await expect(page.getByRole('heading', {name: 'Claim queue', exact: true})).toBeVisible()
  const totals = page.getByLabel('Full archive totals')
  await expect(totals.getByText('2,000,000', {exact: true})).toBeVisible()
  await expect(totals.getByText('High-priority lines')).toBeVisible()
  await expect(totals.getByText('43,516', {exact: true})).toBeVisible()
  await expect(page.getByRole('heading', {name: '2,000,000 archive lines'})).toBeVisible()
  await expect(page.getByRole('row')).toHaveCount(26)
  await page.getByRole('combobox', {name: 'Source feed', exact: true}).selectOption('clearinghouse')
  await page.getByLabel('Archive service year').selectOption('2023')
  await expect(page.getByRole('row').nth(1)).toContainText('2023-')
  await page.getByLabel('Go to page').fill('41')
  await page.getByLabel('Go to page').press('Enter')
  await expect(page.getByRole('group', {name: 'Archive pagination'})).toContainText('Page 41')
  await expect(page.getByRole('row')).toHaveCount(26)
})

test('live claim entry sends the supplied line to the authenticated API', async ({ page }) => {
  await page.route('**/api/screening/capabilities', route => route.fulfill({
    json: {available: true, policy_mode: 'synthetic'},
  }))
  await page.route('**/api/screening', async route => {
    expect(route.request().headers().authorization).toBe('Bearer sample-token')
    expect(route.request().postDataJSON()).toMatchObject({
      payer_code: 'NORTHSTAR', plan_code: 'DEMO', procedure_code: 'IMG-01',
      service_date: '2026-03-30', units: 2, authorization_present: 'no', authorization_date: null,
    })
    await route.fulfill({json: {
      recommendation: 'correct_before_submission',
      evaluated_at: '2026-11-25T15:00:00Z', policy_mode: 'synthetic',
      issues: [{code: 'AUTH_ABSENT', severity: 'correct', message: 'Authorization is required.'}],
      matched_policy: {policy_id: 'NS-IMG-2026-v1', effective_start: '2026-01-01', effective_end: '2026-04-01', source_url: null},
    }})
  })
  await page.goto('./')
  await page.getByRole('button', {name: 'Live claim screening'}).click()
  await page.getByLabel('API access token').fill('sample-token')
  await page.getByRole('combobox', {name: 'Authorization present'}).selectOption('no')
  await page.getByLabel('Units').fill('2')
  await page.getByLabel('Units').press('Enter')
  const result = page.getByRole('region', {name: 'Screening recommendation'})
  await expect(result).toContainText('Correct before submission')
  await expect(result).toContainText('Authorization is required')
  await expect(result).toContainText('NS-IMG-2026-v1')
})

test('static screening explains that the live API is required', async ({ page }) => {
  await page.route('**/api/screening/capabilities', route => route.fulfill({status: 404}))
  await page.goto('./')
  await page.getByRole('button', {name: 'Live claim screening'}).click()
  await expect(page.getByRole('heading', {name: 'A running API is required'})).toBeVisible()
  await expect(page.getByLabel('API access token')).toHaveCount(0)
})

test('static claim workspace links to server setup', async ({ page }) => {
  await page.route('**/api/workspace/capabilities', route => route.fulfill({status: 404}))
  await page.goto('./')
  await page.getByRole('button', {name: 'Claim workspace', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Connect to the full-stack app'})).toBeVisible()
  await expect(page.getByRole('link', {name: 'Workspace setup'})).toHaveAttribute('href', /enable-the-three-workspaces$/)
})

test('homepage explains why the same approval date yields different policy results', async ({ page }) => {
  await page.goto('./')
  await expect(page.getByRole('heading', {name: 'Check a claim before you submit it'})).toBeVisible()
  const result = page.getByRole('region', {name: 'Screening recommendation'})
  await expect(result).toContainText('Ready for review')
  await expect(result).toContainText('2026-v1')
  await page.getByRole('button', {name: 'April 1 service'}).click()
  await expect(result).toContainText('Correct before submission')
  await expect(result).toContainText('2026-v2')
  await page.getByLabel('Authorization on file').selectOption('unknown')
  await expect(result).toContainText('Needs manual review')
  await page.getByRole('button', {name: 'Open the guided denial case'}).click()
  await expect(page.getByRole('heading', {name: 'CLM-GUIDE-1', exact: true})).toBeVisible()
})
