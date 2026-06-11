// ============================================================================
// Map Component — OpenStreetMap via Leaflet (individual point markers & clusters)
// ============================================================================
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import type { Place } from '../App'

// ── Colors for classified place statuses ──
const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  new_place: '#ff4500',
  closed: '#ef4444',
  rebranded: '#a855f7',
  uncertain: '#eab308',
}

// ── Colors for baseline GeoJSON layers ──
const LAYER_COLORS: Record<string, string> = {
  cafes: '#9b59b6',
  restaurants: '#e74c7d',
  hotels: '#2ecc71',
  pharmacies: '#f1c40f',
  'grocery stores': '#8B4513',
  department_stores: '#e74c3c',
  shopping_malls: '#e91e90',
  fuel_station: '#e74c3c',
  theme_parks: '#e74c3c',
  'tourism attraction': '#8e44ad',
}

// ── Dot icon for baseline layer points ──
function dotIcon(color: string, size: number = 10) {
  return L.divIcon({
    className: 'placeiq-dot',
    html: `<div style="
      width:${size}px;height:${size}px;
      background:${color};
      border-radius:50%;
      border:2px solid rgba(255,255,255,0.9);
      box-shadow:0 0 4px rgba(0,0,0,0.4);
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

// ── Status icon for classified places ──
function statusIcon(color: string, isNew: boolean) {
  if (isNew) {
    return L.divIcon({
      className: 'placeiq-new',
      html: `<div style="
        width:22px;height:22px;
        display:flex;align-items:center;justify-content:center;
        font-size:18px;font-weight:900;
        color:white;
        background:${color};
        border-radius:4px;
        border:2px solid white;
        box-shadow:0 0 8px ${color}, 0 0 16px rgba(255,69,0,0.5);
        line-height:1;
        transition: transform 0.2s;
      ">+</div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    })
  }
  return L.divIcon({
    className: 'placeiq-status',
    html: `<div style="
      width:14px;height:14px;
      background:${color};
      border-radius:50%;
      border:2px solid rgba(255,255,255,0.9);
      box-shadow:0 0 6px ${color};
      transition: transform 0.2s;
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

type Props = {
  classifiedPlaces: Place[]
  layers: Record<string, any>
  enabledLayers: Set<string>
  onPlaceClick: (place: Place) => void
  center: [number, number]
}

export default function MapView({ classifiedPlaces, layers, enabledLayers, onPlaceClick, center }: Props) {
  const mapRef = useRef<L.Map | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const classifiedGroupRef = useRef<L.MarkerClusterGroup | null>(null)
  const layerGroupsRef = useRef<Map<string, L.MarkerClusterGroup>>(new Map())

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: [1.3521, 103.8198],
      zoom: 12,
      zoomControl: true,
    })

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map)

    // Cluster group for classified places
    const group = L.markerClusterGroup({
      maxClusterRadius: 40,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      zoomToBoundsOnClick: true,
      iconCreateFunction: (cluster) => {
        const count = cluster.getChildCount()
        return L.divIcon({
          html: `<div style="
            background: rgba(30,41,59,0.9);
            color: white; border: 2px solid white; font-weight: bold; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.5); font-size: 11px;">
            ${count}
          </div>`,
          className: 'custom-cluster-icon',
          iconSize: L.point(30, 30),
        })
      }
    }).addTo(map)

    mapRef.current = map
    classifiedGroupRef.current = group

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // ── Classified place markers ──
  useEffect(() => {
    if (!classifiedGroupRef.current) return
    const group = classifiedGroupRef.current
    group.clearLayers()

    // Create array to hold markers before batch adding
    const markers: L.Marker[] = []

    for (const place of classifiedPlaces) {
      const lat = place.latitude
      const lon = place.longitude
      if (!lat || !lon) continue

      const status = place.status || 'uncertain'
      const color = STATUS_COLORS[status] || '#64748b'
      const isNew = status === 'new_place'
      const name = place.detected_name || place.name || 'Unknown'
      const hasImg = place.image_url ? '📷 ' : ''
      const conf = Math.round((place.confidence || 0) * 100)

      const marker = L.marker([lat, lon], {
        icon: statusIcon(color, isNew),
        zIndexOffset: isNew ? 1000 : 0,
      })

      const tooltipHtml = `
        <div style="min-width:160px">
          <b style="font-size:13px">${hasImg}${name}</b><br/>
          <span style="
            display:inline-block;
            padding:1px 6px;margin:3px 0;
            border-radius:3px;
            font-size:10px;font-weight:600;
            color:white;background:${color};
          ">${status.replace('_', ' ').toUpperCase()}</span>
          <span style="font-size:11px;color:#999"> ${conf}% confidence</span>
          ${place.category ? `<br/><span style="font-size:11px;color:#aaa">📂 ${place.category}</span>` : ''}
          ${place.nearest_baseline_name ? `<br/><span style="font-size:11px;color:#aaa">📍 near ${place.nearest_baseline_name}</span>` : ''}
          ${place.source_count ? `<br/><span style="font-size:11px;color:#aaa">📡 ${place.source_count} sources</span>` : ''}
        </div>`

      marker.bindTooltip(tooltipHtml, {
        direction: 'top',
        offset: [0, -14],
        opacity: 0.95,
        className: 'placeiq-tooltip',
      })

      marker.on('click', () => {
        // Enlarge icon on click briefly
        onPlaceClick(place)
      })
      markers.push(marker)
    }

    group.addLayers(markers)
  }, [classifiedPlaces, onPlaceClick])

  // ── GeoJSON baseline layers — Clustered ──
  useEffect(() => {
    if (!mapRef.current) return
    const map = mapRef.current

    // Remove toggled-off layers
    layerGroupsRef.current.forEach((lg, name) => {
      if (!enabledLayers.has(name)) {
        map.removeLayer(lg)
        layerGroupsRef.current.delete(name)
      }
    })

    // Add newly toggled-on layers
    for (const name of enabledLayers) {
      if (layerGroupsRef.current.has(name)) continue
      const gj = layers[name]
      if (!gj) continue

      const color = LAYER_COLORS[name] || '#64748b'
      
      // Create cluster group for this layer
      const clusterGroup = L.markerClusterGroup({
        maxClusterRadius: 50,
        iconCreateFunction: (cluster) => {
          const count = cluster.getChildCount()
          let size = 26
          if (count > 100) size = 32
          if (count > 500) size = 40
          return L.divIcon({
            html: `<div style="
              background: ${color}cc; border: 2px solid white; color: white;
              display: flex; align-items: center; justify-content: center; width: ${size}px; height: ${size}px;
              border-radius: 50%; box-shadow: 0 0 5px rgba(0,0,0,0.5); font-size: ${size>30?12:10}px; font-weight: bold;">
              ${count}
            </div>`,
            className: 'custom-cluster-icon',
            iconSize: L.point(size, size),
          })
        }
      })

      const geoJsonLayer = L.geoJSON(gj, {
        pointToLayer: (_f, latlng) => {
          return L.marker(latlng, { icon: dotIcon(color, 12) })
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties || {}
          const featureName = p.name || p.Name || 'Unnamed'
          const addr = p.address || p['addr:street'] || ''
          const tooltipHtml = `
            <div style="min-width:140px">
              <b style="font-size:12px">${featureName}</b>
              <br/><span style="
                display:inline-block;
                padding:1px 6px;margin:2px 0;
                border-radius:3px;
                font-size:10px;font-weight:600;
                color:white;background:${color};
              ">${name}</span>
              ${addr ? `<br/><span style="font-size:11px;color:#aaa">${addr}</span>` : ''}
            </div>`
          layer.bindTooltip(tooltipHtml, {
            direction: 'top',
            offset: [0, -8],
            opacity: 0.95,
            className: 'placeiq-tooltip',
          })
        },
      })
      
      clusterGroup.addLayer(geoJsonLayer)
      clusterGroup.addTo(map)
      layerGroupsRef.current.set(name, clusterGroup)
    }
  }, [enabledLayers, layers])

  // Fly to selected place dynamically
  useEffect(() => {
    if (mapRef.current && center) {
      // Zoom closer if it's already close, otherwise standard 17
      const currentZoom = mapRef.current.getZoom()
      const targetZoom = currentZoom > 17 ? currentZoom : 18
      mapRef.current.flyTo(center, targetZoom, { duration: 1.5, easeLinearity: 0.25 })
    }
  }, [center])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
