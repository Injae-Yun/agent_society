"""HTML Time Machine renderer — hex-grid map + replay controls."""

from __future__ import annotations

import json
from pathlib import Path

from agent_society.world.hex_map import CLUSTER_HEXES, HIDEOUT_TERRITORY, ROLE_VISUAL_OFFSET

ROLE_COLORS: dict[str, str] = {
    "farmer":     "#4CAF50",
    "herder":     "#795548",
    "miner":      "#607D8B",
    "orchardist": "#8BC34A",
    "blacksmith": "#FF5722",
    "cook":       "#FFC107",
    "merchant":   "#2196F3",
    "raider":     "#F44336",
    "adventurer": "#9C27B0",
    "player":     "#FFD700",
}

ACTION_ICONS: dict[str, str] = {
    "produce":        "⛏",
    "craft":          "🔨",
    "trade":          "🤝",
    "travel":         "🚶",
    "transit":        "→",
    "collect":        "📦",
    "deliver":        "🏭",
    "equip":          "🗡",
    "consume":        "🍞",
    "raid":           "⚔",
    "idle":           "💤",
    "buy":            "💰",
    "sell":           "💸",
    "acquire_tool":   "🔧",
    "restock":        "🔄",
    "quest_accept":   "📜",
    "quest_work":     "⚒",
    "quest_complete": "🏆",
    "fight":          "⚔",
    "rest":           "🛌",
}


def render_html(data: dict, output_path: Path) -> None:
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = _build_html(json_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _build_html(json_str: str) -> str:
    role_colors_js = json.dumps(ROLE_COLORS)
    action_icons_js = json.dumps(ACTION_ICONS)
    cluster_hexes_js = json.dumps(CLUSTER_HEXES)
    hideout_territory_js = json.dumps(HIDEOUT_TERRITORY)
    # JS receives ROLE_VISUAL_OFFSET as { "node|role": [q, r] } keyed by string.
    role_offset_js = json.dumps({f"{node}|{role}": [q, r]
                                 for (node, role), (q, r) in ROLE_VISUAL_OFFSET.items()})

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Society — Time Machine</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0;
       height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

#controls {{ background: #16213e; padding: 8px 16px; display: flex; align-items: center;
             gap: 12px; border-bottom: 1px solid #0f3460; flex-shrink: 0; }}
#controls button {{ background: #0f3460; border: 1px solid #e94560; color: #e0e0e0;
                    padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
#controls button:hover {{ background: #e94560; }}
#tick-display {{ font-size: 13px; min-width: 180px; }}
#slider {{ flex: 1; accent-color: #e94560; }}
#speed-select {{ background: #0f3460; border: 1px solid #e94560; color: #e0e0e0;
                 padding: 3px 6px; border-radius: 4px; }}

#main {{ display: grid; grid-template-columns: 1fr 340px; grid-template-rows: 1fr 1fr 200px;
         flex: 1; overflow: hidden; gap: 4px; padding: 4px; }}

#map-panel {{ background: #0d1117; border-radius: 6px; position: relative;
              overflow: hidden; grid-row: span 3; }}
#map-svg {{ width: 100%; height: 100%; cursor: grab; }}
#map-svg:active {{ cursor: grabbing; }}
#zoom-controls {{ position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; z-index: 10; }}
#zoom-controls button {{ background: #0f3460cc; border: 1px solid #e94560; color: #e0e0e0;
  width: 28px; height: 28px; border-radius: 4px; cursor: pointer; font-size: 16px; line-height: 1; }}

#quest-panel {{ background: #16213e; border-radius: 6px; overflow-y: auto; padding: 8px; }}
#quest-panel h3 {{ font-size: 12px; color: #e94560; margin-bottom: 6px; }}

#action-log {{ background: #16213e; border-radius: 6px; overflow-y: auto; padding: 8px; }}
#action-log h3 {{ font-size: 12px; color: #e94560; margin-bottom: 6px; }}
.action-item {{ font-size: 11px; padding: 3px 6px; border-radius: 3px; margin-bottom: 2px;
                background: #0f3460; border-left: 3px solid #666; cursor: pointer; }}
.action-item.travel  {{ border-color: #2196F3; }}
.action-item.trade   {{ border-color: #4CAF50; }}
.action-item.raid    {{ border-color: #F44336; }}
.action-item.craft   {{ border-color: #FF5722; }}
.action-item.produce {{ border-color: #8BC34A; }}
.action-item.consume {{ border-color: #FFC107; }}
.action-item.quest_accept   {{ border-color: #9C27B0; }}
.action-item.quest_work     {{ border-color: #9C27B0; }}
.action-item.quest_complete {{ border-color: #9C27B0; }}

.quest-card {{ background: #0f3460; border-radius: 5px; padding: 7px 9px;
               margin-bottom: 6px; border-left: 3px solid #888; }}
.quest-card.pending   {{ border-color: #FFC107; }}
.quest-card.active    {{ border-color: #4CAF50; }}
.quest-card.completed {{ border-color: #2196F3; opacity: 0.7; }}
.quest-card.expired   {{ border-color: #555; opacity: 0.5; }}
.quest-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }}
.quest-type-badge {{ font-size: 10px; padding: 1px 5px; border-radius: 3px;
                     background: #1a1a2e; color: #e94560; }}
.quest-status {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: bold; }}
.quest-status.pending   {{ background: #3a2e00; color: #FFC107; }}
.quest-status.active    {{ background: #003a00; color: #4CAF50; }}
.quest-status.completed {{ background: #001a3a; color: #2196F3; }}
.quest-status.expired   {{ background: #1a1a1a; color: #555; }}
.quest-urgency-bar {{ display: flex; align-items: center; gap: 5px; font-size: 10px; margin: 3px 0; }}
.quest-text {{ font-size: 11px; color: #ccc; line-height: 1.5; margin: 4px 0;
               border-left: 2px solid #333; padding-left: 6px; }}
.quest-meta {{ font-size: 10px; color: #888; display: flex; gap: 10px; flex-wrap: wrap; }}

#detail-panel {{ background: #16213e; border-radius: 6px; padding: 10px; overflow-y: auto; }}
#detail-panel h3 {{ font-size: 12px; color: #e94560; margin-bottom: 8px; }}
.need-bar {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; font-size: 11px; }}
.need-bar .label {{ min-width: 100px; }}
.need-bar .bar-bg {{ flex: 1; height: 8px; background: #0f3460; border-radius: 4px; overflow: hidden; }}
.need-bar .bar-fill {{ height: 100%; border-radius: 4px; }}
.stock-row {{ font-size: 11px; display: flex; justify-content: space-between;
              padding: 2px 0; border-bottom: 1px solid #0f3460; }}
</style>
</head>
<body>

<div id="controls">
  <button onclick="stepBack()">◀◀</button>
  <button onclick="stepOne(-1)">◀</button>
  <button id="play-btn" onclick="togglePlay()">▶</button>
  <button onclick="stepOne(1)">▶</button>
  <button onclick="stepFwd()">▶▶</button>
  <span id="tick-display">Tick 0 / 0</span>
  <input id="slider" type="range" min="0" value="0" oninput="onSlider(this.value)">
  <select id="speed-select" onchange="setSpeed(this.value)">
    <option value="500">0.5x</option>
    <option value="250" selected>1x</option>
    <option value="100">2x</option>
    <option value="40">5x</option>
    <option value="16">10x</option>
  </select>
  <span style="font-size:11px;color:#888;">클릭: 노드·에이전트 상세</span>
</div>

<div id="main">
  <div id="map-panel">
    <svg id="map-svg"></svg>
    <div id="zoom-controls">
      <button onclick="zoomBy(1.25)" title="확대">+</button>
      <button onclick="zoomBy(0.8)" title="축소">−</button>
      <button onclick="zoomReset()" title="초기화">⌂</button>
    </div>
  </div>
  <div id="quest-panel"><h3>📋 퀘스트 현황</h3><div id="quest-items"></div></div>
  <div id="action-log"><h3>▶ 이번 Tick 행동</h3><div id="action-items"></div></div>
  <div id="detail-panel">
    <h3 id="detail-title">노드 또는 에이전트를 클릭하세요</h3>
    <div id="detail-body"></div>
  </div>
</div>

<script>
const DATA = {json_str};
const ROLE_COLORS = {role_colors_js};
const ACTION_ICONS = {action_icons_js};
const CLUSTER_HEXES = {cluster_hexes_js};
const HIDEOUT_TERRITORY = {hideout_territory_js};
const ROLE_OFFSET = {role_offset_js};   // "node|role" → [q, r]

// Role → site label shown on the visual slot hex
const SITE_LABEL = {{
  "city|blacksmith":  "Smithy",
  "city|cook":        "Kitchen",
  "city|merchant":    "Market",
  "city|adventurer":  "Guild",
  "city|player":      "Lodge",
  "farm|farmer":      "Grain",
  "farm|herder":      "Pasture",
  "farm|orchardist":  "Orchard",
  "farm|miner":       "Mine",
  "farm|merchant":    "Hub",
}};

const meta  = DATA.meta;
const ticks = DATA.ticks;
let currentTick = 0, playing = false, playTimer = null, playSpeed = 250;
let selectedId = null, selectedType = null;
let zoomScale = 1, zoomTX = 0, zoomTY = 0;
let isPanning = false, panStartX = 0, panStartY = 0, panTX0 = 0, panTY0 = 0;

const slider  = document.getElementById('slider');
const playBtn = document.getElementById('play-btn');
slider.max = ticks.length - 1;

// ── Hex geometry (pointy-top) ─────────────────────────────────────────────────
let HEX_SIZE   = 28;
let ORIGIN_X   = 0;
let ORIGIN_Y   = 0;

const SQRT3 = Math.sqrt(3);

function axialToPixel(q, r) {{
  return [
    ORIGIN_X + HEX_SIZE * SQRT3 * (q + r / 2),
    ORIGIN_Y + HEX_SIZE * 1.5  *  r,
  ];
}}

function hexCorners(cx, cy, size) {{
  const pts = [];
  for (let i = 0; i < 6; i++) {{
    const angle = Math.PI / 180 * (60 * i + 30);
    pts.push([cx + size * Math.cos(angle), cy + size * Math.sin(angle)]);
  }}
  return pts;
}}

function hexPath(cx, cy, size) {{
  return hexCorners(cx, cy, size).map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ') + ' Z';
}}

// ── SVG helpers ───────────────────────────────────────────────────────────────
const svg = document.getElementById('map-svg');
let svgW = 0, svgH = 0;

function makeSVG(tag, attrs) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}}

function svgGroup(id) {{
  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  if (id) g.id = id;
  return g;
}}

// ── Layout calibration ────────────────────────────────────────────────────────

function calibrate() {{
  const rect = svg.getBoundingClientRect();
  svgW = rect.width  || 900;
  svgH = rect.height || 600;

  const nodes = meta.nodes;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  function addPoint(q, r) {{
    const px = SQRT3 * (q + r / 2);
    const py = 1.5 * r;
    minX = Math.min(minX, px); maxX = Math.max(maxX, px);
    minY = Math.min(minY, py); maxY = Math.max(maxY, py);
  }}

  for (const nd of Object.values(nodes)) {{
    if (nd.hex_q == null) continue;
    addPoint(nd.hex_q, nd.hex_r);
  }}
  for (const hexList of Object.values(CLUSTER_HEXES)) {{
    for (const [q, r] of hexList) addPoint(q, r);
  }}
  for (const [q, r] of HIDEOUT_TERRITORY) addPoint(q, r);
  // M7 — include the dense tile grid so the camera fits the whole map.
  if (meta.tiles) {{
    for (const key of Object.keys(meta.tiles)) {{
      const [qs, rs] = key.split(',');
      addPoint(parseInt(qs), parseInt(rs));
    }}
  }}

  const PAD = 2.0;
  const rangeX = maxX - minX + PAD * 2;
  const rangeY = maxY - minY + PAD * 2;

  const scaleX = svgW / (rangeX * SQRT3);
  const scaleY = svgH / (rangeY * 1.5);
  HEX_SIZE = Math.min(scaleX, scaleY, 34);

  const totalW = (maxX - minX + PAD * 2) * SQRT3 * HEX_SIZE;
  const totalH = (maxY - minY + PAD * 2) * 1.5  * HEX_SIZE;
  ORIGIN_X = (svgW - totalW) / 2 - (minX - PAD) * SQRT3 * HEX_SIZE;
  ORIGIN_Y = (svgH - totalH) / 2 - (minY - PAD) * 1.5  * HEX_SIZE;
}}

// ── Node pixel position (cached) ──────────────────────────────────────────────

const _nodeXY = {{}};
function nodeXY(nid) {{
  if (_nodeXY[nid]) return _nodeXY[nid];
  const nd = meta.nodes[nid];
  if (!nd || nd.hex_q == null) return [svgW / 2, svgH / 2];
  const xy = axialToPixel(nd.hex_q, nd.hex_r);
  _nodeXY[nid] = xy;
  return xy;
}}

/** Visual position for an agent — inside city/farm it snaps to the role slot. */
function agentXY(nid, role) {{
  const key = nid + '|' + role;
  if (ROLE_OFFSET[key]) {{
    const [q, r] = ROLE_OFFSET[key];
    return axialToPixel(q, r);
  }}
  return nodeXY(nid);
}}

// ── Build static SVG ──────────────────────────────────────────────────────────

function applyZoom() {{
  const root = document.getElementById('zoom-root');
  if (root) root.setAttribute('transform', `translate(${{zoomTX}},${{zoomTY}}) scale(${{zoomScale}})`);
}}

function zoomBy(factor) {{
  zoomScale = Math.max(0.3, Math.min(5, zoomScale * factor));
  applyZoom();
}}

function zoomReset() {{
  zoomScale = 1; zoomTX = 0; zoomTY = 0; applyZoom();
}}

function initSVG() {{
  Object.keys(_nodeXY).forEach(k => delete _nodeXY[k]);
  svg.innerHTML = '';
  calibrate();

  const zRoot = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  zRoot.id = 'zoom-root';
  zRoot.setAttribute('transform', `translate(${{zoomTX}},${{zoomTY}}) scale(${{zoomScale}})`);
  svg.appendChild(zRoot);

  svg.addEventListener('wheel', (e) => {{
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.15 : 1/1.15;
    const newScale = Math.max(0.3, Math.min(5, zoomScale * factor));
    zoomTX = mx - (mx - zoomTX) * (newScale / zoomScale);
    zoomTY = my - (my - zoomTY) * (newScale / zoomScale);
    zoomScale = newScale;
    applyZoom();
  }}, {{ passive: false }});

  svg.addEventListener('mousedown', (e) => {{
    if (e.target === svg || e.target === zRoot) {{
      isPanning = true; panStartX = e.clientX; panStartY = e.clientY;
      panTX0 = zoomTX; panTY0 = zoomTY;
    }}
  }});
  svg.addEventListener('mousemove', (e) => {{
    if (!isPanning) return;
    zoomTX = panTX0 + (e.clientX - panStartX);
    zoomTY = panTY0 + (e.clientY - panStartY);
    applyZoom();
  }});
  svg.addEventListener('mouseup', () => {{ isPanning = false; }});
  svg.addEventListener('mouseleave', () => {{ isPanning = false; }});

  const CLUSTER_SIZE  = HEX_SIZE * 0.97;
  const SLOT_SIZE     = HEX_SIZE * 0.82;   // role visual slot hex
  const ROUTE_SIZE    = HEX_SIZE * 0.88;
  const HIDEOUT_SIZE  = HEX_SIZE * 0.92;
  const BIG_HEX_SIZE  = HEX_SIZE * 2.0;    // city/farm centre — encompasses 7 hex cluster

  // ── Layer 0: terrain tiles (M7 hex grid) ─────────────────────────────────
  const BIOME_COLOR = {{
    plains:    '#2a3d1e',
    hills:     '#3d3a1e',
    forest:    '#1a3320',
    mountain:  '#454550',
    coast:     '#1a2f4a',
    wasteland: '#3d1a1a',
    urban:     '#1d2a44',
  }};
  const ROAD_STROKE = {{ 1: '#8a6d3f', 2: '#c0a060', 3: '#7a7a9a' }};
  const tileGroup = svgGroup('g-tiles');
  if (meta.tiles) {{
    for (const [key, tile] of Object.entries(meta.tiles)) {{
      const [qs, rs] = key.split(',');
      const q = parseInt(qs), r = parseInt(rs);
      const [cx, cy] = axialToPixel(q, r);
      const fill = BIOME_COLOR[tile.b] || '#252525';
      tileGroup.appendChild(makeSVG('path', {{
        d: hexPath(cx, cy, CLUSTER_SIZE),
        fill, stroke: '#111', 'stroke-width': 0.5,
        'data-key': key,
      }}));
      if (tile.rd && tile.rd > 0) {{
        // Small road disc in the centre — colour by road tier.
        tileGroup.appendChild(makeSVG('circle', {{
          cx, cy, r: HEX_SIZE * (tile.rd === 2 ? 0.28 : 0.20),
          fill: ROAD_STROKE[tile.rd] || '#8a6d3f',
          opacity: 0.55,
        }}));
      }}
    }}
  }} else {{
    // Legacy fallback: no tile grid → use old cluster/hideout backgrounds.
    for (const [q, r] of HIDEOUT_TERRITORY) {{
      const [cx, cy] = axialToPixel(q, r);
      tileGroup.appendChild(makeSVG('path', {{
        d: hexPath(cx, cy, CLUSTER_SIZE + 1),
        fill: '#200000', stroke: '#5a0000', 'stroke-width': 1,
      }}));
    }}
    for (const [clId, hexList] of Object.entries(CLUSTER_HEXES)) {{
      const fill   = clId === 'city' ? '#0d2240' : '#0d2d0d';
      const stroke = clId === 'city' ? '#1a3a6a' : '#1a4a1a';
      for (const [q, r] of hexList) {{
        const [cx, cy] = axialToPixel(q, r);
        tileGroup.appendChild(makeSVG('path', {{
          d: hexPath(cx, cy, CLUSTER_SIZE + 1),
          fill, stroke, 'stroke-width': 1,
        }}));
      }}
    }}
  }}
  zRoot.appendChild(tileGroup);

  // ── Layer 1b: role-slot labels ("Smithy", "Grain", ...) ──────────────────
  const slotLabels = svgGroup('g-slot-labels');
  for (const [key, label] of Object.entries(SITE_LABEL)) {{
    const [q, r] = ROLE_OFFSET[key];
    const [cx, cy] = axialToPixel(q, r);
    const lbl = makeSVG('text', {{
      x: cx, y: cy - SLOT_SIZE * 0.1,
      'text-anchor': 'middle', 'font-size': Math.max(7, HEX_SIZE * 0.28),
      fill: '#6a7a8a', 'pointer-events': 'none',
    }});
    lbl.textContent = label;
    slotLabels.appendChild(lbl);
  }}
  zRoot.appendChild(slotLabels);

  // ── Layer 2: edges ────────────────────────────────────────────────────────
  const edgeGroup = svgGroup('g-edges');
  for (const edge of meta.edges) {{
    const [x1, y1] = nodeXY(edge.u);
    const [x2, y2] = nodeXY(edge.v);
    const threat = edge.base_threat || 0;
    let stroke, sw, dash;
    if (threat > 0.5) {{
      stroke = '#c0392b'; sw = 2; dash = '6,3';
    }} else if (threat > 0.2) {{
      stroke = '#e67e22'; sw = 1.5; dash = '4,3';
    }} else if (threat > 0) {{
      stroke = '#2e7d32'; sw = 1.5; dash = '';
    }} else {{
      stroke = '#1e3a5a'; sw = 1.2; dash = '';
    }}
    const line = makeSVG('line', {{
      x1, y1, x2, y2,
      stroke, 'stroke-width': sw,
      'stroke-opacity': 0.75,
    }});
    if (dash) line.setAttribute('stroke-dasharray', dash);
    edgeGroup.appendChild(line);
  }}
  zRoot.appendChild(edgeGroup);

  // ── Layer 3: hex tiles (nodes) ────────────────────────────────────────────
  const nodeGroup = svgGroup('g-nodes');
  for (const [nid, nd] of Object.entries(meta.nodes)) {{
    if (nd.hex_q == null) continue;
    const [cx, cy] = nodeXY(nid);

    let fill, stroke, size, strokeW = 1.5;
    if (nid === 'city') {{
      // Large hex enclosing the whole city zone, translucent fill
      fill = 'rgba(33, 150, 243, 0.08)';
      stroke = '#2196F3';
      size = BIG_HEX_SIZE;
      strokeW = 3;
    }} else if (nid === 'farm') {{
      fill = 'rgba(76, 175, 80, 0.08)';
      stroke = '#4CAF50';
      size = BIG_HEX_SIZE;
      strokeW = 3;
    }} else if (nid === 'raider.hideout') {{
      fill = '#3a0000'; stroke = '#e74c3c'; size = HIDEOUT_SIZE;
    }} else if (nid.startsWith('route.risky')) {{
      const threat = _edgeThreat(nid);
      const t = Math.min(1, threat / 0.7);
      fill = lerpColor('#1a1a2e', '#4a0a0a', t);
      stroke = lerpColor('#445', '#c0392b', t);
      size = ROUTE_SIZE;
    }} else if (nid.startsWith('route.safe')) {{
      const threat = _edgeThreat(nid);
      const t = Math.min(1, threat / 0.15);
      fill = lerpColor('#0d1a0d', '#1a2a1a', t);
      stroke = lerpColor('#2e7d32', '#558b2f', t);
      size = ROUTE_SIZE;
    }} else {{
      fill = '#1a1a2e'; stroke = '#555'; size = ROUTE_SIZE;
    }}

    const hex = makeSVG('path', {{
      d: hexPath(cx, cy, size),
      fill, stroke, 'stroke-width': strokeW,
      class: 'node-hex', 'data-id': nid,
      cursor: 'pointer',
    }});
    hex.addEventListener('click', () => selectNode(nid));
    nodeGroup.appendChild(hex);

    // Centre label — bigger font for city/farm
    const short = _shortName(nid, nd.name);
    const fontSize = (nid === 'city' || nid === 'farm')
      ? Math.max(12, HEX_SIZE * 0.55) : Math.max(7, HEX_SIZE * 0.28);
    const yOffset = (nid === 'city' || nid === 'farm') ? -size * 0.7 : size * 0.38;
    const lbl = makeSVG('text', {{
      x: cx, y: cy + yOffset,
      'text-anchor': 'middle', 'font-size': fontSize,
      fill: (nid === 'city' || nid === 'farm') ? '#e0e8f0' : '#8899aa',
      'font-weight': (nid === 'city' || nid === 'farm') ? 'bold' : 'normal',
      'pointer-events': 'none',
    }});
    lbl.textContent = short;
    nodeGroup.appendChild(lbl);
  }}
  zRoot.appendChild(nodeGroup);

  // ── Layer 4: stockpile bubbles (updated each tick) ────────────────────────
  zRoot.appendChild(svgGroup('g-stock'));

  // ── Layer 5: agent dots ───────────────────────────────────────────────────
  const agentGroup = svgGroup('g-agents');
  for (const [aid, ag] of Object.entries(meta.agents)) {{
    const dot = makeSVG('circle', {{
      r: Math.max(4, HEX_SIZE * 0.18),
      class: 'agent-dot',
      fill: ROLE_COLORS[ag.role] || '#aaa',
      stroke: '#fff', 'stroke-width': 1.2,
      'data-id': aid, 'data-role': ag.role, opacity: 0.9, cursor: 'pointer',
    }});
    dot.addEventListener('click', (e) => {{ e.stopPropagation(); selectAgent(aid); }});
    agentGroup.appendChild(dot);
  }}
  zRoot.appendChild(agentGroup);

  // ── Layer 6: event badges ────────────────────────────────────────────────
  zRoot.appendChild(svgGroup('g-events'));
}}

const _threatCache = {{}};
function _edgeThreat(nid) {{
  if (_threatCache[nid] !== undefined) return _threatCache[nid];
  let max = 0;
  for (const e of meta.edges) {{
    if ((e.u === nid || e.v === nid) && e.base_threat > max) max = e.base_threat;
  }}
  _threatCache[nid] = max;
  return max;
}}

function lerpColor(c1, c2, t) {{
  const h = s => parseInt(s, 16);
  const r1 = h(c1.slice(1,3)), g1 = h(c1.slice(3,5)), b1 = h(c1.slice(5,7));
  const r2 = h(c2.slice(1,3)), g2 = h(c2.slice(3,5)), b2 = h(c2.slice(5,7));
  const r = Math.round(r1 + (r2-r1)*t).toString(16).padStart(2,'0');
  const g = Math.round(g1 + (g2-g1)*t).toString(16).padStart(2,'0');
  const b = Math.round(b1 + (b2-b1)*t).toString(16).padStart(2,'0');
  return '#' + r + g + b;
}}

function _shortName(nid, name) {{
  if (nid === 'city') return 'CITY';
  if (nid === 'farm') return 'FARM';
  if (nid === 'raider.hideout') return '☠ Hideout';
  if (nid.startsWith('route.safe.'))  return 'S' + nid.split('.')[2];
  if (nid.startsWith('route.risky.')) return 'R' + nid.split('.')[2];
  return name.slice(0, 6);
}}

// ── Tick render ───────────────────────────────────────────────────────────────

function renderTick(idx) {{
  currentTick = Math.max(0, Math.min(idx, ticks.length - 1));
  slider.value = currentTick;
  const rec = ticks[currentTick];
  document.getElementById('tick-display').textContent =
    `Tick ${{rec.t}} (${{rec.s}}) — ${{currentTick + 1}}/${{ticks.length}}`;

  updateStockBubbles(rec);
  updateAgentPositions(rec);
  updateActionLog(rec);
  updateQuestBoard(rec);
  if (selectedId) {{
    selectedType === 'node' ? renderNodeDetail(selectedId, rec) : renderAgentDetail(selectedId, rec);
  }}
}}

function updateStockBubbles(rec) {{
  const g = document.getElementById('g-stock');
  if (!g) return;
  g.innerHTML = '';
  const hubs = ['city', 'farm'];
  for (const nid of hubs) {{
    const [cx, cy] = nodeXY(nid);
    const gold = rec.ns[nid]?._gold || 0;
    if (gold > 0) {{
      const t = makeSVG('text', {{
        x: cx, y: cy - HEX_SIZE * 0.35,
        'text-anchor': 'middle', 'font-size': Math.max(10, HEX_SIZE * 0.35),
        fill: '#FFD700', 'pointer-events': 'none', 'font-weight': 'bold',
      }});
      t.textContent = gold + 'g';
      g.appendChild(t);
    }}
  }}
}}

function updateAgentPositions(rec) {{
  // Group agents by their actual hex tile so each hex's dots stack together.
  // Priority: state.hx (M7 hex coord) → ROLE_OFFSET (legacy city/farm slot)
  //           → node centre.
  function _slotKey(state, role) {{
    if (state.hx) return 'hx:' + state.hx[0] + ',' + state.hx[1];
    if (ROLE_OFFSET[state.n + '|' + role]) return state.n + '|' + role;
    return state.n;
  }}
  function _slotXY(state, role) {{
    if (state.hx) return axialToPixel(state.hx[0], state.hx[1]);
    return agentXY(state.n, role);
  }}

  const byKey = {{}};
  for (const [aid, as_] of Object.entries(rec.as)) {{
    const role = meta.agents[aid]?.role || '';
    const slotKey = _slotKey(as_, role);
    (byKey[slotKey] = byKey[slotKey] || []).push(aid);
  }}

  const R = Math.max(4, HEX_SIZE * 0.18);

  for (const dot of svg.querySelectorAll('.agent-dot')) {{
    const aid = dot.getAttribute('data-id');
    const role = dot.getAttribute('data-role');
    const state = rec.as[aid];
    if (!state) continue;

    const slotKey = _slotKey(state, role);
    const group = byKey[slotKey] || [aid];
    const idx = group.indexOf(aid);
    const [cx, cy] = _slotXY(state, role);
    const count = group.length;

    let dx = 0, dy = 0;
    if (count > 1) {{
      const spacing = Math.min(R * 2.2, HEX_SIZE * 0.55);
      if (count <= 6) {{
        const angle = (idx / count) * Math.PI * 2 - Math.PI / 2;
        const radius = spacing * (count <= 3 ? 0.9 : 1.2);
        dx = Math.cos(angle) * radius;
        dy = Math.sin(angle) * radius;
      }} else {{
        const cols = Math.ceil(Math.sqrt(count));
        const row = Math.floor(idx / cols), col = idx % cols;
        dx = (col - (cols - 1) / 2) * spacing * 0.8;
        dy = (row - (Math.ceil(count / cols) - 1) / 2) * spacing * 0.8;
      }}
    }}

    dot.setAttribute('cx', cx + dx);
    dot.setAttribute('cy', cy + dy);
    dot.setAttribute('r', R);

    const inTransit = (state.tr || 0) > 0;
    dot.setAttribute('opacity', inTransit ? 0.45 : 0.9);
    dot.setAttribute('stroke-dasharray', inTransit ? '2,2' : 'none');
    dot.setAttribute('stroke-width', aid === selectedId ? 3 : 1.2);
    dot.style.filter = aid === selectedId ? 'drop-shadow(0 0 5px white)' : '';
  }}
}}

// ── Action log ────────────────────────────────────────────────────────────────

function updateActionLog(rec) {{
  const container = document.getElementById('action-items');
  container.innerHTML = '';
  const important = rec.ac.filter(a => a.t !== 'idle' && a.t !== 'transit').slice(0, 60);
  if (!important.length) {{
    container.innerHTML = '<div style="font-size:11px;color:#666;">행동 없음</div>';
    return;
  }}
  for (const a of important) {{
    const div = document.createElement('div');
    div.className = 'action-item ' + a.t;
    div.innerHTML = `<b style="color:${{ROLE_COLORS[a.r]||'#aaa'}}">${{a.nm}}</b> ${{ACTION_ICONS[a.t]||'?'}} ${{formatAction(a)}}`;
    div.addEventListener('click', () => selectAgent(a.id));
    container.appendChild(div);
  }}
  if (rec.ac.length > 60) {{
    const more = document.createElement('div');
    more.style.cssText = 'font-size:10px;color:#666;margin-top:4px;';
    more.textContent = `… 외 ${{rec.ac.length - 60}}개`;
    container.appendChild(more);
  }}
}}

function formatAction(a) {{
  switch (a.t) {{
    case 'produce': return `생산 ${{a.d.good||''}} +${{a.d.amount||1}}`;
    case 'craft':   return `제작 ${{a.d.output_good||''}}`;
    case 'trade':   return `교환 ${{a.d.item_out||''}}→${{a.d.item_in||''}}`;
    case 'travel':  return `이동 → ${{a.d.target_node||a.nd}}`;
    case 'consume': return `식사 ${{a.d.food_good||''}}`;
    case 'collect': return `수집 ${{a.d.good||''}} ×${{a.d.qty||''}} from ${{a.d.node_id||a.nd}}`;
    case 'deliver': return `납품 ${{a.d.good||''}} ×${{a.d.qty||''}} → ${{a.d.deposit_node||''}}`;
    case 'equip':   return `무기구입 ${{a.d.weapon_type||'sword'}}`;
    case 'buy':  {{ const c = a.d.unit_price ? ' (-'+Math.round((a.d.qty||1)*a.d.unit_price)+'g)':''; return `구매 ${{a.d.good||''}} ×${{a.d.qty||''}}${{c}}`; }}
    case 'sell': {{ const r2 = a.d.unit_price ? ' (+'+Math.round((a.d.qty||1)*a.d.unit_price)+'g)':''; return `판매 ${{a.d.good||''}} ×${{a.d.qty||''}}${{r2}}`; }}
    case 'acquire_tool': return `도구 ${{a.d.tool_type||''}}`;
    case 'restock':      return `보충 ${{a.d.good||''}} ×${{a.d.qty||''}}`;
    case 'quest_accept': {{
      const qi = (a.rd && a.rd._quest) ? a.rd._quest : {{}};
      return `퀘스트수락 ${{qi.type||''}} → ${{qi.target||''}}`;
    }}
    case 'quest_work': {{
      const qi = (a.rd && a.rd._quest) ? a.rd._quest : {{}};
      return `퀘스트진행 ${{Math.round((qi.progress||0)*100)}}%`;
    }}
    case 'quest_complete': {{
      const qi = (a.rd && a.rd._quest) ? a.rd._quest : {{}};
      const story = (qi.effect && qi.effect.story) ? ` · ${{qi.effect.story}}` : '';
      return `퀘스트완료 ${{qi.type||''}} (+${{qi.reward||0}}g)${{story}}`;
    }}
    case 'fight': {{
      const fi = (a.rd && a.rd._fight) ? a.rd._fight : {{}};
      const r = fi.result || '';
      if (r === 'critical_success') return `⚔대성공 ${{fi.target||''}} (${{fi.damage||0}}피해)`;
      if (r === 'success')          return `⚔성공 ${{fi.target||''}} (${{fi.damage||0}}피해)`;
      if (r === 'partial')          return `⚔진행 ${{fi.target||''}} (${{fi.damage||0}}피해)`;
      if (r === 'failure')          return `⚔실패 ${{fi.target||''}} (-${{fi.gold_lost||0}}g)`;
      if (r === 'critical_failure') return `☠대실패 ${{fi.target||''}} (-${{fi.gold_lost||0}}g)`;
      if (r === 'no_target')        return `전투 대상 없음`;
      // Legacy pre-dice labels
      if (r === 'victory') return `전투승 ${{fi.target||''}} (${{fi.damage||0}}피해)`;
      if (r === 'defeat')  return `전투패 ${{fi.target||''}} (-${{fi.gold_lost||0}}g)`;
      return `전투 ${{r}}`;
    }}
    case 'rest': return `휴식`;
    case 'raid': {{
      const ri = (a.rd && a.rd._raid) ? a.rd._raid : {{}};
      const kr = ri.result === 'repelled' ? '격퇴' : ri.result === 'partial_loss' ? '부분약탈' : ri.result === 'plundered' ? '완전약탈' : '?';
      const loot = ri.loot ? Object.entries(ri.loot).map(([g,v])=>g+'×'+v).join(',') : '없음';
      return `습격[${{kr}}] ⚔${{ri.attack?.toFixed(1)||'?'}} vs 🛡${{ri.defense??'?'}} ${{loot}}`;
    }}
    default: return a.t;
  }}
}}

// ── Node / Agent selection ────────────────────────────────────────────────────

function selectNode(nid) {{
  selectedId = nid; selectedType = 'node';
  svg.querySelectorAll('.node-hex').forEach(h =>
    h.style.filter = h.getAttribute('data-id') === nid ? 'drop-shadow(0 0 6px #fff)' : '');
  renderNodeDetail(nid, ticks[currentTick]);
}}

function selectAgent(aid) {{
  selectedId = aid; selectedType = 'agent';
  renderAgentDetail(aid, ticks[currentTick]);
  updateAgentPositions(ticks[currentTick]);
}}

function renderNodeDetail(nid, rec) {{
  const node  = meta.nodes[nid];
  const stock = rec.ns[nid] || {{}};
  const agents = Object.entries(rec.as).filter(([,s]) => s.n === nid);
  document.getElementById('detail-title').textContent = `📍 ${{node?.name || nid}}`;

  let html = '<div style="font-size:11px;color:#aaa;margin-bottom:6px;">재고</div>';
  const goods = Object.entries(stock).filter(([k,v]) => !k.startsWith('_') && v > 0).sort(([,a],[,b]) => b-a);
  if (!goods.length) html += '<div style="font-size:11px;color:#555;">재고 없음</div>';
  for (const [g, qty] of goods) {{
    const pct = Math.min(100, qty / 50 * 100);
    html += `<div class="stock-row"><span>${{g}}</span>
      <span style="display:flex;align-items:center;gap:4px;">
        <div style="width:60px;height:6px;background:#0f3460;border-radius:3px;overflow:hidden;">
          <div style="width:${{pct}}%;height:100%;background:#4CAF50;"></div></div>
        ${{qty}}</span></div>`;
  }}
  html += `<div style="font-size:11px;color:#aaa;margin:8px 0 4px;">체류 에이전트 (${{agents.length}})</div>`;
  for (const [aid, as_] of agents) {{
    const ag = meta.agents[aid];
    const wpBadge = as_.wp ? ` 🛡${{as_.wp}}` : '';
    html += `<div style="font-size:11px;padding:2px 0;cursor:pointer;color:${{ROLE_COLORS[ag.role]||'#aaa'}}"
      onclick="selectAgent('${{aid}}')">● ${{ag.name}} (${{ag.role}})${{wpBadge}}</div>`;
  }}
  document.getElementById('detail-body').innerHTML = html;
}}

function renderAgentDetail(aid, rec) {{
  const agent = meta.agents[aid];
  const state = rec.as[aid];
  if (!agent || !state) return;
  document.getElementById('detail-title').textContent = `👤 ${{agent.name}}`;
  const nodeNm = meta.nodes[state.n]?.name || state.n;
  const goldBadge = (state.gold || 0) > 0
    ? `<span style="color:#FFD700;font-weight:bold;margin-left:8px;">💰 ${{state.gold}}g</span>` : '';
  const facBadge = state.fac
    ? `<span style="background:#2a3a5a;color:#8fb3ff;padding:1px 6px;border-radius:3px;margin-left:8px;font-size:10px;">⚑ ${{state.fac}}</span>` : '';
  let html = `<div style="font-size:11px;color:#aaa;margin-bottom:6px;">${{agent.role}} · ${{nodeNm}}${{goldBadge}}${{facBadge}}</div>`;

  // M6 — reputation block
  const repMap = state.rep || state.krep;
  if (repMap && Object.keys(repMap).length) {{
    const title = state.rep ? '세력 명성 (canon)' : '세력 명성 (소문)';
    html += `<div style="font-size:11px;color:#aaa;margin:4px 0 2px;">${{title}}</div>`;
    for (const [fid, val] of Object.entries(repMap)) {{
      const v = Math.round(val);
      const tier = v >= 60 ? 'hero' : v >= 30 ? 'friend' : v <= -60 ? 'enemy' : v <= -30 ? 'wary' : 'neutral';
      const col = tier === 'hero' ? '#FFD700' : tier === 'friend' ? '#4CAF50'
                : tier === 'enemy' ? '#F44336' : tier === 'wary' ? '#FF9800' : '#888';
      const pct = Math.min(100, Math.abs(v));
      html += `<div class="need-bar">
        <span class="label" style="color:${{col}};">⚑ ${{fid}}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%;background:${{col}};"></div></div>
        <span style="font-size:10px;min-width:36px;color:${{col}};">${{v >= 0 ? '+' : ''}}${{v}}</span></div>`;
    }}
  }}

  const needColors = {{hunger:'#F44336',food_satisfaction:'#FF9800',tool_need:'#9C27B0',safety:'#2196F3'}};
  const needNames  = {{hunger:'허기',food_satisfaction:'식욕만족',tool_need:'도구부족',safety:'안전'}};
  for (const [nt, val] of Object.entries(state.needs || {{}})) {{
    const pct = Math.min(100, val * 100);
    const col = needColors[nt] || '#888';
    html += `<div class="need-bar"><span class="label">${{needNames[nt]||nt}}</span>
      <div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%;background:${{col}};"></div></div>
      <span style="font-size:10px;min-width:30px;">${{(val*100).toFixed(0)}}%</span></div>`;
  }}

  if (Object.keys(state.td || {{}}).length) {{
    html += '<div style="font-size:11px;color:#aaa;margin:6px 0 4px;">도구 내구도</div>';
    for (const [tool, dur] of Object.entries(state.td || {{}})) {{
      const pct = Math.min(100, dur / 10 * 100);
      html += `<div class="need-bar"><span class="label">${{tool}}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%;background:#FFC107;"></div></div>
        <span style="font-size:10px;min-width:30px;">${{dur.toFixed(2)}}</span></div>`;
    }}
  }}

  if (state.str != null) {{
    const armory = state.items?.sword || 0;
    const effAtk = state.str + armory * 1.5;
    const strPct = Math.min(100, effAtk);
    const strCol = effAtk > 70 ? '#F44336' : effAtk > 40 ? '#FF9800' : '#4CAF50';
    html += `<div style="font-size:11px;color:#aaa;margin:4px 0 2px;">전투력</div>
      <div class="need-bar">
        <span class="label" style="color:${{strCol}};font-weight:bold;">⚔ ${{effAtk.toFixed(1)}}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${{strPct}}%;background:${{strCol}};"></div></div>
      </div>`;
  }} else if (state.wpn && state.wp > 0) {{
    const wpPct = Math.min(100, state.wp / 30 * 100);
    html += `<div style="font-size:11px;color:#aaa;margin:4px 0 2px;">방어력</div>
      <div class="need-bar">
        <span class="label" style="color:#2196F3;font-weight:bold;">🛡 ${{state.wp}}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${{wpPct}}%;background:#2196F3;"></div></div>
      </div>`;
  }}

  if ((state.tr || 0) > 0) {{
    html += `<div style="font-size:11px;background:#1a3a0a;color:#8BC34A;padding:3px 6px;
      border-radius:3px;margin-bottom:6px;">🚶 이동 중 (${{state.tr}}tick 남음)</div>`;
  }}

  const itemEntries = Object.entries(state.items || {{}}).filter(([,v]) => v > 0).sort(([,a],[,b]) => b-a);
  if (itemEntries.length) {{
    html += `<div style="font-size:11px;color:#aaa;margin:6px 0 4px;">소지품 (합계: ${{state.inv}})</div>`;
    for (const [g, qty] of itemEntries) {{
      const pct = Math.min(100, qty / 10 * 100);
      html += `<div class="stock-row"><span>${{g}}</span>
        <span style="display:flex;align-items:center;gap:4px;">
          <div style="width:50px;height:5px;background:#0f3460;border-radius:2px;overflow:hidden;">
            <div style="width:${{pct}}%;height:100%;background:#2196F3;"></div></div>
          ${{qty}}</span></div>`;
    }}
  }}

  html += '<div style="font-size:11px;color:#aaa;margin:6px 0 4px;">이번 tick 행동</div>';
  const myActs = (rec.ac || []).filter(a => a.id === aid);
  if (!myActs.length) html += '<div style="font-size:11px;color:#555;">idle</div>';
  for (const a of myActs) {{
    html += `<div style="font-size:11px;padding:2px 4px;background:#0f3460;border-radius:3px;margin-bottom:2px;">
      ${{ACTION_ICONS[a.t]||'?'}} ${{formatAction(a)}}</div>`;
  }}

  document.getElementById('detail-body').innerHTML = html;
}}

// ── Quest board ───────────────────────────────────────────────────────────────

const QUEST_ICONS = {{ bulk_delivery:'📦', raider_suppress:'⚔', road_restore:'🔧', escort:'🛡' }};
const QUEST_KR    = {{ bulk_delivery:'물자납품', raider_suppress:'도적토벌', road_restore:'도로복구', escort:'호위' }};

function updateQuestBoard(rec) {{
  const container = document.getElementById('quest-items');
  const quests = rec.qx || [];
  if (!quests.length) {{
    container.innerHTML = '<div style="font-size:11px;color:#555;padding:8px;">활성 퀘스트 없음</div>';
    return;
  }}
  const order = {{ active:0, pending:1, completed:2, expired:3 }};
  const sorted = [...quests].sort((a,b) => (order[a.st]??9)-(order[b.st]??9));
  let html = '';
  for (const q of sorted) {{
    const ugPct = Math.round(q.ug * 100);
    const ugCol = q.ug >= 0.8 ? '#F44336' : q.ug >= 0.6 ? '#FF9800' : '#4CAF50';
    const reward = Object.entries(q.rw||{{}}).map(([g,v])=>`${{g}}×${{v}}`).join(', ') || '없음';
    const left   = q.dt - (rec.t || 0);
    const short  = q.tx ? (q.tx.length > 80 ? q.tx.slice(0,80)+'…' : q.tx) : '(서사 없음)';
    html += `<div class="quest-card ${{q.st}}">
      <div class="quest-header">
        <span style="font-size:13px;">${{QUEST_ICONS[q.qt]||'?'}}</span>
        <span style="font-size:12px;font-weight:bold;flex:1;">${{QUEST_KR[q.qt]||q.qt}}</span>
        <span class="quest-status ${{q.st}}">${{q.st}}</span>
      </div>
      <div class="quest-urgency-bar">
        <span style="min-width:36px;color:#aaa;">긴급도</span>
        <div style="flex:1;height:5px;background:#1a1a2e;border-radius:3px;overflow:hidden;">
          <div style="width:${{ugPct}}%;height:100%;background:${{ugCol}};"></div></div>
        <span style="color:${{ugCol}};min-width:28px;">${{ugPct}}%</span>
      </div>
      <div class="quest-text">${{short}}</div>
      <div class="quest-meta">
        <span>🎯 ${{q.tg}}</span><span>👥 ${{q.sc}}명</span><span>💰 ${{reward}}</span>
        ${{left > 0 ? `<span style="color:#e94560;">⏳${{left}}t</span>` : ''}}
      </div>
    </div>`;
  }}
  container.innerHTML = html;
}}

// ── Playback ──────────────────────────────────────────────────────────────────

function togglePlay() {{
  playing = !playing;
  playBtn.textContent = playing ? '⏸' : '▶';
  if (playing) scheduleTick(); else clearTimeout(playTimer);
}}
function scheduleTick() {{
  playTimer = setTimeout(() => {{
    if (!playing) return;
    if (currentTick >= ticks.length - 1) {{ playing = false; playBtn.textContent = '▶'; return; }}
    renderTick(currentTick + 1);
    scheduleTick();
  }}, playSpeed);
}}
function stepOne(d)  {{ renderTick(currentTick + d); }}
function stepBack()  {{ renderTick(0); }}
function stepFwd()   {{ renderTick(ticks.length - 1); }}
function onSlider(v) {{ renderTick(parseInt(v)); }}
function setSpeed(v) {{ playSpeed = parseInt(v); }}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('load', () => {{ initSVG(); renderTick(0); }});
window.addEventListener('resize', () => {{ initSVG(); renderTick(currentTick); }});
</script>
</body>
</html>"""
