import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Dialog, Drawer } from '../components/Overlay'
import { useToast } from '../components/Toast'
import { ExportButton } from '../components/ExportButton'
import { Badge, Button, Card, Empty, ErrorNote, Field, Note, PageHeader, Pagination, PriceBasisBadge, SearchBox, Seg, SkeletonRows, SortTh, SourceBadge, useLocalInput } from '../components/ui'
import { KpiCard } from '../components/Kpi'
import { fmtQty, packLabel, rupees, unitLabel, wholeRupees } from '../lib/format'
import { useIsOwner } from '../lib/auth'
import { useAsync, useUrlState } from '../lib/hooks'
import type { Product } from '../types'

const PAGE = 25
const UNITS = [['kg', 'Weight (kg)'], ['l', 'Volume (litre)'], ['pack', 'Packet'], ['pc', 'Piece']] as const

function StockCell({ p }: { p: Product }) {
  const cap = Math.max(p.reorder_level * 3, p.stock, 1)
  return (
    <div className="stockcell">
      <div className={`meter ${p.stock_status === 'ok' ? '' : p.stock_status}`} role="img" aria-label={`${fmtQty(p.stock)} ${p.unit} in stock`}><i style={{ width: `${Math.min(100, (p.stock / cap) * 100)}%` }} /></div>
      <span className="nowrap small" style={{ minWidth: 58 }}>{fmtQty(p.stock)} {unitLabel(p.unit)}</span>
    </div>
  )
}
const StatusBadge = ({ s }: { s: Product['stock_status'] }) => s === 'out' ? <Badge tone="bad" dot>Finished</Badge> : s === 'low' ? <Badge tone="warn" dot>Running low</Badge> : <Badge tone="ok" dot>In stock</Badge>

function RestockDialog({ p, onClose, onDone }: { p: Product; onClose: () => void; onDone: () => void }) {
  const { toast } = useToast()
  const [qty, setQty] = useState('')
  const [busy, setBusy] = useState(false)
  const n = Number(qty)
  const valid = n > 0 && n <= 100000
  const step = p.unit === 'kg' || p.unit === 'l' ? '0.5' : '1'
  const go = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true)
    try { await api.restock(p.id, n); toast(`${p.name_en}: added ${fmtQty(n)} ${unitLabel(p.unit)}.`, 'ok'); onDone() } catch (err) { toast((err as Error).message, 'bad') } finally { setBusy(false) }
  }
  return (
    <Dialog title={`Restock ${p.name_en}`} subtitle={`Now ${fmtQty(p.stock)} ${unitLabel(p.unit)} on the shelf`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="restock-form" loading={busy} disabled={!valid}>Add stock</Button></>}>
      <form id="restock-form" className="stack sm" onSubmit={go}>
        <Field label={`How much arrived (${unitLabel(p.unit)})`} htmlFor="rs-q" hint={valid ? `New stock will be ${fmtQty(p.stock + n)} ${unitLabel(p.unit)}.` : 'Enter the quantity you received today.'}>
          <input id="rs-q" type="number" min="0" step={step} inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} data-autofocus />
        </Field>
      </form>
    </Dialog>
  )
}

function ProductForm({ initial, onDone }: { initial?: Product; onDone: () => void }) {
  const { toast } = useToast()
  const [f, setF] = useState({
    sku: initial?.sku ?? '', name_en: initial?.name_en ?? '', name_gu: initial?.name_gu ?? '', name_hi: initial?.name_hi ?? '', brand: initial?.brand ?? '',
    category: initial?.category ?? '', unit: initial?.unit ?? 'kg', price: initial ? String(initial.price_paise / 100) : '', cost: initial?.cost_paise ? String(initial.cost_paise / 100) : '',
    stock: initial ? String(initial.stock) : '0', reorder: initial ? String(initial.reorder_level) : '0', aliases: (initial?.aliases ?? []).join(', '),
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Error | null>(null)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value })
  const price = Math.round(Number(f.price) * 100)
  const priceOk = Number.isFinite(price) && price >= 1
  const costPaise = f.cost.trim() ? Math.round(Number(f.cost) * 100) : null
  const costOk = costPaise === null || (Number.isFinite(costPaise) && costPaise >= 1)
  const skuOk = !!initial || /^[A-Za-z0-9][A-Za-z0-9-]{1,39}$/.test(f.sku.trim())
  const valid = f.name_en.trim().length > 0 && priceOk && costOk && skuOk

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setBusy(true); setErr(null)
    const aliases = f.aliases.split(',').map((s) => s.trim()).filter(Boolean)
    try {
      if (initial) {
        await api.patchProduct(initial.id, { name_en: f.name_en, name_gu: f.name_gu, name_hi: f.name_hi, brand: f.brand, category: f.category, price_paise: price, reorder_level: Number(f.reorder), aliases, ...(costPaise ? { cost_paise: costPaise } : {}) })
        toast('Product updated. The assistant uses the new name straight away.', 'ok')
      } else {
        await api.createProduct({ sku: f.sku.trim().toUpperCase(), name_en: f.name_en, name_gu: f.name_gu, name_hi: f.name_hi, brand: f.brand, category: f.category, unit: f.unit as Product['unit'], price_paise: price, stock: Number(f.stock), reorder_level: Number(f.reorder), aliases, ...(costPaise ? { cost_paise: costPaise } : {}) } as never)
        toast('Product added. Customers can order it now.', 'ok')
      }
      onDone()
    } catch (e2) { setErr(e2 as Error) } finally { setBusy(false) }
  }
  return (
    <form id="product-form" onSubmit={submit} className="stack sm">
      <ErrorNote error={err} />
      <div className="grid2">
        <Field label="Name (English)" htmlFor="f-en"><input id="f-en" type="text" value={f.name_en} onChange={set('name_en')} required maxLength={120} /></Field>
        <Field label="Brand (optional)" htmlFor="f-br"><input id="f-br" type="text" value={f.brand} onChange={set('brand')} maxLength={80} /></Field>
        <Field label="Name (ગુજરાતી)" htmlFor="f-gu"><input id="f-gu" type="text" lang="gu" value={f.name_gu} onChange={set('name_gu')} /></Field>
        <Field label="Name (हिन्दी)" htmlFor="f-hi"><input id="f-hi" type="text" lang="hi" value={f.name_hi} onChange={set('name_hi')} /></Field>
        {!initial && <Field label="SKU" htmlFor="f-sku" hint="Letters, numbers, dashes" error={f.sku && !skuOk ? 'Use 2–40 letters, numbers or dashes' : null}><input id="f-sku" type="text" value={f.sku} onChange={set('sku')} required /></Field>}
        <Field label="Category" htmlFor="f-cat"><input id="f-cat" type="text" value={f.category} onChange={set('category')} maxLength={60} /></Field>
        <Field label="Sold by" htmlFor="f-unit"><select id="f-unit" value={f.unit} onChange={set('unit')} disabled={!!initial}>{UNITS.map(([u, l]) => <option key={u} value={u}>{l}</option>)}</select></Field>
        <Field label={`Selling price per ${f.unit} (₹)`} htmlFor="f-price" error={f.price && !priceOk ? 'Enter a price of at least ₹0.01' : null}><input id="f-price" type="number" min="0.01" step="0.01" inputMode="decimal" value={f.price} onChange={set('price')} required /></Field>
        <Field label="Your cost per unit (₹, optional)" htmlFor="f-cost" hint="Used for the cost value of stock" error={!costOk ? 'Enter a cost of at least ₹0.01' : null}><input id="f-cost" type="number" min="0.01" step="0.01" inputMode="decimal" value={f.cost} onChange={set('cost')} /></Field>
        <Field label="Low-stock alert at" htmlFor="f-re"><input id="f-re" type="number" min="0" step="0.5" value={f.reorder} onChange={set('reorder')} /></Field>
        {!initial && <Field label="Opening stock" htmlFor="f-st"><input id="f-st" type="number" min="0" step="0.5" value={f.stock} onChange={set('stock')} /></Field>}
      </div>
      <Field label="Other names customers use (comma separated, any language)" htmlFor="f-al"><input id="f-al" type="text" value={f.aliases} onChange={set('aliases')} placeholder="chini, cheeni, shakkar, ખાંડ" /></Field>
      <div className="row between"><span /><Button type="submit" loading={busy} disabled={!valid}>{initial ? 'Save changes' : 'Add product'}</Button></div>
    </form>
  )
}

export default function Inventory() {
  const owner = useIsOwner()
  const [f, set] = useUrlState({ q: '', category: '', status: '', source: '', sort: 'name', page: '1' })
  const [qLocal, setQLocal] = useLocalInput(f.q, (v) => set({ q: v }))
  const [edit, setEdit] = useState<Product | 'new' | null>(null)
  const [restock, setRestock] = useState<Product | null>(null)
  const page = Math.max(1, Number(f.page) || 1)
  const inv = useAsync(() => api.inventory({ q: f.q, category: f.category, status: f.status, source: f.source, sort: f.sort, page, page_size: PAGE }), [f.q, f.category, f.status, f.source, f.sort, page])
  const cats = useAsync(() => api.categories(), [])
  const sum = useAsync(() => api.inventorySummary(), [])
  const reload = () => { inv.reload(); sum.reload(); cats.reload() }
  const d = inv.data
  const filtered = !!(f.q || f.category || f.status || f.source)

  return (
    <>
      <PageHeader title="Inventory" description="What is on the shelf, what it sells for and what needs restocking. Stock drops when an order is confirmed and returns if it is cancelled."
        actions={<>
          <ExportButton what="stock" fetchFile={() => api.exportInventory({ q: f.q, category: f.category, status: f.status, source: f.source, sort: f.sort })} />
          {owner && <><Link className="btn secondary" to="/catalogue">Add from catalogue</Link><Button icon="plus" onClick={() => setEdit('new')}>Add product</Button></>}
        </>} />
      <div className="stack">
        {!owner && <Note tone="info"><b>You are signed in as staff.</b> You can look at stock and take orders. Only the shop owner can add products, change prices or restock.</Note>}
        <div className="kpi-grid">
          <KpiCard label="Products in your shop" icon="box" value={sum.data ? sum.data.products.toLocaleString('en-IN') : '-'} loading={sum.loading && !sum.data}
            foot={sum.data ? `${sum.data.price_basis.shop} with your price · ${sum.data.price_basis.demo} with a demo price` : undefined} />
          <KpiCard label="Stock value at selling price" icon="rupee" value={sum.data ? wholeRupees(sum.data.valuation_retail_paise) : '-'} loading={sum.loading && !sum.data}
            foot={sum.data ? (sum.data.valuation_cost_paise !== null ? `At cost: ${wholeRupees(sum.data.valuation_cost_paise)} (${sum.data.products_with_cost} items with a cost)` : 'Add a cost price to see value at cost') : undefined} />
          <KpiCard label="Running low" icon="alert" value={sum.data?.stock_health.low ?? '-'} loading={sum.loading && !sum.data} foot="At or below the alert level" />
          <KpiCard label="Finished" icon="x" value={sum.data?.stock_health.out ?? '-'} loading={sum.loading && !sum.data} foot="Customers cannot order these" />
        </div>
        {sum.data && sum.data.price_basis.demo > 0 && (
          <Note tone="info">{sum.data.price_basis.demo} items still use <b>demo prices</b>, which are placeholders and not real market prices. {owner ? 'Edit an item and save your own price to replace it; the' : 'The shop owner can replace them with real prices. The'} value above is only as accurate as the prices you enter.</Note>
        )}

        <Card flush>
          <div className="toolbar">
            <SearchBox label="Search products" placeholder="Name, brand, barcode or SKU" value={qLocal} onChange={setQLocal} />
            <Field label="Category" htmlFor="inv-cat"><select id="inv-cat" value={f.category} onChange={(e) => set({ category: e.target.value })}><option value="">All categories</option>{cats.data?.map((c) => (<option key={c.category} value={c.category}>{c.category} ({c.count})</option>))}</select></Field>
            <Field label="Source" htmlFor="inv-src"><select id="inv-src" value={f.source} onChange={(e) => set({ source: e.target.value })}><option value="">All sources</option><option value="curated">Curated staples</option><option value="off_india">Open Food Facts</option><option value="manual">Added by shop</option></select></Field>
            <div className="only-sm"><Field label="Sort by" htmlFor="inv-sort"><select id="inv-sort" value={f.sort} onChange={(e) => set({ sort: e.target.value })}>{[['name', 'Name'], ['category', 'Category'], ['price', 'Price'], ['stock', 'Stock'], ['value', 'Stock value'], ['status', 'Status']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field></div>
          </div>
          <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--line)' }}>
            <Seg label="Stock status" value={f.status} onChange={(v) => set({ status: v })} options={[
              { value: '', label: 'All', count: d?.counts.all }, { value: 'ok', label: 'In stock', count: d?.counts.ok },
              { value: 'low', label: 'Running low', count: d?.counts.low }, { value: 'out', label: 'Finished', count: d?.counts.out }]} />
          </div>
          <ErrorNote error={inv.error} onRetry={inv.reload} />
          {inv.loading && !d ? <SkeletonRows rows={8} cols={6} /> : d && d.items.length === 0 ? (
            <Empty title={filtered ? 'No products match' : 'No products yet'} icon="box"
              action={filtered ? <Button variant="secondary" onClick={() => { setQLocal(''); set({ q: '', category: '', status: '', source: '' }) }}>Clear filters</Button> : owner ? <Button onClick={() => setEdit('new')}>Add product</Button> : undefined}>
              {filtered ? 'Try a different search or clear the filters.' : owner ? 'Add a product, or pick items from the catalogue.' : 'The shop owner has not added any products yet.'}
            </Empty>
          ) : d && (
            <div className="table-wrap" style={{ opacity: inv.loading ? 0.6 : 1, transition: 'opacity .15s' }}>
              <table className="tbl stack-sm rows">
                <thead><tr>
                  <SortTh label="Product" field="name" sort={f.sort} onSort={(s) => set({ sort: s })} />
                  <th>Brand</th>
                  <SortTh label="Category" field="category" sort={f.sort} onSort={(s) => set({ sort: s })} />
                  <th>Pack size</th>
                  <SortTh label="Price" field="price" sort={f.sort} onSort={(s) => set({ sort: s })} className="num" />
                  <SortTh label="Stock" field="stock" sort={f.sort} onSort={(s) => set({ sort: s })} />
                  <SortTh label="Value" field="value" sort={f.sort} onSort={(s) => set({ sort: s })} className="num" />
                  <SortTh label="Status" field="status" sort={f.sort} onSort={(s) => set({ sort: s })} />
                  <th aria-label="Actions" />
                </tr></thead>
                <tbody>
                  {d.items.map((p) => (
                    <tr key={p.id}>
                      <td><div className="cell-main"><b>{p.name_en}</b><span className="sub" lang="gu">{[p.name_gu, p.name_hi].filter(Boolean).join(' · ')}</span></div></td>
                      <td data-label="Brand" className="muted">{p.brand || '-'}</td>
                      <td data-label="Category"><div className="cell-main"><span className="muted">{p.category}</span><span><SourceBadge source={p.source} /></span></div></td>
                      <td data-label="Pack size" className="muted nowrap">{packLabel(p.pack_size, p.pack_size_unit)}</td>
                      <td className="num" data-label="Price"><div className="cell-main end"><span><b>{rupees(p.price_paise)}</b> <span className="sub inline">/ {unitLabel(p.unit)}</span></span><PriceBasisBadge basis={p.price_basis} /></div></td>
                      <td data-label="Stock"><StockCell p={p} /></td>
                      <td className="num muted" data-label="Value">{wholeRupees(p.stock_value_paise)}</td>
                      <td><StatusBadge s={p.stock_status} /></td>
                      <td>{owner && <span className="row tight nowrap"><Button size="sm" variant="secondary" onClick={() => setRestock(p)} aria-label={`Restock ${p.name_en}`}>Restock</Button><Button size="sm" variant="ghost" iconOnly icon="edit" onClick={() => setEdit(p)} aria-label={`Edit ${p.name_en}`} /></span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {d && d.total > 0 && <Pagination page={page} pageSize={PAGE} total={d.total} noun="products" onPage={(p) => set({ page: String(p) }, { keepPage: true })} />}
        </Card>
      </div>

      {restock && <RestockDialog p={restock} onClose={() => setRestock(null)} onDone={() => { setRestock(null); reload() }} />}
      {edit && (
        <Drawer title={edit === 'new' ? 'Add product' : edit.name_en} subtitle={edit === 'new' ? 'Customers can order it as soon as you save.' : <span className="row tight"><SourceBadge source={edit.source} /><PriceBasisBadge basis={edit.price_basis} />{edit.ean && <span className="mono-id">EAN {edit.ean}</span>}</span>} onClose={() => setEdit(null)}>
          <ProductForm initial={edit === 'new' ? undefined : edit} onDone={() => { setEdit(null); reload() }} />
        </Drawer>
      )}
    </>
  )
}
