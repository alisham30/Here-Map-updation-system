// ============================================================================
// Sidebar Component
// ============================================================================
import type { Place, SidebarTab } from '../App'

type Props = {
  tab: SidebarTab
  setTab: (t: SidebarTab) => void
  stats: any
  analyticsData: any
  places: Place[]
  reviewQueue: Place[]
  reviewStats: any
  layers: Record<string, any>
  enabledLayers: Set<string>
  toggleLayer: (name: string) => void
  statusFilter: string | null
  setStatusFilter: (s: string | null) => void
  showVisualsOnly: boolean
  setShowVisualsOnly: (v: boolean) => void
  searchQuery: string
  setSearchQuery: (q: string) => void
  pipelineRunning: boolean
  pipelineEvents: any[]
  nlpQuery: string
  setNlpQuery: (q: string) => void
  nlpLoading: boolean
  nlpInterpretation: string
  nlpReason: string
  nlpUsedModel: string
  nlpResultCount: number
  nlpMode: boolean
  nlpGrounding: any
  onVerifyQuery: (q: string) => void
  onRunNlpSearch: () => void
  onClearNlpMode: () => void
  onPlaceClick: (place: Place) => void
  onReviewAction: (index: number, action: string) => void
  hasResults: boolean
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  new_place: 'New Place',
  closed: 'Closed',
  rebranded: 'Rebranded',
  uncertain: 'Uncertain',
}

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  new_place: '#3b82f6',
  closed: '#ef4444',
  rebranded: '#a855f7',
  uncertain: '#eab308',
}

export default function Sidebar(props: Props) {
  const { tab, setTab, stats, analyticsData, places, reviewQueue, reviewStats,
    layers, enabledLayers, toggleLayer, statusFilter, setStatusFilter,
    showVisualsOnly, setShowVisualsOnly, searchQuery, setSearchQuery, pipelineRunning, pipelineEvents,
    nlpQuery, setNlpQuery, nlpLoading, nlpInterpretation, nlpReason, nlpUsedModel, nlpResultCount, nlpMode, nlpGrounding, onVerifyQuery, onRunNlpSearch, onClearNlpMode,
    onPlaceClick, onReviewAction, hasResults } = props

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        {(['dashboard', 'places', 'review', 'layers', 'pipeline', 'nlp'] as SidebarTab[]).map(t => (
          <button
            key={t}
            className={`sidebar-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="sidebar-content">
        {tab === 'dashboard' && <DashboardTab stats={stats} analyticsData={analyticsData} hasResults={hasResults} />}
        {tab === 'places' && (
          <PlacesTab
            places={places} statusFilter={statusFilter} setStatusFilter={setStatusFilter}
            showVisualsOnly={showVisualsOnly}
            setShowVisualsOnly={setShowVisualsOnly}
            searchQuery={searchQuery} setSearchQuery={setSearchQuery}
            onPlaceClick={onPlaceClick}
          />
        )}
        {tab === 'review' && (
          <ReviewTab queue={reviewQueue} stats={reviewStats} onAction={onReviewAction} />
        )}
        {tab === 'layers' && (
          <LayersTab layers={layers} enabledLayers={enabledLayers} toggleLayer={toggleLayer} />
        )}
        {tab === 'pipeline' && (
          <PipelineTab running={pipelineRunning} events={pipelineEvents} />
        )}
        {tab === 'nlp' && (
          <NlpTab
            query={nlpQuery}
            setQuery={setNlpQuery}
            loading={nlpLoading}
            interpretation={nlpInterpretation}
            reason={nlpReason}
            usedModel={nlpUsedModel}
            resultCount={nlpResultCount}
            nlpMode={nlpMode}
            grounding={nlpGrounding}
            matches={nlpMode ? places : []}
            onVerify={onVerifyQuery}
            onPlaceClick={onPlaceClick}
            onRun={onRunNlpSearch}
            onClear={onClearNlpMode}
          />
        )}
      </div>
    </div>
  )
}

// ── Dashboard Tab ──────────────────────────────────────────────────────────
function DashboardTab({ stats, analyticsData, hasResults }: { stats: any; analyticsData: any; hasResults: boolean }) {
  const statuses = analyticsData?.statuses || {}
  return (
    <div>
      <h3 style={{ marginBottom: 12, fontSize: 14 }}>Overview</h3>
      <div className="summary-grid">
        <div className="summary-card">
          <div className="label">Baseline POIs</div>
          <div className="value" style={{ color: 'var(--cyan)' }}>{stats?.total?.toLocaleString() || '—'}</div>
        </div>
        <div className="summary-card">
          <div className="label">Classified</div>
          <div className="value">{analyticsData?.total_classified || '—'}</div>
        </div>
        <div className="summary-card">
          <div className="label">New Places</div>
          <div className="value" style={{ color: STATUS_COLORS.new_place }}>{statuses.new_place || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Closed</div>
          <div className="value" style={{ color: STATUS_COLORS.closed }}>{statuses.closed || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Rebranded</div>
          <div className="value" style={{ color: STATUS_COLORS.rebranded }}>{statuses.rebranded || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Uncertain</div>
          <div className="value" style={{ color: STATUS_COLORS.uncertain }}>{statuses.uncertain || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Active</div>
          <div className="value" style={{ color: STATUS_COLORS.active }}>{statuses.active || 0}</div>
        </div>
        <div className="summary-card">
          <div className="label">Review Queue</div>
          <div className="value" style={{ color: 'var(--orange)' }}>{analyticsData?.review_queue_size || 0}</div>
        </div>
      </div>

      {!hasResults && (
        <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
          <p style={{ fontSize: 13, marginBottom: 8 }}>No pipeline results yet.</p>
          <p style={{ fontSize: 12 }}>Click <b>"▶ Run Pipeline"</b> to start the agentic analysis.</p>
        </div>
      )}

      {hasResults && analyticsData?.source_contribution && (
        <>
          <h3 style={{ margin: '16px 0 8px', fontSize: 14 }}>Source Contributions</h3>
          {Object.entries(analyticsData.source_contribution as Record<string, number>)
            .sort(([, a], [, b]) => (b as number) - (a as number))
            .map(([src, count]) => {
              const max = Math.max(...Object.values(analyticsData.source_contribution as Record<string, number>).map(Number))
              const pct = max > 0 ? ((count as number) / max) * 100 : 0
              return (
                <div className="chart-bar-row" key={src}>
                  <div className="chart-bar-label">{src.replace(/_/g, ' ')}</div>
                  <div className="chart-bar-track">
                    <div className="chart-bar-fill" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
                  </div>
                  <div className="chart-bar-count">{count as number}</div>
                </div>
              )
            })}
        </>
      )}

      {stats?.layers && (
        <>
          <h3 style={{ margin: '16px 0 8px', fontSize: 14 }}>Baseline Layers</h3>
          {Object.entries(stats.layers as Record<string, number>)
            .sort(([, a], [, b]) => (b as number) - (a as number))
            .map(([layer, count]) => {
              const max = Math.max(...Object.values(stats.layers as Record<string, number>).map(Number))
              const pct = max > 0 ? ((count as number) / max) * 100 : 0
              return (
                <div className="chart-bar-row" key={layer}>
                  <div className="chart-bar-label">{layer}</div>
                  <div className="chart-bar-track">
                    <div className="chart-bar-fill" style={{ width: `${pct}%`, background: 'var(--cyan)' }} />
                  </div>
                  <div className="chart-bar-count">{count as number}</div>
                </div>
              )
            })}
        </>
      )}
    </div>
  )
}

// ── Places Tab ─────────────────────────────────────────────────────────────
function PlacesTab({ places, statusFilter, setStatusFilter, showVisualsOnly, setShowVisualsOnly, searchQuery, setSearchQuery, onPlaceClick }: {
  places: Place[]; statusFilter: string | null; setStatusFilter: (s: string | null) => void;
  showVisualsOnly: boolean; setShowVisualsOnly: (v: boolean) => void;
  searchQuery: string; setSearchQuery: (q: string) => void; onPlaceClick: (p: Place) => void;
}) {
  return (
    <div>
      <input
        className="search-input"
        placeholder="Search places..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
      />
      <div className="filter-bar">
        <span
          className={`filter-chip ${!statusFilter ? 'active' : ''}`}
          onClick={() => setStatusFilter(null)}
        >All</span>
        {Object.entries(STATUS_LABELS).map(([key, label]) => (
          <span
            key={key}
            className={`filter-chip ${statusFilter === key ? 'active' : ''}`}
            onClick={() => setStatusFilter(statusFilter === key ? null : key)}
          >{label}</span>
        ))}
        <span
          className={`filter-chip ${showVisualsOnly ? 'active' : ''}`}
          onClick={() => setShowVisualsOnly(!showVisualsOnly)}
        >Images</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
        Showing {places.length} places
      </div>
      <div className="place-list">
        {places.slice(0, 200).map((p, i) => (
          <div key={i} className="place-item" onClick={() => onPlaceClick(p)}>
            <div className="place-name">
              {p.detected_name || p.name || 'Unknown'}
              <span className={`badge badge-${p.status || 'uncertain'}`} style={{ marginLeft: 8 }}>
                {STATUS_LABELS[p.status || 'uncertain'] || p.status}
              </span>
            </div>
            <div className="place-meta">
              <span>{p.category || p.source_layer}</span>
              <span>{Math.round((p.confidence || 0) * 100)}% conf</span>
              <span>{p.source_count || 0} sources</span>
            </div>
          </div>
        ))}
        {places.length === 0 && (
          <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 12 }}>
            No places found. Run the pipeline first.
          </div>
        )}
      </div>
    </div>
  )
}

// ── Review Tab ─────────────────────────────────────────────────────────────
function ReviewTab({ queue, stats, onAction }: {
  queue: Place[]; stats: any; onAction: (i: number, action: string) => void;
}) {
  return (
    <div>
      <h3 style={{ marginBottom: 8, fontSize: 14 }}>Review Queue</h3>
      {stats && (
        <div className="summary-grid" style={{ marginBottom: 12 }}>
          <div className="summary-card">
            <div className="label">Total</div>
            <div className="value">{stats.total || 0}</div>
          </div>
          <div className="summary-card">
            <div className="label">Pending</div>
            <div className="value" style={{ color: 'var(--orange)' }}>{stats.pending || 0}</div>
          </div>
          <div className="summary-card">
            <div className="label">Reviewed</div>
            <div className="value" style={{ color: 'var(--green)' }}>{stats.reviewed || 0}</div>
          </div>
        </div>
      )}
      {queue.map((item, i) => (
        <div key={i} className="review-item">
          <div className="review-name">
            {item.detected_name || item.name || 'Unknown'}
            <span className={`badge badge-${item.status || 'uncertain'}`} style={{ marginLeft: 8 }}>
              {STATUS_LABELS[item.status || 'uncertain'] || item.status}
            </span>
            {item.priority && <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 6 }}>P{item.priority}</span>}
          </div>
          <div className="review-reason">{item.review_reason || item.evidence_summary || 'Needs review'}</div>
          {item.evidence_summary && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>{item.evidence_summary}</div>}
          <div className="review-actions">
            <button className="btn btn-sm btn-green" onClick={() => onAction(i, 'approve_new')}>New</button>
            <button className="btn btn-sm btn-red" onClick={() => onAction(i, 'approve_closed')}>Closed</button>
            <button className="btn btn-sm btn-purple" onClick={() => onAction(i, 'approve_rebrand')}>Rebrand</button>
            <button className="btn btn-sm btn-outline" onClick={() => onAction(i, 'mark_active')}>Active</button>
            <button className="btn btn-sm btn-outline" onClick={() => onAction(i, 'need_more_evidence')}>Need More</button>
          </div>
        </div>
      ))}
      {queue.length === 0 && (
        <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 12 }}>
          No items in review queue.
        </div>
      )}
    </div>
  )
}

// ── Layers Tab ─────────────────────────────────────────────────────────────
function LayersTab({ layers, enabledLayers, toggleLayer }: {
  layers: Record<string, any>; enabledLayers: Set<string>; toggleLayer: (n: string) => void;
}) {
  return (
    <div>
      <h3 style={{ marginBottom: 12, fontSize: 14 }}>GeoJSON Layers</h3>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
        Toggle baseline layers from the OSM dataset on the map.
      </p>
      {Object.entries(layers).map(([name, gj]) => (
        <label key={name} className="layer-toggle">
          <input
            type="checkbox"
            checked={enabledLayers.has(name)}
            onChange={() => toggleLayer(name)}
          />
          <span>{name}</span>
          <span className="layer-count">{(gj as any)?.features?.length || 0}</span>
        </label>
      ))}
      {Object.keys(layers).length === 0 && (
        <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 12 }}>
          Loading layers...
        </div>
      )}
    </div>
  )
}

// ── Pipeline Tab — agentic reasoning timeline ───────────────────────────────
const STAGE_META: Record<string, { label: string }> = {
  baseline:   { label: 'Baseline' },
  plan:       { label: 'Plan' },
  extraction: { label: 'Gather evidence' },
  reasoning:  { label: 'Reason' },
  reflection: { label: 'Reflect & re-plan' },
  review:     { label: 'Review queue' },
  done:       { label: 'Done' },
  error:      { label: 'Error' },
  start:      { label: 'Start' },
}

const STATUS_DOT: Record<string, string> = {
  selected: '#22c55e', complete: '#22c55e', progress: '#3b82f6',
  running: '#3b82f6', replan: '#a855f7', warning: '#f97316',
  skipped: '#64748b', error: '#ef4444',
}

function PipelineTab({ running, events }: { running: boolean; events: any[] }) {
  // Group consecutive events by stage to form timeline phases.
  const phases: { stage: string; events: any[] }[] = []
  for (const e of events) {
    const last = phases[phases.length - 1]
    if (last && last.stage === e.stage) last.events.push(e)
    else phases.push({ stage: e.stage, events: [e] })
  }

  const planned = events.filter(e => e.stage === 'plan' && e.status === 'selected').length
  const skipped = events.filter(e => e.stage === 'plan' && e.status === 'skipped').length
  const didReplan = events.some(e => e.stage === 'reflection' && e.status === 'replan')

  return (
    <div>
      <h3 style={{ marginBottom: 10, fontSize: 14 }}>
        Agent Pipeline {running && <span className="spinner" style={{ display: 'inline-block', marginLeft: 8 }} />}
      </h3>

      {events.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          <MiniStat label="agents planned" value={planned} color="#22c55e" />
          <MiniStat label="skipped" value={skipped} color="#64748b" />
          {didReplan && <MiniStat label="adaptive re-plan" value="yes" color="#a855f7" />}
        </div>
      )}

      {running && (
        <div className="progress-bar" style={{ marginBottom: 12 }}>
          <div className="progress-fill" style={{ width: '60%' }} />
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {phases.map((phase, pi) => {
          const meta = STAGE_META[phase.stage] || { label: phase.stage }
          return (
            <div key={pi} style={{ display: 'flex', gap: 10 }}>
              {/* Rail */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 4 }}>
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--accent)', flexShrink: 0 }} />
                {pi < phases.length - 1 && (
                  <div style={{ width: 2, flex: 1, background: 'var(--border)', minHeight: 10, marginTop: 2 }} />
                )}
              </div>
              {/* Phase content */}
              <div style={{ paddingBottom: 10, flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                  letterSpacing: '0.4px', color: 'var(--text-secondary)', marginBottom: 3,
                }}>
                  {meta.label}
                </div>
                {phase.events.map((e, ei) => (
                  <div key={ei} style={{
                    display: 'flex', gap: 6, alignItems: 'flex-start',
                    fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45, padding: '1px 0',
                  }}>
                    <span style={{
                      width: 6, height: 6, borderRadius: '50%', marginTop: 5, flexShrink: 0,
                      background: STATUS_DOT[e.status] || 'var(--text-muted)',
                    }} />
                    <span>{e.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
        {events.length === 0 && !running && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            Pipeline not running. Click "▶ Run Pipeline" to watch the agents plan, gather, reason, and re-plan.
          </div>
        )}
      </div>
    </div>
  )
}

function MiniStat({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <span style={{
      fontSize: 10, padding: '3px 8px', borderRadius: 6,
      background: `${color}1a`, border: `1px solid ${color}40`, color,
      fontWeight: 700,
    }}>
      {value} <span style={{ opacity: 0.7, fontWeight: 500 }}>{label}</span>
    </span>
  )
}

// ── NLP Tab ───────────────────────────────────────────────────────────────
function NlpTab({
  query, setQuery, loading, interpretation, reason, usedModel, resultCount, nlpMode, grounding, matches, onVerify, onPlaceClick, onRun, onClear,
}: {
  query: string
  setQuery: (q: string) => void
  loading: boolean
  interpretation: string
  reason: string
  usedModel: string
  resultCount: number
  nlpMode: boolean
  grounding: any
  matches: Place[]
  onVerify: (q: string) => void
  onPlaceClick: (p: Place) => void
  onRun: () => void
  onClear: () => void
}) {
  const groundChips: { label: string; value: string }[] = []
  if (grounding) {
    if (grounding.intent) groundChips.push({ label: 'intent', value: String(grounding.intent) })
    if (grounding.entity_type) groundChips.push({ label: 'entity', value: String(grounding.entity_type) })
    if (grounding.location_scope) groundChips.push({ label: 'where', value: String(grounding.location_scope) })
    if (grounding.status_filter) groundChips.push({ label: 'status', value: String(grounding.status_filter) })
  }
  return (
    <div>
      <h3 style={{ marginBottom: 10, fontSize: 14 }}>Semantic Search</h3>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
        Ask naturally: "veg restaurant near orchard", "hotel near marina bay", etc.
      </div>
      <textarea
        className="search-input"
        placeholder="Type your query..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={3}
        style={{ resize: 'vertical', marginBottom: 8 }}
      />
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <button className="btn btn-primary" onClick={onRun} disabled={loading || !query.trim()}>
          {loading ? 'Searching...' : 'Search'}
        </button>
        {nlpMode && (
          <button className="btn btn-outline" onClick={onClear}>Clear</button>
        )}
      </div>

      {/* Targeted classification: run the agentic pipeline on the searched
          category/area so these places get a real verified verdict. */}
      <button
        className="btn"
        onClick={() => onVerify(query)}
        disabled={!query.trim()}
        style={{
          width: '100%', marginBottom: 10, fontSize: 12, fontWeight: 600,
          background: 'rgba(34,197,94,0.15)', color: '#22c55e',
          border: '1px solid rgba(34,197,94,0.35)', borderRadius: 6, padding: '8px',
          cursor: query.trim() ? 'pointer' : 'not-allowed',
        }}
        title="Run the agentic pipeline on these places to verify open/closed/rebranded"
      >
        Verify these places (run pipeline on "{query.trim() || '…'}")
      </button>
      <div style={{
        background: 'var(--bg-primary)', border: '1px solid var(--border)',
        borderRadius: 8, padding: 10, fontSize: 12,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span><strong>Matches:</strong> {resultCount}</span>
          <span style={{
            fontSize: 10, padding: '2px 7px', borderRadius: 999, fontWeight: 700,
            background: usedModel === 'openai' ? 'rgba(34,197,94,0.15)' : usedModel === 'groq' ? 'rgba(59,130,246,0.15)' : 'rgba(100,116,139,0.15)',
            color: usedModel === 'openai' ? '#22c55e' : usedModel === 'groq' ? '#3b82f6' : '#94a3b8',
          }}>
            {usedModel === 'openai' ? 'GPT-4o grounding' : usedModel === 'groq' ? 'Groq' : usedModel === 'fallback' ? 'lexical fallback' : usedModel}
          </span>
        </div>

        {/* Structured query grounding (intent / entity / location / status) */}
        {groundChips.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 8 }}>
            {groundChips.map((c, i) => (
              <span key={i} style={{
                fontSize: 10, padding: '3px 7px', borderRadius: 6,
                background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.3)',
                color: 'var(--text-secondary)',
              }}>
                <span style={{ opacity: 0.65 }}>{c.label}:</span>{' '}
                <strong style={{ color: 'var(--accent)' }}>{c.value}</strong>
              </span>
            ))}
          </div>
        )}

        {interpretation && (
          <div style={{ marginBottom: 4 }}>
            <strong>Reading:</strong> {interpretation}
          </div>
        )}
        {reason && (
          <div style={{ color: 'var(--text-secondary)' }}>
            <strong>Why:</strong> {reason}
          </div>
        )}
      </div>

      {/* Named results list — click to fly to the place on the map */}
      {nlpMode && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>
            {matches.length} place{matches.length !== 1 ? 's' : ''} found
          </div>
          <div className="place-list">
            {matches.map((p, i) => (
              <div key={i} className="place-item" onClick={() => onPlaceClick(p)}>
                <div className="place-name">
                  {p.detected_name || p.name || 'Unknown'}
                  <span className={`badge badge-${p.status || 'uncertain'}`} style={{ marginLeft: 8 }}>
                    {STATUS_LABELS[p.status || 'uncertain'] || p.status}
                  </span>
                </div>
                <div className="place-meta">
                  <span>{p.cuisine || p.category || p.source_layer}</span>
                  {p.address ? <span>{p.address}</span> : null}
                </div>
              </div>
            ))}
            {matches.length === 0 && (
              <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
                No matches.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
