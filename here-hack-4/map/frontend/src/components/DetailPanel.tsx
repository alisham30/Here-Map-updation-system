// ============================================================================
// Detail Panel — Place details with XAI proof cards & explanations
// ============================================================================
import { useState, useEffect } from 'react'
import { api } from '../api'
import type { Place } from '../App'

const STATUS_LABELS: Record<string, string> = {
  active: 'Active', new_place: 'New Place', closed: 'Closed',
  rebranded: 'Rebranded', uncertain: 'Uncertain',
}

const STATUS_COLORS: Record<string, string> = {
  active: 'var(--green)', new_place: '#22c55e', closed: 'var(--red)',
  rebranded: 'var(--accent)', uncertain: 'var(--orange)',
}

const RELIABILITY_COLORS: Record<string, string> = {
  very_high: '#22c55e', high: '#3b82f6', medium_high: '#06b6d4',
  medium: '#eab308', low: '#f97316',
}

const SIGNAL_COLORS: Record<string, string> = {
  positive: '#22c55e', negative: '#ef4444', neutral: '#64748b',
}

type ProofCard = {
  source_type: string
  source_name: string
  source_icon: string
  finding: string
  confidence_contribution: number
  freshness: string
  reliability: string
  reasoning: string
  signal_direction: string
  supports_status: string
  signal_key?: string
}

type Explanation = {
  headline: string
  summary: string
  natural_explanation?: string
  proof_cards: ProofCard[]
  baseline_comparison: {
    nearest_name: string
    distance_m: number | null
    match_score: number
    match_type: string
    why_not_same: string
  } | null
  uncertainty_reasons: string[]
  total_proof_confidence: number
  recommendation: string
  // Faithfulness metadata (from the decision agent's real signal_breakdown)
  model?: string
  model_score?: number
  net_signal_score?: number
  is_faithful?: boolean
}

const MODEL_LABELS: Record<string, string> = {
  closure_score: 'Closure model',
  new_place_confidence: 'New-place model',
  rebrand_confidence: 'Rebrand model',
}

type Props = {
  place: Place
  placeIndex: number
  onClose: () => void
}

const STOREFRONT_COLORS: Record<string, string> = {
  ACTIVE: '#22c55e', CLOSED_TEMPORARY: '#f97316', CLOSED_PERMANENT: '#ef4444',
  UNDER_CONSTRUCTION: '#eab308', VACANT_LOT: '#ef4444', DIFFERENT_BUSINESS: '#8b5cf6', UNCLEAR: '#64748b',
}

function VisionSection({ place }: { place: Place }) {
  const [vision, setVision] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [showGradcam, setShowGradcam] = useState(false)

  const runVision = async () => {
    setLoading(true)
    try {
      const res = await api.visionAnalysis(
        place.latitude!, place.longitude!,
        place.detected_name || place.name || '',
        place.category || '',
        place.place_id || String(place.latitude) + '_' + String(place.longitude),
      )
      setVision(res.vision)
    } catch (e) {
      setVision({ vision_available: false, vision_error: String(e) })
    } finally {
      setLoading(false)
    }
  }

  // Backend renamed gemini_result -> vision_model_result (GPT-4o, no Google).
  const vm = vision?.vision_model_result || vision?.gemini_result || {}
  const statusColor = vision ? STOREFRONT_COLORS[vision.storefront_status] || '#64748b' : '#64748b'
  const recencyWeight = vision?.recency_weight ?? vision?.mapillary_result?.recency_weight
  const capturedAt = vision?.mapillary_result?.captured_at || vision?.satellite_result?.capture_date
  const ocrMatchScore = vision?.ocr_result?.match_score
  const ocrBestMatchText = vision?.ocr_result?.best_match_text
  const ocrNameMismatch = vision?.ocr_result?.name_mismatch
  const ocrClosureKeywords = vision?.ocr_result?.closure_keywords_found || []
  const yoloObjects = (vision?.yolo_result?.detected_objects || [])
    .map((o: any) => o?.class || o?.object)
    .filter(Boolean)

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 8,
      }}>
        <h4 style={{
          fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)',
          textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0,
        }}>
          Vision Intelligence
        </h4>
        {!vision && (
          <button
            onClick={runVision}
            disabled={loading}
            style={{
              fontSize: 11, fontWeight: 600, padding: '4px 10px',
              background: loading ? 'var(--bg-primary)' : 'rgba(59,130,246,0.15)',
              color: 'var(--accent)', border: '1px solid rgba(59,130,246,0.3)',
              borderRadius: 6, cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Analysing...' : 'Run Vision'}
          </button>
        )}
      </div>

      {!vision && !loading && (
        <div style={{
          padding: '10px 14px', background: 'var(--bg-primary)',
          border: '1px dashed var(--border)', borderRadius: 8,
          fontSize: 11, color: 'var(--text-muted)', textAlign: 'center',
        }}>
          Click "Run Vision" to fetch street imagery, run GradCAM &amp; AI analysis
        </div>
      )}

      {vision && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Verdict banner */}
          <div style={{
            padding: '10px 14px',
            background: `${statusColor}18`,
            border: `1px solid ${statusColor}50`,
            borderRadius: 8,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontWeight: 700, color: statusColor, fontSize: 13 }}>
                {vision.storefront_status || 'UNCLEAR'}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                confidence: {((vision.final_confidence || 0) * 100).toFixed(1)}%
              </span>
            </div>
            {/* Rebrand flag — a different business name on the sign than the map records */}
            {vision.is_rebrand && (
              <div style={{
                fontSize: 11, fontWeight: 700, color: '#8b5cf6', marginBottom: 6,
                padding: '4px 8px', borderRadius: 6,
                background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.35)',
              }}>
                Rebrand detected{vision.detected_name ? ` — sign reads "${vision.detected_name}"` : ''}
              </div>
            )}
            {vision.age_label && (
              <div style={{
                fontSize: 10, padding: '3px 8px', borderRadius: 4, display: 'inline-block',
                background: 'rgba(234,179,8,0.15)', color: '#eab308', marginBottom: 6,
              }}>
                {vision.age_label}
              </div>
            )}
            {typeof recencyWeight === 'number' && recencyWeight < 0.5 && (
              <div style={{ fontSize: 10, color: '#f97316', marginBottom: 6 }}>
                Older imagery detected (confidence reduced)
              </div>
            )}
            {capturedAt && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>
                Captured: {capturedAt}
              </div>
            )}
            {vm?.visual_evidence && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {vm.visual_evidence}
              </div>
            )}
            {vm?.active_indicators?.length > 0 && (
              <div style={{ fontSize: 10, color: '#22c55e', marginTop: 4 }}>
                Active: {vm.active_indicators.join(' · ')}
              </div>
            )}
            {vm?.closure_indicators?.length > 0 && (
              <div style={{ fontSize: 10, color: '#ef4444', marginTop: 4 }}>
                Closure: {vm.closure_indicators.join(' · ')}
              </div>
            )}
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 6, letterSpacing: '0.3px' }}>
              {(vision.vision_provider || 'gpt-4o')} · Mapillary{vision.gradcam_overlay_b64 || vision.gradcam_result?.gradcam_overlay_b64 ? ' · GradCAM' : ''}
            </div>
          </div>

          {/* Vision score bar */}
          {vision.vision_score >= 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 70 }}>Vision score</span>
              <div style={{ flex: 1, height: 6, background: 'var(--bg-primary)', borderRadius: 3 }}>
                <div style={{
                  width: `${vision.vision_score}%`, height: '100%', borderRadius: 3,
                  background: vision.vision_score >= 70 ? '#22c55e' : vision.vision_score >= 40 ? '#eab308' : '#ef4444',
                }} />
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', width: 28 }}>
                {vision.vision_score}
              </span>
            </div>
          )}

          {/* Street image */}
          {vision.image_url && (
            <div>
              <img
                src={vision.image_url}
                alt="Street view"
                style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)', maxHeight: 200, objectFit: 'cover' }}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          )}

          {/* GradCAM toggle */}
          {(vision.gradcam_overlay_b64 || vision.gradcam_result?.gradcam_overlay_b64) && (
            <div>
              <button
                onClick={() => setShowGradcam(v => !v)}
                style={{
                  width: '100%', padding: '6px', fontSize: 11, fontWeight: 600,
                  background: 'var(--bg-primary)', color: 'var(--accent)',
                  border: '1px solid var(--border)', borderRadius: 6, cursor: 'pointer',
                }}
              >
                {showGradcam ? 'Hide GradCAM Heatmap' : 'Show GradCAM Heatmap'}
              </button>
              {showGradcam && (
                <div style={{ marginTop: 6 }}>
                  <img
                    src={`data:image/jpeg;base64,${vision.gradcam_overlay_b64 || vision.gradcam_result?.gradcam_overlay_b64}`}
                    alt="GradCAM overlay"
                    style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)' }}
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                    Attention focus: <strong>{vision.gradcam_result?.attention_focus_zone || '—'}</strong>
                    {' · '}reliable: <strong>{vision.gradcam_result?.attention_reliable ? 'yes' : 'no'}</strong>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* OCR texts */}
          {vision.ocr_result?.raw_texts?.length > 0 && (
            <div style={{
              padding: '8px 10px', background: 'var(--bg-primary)',
              border: '1px solid var(--border)', borderRadius: 8,
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4 }}>
                OCR SIGNAGE TEXT
              </div>
              {vision.ocr_result.raw_texts.map((t: string, i: number) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--text-primary)' }}>"{t}"</div>
              ))}
              {vision.ocr_result.closure_signal_strength > 0 && (
                <div style={{ fontSize: 10, color: '#ef4444', marginTop: 4 }}>
                  Closure signal strength: {(vision.ocr_result.closure_signal_strength * 100).toFixed(0)}%
                </div>
              )}
              {ocrBestMatchText && typeof ocrMatchScore === 'number' && (
                <div style={{
                  fontSize: 10,
                  color: ocrNameMismatch ? '#ef4444' : '#22c55e',
                  marginTop: 4,
                }}>
                  Best sign match: "{ocrBestMatchText}" ({Math.round(ocrMatchScore * 100)}%){ocrNameMismatch ? ' — mismatch' : ' — match'}
                </div>
              )}
              {ocrClosureKeywords.length > 0 && (
                <div style={{ fontSize: 10, color: '#ef4444', marginTop: 4 }}>
                  Closure keywords: {ocrClosureKeywords.join(', ')}
                </div>
              )}
            </div>
          )}

          {/* YOLO objects */}
          {yoloObjects.length > 0 && (
            <div style={{
              padding: '8px 10px',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              fontSize: 10,
              color: 'var(--text-muted)',
            }}>
              Objects detected: {Array.from(new Set(yoloObjects)).slice(0, 8).join(', ')}
            </div>
          )}

          {/* Re-run button */}
          <button
            onClick={runVision}
            disabled={loading}
            style={{
              fontSize: 10, padding: '4px 8px', background: 'none',
              color: 'var(--text-muted)', border: '1px solid var(--border)',
              borderRadius: 5, cursor: 'pointer',
            }}
          >
            {loading ? 'Running...' : 'Re-run Vision'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function DetailPanel({ place, placeIndex, onClose }: Props) {
  // Sync explanation directly from the bundled object
  const explanation = place.xai_explanation as Explanation | null
  const [expanded, setExpanded] = useState(true)

  const name = place.detected_name || place.name || 'Unknown Place'
  const status = place.status || 'uncertain'
  const confidence = Math.round((place.confidence || 0) * 100)
  const confColor = confidence >= 70 ? 'var(--green)' : confidence >= 40 ? 'var(--yellow)' : 'var(--red)'
  const ageLabel = place.age_label || ''
  const recencyWeight = typeof place.recency_weight === 'number' ? place.recency_weight : 1.0
  const allTextFound = Array.isArray(place.all_text_found) ? place.all_text_found : []
  const detectedBusinessName = place.detected_business_name
  const nameMatchScore = typeof place.name_match_score === 'number' ? place.name_match_score : 0
  const closureKeywords = Array.isArray(place.closure_keywords) ? place.closure_keywords : []
  const yoloObjects = Array.isArray(place.yolo_objects) ? place.yolo_objects : []
  const imageExplanation = place.image_explanation || place.observation

  // Fetch explanation when place changes
  useEffect(() => {
    // No-op: Explanation is now bundled directly in the Place payload via FusionDecisionAgent
  }, [placeIndex])

  return (
    <div className="detail-panel" style={{
      width: 420, maxHeight: 'calc(100% - 24px)',
      backdropFilter: 'blur(12px)',
      background: 'rgba(30, 41, 59, 0.95)',
    }}>
      {/* Header */}
      <div className="detail-header" style={{ padding: '16px 20px' }}>
        <div>
          <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>{name}</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className={`badge badge-${status}`} style={{ fontSize: 11 }}>
              {STATUS_LABELS[status] || status}
            </span>
            <div className="confidence-bar" style={{ flex: 1 }}>
              <div className="confidence-track" style={{ height: 8, borderRadius: 4 }}>
                <div className="confidence-fill" style={{
                  width: `${confidence}%`,
                  background: `linear-gradient(90deg, ${confColor}, ${confColor}aa)`,
                  borderRadius: 4,
                }} />
              </div>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{confidence}%</span>
            </div>
          </div>
        </div>
        <button className="detail-close" onClick={onClose} style={{ fontSize: 20 }}>×</button>
      </div>

      <div className="detail-body" style={{ padding: '0 20px 20px' }}>

        {/* XAI Headline */}
        {explanation && (
          <div style={{
            padding: '12px 14px', marginBottom: 16,
            background: `${STATUS_COLORS[status]}15`,
            border: `1px solid ${STATUS_COLORS[status]}40`,
            borderRadius: 8,
          }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: STATUS_COLORS[status], marginBottom: 6 }}>
              {explanation.headline}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {explanation.natural_explanation || explanation.summary}
            </div>
            {/* Faithful-XAI strip: which model decided, its real score, and that
                the proof cards below sum to it (true model weights, not estimates). */}
            {explanation.model && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
                marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)',
              }}>
                {explanation.is_faithful && (
                  <span title="Proof cards below use the exact weights the decision model scored with"
                    style={{
                      fontSize: 9, fontWeight: 800, letterSpacing: '0.4px',
                      padding: '2px 7px', borderRadius: 999,
                      background: 'rgba(34,197,94,0.15)', color: '#22c55e',
                      border: '1px solid rgba(34,197,94,0.35)', textTransform: 'uppercase',
                    }}>
                    Faithful XAI
                  </span>
                )}
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  {MODEL_LABELS[explanation.model] || explanation.model}
                </span>
                {typeof explanation.net_signal_score === 'number' && (
                  <span style={{
                    fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
                    color: 'var(--text-secondary)',
                  }}>
                    net&nbsp;score&nbsp;
                    <strong style={{ color: STATUS_COLORS[status] }}>
                      {explanation.net_signal_score >= 0 ? '+' : ''}{explanation.net_signal_score.toFixed(2)}
                    </strong>
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Visual Evidence */}
        {place.image_url && (
          <>
            <SectionTitle text="Street View Evidence" />
            {ageLabel && (
              recencyWeight < 0.5 ? (
                <div style={{
                  marginBottom: 8, padding: '8px 10px', borderRadius: 8,
                  background: 'rgba(249,115,22,0.12)', border: '1px solid rgba(249,115,22,0.35)',
                  fontSize: 11, color: '#f97316',
                }}>
                  Image captured {ageLabel} — confidence reduced to {Math.round(recencyWeight * 100)}%
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                  Captured {ageLabel}
                </div>
              )
            )}
            <img
              src={String(place.image_url)}
              alt="Street View Evidence"
              style={{ width: '100%', borderRadius: 8, border: '1px solid var(--border)', marginBottom: 8 }}
            />
            {imageExplanation && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>AI note:</strong> {String(imageExplanation)}
              </div>
            )}
            {allTextFound.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>Text on signs:</strong> {allTextFound.map(String).join(', ')}
              </div>
            )}
            {detectedBusinessName && String(detectedBusinessName).toLowerCase() !== 'null' && String(detectedBusinessName).toLowerCase() !== 'none' && (
              nameMatchScore > 0.6 ? (
                <div style={{
                  marginBottom: 8, padding: '8px 10px', borderRadius: 8,
                  background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.35)',
                  fontSize: 11, color: '#22c55e',
                }}>
                  Sign reads '{String(detectedBusinessName)}' — matches OSM name ({Math.round(nameMatchScore * 100)}%)
                </div>
              ) : nameMatchScore > 0.3 ? (
                <div style={{
                  marginBottom: 8, padding: '8px 10px', borderRadius: 8,
                  background: 'rgba(234,179,8,0.12)', border: '1px solid rgba(234,179,8,0.35)',
                  fontSize: 11, color: '#eab308',
                }}>
                  Sign reads '{String(detectedBusinessName)}' — partial match ({Math.round(nameMatchScore * 100)}%)
                </div>
              ) : (
                <div style={{
                  marginBottom: 8, padding: '8px 10px', borderRadius: 8,
                  background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)',
                  fontSize: 11, color: '#ef4444',
                }}>
                  Sign reads '{String(detectedBusinessName)}' — does NOT match OSM name '{name}' ({Math.round(nameMatchScore * 100)}%)
                </div>
              )
            )}
            {closureKeywords.length > 0 && (
              <div style={{
                marginBottom: 8, padding: '8px 10px', borderRadius: 8,
                background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)',
                fontSize: 11, color: '#ef4444',
              }}>
                Closure signals found: {closureKeywords.map(String).join(', ')}
              </div>
            )}
            {place.status && place.status !== 'UNCLEAR' && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>Vision verdict:</strong>{' '}
                {place.status}
              </div>
            )}
            {yoloObjects.length > 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>Objects detected:</strong>{' '}
                {Array.from(new Set(yoloObjects.slice(0, 8).map((d: any) => String(d?.object || d?.class || '')))).filter(Boolean).join(', ')}
              </div>
            )}
          </>
        )}

        {/* Location Info */}
        <SectionTitle text="Location" />
        <Row label="Address" value={place.address} />
        <Row label="Category" value={place.category || place.source_layer} />
        <Row label="Coordinates" value={
          place.latitude && place.longitude
            ? `${place.latitude?.toFixed(5)}, ${place.longitude?.toFixed(5)}`
            : undefined
        } />

        {/* Proof Cards */}
        {explanation && explanation.proof_cards.length > 0 && (
          <>
            <SectionTitle
              text={`Evidence Proof Cards (${explanation.proof_cards.length})`}
              action={<button
                onClick={() => setExpanded(!expanded)}
                style={{
                  background: 'none', border: 'none', color: 'var(--accent)',
                  cursor: 'pointer', fontSize: 11, fontWeight: 600,
                }}
              >
                {expanded ? 'Collapse' : 'Expand'}
              </button>}
            />
            {expanded && explanation.proof_cards.map((card, i) => (
              <ProofCardComponent key={i} card={card} />
            ))}
          </>
        )}

        {/* Baseline Comparison */}
        {explanation?.baseline_comparison && (
          <>
            <SectionTitle text="Baseline Comparison" />
            <div style={{
              padding: 12, background: 'var(--bg-primary)',
              borderRadius: 8, border: '1px solid var(--border)', marginBottom: 8,
            }}>
              <Row label="Nearest Baseline" value={explanation.baseline_comparison.nearest_name} />
              <Row label="Distance" value={
                explanation.baseline_comparison.distance_m != null
                  ? `${explanation.baseline_comparison.distance_m.toFixed(0)}m`
                  : 'N/A'
              } />
              <Row label="Match Score" value={`${(explanation.baseline_comparison.match_score * 100).toFixed(0)}%`} />
              <Row label="Match Type" value={explanation.baseline_comparison.match_type?.replace('_', ' ')} />
              <div style={{
                marginTop: 8, padding: '8px 10px',
                background: 'rgba(59, 130, 246, 0.08)',
                borderRadius: 6, fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5,
              }}>
                <strong style={{ color: 'var(--accent)' }}>Why not the same place?</strong><br />
                {explanation.baseline_comparison.why_not_same}
              </div>
            </div>
          </>
        )}

        {/* Uncertainty Reasons */}
        {explanation && explanation.uncertainty_reasons.length > 0 && (
          <>
            <SectionTitle text="What's Missing" />
            <div style={{
              padding: 10, background: 'rgba(249, 115, 22, 0.08)',
              borderRadius: 8, border: '1px solid rgba(249, 115, 22, 0.2)',
            }}>
              {explanation.uncertainty_reasons.map((reason, i) => (
                <div key={i} style={{
                  fontSize: 11, color: 'var(--text-secondary)', padding: '3px 0',
                  display: 'flex', gap: 6, alignItems: 'flex-start',
                }}>
                  <span style={{ color: 'var(--orange)', flexShrink: 0 }}>•</span>
                  {reason}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Recommendation */}
        {explanation && (
          <div style={{
            marginTop: 16, padding: '10px 14px',
            background: 'rgba(59, 130, 246, 0.08)',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            borderRadius: 8, fontSize: 12, color: 'var(--text-secondary)',
          }}>
            <span style={{ fontWeight: 700, color: 'var(--accent)' }}>Recommendation: </span>
            {explanation.recommendation}
          </div>
        )}

        {/* Source List */}
        {place.source_types && place.source_types.length > 0 && (
          <>
            <SectionTitle text="Sources Used" />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {place.source_types.map((s, i) => (
                <span key={i} className="badge" style={{
                  background: 'var(--bg-primary)', color: 'var(--text-secondary)',
                  fontSize: 10, padding: '3px 8px',
                }}>
                  {s.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </>
        )}

        {/* Review Alert */}
        {place.review_reason && (
          <div style={{
            marginTop: 14, padding: 12,
            background: 'rgba(234,179,8,0.1)',
            borderRadius: 8, border: '1px solid rgba(234,179,8,0.2)',
          }}>
            <div style={{ fontSize: 11, color: 'var(--yellow)', fontWeight: 700, marginBottom: 4 }}>
              Review Needed
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
              {place.review_reason}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function SectionTitle({ text, action }: { text: string; action?: React.ReactNode }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      marginTop: 18, marginBottom: 8,
    }}>
      <h4 style={{
        fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)',
        textTransform: 'uppercase', letterSpacing: '0.5px',
      }}>
        {text}
      </h4>
      {action}
    </div>
  )
}

function ProofCardComponent({ card }: { card: ProofCard }) {
  const isPositive = card.signal_direction === 'positive'
  const isNegative = card.signal_direction === 'negative'
  const contribColor = isPositive ? '#22c55e' : isNegative ? '#ef4444' : '#64748b'
  const contribSign = card.confidence_contribution >= 0 ? '+' : ''
  const contribPct = (card.confidence_contribution * 100).toFixed(1)

  return (
    <div style={{
      padding: '12px 14px', marginBottom: 8,
      background: 'var(--bg-primary)',
      border: `1px solid ${isNegative ? 'rgba(239,68,68,0.3)' : 'var(--border)'}`,
      borderRadius: 8,
      borderLeft: `3px solid ${contribColor}`,
    }}>
      {/* Source header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 6,
      }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
          {card.source_name}
        </span>
        <span style={{
          fontSize: 13, fontWeight: 800, color: contribColor,
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {contribSign}{contribPct}%
        </span>
      </div>

      {/* Signed weight bar — visualises the REAL model contribution, centred at 0 */}
      <div style={{ position: 'relative', height: 6, background: 'var(--bg-secondary)', borderRadius: 3, marginBottom: 8 }}>
        <div style={{ position: 'absolute', left: '50%', top: -1, bottom: -1, width: 1, background: 'var(--border)' }} />
        <div style={{
          position: 'absolute', top: 0, bottom: 0,
          left: isNegative ? `${50 - Math.min(Math.abs(card.confidence_contribution) * 100, 50)}%` : '50%',
          width: `${Math.min(Math.abs(card.confidence_contribution) * 100, 50)}%`,
          background: contribColor, borderRadius: 3,
        }} />
      </div>

      {/* Finding */}
      <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 6, lineHeight: 1.4 }}>
        {card.finding}
      </div>

      {/* Reasoning */}
      <div style={{
        fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4,
        fontStyle: 'italic', marginBottom: 6,
      }}>
        "{card.reasoning}"
      </div>

      {/* Meta pills */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <MetaPill label="Freshness" value={card.freshness} />
        <MetaPill
          label="Reliability"
          value={card.reliability?.replace('_', ' ')}
          color={RELIABILITY_COLORS[card.reliability] || 'var(--text-muted)'}
        />
        <MetaPill
          label="Signal"
          value={card.signal_direction}
          color={SIGNAL_COLORS[card.signal_direction] || 'var(--text-muted)'}
        />
      </div>
    </div>
  )
}

function MetaPill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span style={{
      fontSize: 9, padding: '2px 6px', borderRadius: 4,
      background: 'rgba(100,116,139,0.15)',
      color: color || 'var(--text-muted)',
      fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.3px',
    }}>
      {label}: {value}
    </span>
  )
}

function Row({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="detail-row">
      <span className="dl">{label}</span>
      <span>{value}</span>
    </div>
  )
}
