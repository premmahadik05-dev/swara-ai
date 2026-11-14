import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChartCard, DataTable, Legend } from '../components/charts'
import { CurveChart, VerdictBars, type CurveRow, type VerdictRow } from '../components/evalCharts'
import { GridTable, type GridColumn } from '../components/GridTable'
import { ConfusionMatrix, Heatmap } from '../components/Heatmap'
import { KpiCard } from '../components/Kpi'
import { Badge, Card, Empty, ErrorNote, Note, PageHeader, SkeletonCard } from '../components/ui'
import { DATASET_ORDER, HEAT_COLUMNS, errorDistribution, fmtPct, headline, heatmap, httpRows, languageRows, metricRows, ratio } from '../lib/evaluation'
import type { LanguageEvalRow, MetricRow, TechRow, VerificationRow } from '../lib/evaluation'
import { useAsync } from '../lib/hooks'
import { ms } from '../lib/format'

const DATASET_COLOR: Record<string, { bg: string; ink: string }> = {
  handwritten: { bg: 'var(--c1)', ink: '#ffffff' }, templated: { bg: 'var(--c2)', ink: 'var(--text)' }, authored: { bg: 'var(--c3)', ink: 'var(--text)' }, branded: { bg: 'var(--c4)', ink: 'var(--text)' },
}
const VERDICT = {
  exact: { bg: 'var(--ok)', ink: '#ffffff' }, asked: { bg: 'var(--gold)', ink: 'var(--text)' }, notRecognised: { bg: 'var(--warn)', ink: '#ffffff' }, wrong: { bg: 'var(--bad)', ink: '#ffffff' },
}
const CER_SERIES = { exact: 'var(--c1)', skeleton: 'var(--c2)', stem: 'var(--c3)', fuzzy: 'var(--c4)' } as const
const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true }) + ' IST'

/** Colour for a status phrase. Anything that says it was not live-verified, mocked, skipped or not run is amber, whatever else the phrase says. */
const tone = (s: string): 'ok' | 'warn' | 'bad' | 'info' | 'plain' =>
  /fail/i.test(s) ? 'bad' : /^not used/i.test(s) ? 'plain' : /(not live|mocked|partial|skipped|not run|not measured)/i.test(s) ? 'warn' : /text only/i.test(s) ? 'info' : /^(passed|implemented|measured)/i.test(s) ? 'ok' : 'info'

function Section({ id, title, children }: { id: string; title: string; children?: ReactNode }) {
  return <h2 id={id} className="sect">{title}{children}</h2>
}

export default function Performance() {
  const ev = useAsync(() => api.evaluation(), [])
  const lat = useAsync(() => api.latency(), [])
  const s = ev.data?.summary ?? null
  const [dataset, setDataset] = useState('all')

  const model = useMemo(() => {
    if (!s) return null
    const langNames = Object.fromEntries(s.languages.map((l) => [l.key, l.name]))
    const heat = heatmap(s)
    const errors = errorDistribution(s)
    const noiseRows: CurveRow[] = s.noise.levels.map((l) => ({
      x: Math.round(l.cer * 100), exact: 100 * l.utterance_exact, band: [100 * l.utterance_exact_min, 100 * l.utterance_exact_max],
      precision: 100 * l.line_precision, recall: 100 * l.line_recall, f1: 100 * l.line_f1,
    }))
    const stages = [...new Set(s.noise.ablation.map((a) => a.stage))]
    const stageLabel = Object.fromEntries(s.noise.ablation.map((a) => [a.stage, a.label]))
    const cers = [...new Set(s.noise.ablation.map((a) => a.cer))].sort((a, b) => a - b)
    const ablationRows: CurveRow[] = cers.map((cer) => {
      const row: CurveRow = { x: Math.round(cer * 100) }
      for (const st of stages) { const p = s.noise.ablation.find((a) => a.cer === cer && a.stage === st); if (p) row[st] = 100 * p.utterance_exact }
      return row
    })
    const composition: VerdictRow[] = s.languages.flatMap((l) => {
      const parts = DATASET_ORDER.map((d) => ({ name: s.datasets.find((x) => x.id === d)?.name ?? d, n: s.sentence_check.filter((r) => r.lang === l.key && r.dataset === d).reduce((a, r) => a + r.n, 0), color: DATASET_COLOR[d].bg, ink: DATASET_COLOR[d].ink }))
      return parts.some((p) => p.n) ? [{ key: l.key, label: l.name, parts }] : []
    })
    const verdictRows: VerdictRow[] = errors.map((r) => ({
      key: r.lang, label: r.name,
      parts: [
        { name: 'Exact product', n: r.exact, color: VERDICT.exact.bg, ink: VERDICT.exact.ink }, { name: 'Asked which', n: r.asked, color: VERDICT.asked.bg, ink: VERDICT.asked.ink },
        { name: 'Not recognised', n: r.notRecognised, color: VERDICT.notRecognised.bg, ink: VERDICT.notRecognised.ink }, { name: 'Wrong product', n: r.wrong, color: VERDICT.wrong.bg, ink: VERDICT.wrong.ink },
      ],
    }))
    const written = languageRows(s, 'written')
    const rates = written.map((r) => r.exact_pct).filter((v): v is number => v !== null)
    const thin = written.filter((r) => r.samples < 20).length
    const labelErrors = s.language_detection.per_language.filter((r) => r.pct < 100).map((r) => `${langNames[r.lang] ?? r.lang} ${r.pct.toFixed(1)}%`)
    return {
      langNames, heat, errors, noiseRows, ablationRows, stages, stageLabel, composition, verdictRows, hl: headline(s), langRows: languageRows(s, dataset),
      rateMin: Math.min(...rates), rateMax: Math.max(...rates), thin, labelErrors,
    }
  }, [s, dataset])

  const metrics = useMemo(() => (s ? metricRows(s, lat.data, ev.data?.api_latency) : []), [s, lat.data, ev.data?.api_latency])
  const err = ev.error

  const langColumns: GridColumn<LanguageEvalRow>[] = [
    { key: 'name', label: 'Language', value: (r) => r.name },
    { key: 'samples', label: 'Samples', value: (r) => r.samples, num: true, hint: 'Sentences scored in the chosen sentence set' },
    { key: 'exact', label: 'Exact', value: (r) => r.exact, num: true, hint: 'Parsed order equals the gold order' },
    { key: 'wrong', label: 'Incorrect', value: (r) => r.wrong, num: true, hint: 'An order was produced but it differs from the gold order' },
    { key: 'unrec', label: 'Unrecognised', value: (r) => r.unrecognised, num: true, hint: 'No order lines were found' },
    { key: 'amb', label: 'Ambiguous', value: (r) => r.ambiguous, num: true, hint: 'The assistant would ask which product was meant' },
    { key: 'acc', label: 'Exact accuracy', value: (r) => (r.exact_pct === null ? null : Math.round(r.exact_pct * 10) / 10), num: true, render: (r) => <b>{fmtPct(r.exact_pct)}</b> },
  ]
  const metricColumns: GridColumn<MetricRow>[] = [
    { key: 'metric', label: 'Metric', value: (r) => r.metric, render: (r) => <b>{r.metric}</b> },
    { key: 'result', label: 'Result', value: (r) => r.result, render: (r) => (r.measured === 'not measured' ? <Badge tone="plain">Not measured</Badge> : <span className="nowrap">{r.result}{r.measured === 'live' && <> <Badge tone="ok">Live</Badge></>}</span>) },
    { key: 'dataset', label: 'Dataset', value: (r) => r.dataset },
    { key: 'method', label: 'Method', value: (r) => r.method },
    { key: 'interp', label: 'Interpretation', value: (r) => r.interpretation },
  ]
  const techColumns: GridColumn<TechRow>[] = [
    { key: 'component', label: 'Component', value: (r) => r.component, render: (r) => <b>{r.component}</b> },
    { key: 'technology', label: 'Technology', value: (r) => r.technology },
    { key: 'purpose', label: 'Purpose', value: (r) => r.purpose },
    { key: 'status', label: 'Implementation status', value: (r) => r.status, render: (r) => <Badge tone={tone(r.status)} dot>{r.status}</Badge> },
  ]
  const verColumns: GridColumn<VerificationRow>[] = [
    { key: 'category', label: 'Category', value: (r) => r.category, render: (r) => <div className="cell-main"><b>{r.category}</b><span className="sub">{r.how}</span></div> },
    { key: 'total', label: 'Total', value: (r) => r.total, num: true },
    { key: 'passed', label: 'Passed', value: (r) => r.passed, num: true },
    { key: 'failed', label: 'Failed', value: (r) => r.failed, num: true },
    { key: 'skipped', label: 'Skipped', value: (r) => r.skipped, num: true },
    { key: 'status', label: 'Status', value: (r) => r.status, render: (r) => <Badge tone={tone(r.status)} dot>{r.status}</Badge> },
  ]

  const lp = s?.parser_latency
  const http = httpRows(ev.data?.api_latency)
  const stt = lat.data?.['gnani-stt'], tts = lat.data?.['gnani-tts']
  const liveCalls = (stt?.calls ?? 0) + (tts?.calls ?? 0)

  return (
    <>
      <PageHeader title="AI performance"
        description="How well the order parser understands what people say, measured on text. Every figure is read from one results file, so this page, the report and the documents cannot disagree."
        meta={s ? <><Badge tone="info">Text only: no speech measured</Badge><Badge>Built {when(s.generated_at)}</Badge><Badge>Version {s.app_version}</Badge></> : undefined} />
      <div className="stack">
        <ErrorNote error={err ?? lat.error} onRetry={() => { ev.reload(); lat.reload() }} />
        {ev.loading && !ev.data && <SkeletonCard lines={6} height={300} />}
        {ev.data && !ev.data.available && (
          <Card><Empty title="The evaluation results have not been built yet" icon="chart">Run <code>{ev.data.how_to_create}</code> in the project folder (about 20 seconds), then reload this page. Nothing is shown rather than made up.</Empty></Card>
        )}

        {s && model && (
          <>
            <Note tone="warn">
              <b>Read these numbers with their limits.</b> {s.limitations[0]} {s.limitations[1]} Speech recognition was not measured, because no live Gnani call has been made.{' '}
              <a href="#limits">All limits</a>
            </Note>

            <div className="kpi-grid">
              <KpiCard label="Held-out brand match, exact" icon="tag" value={fmtPct(model.hl.brandedExact.pct)} foot={`${model.hl.brandedExact.n} of ${model.hl.brandedExact.of} synthetic sentences`} />
              <KpiCard label="Wrong product picked" icon="alert" value={fmtPct(model.hl.brandedWrong.pct)} foot={`${model.hl.brandedWrong.n} of ${model.hl.brandedWrong.of}. ${model.hl.brandedAsked.n} asked which pack, ${model.hl.brandedAsked.notRecognised} not recognised`} />
              <KpiCard label="Typed orders correct" icon="check" value={`${model.hl.orders.correct} of ${model.hl.orders.scored}`} foot={`${model.hl.orders.wrong} wrong. Author-written sentences, so a ceiling`} />
              <KpiCard label="Parser time per sentence" icon="clock" value={lp ? `${lp.p50_ms} ms` : '-'} foot={lp ? `p95 ${lp.p95_ms} ms. Text parsing only, no speech` : undefined} />
            </div>

            <Section id="by-language" title="Results by language" />
            <ChartCard title="Language by metric" sub="Share of sentences handled correctly. Darker is higher. Each cell prints its value; hover for the counts."
              legend={<span>Hatched cell: not measured for that language. Hinglish has no product names of its own, and the held-out brand test covers four languages only.</span>}
              table={<DataTable head={['Language', ...HEAT_COLUMNS.map((c) => c.label)]} rows={model.heat.map((r) => [r.name, ...r.cells.map((c) => c.text)])} />}>
              <Heatmap caption="Percent correct for each language and each test" columns={HEAT_COLUMNS.map((c) => ({ key: c.key, label: c.label, note: c.note }))}
                rows={model.heat.map((r) => ({ key: r.lang, label: r.name, cells: r.cells }))} />
              <p className="muted small" style={{ margin: '12px 0 0' }}>
                {model.rateMin === 100 ? 'Every sentence the project\'s author wrote parses exactly, in every language.' : `Exact matches on the author's own sentences run from ${fmtPct(model.rateMin)} to ${fmtPct(model.rateMax)}.`}{' '}
                That shows the parser agrees with its author, not that it would reach the same share on real speech.
                {model.thin > 0 && <> {model.thin} languages rest on fewer than 20 authored sentences each, with no native-speaker review.</>}
                {model.labelErrors.length > 0 && <> Without a language selected, the label is sometimes wrong for: {model.labelErrors.join(', ')}. Languages that share a script are the usual cause.</>}
              </p>
            </ChartCard>

            <Card title="Language evaluation" description="Sentences scored per language, by result. Choose one sentence set or add them together." flush>
              <div className="toolbar" style={{ borderBottom: 0, paddingBottom: 0 }}>
                <div className="field"><span className="label">Sentence set</span>
                  <div className="seg" role="group" aria-label="Sentence set">
                    {[['all', 'All sets'], ...s.datasets.map((d) => [d.id, d.name.split(',')[0]])].map(([v, l]) => (
                      <button key={v} type="button" aria-pressed={dataset === v} onClick={() => setDataset(v)}>{l}</button>
                    ))}
                  </div>
                </div>
              </div>
              <GridTable rows={model.langRows} columns={langColumns} rowKey={(r) => r.lang} noun="languages" exportName="language-evaluation" pageSize={12} initialSort={{ key: 'name', dir: 'asc' }} />
            </Card>

            <Section id="matching" title="Product matching" />
            <div className="cols even">
              <ChartCard title="Held-out brands: how each sentence ended" sub="Synthetic sentences built from products the parser had not seen. One bar per language."
                legend={<Legend items={[{ label: 'Exact product', color: VERDICT.exact.bg }, { label: 'Asked which one', color: VERDICT.asked.bg }, { label: 'Not recognised', color: VERDICT.notRecognised.bg }, { label: 'Wrong product', color: VERDICT.wrong.bg }]} />}
                table={<DataTable head={['Language', 'Exact', 'Asked which', 'Not recognised', 'Wrong', 'Total']} rows={model.errors.map((r) => [r.name, r.exact, r.asked, r.notRecognised, r.wrong, r.total])} />}>
                <VerdictBars rows={model.verdictRows} />
                <p className="muted small" style={{ margin: '12px 0 0' }}>Wrong product is the costly outcome, since the shop would be handed the wrong item. Asking which pack and not recognising are both safe: nothing wrong is added to the order.</p>
              </ChartCard>
              <ChartCard title="Evaluation sentences" sub="How many sentences each language has, and from which set"
                legend={<Legend items={DATASET_ORDER.map((d) => ({ label: s.datasets.find((x) => x.id === d)?.name ?? d, color: DATASET_COLOR[d].bg }))} />}
                table={<DataTable head={['Language', ...DATASET_ORDER.map((d) => s.datasets.find((x) => x.id === d)?.name ?? d)]} rows={model.composition.map((r) => [r.label, ...r.parts.map((p) => p.n)])} />}>
                <VerdictBars rows={model.composition} />
                <p className="muted small" style={{ margin: '12px 0 0' }}>Bar length is the number of sentences, on one scale. {model.thin} languages have fewer than 20 authored sentences each, so their percentages move a lot with a single sentence.</p>
              </ChartCard>
            </div>

            <ChartCard title="Product category confusion" sub="Rows: the category of the product the sentence asked for. Columns: what the parser returned. Shaded by share of the row."
              legend={<span><i style={{ background: 'var(--gold)' }} />Right category <i style={{ background: 'var(--c-muted)', opacity: 0.5, marginLeft: 12 }} />Asked which pack, or not recognised (safe) <i style={{ background: 'var(--bad)', opacity: 0.45, marginLeft: 12 }} />A different category was returned</span>}
              table={<DataTable head={['Asked-for category', ...s.branded.confusion.labels_cols]} rows={s.branded.confusion.labels_rows.map((r, i) => [r, ...s.branded.confusion.matrix[i]])} />}>
              <ConfusionMatrix caption="Asked-for product category against returned product category" rowHeader="Asked for" colHeader="Returned" rows={s.branded.confusion.labels_rows} cols={s.branded.confusion.labels_cols} matrix={s.branded.confusion.matrix}
                kind={(r, c) => (r === c ? 'hit' : c >= s.branded.confusion.labels_rows.length ? 'safe' : 'miss')} />
              <p className="muted small" style={{ margin: '12px 0 0' }}>A wrong product in the same category (two biscuits) sits on the diagonal and is not visible here. The pairs are listed below.</p>
            </ChartCard>

            <Card title="Wrong products picked, pair by pair" description={`${s.branded.verdicts.wrong_product} sentences returned one product that was not the one asked for. A pair can be two records of what is really the same item (a catalogue "Parle G" and the shop's "Parle-G 100 g"); it still counts as wrong because the records differ.`} flush>
              <GridTable rows={s.branded.confusion.wrong_pairs} rowKey={(r) => `${r.expected}|${r.got}`} noun="pairs" exportName="wrong-product-pairs" pageSize={8} initialSort={{ key: 'count', dir: 'desc' }}
                columns={[
                  { key: 'expected', label: 'Asked for', value: (r) => r.expected },
                  { key: 'got', label: 'Parser returned', value: (r) => r.got },
                  { key: 'count', label: 'Times', value: (r) => r.count, num: true },
                ]}
                empty={<Empty title="No wrong products" icon="check">Every sentence returned the right product, asked, or was not recognised.</Empty>} />
            </Card>

            <ChartCard title="Language label without a selector" sub="Rows: true language. Columns: the label the parser gave when no language was chosen."
              legend={<span><i style={{ background: 'var(--gold)' }} />Right label <i style={{ background: 'var(--bad)', opacity: 0.45, marginLeft: 12 }} />Different label</span>}
              table={<DataTable head={['True language', 'Sentences', 'Correct label', 'Share']} rows={s.language_detection.per_language.map((r) => [model.langNames[r.lang] ?? r.lang, r.n, r.correct, fmtPct(r.pct)])} />}>
              <ConfusionMatrix caption="True language against the language label the parser gave" rowHeader="True language" colHeader="Label given"
                rows={s.language_detection.labels.map((k) => model.langNames[k] ?? k)} cols={s.language_detection.labels.map((k) => model.langNames[k] ?? k)} matrix={s.language_detection.matrix}
                kind={(r, c) => (r === c ? 'hit' : 'miss')} />
              <p className="muted small" style={{ margin: '12px 0 0' }}>{s.language_detection.note}</p>
            </ChartCard>

            <Section id="robustness" title="Robustness to noisy text" />
            <div className="cols even">
              <ChartCard title="Whole sentence still exact" sub={`Handwritten order sentences with random letter damage, ${s.noise.seeds} random seeds. Shaded band: lowest to highest seed.`}
                table={<DataTable head={['Letters damaged', 'Exact (mean)', 'Lowest seed', 'Highest seed']} rows={s.noise.levels.map((l) => [`${Math.round(l.cer * 100)}%`, fmtPct(100 * l.utterance_exact), fmtPct(100 * l.utterance_exact_min), fmtPct(100 * l.utterance_exact_max)])} />}>
                <CurveChart data={model.noiseRows} series={[{ key: 'exact', label: 'Whole sentence exact', color: 'var(--c1)' }]} bandOf="exact" bandLabel={`Range over ${s.noise.seeds} seeds`} xTitle="Share of letters damaged" yTitle="Sentences exact" />
              </ChartCard>
              <ChartCard title="Order lines found: precision, recall, F1" sub="A line counts only if product, quantity and unit are all right."
                legend={<Legend items={[{ label: 'Precision', color: 'var(--c1)' }, { label: 'Recall', color: 'var(--c2)' }, { label: 'F1', color: 'var(--c3)' }]} />}
                table={<DataTable head={['Letters damaged', 'Precision', 'Recall', 'F1', 'Product-only F1']} rows={s.noise.levels.map((l) => [`${Math.round(l.cer * 100)}%`, l.line_precision.toFixed(3), l.line_recall.toFixed(3), l.line_f1.toFixed(3), l.product_f1.toFixed(3)])} />}>
                <CurveChart data={model.noiseRows} series={[{ key: 'precision', label: 'Precision', color: 'var(--c1)' }, { key: 'recall', label: 'Recall', color: 'var(--c2)', dash: '6 4' }, { key: 'f1', label: 'F1', color: 'var(--c3)' }]} xTitle="Share of letters damaged" yTitle="Order lines" fmtY={(n) => `${n.toFixed(1)}%`} />
              </ChartCard>
            </div>
            <ChartCard title="Which matching stage earns its place" sub="Same noisy sentences, matching stages switched on one after another. The last line is the full system."
              legend={<Legend items={model.stages.map((st, i) => ({ label: model.stageLabel[st], color: Object.values(CER_SERIES)[i] }))} />}
              table={<DataTable head={['Letters damaged', ...model.stages.map((st) => model.stageLabel[st])]} rows={model.ablationRows.map((r) => [`${r.x}%`, ...model.stages.map((st) => fmtPct(Number(r[st])))])} />}>
              <CurveChart data={model.ablationRows} series={model.stages.map((st, i) => ({ key: st, label: model.stageLabel[st], color: Object.values(CER_SERIES)[i], dash: i === 2 ? '2 4' : undefined }))} xTitle="Share of letters damaged" yTitle="Sentences exact" />
              <p className="muted small" style={{ margin: '12px 0 0' }}>The phonetic and fuzzy stages recover sentences that exact matching loses. Removing case endings changes nothing on these sentences, so the two lines overlap (dotted).</p>
            </ChartCard>
            <p className="muted small" style={{ margin: 0 }}>{s.noise.note}</p>

            <Section id="end-to-end" title="End to end and stock safety" />
            <div className="cols even">
              <Card title="Typed order to confirmed order" description={`${model.hl.orders.scored} sentences through the real dialogue, in 11 languages`}>
                <dl className="kv">
                  <dt>Correct orders</dt><dd><b>{model.hl.orders.correct} of {model.hl.orders.scored}</b> ({fmtPct(ratio(model.hl.orders.correct, model.hl.orders.scored))})</dd>
                  <dt>Wrong orders</dt><dd><b>{model.hl.orders.wrong}</b></dd>
                  <dt>Not scored</dt><dd>{s.end_to_end.n_sentences - model.hl.orders.scored} (gold cannot be written as an order)</dd>
                  <dt>Ambiguous sentences</dt><dd>{s.behaviour_checks.ambiguous_not_guessed} left unguessed</dd>
                  <dt>Non-order sentences</dt><dd>{s.behaviour_checks.no_item_no_false_add} added nothing</dd>
                </dl>
                <p className="muted small" style={{ margin: '10px 0 0' }}>{s.end_to_end.note}</p>
              </Card>
              <Card title="Stock guard" description="The same orders against a shelf with too little stock">
                <dl className="kv">
                  <dt>Shelf empty</dt><dd><b>{s.end_to_end.stock_guard.empty_refused ?? 0} of {s.end_to_end.stock_guard.empty_checked ?? 0}</b> refused</dd>
                  <dt>Half the quantity</dt><dd><b>{s.end_to_end.stock_guard.half_asked_or_offered ?? 0}</b> offered what is left, {s.end_to_end.stock_guard.half_refused ?? 0} refused</dd>
                  <dt>Stock below zero</dt><dd><b>{(s.end_to_end.stock_guard.empty_negative_stock ?? 0) + (s.end_to_end.stock_guard.half_negative_stock ?? 0)}</b> times</dd>
                  <dt>Orders over stock</dt><dd><b>{(s.end_to_end.stock_guard.empty_order_over_stock ?? 0) + (s.end_to_end.stock_guard.half_order_over_stock ?? 0)}</b></dd>
                </dl>
                <p className="muted small" style={{ margin: '10px 0 0' }}>An order that cannot be filled is never created, and stock is updated in the same database transaction as the order.</p>
              </Card>
            </div>

            <Section id="latency" title="Speed" />
            <div className="cols even">
              <Card title="Measured on this build" description="Parser only, on the machine that built the results file">
                <dl className="kv">
                  <dt>Median</dt><dd><b>{lp?.p50_ms} ms</b> per sentence</dd>
                  <dt>95th percentile</dt><dd>{lp?.p95_ms} ms</dd>
                  <dt>Slowest</dt><dd>{lp?.max_ms} ms</dd>
                  <dt>Timings</dt><dd>{lp?.n.toLocaleString('en-IN')}</dd>
                </dl>
                <p className="muted small" style={{ margin: '10px 0 0' }}>Text parsing only. It excludes speech recognition, speech synthesis and the network.</p>
              </Card>
              <Card title="Measured on live Gnani calls" description="Recorded by this server for each real call">
                {lat.loading && !lat.data ? <SkeletonCard lines={3} /> : liveCalls === 0 ? (
                  <Empty title="No live call recorded" icon="mic">Speech recognition and synthesis times appear here after the first real Gnani call. Add a key in <Link to="/settings">Settings</Link> and use the voice desk. Until then nothing is shown rather than an estimate.</Empty>
                ) : (
                  <dl className="kv">
                    <dt>Speech recognition</dt><dd>{stt && stt.ok ? <><b>{ms(stt.p50_ms)}</b> median, {ms(stt.p95_ms)} p95, {stt.ok} calls ({stt.errors} failed)</> : 'No successful call'}</dd>
                    <dt>Speech synthesis</dt><dd>{tts && tts.ok ? <><b>{ms(tts.p50_ms)}</b> median, {ms(tts.p95_ms)} p95, {tts.ok} calls ({tts.errors} failed)</> : 'No successful call'}</dd>
                  </dl>
                )}
              </Card>
            </div>

            {http.length > 0 && ev.data?.api_latency && (
              <Card title="Server response time" description={`Local HTTP on ${ev.data.api_latency.machine}. ${ev.data.api_latency.note}`} flush>
                <div className="table-wrap">
                  <table className="tbl">
                    <caption className="sr-only">Server response time per endpoint in milliseconds</caption>
                    <thead><tr><th scope="col">Request</th><th scope="col" className="num">Median (ms)</th><th scope="col" className="num">95th percentile (ms)</th><th scope="col" className="num">Requests</th></tr></thead>
                    <tbody>
                      {http.map((r) => (
                        <tr key={r.endpoint}><th scope="row">{r.label}</th><td className="num">{r.stat.p50_ms}</td><td className="num">{r.stat.p95_ms}</td><td className="num">{r.stat.n}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted small card-pad" style={{ margin: 0 }}>One machine and one server process over loopback, so it shows the server is not the slow part. It is not what a shop on a real network will see, and it contains no Gnani call.</p>
              </Card>
            )}

            <Section id="tables" title="Evaluation tables" />
            <Card title="AI evaluation metrics" description="Every result with the data and method behind it, and what it does and does not tell you" flush>
              <GridTable rows={metrics} columns={metricColumns} rowKey={(r) => r.metric} noun="metrics" exportName="evaluation-metrics" pageSize={8} />
            </Card>
            <Card title="Test and verification" description={ev.data?.verification ? `Recorded from the last full run, ${when(ev.data.verification.generated_at)}. Commands are in docs/TESTING.md.` : undefined} flush>
              {ev.data?.verification ? (
                <GridTable rows={ev.data.verification.rows} columns={verColumns} rowKey={(r) => r.category} noun="categories" exportName="test-verification" pageSize={12} />
              ) : (
                <div className="card-pad"><Empty title="No test record yet" icon="shield">Run <code>python scripts/build_verification_summary.py</code> after a test run to record the results here.</Empty></div>
              )}
            </Card>
            <Card title="Technology stack" description="What the product is built from and how far each part is implemented and checked" flush>
              {s.technology?.length ? <GridTable rows={s.technology} columns={techColumns} rowKey={(r) => r.component} noun="components" exportName="technology-stack" pageSize={12} /> : <div className="card-pad"><Empty title="Not recorded" icon="database" /></div>}
            </Card>

            <Section id="limits" title="Limits of these results" />
            <Card>
              <ul className="list-bullets">{s.limitations.map((l) => <li key={l}>{l}</li>)}{s.branded.caveats.map((l) => <li key={l}>{l}</li>)}</ul>
              <p className="muted small" style={{ margin: '10px 0 0' }}>Source: <code>eval/results/evaluation_summary.json</code>, built by <code>scripts/build_evaluation_summary.py</code>{ev.data?.file_modified ? ` (file saved ${when(ev.data.file_modified)})` : ''}. {s.scope}</p>
            </Card>
          </>
        )}
      </div>
    </>
  )
}
