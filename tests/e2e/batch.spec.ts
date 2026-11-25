import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

test('analyzes 5,000 lines and shows evidence for each recommendation', async ({ page }) => {
  await page.goto('./')
  await page.getByRole('button', {name: 'Batch claim review'}).click()
  await page.getByRole('button', {name: 'Analyze 5,000 sample lines'}).click()
  await expect(page.getByRole('status')).toHaveText('5,000 lines analyzed')
  await expect(page.getByRole('row', {name: /TEST-0001/})).toContainText('Recommend approval')
  await expect(page.getByRole('row', {name: /TEST-0002/})).toContainText('Recommend denial')
  await expect(page.getByRole('row', {name: /TEST-0003/})).toContainText('Needs review')
  await page.getByRole('button', {name: 'Next', exact: true}).click()
  await expect(page.getByText('Page 2 of 200')).toBeVisible()
})

test('accepts a manual line and structured files, and rejects invalid inputs', async ({ page }) => {
  await page.goto('./')
  await page.getByRole('button', {name: 'Batch claim review'}).click()
  await page.getByLabel('Line ID').fill('MANUAL-1')
  await page.getByLabel('Service date').fill('2025-07-01')
  await page.getByLabel('Coverage active').selectOption('yes')
  await page.getByLabel('Confirmed duplicate').selectOption('no')
  await page.getByLabel('Authorization present').selectOption('yes')
  await page.getByLabel('Authorization approval date').fill('2025-07-01')
  await page.getByRole('button', {name: 'Analyze line', exact: true}).click()
  await expect(page.getByRole('row', {name: /MANUAL-1/})).toContainText('Only dates were supplied')
  await expect(page.getByRole('row', {name: /MANUAL-1/})).toContainText('NS-IMG-v2')

  const upload = page.getByLabel('Upload claim documents')
  const file = (name: string, content: unknown) => ({ name, mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(content)) })
  const line = {id: 'UPLOAD-1', payer: 'Northstar Health', procedure: 'IMG-01', service: '2025-06-30',
    eligible: 'yes', duplicate: 'no', authorization: 'yes', authorizationDate: '2025-07-02'}
  await upload.setInputFiles([file('line.json', line), file('array.json', [{...line, id: 'UPLOAD-2', payer: 'Unknown payer'}])])
  await expect(page.getByRole('status')).toHaveText('2 lines analyzed')
  await expect(page.getByRole('row', {name: /UPLOAD-1/})).toContainText('Recommend approval')
  await expect(page.getByRole('row', {name: /UPLOAD-2/})).toContainText('No demo policy')
  await upload.setInputFiles(file('invalid.json', [{...line, service: '2025-02-30'}]))
  await expect(page.getByRole('alert')).toContainText('invalid or missing service date')
})
