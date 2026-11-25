import { useEffect, useState } from 'react'

type Group = {feed: string; year: number; lines: number}
type Catalog = {
  lines: number; claims: number; start: string; end_exclusive: string; chunk_size: number
  feeds: Record<string, string>; payers: Record<string, string>; groups: Group[]
}
const PAGE_SIZE = 25
const number = new Intl.NumberFormat('en-US')
const reasons: Record<string, string> = {AUTH: 'Authorization', DUP: 'Duplicate', ELIG: 'Eligibility'}
const root = import.meta.env.BASE_URL + 'claims-archive/'

export function ArchiveQueue({back}: {back: () => void}) {
  const [catalog, setCatalog] = useState<Catalog>()
  const [feed, setFeed] = useState('hospital')
  const [year, setYear] = useState(2025)
  const [page, setPage] = useState(1)
  const [jump, setJump] = useState('')
  const [content, setContent] = useState<{path: string; rows: string[][]}>()
  const [failed, setFailed] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(root + 'index.json', {signal: controller.signal})
      .then(response => {
        if (!response.ok) throw Error('The archive catalogue could not be loaded.')
        return response.json()
      })
      .then((value: Catalog) => {
        setYear(Math.max(...value.groups.map(group => group.year)))
        setCatalog(value)
      })
      .catch(() => {if (!controller.signal.aborted) setFailed('The archive catalogue could not be loaded.')})
    return () => controller.abort()
  }, [retry])

  const group = catalog?.groups.find(item => item.feed === feed && item.year === year)
  const pageStart = (page - 1) * PAGE_SIZE
  const chunkSize = catalog?.chunk_size ?? PAGE_SIZE
  const chunk = Math.floor(pageStart / chunkSize)
  const offset = pageStart % chunkSize
  const path = group ? root + `feed=${feed}/service_year=${year}/chunk=${chunk}/rows_0.csv.gz` : ''
  const totalPages = Math.ceil((group?.lines ?? 0) / PAGE_SIZE)
  const rows = content?.path === path ? content.rows.slice(offset, offset + PAGE_SIZE) : undefined

  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    fetch(path, {signal: controller.signal})
      .then(async response => {
        if (!response.ok) throw Error('The archive page could not be loaded.')
        const bytes = await response.arrayBuffer()
        const magic = new Uint8Array(bytes, 0, Math.min(2, bytes.byteLength))
        const text = magic[0] === 31 && magic[1] === 139
          ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
          : new TextDecoder().decode(bytes)
        if (!controller.signal.aborted) {
          const records = text.trimEnd().split('\n').map(row => row.split('\t'))
          if (records.some(row => row.length !== 8)) throw Error('Invalid archive rows')
          setContent({path, rows: records})
        }
      })
      .catch(() => {if (!controller.signal.aborted) setFailed(path)})
    return () => controller.abort()
  }, [path, retry])

  function choose(source: string, selectedYear: number) {
    setFeed(source)
    setYear(selectedYear)
    setPage(1)
    setJump('')
    setFailed('')
  }

  function changePage(next: number) {
    setPage(Math.min(totalPages, Math.max(next, 1)))
    setJump('')
    setFailed('')
  }

  return <>
    <button className="text-button back" onClick={back}>← Guided claim queue</button>
    <h1>Claim archive by source</h1>
    <p className="subtitle">Synthetic hospital billing, clearinghouse, and practice management feeds. Service years 2023–2025.</p>
    {!catalog ? <p role={failed ? 'alert' : 'status'}>{failed || 'Loading archive catalogue…'}</p> : <section className="panel section" aria-label="Claim archive">
      <h2>{number.format(catalog.lines)} archive lines</h2>
      <p>{number.format(catalog.claims)} distinct claims across three fictional feeds. Review priority is based on evidence flags.</p>
      <div className="guide-actions archive-controls">
        <label>Source feed <select aria-label="Source feed" value={feed} onChange={event => choose(event.target.value, year)}>
          {Object.entries(catalog.feeds).map(([id, name]) => <option value={id} key={id}>{name}</option>)}
        </select></label>
        <label>Archive service year <select aria-label="Archive service year" value={year} onChange={event => choose(feed, Number(event.target.value))}>
          {[...new Set(catalog.groups.map(item => item.year))].map(item => <option key={item}>{item}</option>)}
        </select></label>
      </div>
      <div className="queue-pagination" role="group" aria-label="Archive pagination">
        <span aria-live="polite">Page {number.format(page)} of {number.format(totalPages)} · {number.format(group?.lines ?? 0)} lines in this feed and year</span>
        <div>
          <button className="text-button" onClick={() => changePage(page - 1)} disabled={page <= 1}>Previous archive page</button>
          <button className="text-button" onClick={() => changePage(page + 1)} disabled={page >= totalPages}>Next archive page</button>
        </div>
      </div>
      <form className="archive-jump" onSubmit={event => {event.preventDefault(); if (jump) changePage(Number(jump))}}>
        <label>Go to page <input type="number" min={1} max={totalPages} required value={jump} onChange={event => setJump(event.target.value)}/></label>
        <button className="text-button">Go</button>
      </form>
      {failed === path && failed ? <p role="alert">Could not load this archive page. <button className="text-button" onClick={() => {setFailed(''); setRetry(value => value + 1)}}>Retry</button></p> :
        !rows ? <p role="status">Loading archive page…</p> :
          <div className="scroll"><table>
            <thead><tr><th>Line ID</th><th>Claim ID</th><th>Service date</th><th>Procedure</th><th>Payer</th><th>Review priority</th><th>Recorded status</th><th>Payer reason</th></tr></thead>
            <tbody>{rows.map(([line, claim, service, payer, procedure, status, reason, priority]) =>
              <tr key={line}><td>LINE-{line.padStart(7, '0')}</td><td>CLM-{claim.padStart(6, '0')}</td>
                <td>{service}</td><td>{procedure}</td><td>{catalog.payers[payer]}</td>
                <td>{Number(priority) >= 4 ? 'High' : Number(priority) > 0 ? 'Flagged' : 'Routine'}</td>
                <td>{status}</td><td>{reasons[reason] ?? '—'}</td></tr>)}</tbody>
          </table></div>}
    </section>}
  </>
}
