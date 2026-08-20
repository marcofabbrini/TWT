import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  GeoJSON,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { motion, AnimatePresence } from "framer-motion";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { Map as MapIcon, ChevronDown, MapPin, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

// ── Palette ────────────────────────────────────────────
const MODE_COLOR = {
  car: "#5EEAD4",
  walk: "#F59E0B",
  train: "#8B5CF6",
  plane: "#EC4899",
  other: "#94A3B8",
};

const MODE_LABEL = {
  car: "Car",
  walk: "Walk",
  train: "Train",
  plane: "Plane",
  other: "Other",
};

function colorFor(mode) {
  return MODE_COLOR[mode] || MODE_COLOR.other;
}

// ── Helpers ────────────────────────────────────────────
function fmtKm(m) {
  if (m === null || m === undefined) return null;
  const km = m / 1000;
  return `${km >= 100 ? Math.round(km) : km.toFixed(1)} km`;
}

function fmtDuration(s) {
  if (s === null || s === undefined) return null;
  const total = Math.round(s / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/** Great-circle arc via quadratic bezier through a perpendicularly-offset midpoint.
 *  Returns [[lat, lng], ...] for Leaflet Polyline. */
function airplaneArc(a, b, samples = 48) {
  // a, b: [lng, lat]
  const [alng, alat] = a;
  const [blng, blat] = b;
  const mx = (alng + blng) / 2;
  const my = (alat + blat) / 2;
  // Perpendicular offset (rough — good enough for visual arc)
  const dx = blng - alng;
  const dy = blat - alat;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const px = -dy / dist;
  const py = dx / dist;
  const bow = dist * 0.18; // curvature strength
  const cx = mx + px * bow;
  const cy = my + py * bow;
  const pts = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const one = 1 - t;
    const lng = one * one * alng + 2 * one * t * cx + t * t * blng;
    const lat = one * one * alat + 2 * one * t * cy + t * t * blat;
    pts.push([lat, lng]);
  }
  return pts;
}

/** Build a Leaflet DivIcon representing a numbered pill marker (teal). */
function buildMarkerIcon(order) {
  const html = `
    <div class="twt-map-pin" role="button" aria-label="Stop ${order + 1}">
      <span class="twt-map-pin__num">${order + 1}</span>
    </div>`;
  return L.divIcon({
    className: "twt-map-pin-wrap",
    html,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -12],
  });
}

/** Auto-fit the map to given [lat,lng] points. */
function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!points || points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 10, { animate: true });
      return;
    }
    const bounds = L.latLngBounds(points);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
  }, [map, JSON.stringify(points)]);
  return null;
}

function scrollToStop(stopId) {
  const el = document.querySelector(`[data-testid="stop-card-${stopId}"]`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ── Component ─────────────────────────────────────────
export default function TripMap({ tripId, syncVersion }) {
  const storageKey = `tripmap-open-${tripId}`;
  const [open, setOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    const v = window.localStorage.getItem(storageKey);
    return v === null ? true : v === "1";
  });
  const [data, setData] = useState(null); // { stops, routes }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [routePopup, setRoutePopup] = useState(null); // { latlng, route }

  useEffect(() => {
    window.localStorage.setItem(storageKey, open ? "1" : "0");
  }, [open, storageKey]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get(`/trips/${tripId}/route-geometry`);
        if (!cancelled) setData(res.data);
      } catch (e) {
        if (!cancelled) setError(e?.response?.data?.detail || e?.message || "Failed to load map");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [tripId, syncVersion]);

  const stopsWithCoords = useMemo(
    () => (data?.stops || []).filter((s) => s.coords),
    [data]
  );
  const stopsById = useMemo(() => {
    const m = new Map();
    (data?.stops || []).forEach((s) => m.set(s.stop_id, s));
    return m;
  }, [data]);

  const points = useMemo(
    () => stopsWithCoords.map((s) => [s.coords[1], s.coords[0]]),
    [stopsWithCoords]
  );

  const modesInUse = useMemo(() => {
    const set = new Set();
    (data?.routes || []).forEach((r) => set.add(r.transport_mode));
    return Array.from(set);
  }, [data]);

  return (
    <div className="mb-8" data-testid="trip-map-wrapper">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="glass rounded-2xl overflow-hidden">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="w-full flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition"
              data-testid="trip-map-toggle"
            >
              <div className="w-9 h-9 rounded-xl bg-twt-teal/12 grid place-items-center text-twt-teal">
                <MapIcon className="w-4 h-4" />
              </div>
              <div className="flex-1 text-left">
                <div className="font-display font-bold text-twt-text text-sm leading-none">
                  Trip map
                </div>
                <div className="text-[11px] text-twt-muted mt-1 tabular-nums">
                  {stopsWithCoords.length} of {(data?.stops || []).length} stops
                  located
                  {modesInUse.length > 0 && (
                    <>
                      {" · "}
                      {modesInUse.map((m) => MODE_LABEL[m] || m).join(" · ")}
                    </>
                  )}
                </div>
              </div>
              <motion.div
                animate={{ rotate: open ? 180 : 0 }}
                transition={{ duration: 0.2 }}
                className="text-twt-muted"
              >
                <ChevronDown className="w-4 h-4" />
              </motion.div>
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent forceMount>
            <AnimatePresence initial={false}>
              {open && (
                <motion.div
                  key="body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                  style={{ overflow: "hidden" }}
                >
                  <div className="px-5 pb-5 pt-1">
                    {/* Legend */}
                    <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px] text-twt-muted">
                      {modesInUse.length === 0 ? (
                        <span className="text-twt-muted/70">
                          No routes yet.
                        </span>
                      ) : (
                        modesInUse.map((m) => (
                          <span
                            key={m}
                            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full glass"
                            data-testid={`map-legend-${m}`}
                          >
                            <span
                              className="w-2.5 h-2.5 rounded-full"
                              style={{ background: colorFor(m) }}
                            />
                            {MODE_LABEL[m] || m}
                          </span>
                        ))
                      )}
                    </div>

                    <div
                      className="relative rounded-xl overflow-hidden border border-white/10"
                      style={{ height: 380 }}
                    >
                      {loading && !data && (
                        <div
                          className="absolute inset-0 grid place-items-center bg-[#0f1116]"
                          data-testid="trip-map-loading"
                        >
                          <Loader2 className="w-5 h-5 animate-spin text-twt-teal" />
                        </div>
                      )}
                      {error && (
                        <div
                          className="absolute inset-0 grid place-items-center text-twt-muted text-sm"
                          data-testid="trip-map-error"
                        >
                          {error}
                        </div>
                      )}

                      {!error && (
                        <MapContainer
                          center={[41.9, 12.5]}
                          zoom={4}
                          scrollWheelZoom={true}
                          style={{ height: "100%", width: "100%" }}
                          data-testid="trip-map-container"
                        >
                          <TileLayer
                            attribution='&copy; <a href="https://osm.org/copyright">OpenStreetMap</a>'
                            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                          />
                          <FitBounds points={points} />

                          {stopsWithCoords.map((s) => (
                            <Marker
                              key={s.stop_id}
                              position={[s.coords[1], s.coords[0]]}
                              icon={buildMarkerIcon(s.order)}
                            >
                              <Popup>
                                <div
                                  className="twt-map-popup"
                                  data-testid={`trip-map-marker-popup-${s.stop_id}`}
                                >
                                  <div className="twt-map-popup__title">
                                    {s.order + 1}. {s.title}
                                  </div>
                                  {s.location && (
                                    <div className="twt-map-popup__meta">
                                      {s.location}
                                    </div>
                                  )}
                                  {s.start_date && s.end_date && (
                                    <div className="twt-map-popup__meta">
                                      {s.start_date} → {s.end_date}
                                    </div>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => scrollToStop(s.stop_id)}
                                    className="twt-map-popup__btn"
                                    data-testid={`trip-map-goto-${s.stop_id}`}
                                  >
                                    <MapPin size={12} />
                                    Go to stop
                                  </button>
                                </div>
                              </Popup>
                            </Marker>
                          ))}

                          {(data?.routes || []).map((r, i) => {
                            const from = stopsById.get(r.from_stop_id);
                            const to = stopsById.get(r.to_stop_id);
                            if (!from?.coords || !to?.coords) return null;
                            const color = colorFor(r.transport_mode);
                            const routeKey = `${r.from_stop_id}-${r.to_stop_id}-${r.transport_mode}`;

                            const onRouteClick = (e) => {
                              if (e?.originalEvent) {
                                e.originalEvent.stopPropagation?.();
                              }
                              setRoutePopup({
                                latlng: e.latlng,
                                route: r,
                                from,
                                to,
                              });
                            };

                            // Plane → local arc
                            if (r.transport_mode === "plane") {
                              const arc = airplaneArc(from.coords, to.coords);
                              return (
                                <Polyline
                                  key={routeKey}
                                  positions={arc}
                                  pathOptions={{
                                    color,
                                    weight: 3,
                                    opacity: 0.85,
                                    dashArray: "1, 6",
                                  }}
                                  eventHandlers={{ click: onRouteClick }}
                                />
                              );
                            }

                            // Real ORS polyline
                            if (r.geojson) {
                              return (
                                <GeoJSON
                                  key={routeKey}
                                  data={r.geojson}
                                  style={{
                                    color,
                                    weight: 4,
                                    opacity: 0.8,
                                  }}
                                  eventHandlers={{ click: onRouteClick }}
                                />
                              );
                            }

                            // Fallback: straight dashed line
                            return (
                              <Polyline
                                key={routeKey}
                                positions={[
                                  [from.coords[1], from.coords[0]],
                                  [to.coords[1], to.coords[0]],
                                ]}
                                pathOptions={{
                                  color,
                                  weight: 3,
                                  opacity: 0.7,
                                  dashArray: "6, 6",
                                }}
                                eventHandlers={{ click: onRouteClick }}
                              />
                            );
                          })}

                          {routePopup && (
                            <Popup
                              position={[
                                routePopup.latlng.lat,
                                routePopup.latlng.lng,
                              ]}
                              eventHandlers={{
                                remove: () => setRoutePopup(null),
                              }}
                            >
                              <div
                                className="twt-map-popup"
                                data-testid={`trip-map-route-popup-${routePopup.route.from_stop_id}-${routePopup.route.to_stop_id}`}
                              >
                                <div className="twt-map-popup__title">
                                  {routePopup.from.title} →{" "}
                                  {routePopup.to.title}
                                </div>
                                <div className="twt-map-popup__meta">
                                  {MODE_LABEL[
                                    routePopup.route.transport_mode
                                  ] || routePopup.route.transport_mode}
                                </div>
                                <div className="twt-map-popup__meta">
                                  {fmtKm(routePopup.route.distance_m) ||
                                    "Not calculated"}
                                  {fmtDuration(routePopup.route.duration_s) &&
                                    ` · ${fmtDuration(routePopup.route.duration_s)}`}
                                </div>
                              </div>
                            </Popup>
                          )}
                        </MapContainer>
                      )}

                      {!loading && stopsWithCoords.length === 0 && !error && (
                        <div
                          className="absolute inset-0 grid place-items-center text-twt-muted text-sm pointer-events-none"
                          data-testid="trip-map-empty"
                        >
                          No geocoded stops yet.
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  );
}
