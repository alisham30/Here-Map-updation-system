// ============================================================================
// API Client
// ============================================================================
const BASE = '';

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, opts);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  // Baseline
  baselineStats: () => fetchJSON<any>('/api/baseline/stats'),
  baselinePlaces: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchJSON<any>('/api/baseline/places' + qs);
  },
  layers: () => fetchJSON<any>('/api/layers'),

  // Pipeline. Optional opts:
  //   limit — how many places to verify (5–200)        [bigger batch]
  //   query — category/area target e.g. "seafood"      [targeted run]
  runPipeline: (opts?: { limit?: number; query?: string }) => {
    const p = new URLSearchParams()
    if (opts?.limit) p.set('limit', String(opts.limit))
    if (opts?.query && opts.query.trim()) p.set('query', opts.query.trim())
    const qs = p.toString() ? '?' + p.toString() : ''
    return fetchJSON<any>('/api/pipeline/run' + qs, { method: 'POST' })
  },
  pipelineStatus: () => fetchJSON<any>('/api/pipeline/status'),

  // Places (classified)
  places: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchJSON<any>('/api/places' + qs);
  },
  placesGeoJSON: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchJSON<any>('/api/places/geojson' + qs);
  },

  // Analytics
  analyticsSummary: () => fetchJSON<any>('/api/analytics/summary'),

  // Review
  reviewQueue: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchJSON<any>('/api/review/queue' + qs);
  },
  reviewAction: (index: number, action: string, notes: string = '') =>
    fetchJSON<any>(`/api/review/action?item_index=${index}&action=${action}&notes=${encodeURIComponent(notes)}`, { method: 'POST' }),
  reviewStats: () => fetchJSON<any>('/api/review/stats'),

  // Vision Intelligence
  visionAnalysis: (lat: number, lon: number, name: string, category: string, osmId: string) =>
    fetchJSON<any>(`/api/vision?lat=${lat}&lon=${lon}&name=${encodeURIComponent(name)}&category=${encodeURIComponent(category)}&osm_id=${encodeURIComponent(osmId)}`),

  // Health
  health: () => fetchJSON<any>('/api/health'),

  // XAI Explanations
  placeExplanation: (index: number) => fetchJSON<any>(`/api/places/${index}/explanation`),
  allWithExplanations: (status?: string) => {
    const qs = status ? `?status=${status}` : '';
    return fetchJSON<any>('/api/places/all-with-explanations' + qs);
  },

  // NLP semantic POI search
  nlpSearch: (query: string, limit: number = 10, useFull: boolean = false) =>
    fetchJSON<any>('/api/nlp/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit, use_full: useFull }),
    }),
};
