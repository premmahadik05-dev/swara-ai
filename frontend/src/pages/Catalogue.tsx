import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Icon } from '../components/Icons'
import { Drawer } from '../components/Overlay'
import { useToast } from '../components/Toast'
import { Badge, Button, Card, Empty, ErrorNote, Field, Note, PageHeader, Pagination, SearchBox, SkeletonCard, SkeletonRows, useLocalInput } from '../components/ui'
import { istDate } from '../lib/format'
import { useIsOwner } from '../lib/auth'
import { rowKey, useAsync, useUrlState } from '../lib/hooks'
import type { CatalogDetail, CatalogItem } from '../types'

const PAGE = 24
/** Plain-language meaning of the rule codes written by scripts/data/build_catalog.py into each row's `transforms`. */
function explainRule(t: string): string {
  if (t === 'name:cleaned') return 'Tidied the name (HTML characters, spacing, capitalisation)'
  if (t === 'brand:missing') return 'The source lists no brand, so the brand is left blank (not guessed)'
  if (t.startsWith('name:')) return { en: 'Used the English product name from the source', main: 'Used the main (original-language) product name; no English name was published', fr: 'Used the French name; no English name was published', hi: 'Used the Hindi name; no English name was published', mr: 'Used the Marathi name; no English name was published' }[t.slice(5)] ?? `Name source: ${t.slice(5)}`
  if (t.startsWith('qty:')) { const [conv, extra] = t.slice(4).split(':'); return `Read the pack size from the source text and converted it (${conv.replace('->', ' → ')})${extra === 'multipack' ? ', counting a multipack' : ''}` }
  if (t === 'cat:name') return 'Assigned the shop category from words in the product name'
  if (t === 'cat:categories') return 'Assigned the shop category from the Open Food Facts category tags'
  if (t === 'cat:categories-generic') return 'Assigned the shop category from broad Open Food Facts tags (lower confidence)'
  return t
}

function SourceCard() {
  const src = useAsync(() => api.catalogSource(), [])
  const [open, setOpen] = useState(false)
  const s = src.data
  return (
    <Card className="source-card-wrap">
      <div className="source-card">
        <span className="empty" style={{ padding: 0 }}><span className="ico"><Icon name="database" size={22} /></span></span>
        <div style={{ minWidth: 0 }}>
          {!s ? <SkeletonCard lines={2} /> : (
            <>
              <b>{s.title ?? 'Reference catalogue'}</b>
              <p className="muted small" style={{ margin: '2px 0 0' }}>
                {s.rows_loaded.toLocaleString('en-IN')} packaged-food products from {s.origin ?? 'Open Food Facts'}
                {s.licence ? <> · licence {s.licence}</> : null}{s.retrieved_on ? <> · retrieved {istDate(s.retrieved_on)}</> : null}{s.snapshot_date ? <> · snapshot {s.snapshot_date}</> : null}.
                {' '}Names, brands, pack sizes and barcodes only: <b>no prices and no stock</b>. You set those when you add an item to your shop.
              </p>
            </>
          )}
        </div>
        {s?.manifest_found && <Button variant="secondary" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide details' : 'Source and limits'}</Button>}
      </div>
      {open && s && (
        <div style={{ padding: '0 18px 16px' }}>
          <dl className="kv" style={{ marginBottom: 12 }}>
            <dt>Attribution</dt><dd>{s.attribution}</dd>
            {s.origin_url && <><dt>Origin</dt><dd><a href={s.origin_url} target="_blank" rel="noreferrer">{s.origin_url}</a></dd></>}
            <dt>Records</dt><dd>{s.raw_rows?.toLocaleString('en-IN')} rows read, {s.rows_loaded.toLocaleString('en-IN')} kept after cleaning</dd>
          </dl>
          {s.limitations && s.limitations.length > 0 && (
            <><b className="small">Known limits</b><ul className="transform-list">{s.limitations.map((l) => <li key={l}>{l}</li>)}</ul></>
          )}
          <p className="muted small" style={{ margin: '10px 0 0' }}>Every record here is labelled <i>sourced</i> (as published) or <i>transformed</i> (cleaned by our script, with the rule listed). Nothing in this catalogue is invented. Full notes: docs/DATA.md.</p>
        </div>
      )}
    </Card>
  )
}

function ImportForm({ item, onDone }: { item: CatalogDetail; onDone: () => void }) {
  const { toast } = useToast()
  const [f, setF] = useState({ price: '', stock: '', reorder: '', cost: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Error | null>(null)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const price = Math.round(Number(f.price) * 100)
  const priceOk = f.price.trim() !== '' && Number.isFinite(price) && price >= 1 && price <= 10_000_000
  const cost = f.cost.trim() ? Math.round(Number(f.cost) * 100) : null
  const costOk = cost === null || (Number.isFinite(cost) && cost >= 1)
  const stock = f.stock.trim() ? Number(f.stock) : 0
  const reorder = f.reorder.trim() ? Number(f.reorder) : 0
  const numsOk = stock >= 0 && reorder >= 0 && Number.isFinite(stock) && Number.isFinite(reorder)
  const valid = priceOk && costOk && numsOk

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true); setErr(null)
    try {
      await api.importCatalogItem(item.id, { price_paise: price, stock, reorder_level: reorder, cost_paise: cost })
      toast(`${item.display_name} added to your shop. Customers can order it now.`, 'ok')
      onDone()
    } catch (e2) { setErr(e2 as Error) } finally { setBusy(false) }
  }
  return (
    <form className="stack sm" onSubmit={submit} aria-label="Add to your shop">
      <ErrorNote error={err} />
      <div className="grid2">
        <Field label="Your selling price (₹)" htmlFor="im-price" hint={`Per ${item.pack_label} pack. Required: the catalogue has no prices.`} error={f.price && !priceOk ? 'Enter a price between ₹0.01 and ₹1,00,000' : null}>
          <input id="im-price" type="number" min="0.01" step="0.01" inputMode="decimal" value={f.price} onChange={set('price')} required data-autofocus aria-invalid={!!f.price && !priceOk} />
        </Field>
        <Field label="Your cost (₹, optional)" htmlFor="im-cost" error={!costOk ? 'Enter at least ₹0.01' : null}><input id="im-cost" type="number" min="0.01" step="0.01" inputMode="decimal" value={f.cost} onChange={set('cost')} /></Field>
        <Field label="Packs in stock now" htmlFor="im-stock"><input id="im-stock" type="number" min="0" step="1" inputMode="numeric" value={f.stock} onChange={set('stock')} placeholder="0" /></Field>
        <Field label="Alert me at (packs)" htmlFor="im-re"><input id="im-re" type="number" min="0" step="1" inputMode="numeric" value={f.reorder} onChange={set('reorder')} placeholder="0" /></Field>
      </div>
      <Button type="submit" loading={busy} disabled={!valid} icon="plus">Add to my shop</Button>
    </form>
  )
}

function ItemDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const owner = useIsOwner()
  const res = useAsync(() => api.catalogItem(id), [id])
  const c = res.data
  return (
    <Drawer title={c ? c.display_name : 'Catalogue item'} subtitle={c ? <span className="row tight"><Badge tone="accent">Open Food Facts</Badge><Badge>{c.provenance}</Badge><span className="mono-id">EAN {c.ean}</span></span> : undefined} onClose={onClose}>
      <ErrorNote error={res.error} onRetry={res.reload} />
      {!c && !res.error && <SkeletonRows rows={6} cols={2} />}
      {c && (
        <div className="stack">
          <div className="prov">
            <h3>What the dataset says, and what we changed</h3>
            <dl className="kv">
              <dt>Original name</dt><dd><span className="mono">{c.name_raw}</span> <Badge tone="plain">sourced</Badge></dd>
              <dt>Cleaned name</dt><dd>{c.name} <Badge tone="plain">transformed</Badge></dd>
              <dt>Brand</dt><dd>{c.brand || <span className="faint">Not stated</span>}</dd>
              <dt>Original pack text</dt><dd><span className="mono">{c.quantity_raw || '(none)'}</span> <Badge tone="plain">sourced</Badge></dd>
              <dt>Pack size</dt><dd>{c.pack_label} <Badge tone="plain">transformed</Badge></dd>
              <dt>Original categories</dt><dd className="small muted">{c.off_categories_raw || '(none)'}</dd>
              <dt>Shop category</dt><dd>{c.category} <Badge tone="plain">transformed</Badge></dd>
              <dt>Last edited at source</dt><dd>{c.last_modified ? istDate(c.last_modified) : 'Unknown'}</dd>
            </dl>
            {c.transforms.length > 0 && (
              <><b className="small" style={{ display: 'block', marginTop: 10 }}>Cleaning steps applied</b>
                <ul className="transform-list">{c.transforms.map((t) => <li key={t}>{explainRule(t)}</li>)}</ul></>
            )}
          </div>
          {c.in_shop ? (
            <Note tone="ok"><b>This product is in your shop.</b> Set its price and stock in <Link to={`/inventory?q=${encodeURIComponent(c.ean)}`}>Inventory</Link>.</Note>
          ) : (
            owner ? (
              <Card title="Add to your shop" description="You set the price and stock. The assistant starts recognising it straight away.">
                <ImportForm item={c} onDone={() => { res.reload(); onChanged() }} />
              </Card>
            ) : <Note tone="info"><b>You are signed in as staff.</b> Only the shop owner can add this product to the shop and set its price.</Note>
          )}
          {!c.in_shop && c.suggested_aliases.length > 0 && (
            <p className="muted small">Customers can ask for it as: {c.suggested_aliases.map((a) => <Badge key={a} tone="plain">{a}</Badge>)} </p>
          )}
        </div>
      )}
    </Drawer>
  )
}

export default function Catalogue() {
  const owner = useIsOwner()
  const [f, set] = useUrlState({ q: '', category: '', brand: '', unit: '', sort: 'name', page: '1', open: '' })
  const [qLocal, setQLocal] = useLocalInput(f.q, (v) => set({ q: v }))
  const page = Math.max(1, Number(f.page) || 1)
  const facets = useAsync(() => api.catalogFacets(), [])
  const res = useAsync(() => api.catalog({ q: f.q, category: f.category, brand: f.brand, unit: f.unit, sort: f.sort, page, page_size: PAGE }), [f.q, f.category, f.brand, f.unit, f.sort, page])
  const d = res.data
  const filtered = !!(f.q || f.category || f.brand || f.unit)
  const openId = Number(f.open) || null

  return (
    <>
      <PageHeader title="Catalogue" description="Real packaged products from Open Food Facts. Pick the ones you stock, enter your own price, and customers can ask for them by brand." />
      <div className="stack">
        <SourceCard />
        <Card flush>
          <div style={{ padding: '12px 16px 4px' }}>
            <div className="pill-scroll" role="group" aria-label="Category">
              <button type="button" aria-pressed={!f.category} onClick={() => set({ category: '' })}>All<span className="count">{facets.data?.total.toLocaleString('en-IN')}</span></button>
              {facets.data?.categories.map((c) => <button key={c.name} type="button" aria-pressed={f.category === c.name} onClick={() => set({ category: f.category === c.name ? '' : c.name })}>{c.name}<span className="count">{c.count.toLocaleString('en-IN')}</span></button>)}
            </div>
          </div>
          <div className="toolbar">
            <SearchBox label="Search the catalogue" placeholder="Name, brand or barcode" value={qLocal} onChange={setQLocal} />
            <Field label="Brand" htmlFor="ca-br"><select id="ca-br" value={f.brand} onChange={(e) => set({ brand: e.target.value })}><option value="">All brands</option>{facets.data?.brands.map((b) => <option key={b.name} value={b.name}>{b.name} ({b.count})</option>)}</select></Field>
            <Field label="Pack measured in" htmlFor="ca-un"><select id="ca-un" value={f.unit} onChange={(e) => set({ unit: e.target.value })}><option value="">Any</option><option value="kg">Weight (g, kg)</option><option value="l">Volume (ml, l)</option><option value="pc">Pieces</option></select></Field>
            <Field label="Sort" htmlFor="ca-so"><select id="ca-so" value={f.sort} onChange={(e) => set({ sort: e.target.value })}><option value="name">Name</option><option value="brand">Brand</option><option value="recent">Recently updated</option></select></Field>
          </div>
          <ErrorNote error={res.error} onRetry={res.reload} />
          {res.loading && !d ? <SkeletonRows rows={8} cols={5} /> : d && d.items.length === 0 ? (
            <Empty title={filtered ? 'No catalogue products match' : 'The catalogue is empty'} icon="catalogue"
              action={filtered ? <Button variant="secondary" onClick={() => { setQLocal(''); set({ q: '', category: '', brand: '', unit: '' }) }}>Clear filters</Button> : undefined}>
              {filtered ? 'Try fewer words, or search by brand or barcode.' : <>Run <code>python scripts/seed_db.py --reset</code> to load the catalogue from <code>data/processed</code>.</>}
            </Empty>
          ) : d && (
            <div className="table-wrap" style={{ opacity: res.loading ? 0.6 : 1, transition: 'opacity .15s' }}>
              <table className="tbl">
                <thead><tr><th>Product</th><th>Category</th><th>Pack</th><th>Barcode (EAN)</th><th aria-label="Status" /></tr></thead>
                <tbody>
                  {d.items.map((c: CatalogItem) => (
                    <tr key={c.id} className="clickable" tabIndex={0} onClick={() => set({ open: String(c.id) }, { keepPage: true })} onKeyDown={(e) => rowKey(e, () => set({ open: String(c.id) }, { keepPage: true }))} aria-label={`Open ${c.display_name}`}>
                      <td><div className="cell-main"><b>{c.name}</b><span className="sub">{c.brand || 'Unbranded'}</span></div></td>
                      <td className="muted">{c.category}</td>
                      <td className="nowrap">{c.pack_label}</td>
                      <td><span className="mono-id">{c.ean}</span></td>
                      <td className="nowrap">{c.in_shop ? <Badge tone="ok" dot>In your shop</Badge> : <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); set({ open: String(c.id) }, { keepPage: true }) }}>{owner ? 'Add to shop' : 'Details'}</Button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {d && d.total > 0 && <Pagination page={page} pageSize={PAGE} total={d.total} noun="products" onPage={(p) => set({ page: String(p) }, { keepPage: true })} />}
        </Card>
      </div>
      {openId && <ItemDrawer id={openId} onClose={() => set({ open: '' }, { keepPage: true })} onChanged={res.reload} />}
    </>
  )
}
