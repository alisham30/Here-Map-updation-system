// ============================================================================
// PlaceIQ Singapore — Main App Component
// ============================================================================
import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'
import MapView from './components/MapView'
import Sidebar from './components/Sidebar'
import DetailPanel from './components/DetailPanel'

export type Place = {
  detected_name?: string; name?: string;
  latitude?: number; longitude?: number;
  status?: string; confidence?: number;
  category?: string; source_layer?: string;
  source_count?: number; match_type?: string;
  review_needed?: boolean; review_reason?: string;
  nearest_baseline_name?: string;
  website_state?: string; delivery_available?: boolean;
  social_active?: boolean; visual_state?: string;
  discussion_sentiment?: string; source_types?: string[];
  address?: string; place_id?: string;
  distance_m?: number; brand?: string;
  evidence_summary?: string; priority?: number;
  suggested_action?: string;
  [key: string]: any;
}

export type SidebarTab = 'dashboard' | 'places' | 'review' | 'layers' | 'pipeline' | 'nlp'

export default function App() {
  const [tab, setTab] = useState<SidebarTab>('dashboard')
  const [stats, setStats] = useState<any>(null)
  const [analyticsData, setAnalyticsData] = useState<any>(null)
  const [places, setPlaces] = useState<Place[]>([])
  const [reviewQueue, setReviewQueue] = useState<Place[]>([])
  const [reviewStats, setReviewStats] = useState<any>(null)
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null)
  const [selectedPlaceIndex, setSelectedPlaceIndex] = useState<number>(-1)
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [pipelineEvents, setPipelineEvents] = useState<any[]>([])
  const [batchSize, setBatchSize] = useState(50)
  const [layers, setLayers] = useState<Record<string, any>>({})
  const [enabledLayers, setEnabledLayers] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [showVisualsOnly, setShowVisualsOnly] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [hasResults, setHasResults] = useState(false)
  const [mapCenter, setMapCenter] = useState<[number, number]>([1.3521, 103.8198])
  const [nlpQuery, setNlpQuery] = useState('')
  const [nlpLoading, setNlpLoading] = useState(false)
  const [nlpMatches, setNlpMatches] = useState<Place[]>([])
  const [nlpInterpretation, setNlpInterpretation] = useState('')
  const [nlpReason, setNlpReason] = useState('')
  const [nlpUsedModel, setNlpUsedModel] = useState<string>('none')
  const [nlpGrounding, setNlpGrounding] = useState<any>(null)
  const [nlpMode, setNlpMode] = useState(false)
  const layersLoadedRef = useRef(false)

  const loadResults = useCallback(async () => {
    try {
      const [placesRes, analyticsRes, reviewRes, reviewStatsRes] = await Promise.all([
        api.places(),
        api.analyticsSummary(),
        api.reviewQueue(),
        api.reviewStats(),
      ])
      setPlaces(placesRes.places || [])
      setNlpMode(false)
      setNlpMatches([])
      setNlpInterpretation('')
      setNlpReason('')
      setNlpUsedModel('none')
      setAnalyticsData(analyticsRes)
      setReviewQueue(reviewRes.items || [])
      setReviewStats(reviewStatsRes)
      setHasResults(true)
    } catch (e) {
      console.error('Failed to load results:', e)
    }
  }, [])

  const loadLayers = useCallback(async () => {
    if (layersLoadedRef.current) return
    try {
      const data = await api.layers()
      const loadedLayers = data.layers || {}
      setLayers(loadedLayers)
      // Enable ALL layers by default so baseline features are visible
      setEnabledLayers(new Set(Object.keys(loadedLayers)))
      layersLoadedRef.current = true
    } catch (e) {
      console.error('Failed to load layers:', e)
    }
  }, [])

  // Load initial data + all baseline layers
  useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        const [statsRes, statusRes] = await Promise.all([
          api.baselineStats(),
          api.pipelineStatus(),
        ])
        if (cancelled) return
        setStats(statsRes)
        setHasResults(statusRes.has_results)
        // Always load baseline layers so the map shows all features
        loadLayers()
        if (statusRes.has_results) {
          loadResults()
        }
      } catch (e) {
        console.error('Failed to load initial data:', e)
      }
    }
    init()
    return () => { cancelled = true }
  }, [loadResults, loadLayers])

  const runPipeline = useCallback(async (opts?: { limit?: number; query?: string }) => {
    setPipelineRunning(true)
    setPipelineEvents([])
    setTab('pipeline')
    try {
      const result = await api.runPipeline(opts)
      if (result.success) {
        setPipelineEvents(result.events || [])
        await loadResults()
        setTab('dashboard')
      } else {
        setPipelineEvents([{ stage: 'error', status: 'error', message: result.error }])
      }
    } catch (e: any) {
      setPipelineEvents([{ stage: 'error', status: 'error', message: e.message }])
    } finally {
      setPipelineRunning(false)
    }
  }, [loadResults])

  const handleReviewAction = useCallback(async (index: number, action: string) => {
    try {
      await api.reviewAction(index, action)
      await loadResults()
    } catch (e) {
      console.error('Review action failed:', e)
    }
  }, [loadResults])

  const runNlpSearch = useCallback(async () => {
    if (!nlpQuery.trim()) return
    setNlpLoading(true)
    try {
      const res = await api.nlpSearch(nlpQuery.trim(), 150, false)
      const matches = res.matches || []
      setNlpMatches(matches)
      setNlpInterpretation(res.interpretation || '')
      setNlpReason(res.reason || '')
      setNlpUsedModel(res.used_model || 'unknown')
      setNlpGrounding(res.grounding || null)
      setNlpMode(true)
      setTab('nlp')
      if (matches.length > 0) {
        const first = matches[0]
        if (first?.latitude && first?.longitude) {
          setMapCenter([first.latitude, first.longitude])
        }
      }
    } catch (e) {
      console.error('NLP search failed:', e)
    } finally {
      setNlpLoading(false)
    }
  }, [nlpQuery])

  const clearNlpMode = useCallback(() => {
    setNlpMode(false)
    setNlpMatches([])
    setNlpInterpretation('')
    setNlpReason('')
    setNlpUsedModel('none')
    setNlpGrounding(null)
  }, [])

  const toggleLayer = useCallback((name: string) => {
    setEnabledLayers(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }, [])

  const flyTo = useCallback((lat: number, lon: number) => {
    setMapCenter([lat, lon])
  }, [])

  const handlePlaceClick = useCallback((place: Place) => {
    setSelectedPlace(place)
    // Find the index in the full places array for XAI explanation API
    const idx = places.findIndex(p =>
      (p.detected_name || p.name) === (place.detected_name || place.name) &&
      p.latitude === place.latitude && p.longitude === place.longitude
    )
    setSelectedPlaceIndex(idx)
    const lat = place.latitude
    const lon = place.longitude
    if (lat && lon) flyTo(lat, lon)
  }, [flyTo, places])

  // Load layers when tab switches to layers
  useEffect(() => {
    if (tab === 'layers') {
      loadLayers()
    }
  }, [tab, loadLayers])

  // Filtered places
  // In NLP mode, show the semantic search results exactly as returned — do NOT
  // re-apply the status/image chips (they'd hide e.g. active seafood when a
  // "Closed"/"New Place" chip was left selected).
  const filteredPlaces = nlpMode
    ? nlpMatches
    : places.filter(p => {
        if (statusFilter && p.status !== statusFilter) return false
        if (showVisualsOnly && !p.image_url) return false
        if (searchQuery) {
          const q = searchQuery.toLowerCase()
          const name = (p.detected_name || p.name || '').toLowerCase()
          if (!name.includes(q)) return false
        }
        return true
      })

  return (
    <div className="app-container">
      <header className="app-header">
        <h1><span>PlaceIQ</span> Singapore</h1>
        <div className="header-actions">
          {hasResults && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {places.length} classified places
            </span>
          )}
          <select
            value={batchSize}
            onChange={e => setBatchSize(Number(e.target.value))}
            disabled={pipelineRunning}
            title="How many places to verify per run"
            style={{
              background: 'var(--bg-primary)', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px',
              fontSize: 12,
            }}
          >
            <option value={50}>50 places</option>
            <option value={100}>100 places</option>
            <option value={150}>150 places</option>
            <option value={200}>200 places</option>
          </select>
          <button
            className="btn btn-primary"
            onClick={() => runPipeline({ limit: batchSize })}
            disabled={pipelineRunning}
          >
            {pipelineRunning ? (
              <><span className="spinner" /> Running...</>
            ) : 'Run Pipeline'}
          </button>
        </div>
      </header>

      <div className="main-content">
          <Sidebar
            tab={tab}
            setTab={setTab}
          stats={stats}
          analyticsData={analyticsData}
          places={filteredPlaces}
          reviewQueue={reviewQueue}
          reviewStats={reviewStats}
          layers={layers}
          enabledLayers={enabledLayers}
          toggleLayer={toggleLayer}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            showVisualsOnly={showVisualsOnly}
            setShowVisualsOnly={setShowVisualsOnly}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            pipelineRunning={pipelineRunning}
            pipelineEvents={pipelineEvents}
            nlpQuery={nlpQuery}
            setNlpQuery={setNlpQuery}
            nlpLoading={nlpLoading}
            nlpInterpretation={nlpInterpretation}
            nlpReason={nlpReason}
            nlpUsedModel={nlpUsedModel}
            nlpResultCount={nlpMatches.length}
            nlpMode={nlpMode}
            nlpGrounding={nlpGrounding}
            onVerifyQuery={(q: string) => runPipeline({ query: q, limit: batchSize })}
            onRunNlpSearch={runNlpSearch}
            onClearNlpMode={clearNlpMode}
            onPlaceClick={handlePlaceClick}
            onReviewAction={handleReviewAction}
            hasResults={hasResults}
        />
        <div className="map-container">
          <MapView
            classifiedPlaces={filteredPlaces}
            layers={layers}
            enabledLayers={enabledLayers}
            onPlaceClick={handlePlaceClick}
            center={mapCenter}
          />
          {selectedPlace && (
            <DetailPanel
              place={selectedPlace}
              placeIndex={selectedPlaceIndex}
              onClose={() => { setSelectedPlace(null); setSelectedPlaceIndex(-1); }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
