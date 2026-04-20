"""HTML Time Machine renderer — generates a self-contained replay HTML file."""

from __future__ import annotations

import json
from pathlib import Path

ROLE_COLORS: dict[str, str] = {
    "farmer":     "#4CAF50",
    "herder":     "#795548",
    "miner":      "#607D8B",
    "orchardist": "#8BC34A",
    "blacksmith": "#FF5722",
    "cook":       "#FFC107",
    "merchant":   "#2196F3",
    "raider":     "#F44336",
}

ACTION_ICONS: dict[str, str] = {
    "produce":  "⛏",
    "craft":    "🔨",
    "trade":    "🤝",
    "travel":   "🚶",
    "transit":  "→",
    "collect":  "📦",
    "deliver":  "🏭",
    "equip":    "🗡",
    "consume":  "🍞",
    "raid":     "⚔",
    "idle":     "💤",
}

# Node layout positions (x%, y%) — hand-tuned for the MVP map
NODE_POSITIONS: dict[str, tuple[float, float]] = {
    "city.market":      (12, 45),
    "city.smithy":      (8,  30),
    "city.kitchen":     (8,  60),
    "city.residential": (4,  45),
    "route.safe_mid":   (35, 20),
    "route.risky_mid":  (35, 70),
    "raider.hideout":   (50, 82),
    "farm.hub":         (62, 45),
    "farm.grain_field": (78, 28),
    "farm.pasture":     (78, 42),
    "farm.orchard":     (78, 56),
    "farm.mine":        (78, 70),
}


def render_html(data: dict, output_path: Path) -> None:
    """Embed simulation JSON into a self-contained HTML file."""
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = _build_html(json_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _build_html(json_str: str) -> str:
    node_pos_js = json.dumps(NODE_POSITIONS)
    role_colors_js = json.dumps(ROLE_COLORS)
    action_icons_js = json.dumps(ACTION_ICONS)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Society — Time Machine</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

/* ── Controls ── */
#controls {{ background: #16213e; padding: 8px 16px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #0f3460; flex-shrink: 0; }}
#controls button {{ background: #0f3460; border: 1px solid #e94560; color: #e0e0e0; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
#controls button:hover {{ background: #e94560; }}
#tick-display {{ font-size: 13px; min-width: 160px; }}
#slider {{ flex: 1; accent-color: #e94560; }}
#speed-select {{ background: #0f3460; border: 1px solid #e94560; color: #e0e0e0; padding: 3px 6px; border-radius: 4px; }}

/* ── Main layout ── */
#main {{ display: grid; grid-template-columns: 1fr 340px; grid-template-rows: 1fr 1fr 200px; flex: 1; overflow: hidden; gap: 4px; padding: 4px; }}

/* ── Map ── */
#map-panel {{ background: #16213e; border-radius: 6px; position: relative; overflow: hidden; grid-row: span 3; }}
#map-svg {{ width: 100%; height: 100%; }}

/* ── Quest panel (top-right) ── */
#quest-panel {{ background: #16213e; border-radius: 6px; overflow-y: auto; padding: 8px; }}
#quest-panel h3 {{ font-size: 12px; color: #e94560; margin-bottom: 6px; flex-shrink: 0; }}

/* ── Action log (middle-right) ── */
#action-log {{ background: #16213e; border-radius: 6px; overflow-y: auto; padding: 8px; }}
#action-log h3 {{ font-size: 12px; color: #e94560; margin-bottom: 6px; }}
.action-item {{ font-size: 11px; padding: 3px 6px; border-radius: 3px; margin-bottom: 2px; background: #0f3460; border-left: 3px solid #666; }}
.action-item.travel {{ border-color: #2196F3; }}
.action-item.trade  {{ border-color: #4CAF50; }}
.action-item.raid   {{ border-color: #F44336; }}
.action-item.craft  {{ border-color: #FF5722; }}
.action-item.produce {{ border-color: #8BC34A; }}
.action-item.consume {{ border-color: #FFC107; }}

/* ── Quest board ── */
.quest-card {{ background: #0f3460; border-radius: 5px; padding: 7px 9px; margin-bottom: 6px; border-left: 3px solid #888; }}
.quest-card.pending  {{ border-color: #FFC107; }}
.quest-card.active   {{ border-color: #4CAF50; }}
.quest-card.completed {{ border-color: #2196F3; opacity: 0.7; }}
.quest-card.expired  {{ border-color: #555; opacity: 0.5; }}
.quest-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }}
.quest-type-badge {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; background: #1a1a2e; color: #e94560; }}
.quest-status {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: bold; }}
.quest-status.pending  {{ background: #3a2e00; color: #FFC107; }}
.quest-status.active   {{ background: #003a00; color: #4CAF50; }}
.quest-status.completed {{ background: #001a3a; color: #2196F3; }}
.quest-status.expired  {{ background: #1a1a1a; color: #555; }}
.quest-urgency-bar {{ display: flex; align-items: center; gap: 5px; font-size: 10px; margin: 3px 0; }}
.quest-text {{ font-size: 11px; color: #ccc; line-height: 1.5; margin: 4px 0; border-left: 2px solid #333; padding-left: 6px; }}
.quest-meta {{ font-size: 10px; color: #888; display: flex; gap: 10px; flex-wrap: wrap; }}

/* ── Node/Agent detail ── */
#detail-panel {{ background: #16213e; border-radius: 6px; padding: 10px; overflow-y: auto; }}
#detail-panel h3 {{ font-size: 12px; color: #e94560; margin-bottom: 8px; }}
.need-bar {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; font-size: 11px; }}
.need-bar .label {{ min-width: 100px; }}
.need-bar .bar-bg {{ flex: 1; height: 8px; background: #0f3460; border-radius: 4px; overflow: hidden; }}
.need-bar .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.15s; }}
.stock-row {{ font-size: 11px; display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px solid #0f3460; }}

/* ── SVG elements ── */
.node-circle {{ cursor: pointer; transition: opacity 0.1s; }}
.node-circle:hover {{ opacity: 0.8; }}
.agent-dot {{ cursor: pointer; transition: cx 0.2s, cy 0.2s; }}
.agent-dot:hover {{ stroke-width: 3; }}
.edge-line {{ stroke: #334; stroke-width: 2; }}
.edge-line.threat-high {{ stroke: #F44336; stroke-dasharray: 5,3; opacity: 0.6; }}
.edge-line.threat-low  {{ stroke: #4CAF50; opacity: 0.4; }}
.node-label {{ font-size: 10px; fill: #aaa; pointer-events: none; }}
.raider-node {{ fill: #3a1a1a; stroke: #F44336; }}
.city-node   {{ fill: #1a2a3a; stroke: #2196F3; }}
.farm-node   {{ fill: #1a3a1a; stroke: #4CAF50; }}
.route-node  {{ fill: #2a2a2a; stroke: #888; }}
.event-badge {{ font-size: 9px; fill: #e94560; }}
</style>
</head>
<body>

<!-- Controls -->
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

<!-- Main -->
<div id="main">
  <div id="map-panel"><svg id="map-svg"></svg></div>
  <div id="quest-panel"><h3>📋 퀘스트 현황</h3><div id="quest-items"></div></div>
  <div id="action-log"><h3>▶ 이번 Tick 행동</h3><div id="action-items"></div></div>
  <div id="detail-panel"><h3 id="detail-title">노드 또는 에이전트를 클릭하세요</h3><div id="detail-body"></div></div>
</div>

<script>
const DATA = {json_str};
const NODE_POS = {node_pos_js};
const ROLE_COLORS = {role_colors_js};
const ACTION_ICONS = {action_icons_js};

const meta = DATA.meta;
const ticks = DATA.ticks;
let currentTick = 0;
let playing = false;
let playTimer = null;
let playSpeed = 250;
let selectedId = null;   // node or agent id
let selectedType = null; // 'node' or 'agent'

const slider = document.getElementById('slider');
const playBtn = document.getElementById('play-btn');
slider.max = ticks.length - 1;

// ── SVG setup ────────────────────────────────────────────────────────────────
const svg = document.getElementById('map-svg');
let svgW = 0, svgH = 0;

function pct(x, y) {{
  return [svgW * x / 100, svgH * y / 100];
}}

function initSVG() {{
  svg.innerHTML = '';
  const rect = svg.getBoundingClientRect();
  svgW = rect.width || 900;
  svgH = rect.height || 600;

  // Edges
  for (const edge of meta.edges) {{
    const [x1,y1] = getNodeXY(edge.u);
    const [x2,y2] = getNodeXY(edge.v);
    const line = makeSVG('line', {{
      x1, y1, x2, y2,
      class: 'edge-line ' + (edge.base_threat > 0.5 ? 'threat-high' : edge.base_threat > 0 ? 'threat-low' : ''),
    }});
    svg.appendChild(line);
  }}

  // Nodes
  for (const [nid, node] of Object.entries(meta.nodes)) {{
    const [cx, cy] = getNodeXY(nid);
    const cls = nid.startsWith('city') ? 'city-node' :
                nid.startsWith('farm') ? 'farm-node' :
                nid.startsWith('raider') ? 'raider-node' : 'route-node';
    const circle = makeSVG('circle', {{
      cx, cy, r: 18,
      class: 'node-circle ' + cls,
      'data-id': nid,
    }});
    circle.addEventListener('click', () => selectNode(nid));
    svg.appendChild(circle);
    const lbl = makeSVG('text', {{
      x: cx, y: cy + 28,
      class: 'node-label',
      'text-anchor': 'middle',
    }});
    lbl.textContent = node.name.replace('City ', '').replace('Farmland ', '').replace(' ', '\\n');
    svg.appendChild(lbl);
  }}

  // Agent dots (grouped by node)
  for (const [aid, agent] of Object.entries(meta.agents)) {{
    const dot = makeSVG('circle', {{
      r: 6,
      class: 'agent-dot',
      fill: ROLE_COLORS[agent.role] || '#aaa',
      stroke: '#fff',
      'stroke-width': 1.5,
      'data-id': aid,
      opacity: 0.9,
    }});
    dot.addEventListener('click', (e) => {{ e.stopPropagation(); selectAgent(aid); }});
    svg.appendChild(dot);
  }}
}}

function getNodeXY(nid) {{
  const pos = NODE_POS[nid] || [50, 50];
  return pct(pos[0], pos[1]);
}}

function makeSVG(tag, attrs) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}}

// ── Render a tick ─────────────────────────────────────────────────────────────
function renderTick(idx) {{
  currentTick = Math.max(0, Math.min(idx, ticks.length - 1));
  slider.value = currentTick;
  const rec = ticks[currentTick];
  document.getElementById('tick-display').textContent =
    `Tick ${{rec.t}} (${{rec.s}}) — ${{currentTick+1}}/${{ticks.length}}`;

  updateAgentPositions(rec);
  updateActionLog(rec);
  updateQuestBoard(rec);
  if (selectedId) {{
    if (selectedType === 'node') renderNodeDetail(selectedId, rec);
    else renderAgentDetail(selectedId, rec);
  }}
}}

function updateAgentPositions(rec) {{
  // Group agents by node to offset dots
  const byNode = {{}};
  for (const [aid, as_] of Object.entries(rec.as)) {{
    if (!byNode[as_.n]) byNode[as_.n] = [];
    byNode[as_.n].push(aid);
  }}

  for (const dot of svg.querySelectorAll('.agent-dot')) {{
    const aid = dot.getAttribute('data-id');
    const state = rec.as[aid];
    if (!state) continue;
    const agents = byNode[state.n] || [aid];
    const idx = agents.indexOf(aid);
    const [cx, cy] = getNodeXY(state.n);
    const count = agents.length;
    // Spiral layout around node
    const angle = (idx / count) * Math.PI * 2;
    const radius = count > 1 ? Math.min(12 + count, 28) : 0;
    dot.setAttribute('cx', cx + Math.cos(angle) * radius);
    dot.setAttribute('cy', cy + Math.sin(angle) * radius);
    // In-transit visual cue
    const inTransit = (state.tr || 0) > 0;
    dot.setAttribute('opacity', inTransit ? 0.5 : 0.9);
    dot.setAttribute('stroke-dasharray', inTransit ? '2,2' : 'none');
    // Highlight if selected
    dot.setAttribute('stroke-width', aid === selectedId ? 3 : 1.5);
    dot.setAttribute('stroke', aid === selectedId ? '#fff' : '#fff');
    dot.style.filter = aid === selectedId ? 'drop-shadow(0 0 4px white)' : '';
  }}
}}

function updateActionLog(rec) {{
  const container = document.getElementById('action-items');
  container.innerHTML = '';
  const important = rec.ac.filter(a => a.t !== 'idle' && a.t !== 'transit').slice(0, 60);
  if (important.length === 0) {{
    container.innerHTML = '<div style="font-size:11px;color:#666;">행동 없음</div>';
    return;
  }}
  for (const a of important) {{
    const icon = ACTION_ICONS[a.t] || '?';
    const div = document.createElement('div');
    div.className = 'action-item ' + a.t;
    div.innerHTML = `<b style="color:${{ROLE_COLORS[a.r]||'#aaa'}}">${{a.nm}}</b> ${{icon}} ${{formatAction(a)}}`;
    div.style.cursor = 'pointer';
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
  switch(a.t) {{
    case 'produce': return `생산 ${{a.d.good||''}} +${{a.d.amount||1}}`;
    case 'craft':   return `제작 ${{a.d.output_good||''}}`;
    case 'trade':   return `교환 ${{a.d.item_out||''}}→${{a.d.item_in||''}} (with ${{a.d.buyer_name||'?'}})`;
    case 'travel':  {{ const dest = a.d.target_node || a.nd; const cost = a.d.cost ? ' (' + a.d.cost + 't)' : ''; return '이동' + cost + ' → ' + dest; }}
    case 'consume': return `식사 ${{a.d.food_good||''}}`;
    case 'collect': return `수집 ${{a.d.good||''}} ×${{a.d.qty||''}} from ${{a.d.node_id||a.nd}}`;
    case 'deliver': return `납품 ${{a.d.good||''}} ×${{a.d.qty||''}} → ${{a.d.deposit_node||''}}`;
    case 'equip':   return `무기구입 ${{a.d.weapon_type||'sword'}} from ${{a.d.source_node||''}}`;
    case 'raid':    {{
      const ri = (a.rd && a.rd._raid) ? a.rd._raid : {{}};
      const resKr = ri.result === 'repelled' ? '격퇴' : ri.result === 'partial_loss' ? '부분성공' : ri.result === 'plundered' ? '완전약탈' : '?';
      const atkStr = ri.attack !== undefined ? ri.attack.toFixed(1) : '?';
      const defStr = ri.defense !== undefined ? ri.defense : '?';
      const lootStr = ri.loot ? Object.entries(ri.loot).map(function(e){{return e[0]+'×'+e[1];}}).join(', ') : '없음';
      return '습격 [' + resKr + '] ⚔' + atkStr + ' vs 🛡' + defStr + ' | ' + lootStr;
    }}
    default:        return a.t;
  }}
}}

// ── Selection detail ─────────────────────────────────────────────────────────
function selectNode(nid) {{
  selectedId = nid; selectedType = 'node';
  // Highlight
  for (const c of svg.querySelectorAll('.node-circle')) {{
    c.style.filter = c.getAttribute('data-id') === nid ? 'drop-shadow(0 0 6px white)' : '';
  }}
  renderNodeDetail(nid, ticks[currentTick]);
}}

function selectAgent(aid) {{
  selectedId = aid; selectedType = 'agent';
  renderAgentDetail(aid, ticks[currentTick]);
  updateAgentPositions(ticks[currentTick]);
}}

function renderNodeDetail(nid, rec) {{
  const node = meta.nodes[nid];
  const stock = rec.ns[nid] || {{}};
  const agents = Object.entries(rec.as).filter(([,s]) => s.n === nid);
  document.getElementById('detail-title').textContent = `📍 ${{node?.name || nid}}`;
  let html = '<div style="font-size:11px;color:#aaa;margin-bottom:6px;">재고</div>';
  const goods = Object.entries(stock).filter(([,v])=>v>0).sort(([,a],[,b])=>b-a);
  if (goods.length === 0) html += '<div style="font-size:11px;color:#555;">재고 없음</div>';
  for (const [g, qty] of goods) {{
    const pct = Math.min(100, qty / 50 * 100);
    html += `<div class="stock-row"><span>${{g}}</span><span style="display:flex;align-items:center;gap:4px;">
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
  let html = `<div style="font-size:11px;color:#aaa;margin-bottom:6px;">${{agent.role}} · ${{nodeNm}}${{goldBadge}}</div>`;

  // Needs bars
  const needColors = {{hunger:'#F44336',food_satisfaction:'#FF9800',tool_need:'#9C27B0',safety:'#2196F3'}};
  const needNames = {{hunger:'허기',food_satisfaction:'식욕만족',tool_need:'도구부족',safety:'안전'}};
  for (const [nt, val] of Object.entries(state.needs || {{}})) {{
    const pct = Math.min(100, val * 100);
    const col = needColors[nt] || '#888';
    html += `<div class="need-bar"><span class="label">${{needNames[nt]||nt}}</span>
      <div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%;background:${{col}};"></div></div>
      <span style="font-size:10px;min-width:30px;">${{(val*100).toFixed(0)}}%</span></div>`;
  }}

  // Tool durability
  if (Object.keys(state.td||{{}}).length > 0) {{
    html += `<div style="font-size:11px;color:#aaa;margin:6px 0 4px;">도구 내구도</div>`;
    for (const [tool, dur] of Object.entries(state.td||{{}})) {{
      const pct = Math.min(100, dur / 10 * 100);
      html += `<div class="need-bar"><span class="label">${{tool}}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${{pct}}%;background:#FFC107;"></div></div>
        <span style="font-size:10px;min-width:30px;">${{dur.toFixed(2)}}</span></div>`;
    }}
  }}

  // Raider: strength + armory as combat power
  if (state.str !== null && state.str !== undefined) {{
    const str = state.str;
    const armory = (state.items && state.items.sword) ? state.items.sword : 0;
    const effAtk = str + armory * 1.5;
    const strPct = Math.min(100, effAtk / 100 * 100);
    const strCol = effAtk > 70 ? '#F44336' : effAtk > 40 ? '#FF9800' : '#4CAF50';
    html += `<div style="font-size:11px;color:#aaa;margin:4px 0 2px;">전투력 (공격)</div>
      <div class="need-bar">
        <span class="label" style="color:${{strCol}};font-weight:bold;">⚔ ${{effAtk.toFixed(1)}}</span>
        <div class="bar-bg" style="flex:1;"><div class="bar-fill" style="width:${{strPct}}%;background:${{strCol}};"></div></div>
      </div>
      <div style="font-size:10px;color:#888;margin:-2px 0 4px 4px;">기본 ${{str.toFixed(1)}} + 무기 ${{armory}}자루 × 1.5</div>`;
  }}

  // Merchant/other agents: equipped weapon → defense power
  if (state.wpn && (state.wp || 0) > 0) {{
    const wp = state.wp;
    const wpPct = Math.min(100, wp / 15 * 100);
    html += `<div style="font-size:11px;color:#aaa;margin:4px 0 2px;">전투력 (방어)</div>
      <div class="need-bar">
        <span class="label" style="color:#2196F3;font-weight:bold;">🛡 ${{wp}}</span>
        <div class="bar-bg" style="flex:1;"><div class="bar-fill" style="width:${{wpPct}}%;background:#2196F3;"></div></div>
      </div>
      <div style="font-size:10px;color:#888;margin:-2px 0 4px 4px;">무장: ${{state.wpn}}</div>`;
  }} else if (state.str === null || state.str === undefined) {{
    html += `<div style="font-size:11px;color:#555;margin:2px 0 6px 4px;">비무장 (방어력 0)</div>`;
  }}

  // In-transit badge
  if ((state.tr || 0) > 0) {{
    html += `<div style="font-size:11px;background:#1a3a0a;color:#8BC34A;padding:3px 6px;border-radius:3px;margin-bottom:6px;">
      🚶 이동 중 (${{state.tr}}tick 남음)</div>`;
  }}

  // Inventory
  const items = state.items || {{}};
  const itemEntries = Object.entries(items).filter(([,v])=>v>0).sort(([,a],[,b])=>b-a);
  if (itemEntries.length > 0) {{
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

  // Recent actions
  html += `<div style="font-size:11px;color:#aaa;margin:6px 0 4px;">이번 tick 행동</div>`;
  const myActions = (rec.ac||[]).filter(a=>a.id===aid);
  if (myActions.length === 0) html += '<div style="font-size:11px;color:#555;">idle</div>';
  for (const a of myActions) {{
    html += `<div style="font-size:11px;padding:2px 4px;background:#0f3460;border-radius:3px;margin-bottom:2px;">
      ${{ACTION_ICONS[a.t]||'?'}} ${{formatAction(a)}}</div>`;
  }}

  document.getElementById('detail-body').innerHTML = html;
}}

// ── Quest board ───────────────────────────────────────────────────────────────
const QUEST_TYPE_ICONS = {{
  bulk_delivery: '📦',
  raider_suppress: '⚔',
  road_restore: '🔧',
  escort: '🛡',
}};
const QUEST_TYPE_KR = {{
  bulk_delivery: '물자 납품',
  raider_suppress: '도적 토벌',
  road_restore: '도로 복구',
  escort: '호위',
}};

function updateQuestBoard(rec) {{
  const container = document.getElementById('quest-items');
  const quests = rec.qx || [];
  if (quests.length === 0) {{
    container.innerHTML = '<div style="font-size:11px;color:#555;padding:8px;">이 시점에 활성 퀘스트 없음</div>';
    return;
  }}

  // 상태 순서: active → pending → completed → expired
  const order = {{ active: 0, pending: 1, completed: 2, expired: 3 }};
  const sorted = [...quests].sort((a, b) => (order[a.st] ?? 9) - (order[b.st] ?? 9));

  let html = '';
  for (const q of sorted) {{
    const icon = QUEST_TYPE_ICONS[q.qt] || '?';
    const typeKr = QUEST_TYPE_KR[q.qt] || q.qt;
    const ugPct = Math.round(q.ug * 100);
    const ugCol = q.ug >= 0.8 ? '#F44336' : q.ug >= 0.6 ? '#FF9800' : '#4CAF50';
    const rewardStr = Object.entries(q.rw || {{}}).map(([g,v]) => `${{g}} ×${{v}}`).join(', ') || '없음';
    const ticksLeft = q.dt - (rec.t || 0);
    const shortText = q.tx ? (q.tx.length > 80 ? q.tx.slice(0, 80) + '…' : q.tx) : '(서사 없음)';

    html += `<div class="quest-card ${{q.st}}">
      <div class="quest-header">
        <span style="font-size:13px;">${{icon}}</span>
        <span style="font-size:12px;font-weight:bold;flex:1;">${{typeKr}}</span>
        <span class="quest-status ${{q.st}}">${{q.st}}</span>
      </div>
      <div class="quest-urgency-bar">
        <span style="min-width:36px;color:#aaa;">긴급도</span>
        <div style="flex:1;height:5px;background:#1a1a2e;border-radius:3px;overflow:hidden;">
          <div style="width:${{ugPct}}%;height:100%;background:${{ugCol}};"></div></div>
        <span style="color:${{ugCol}};min-width:28px;">${{ugPct}}%</span>
      </div>
      <div class="quest-text">${{shortText}}</div>
      <div class="quest-meta">
        <span>🎯 ${{q.tg}}</span>
        <span>👥 의뢰자 ${{q.sc}}명</span>
        <span>💰 ${{rewardStr}}</span>
        ${{ticksLeft > 0 ? `<span style="color:#e94560;">⏳ ${{ticksLeft}}tick 남음</span>` : ''}}
      </div>
    </div>`;
  }}
  container.innerHTML = html;
}}

// ── Playback controls ─────────────────────────────────────────────────────────
function togglePlay() {{
  playing = !playing;
  playBtn.textContent = playing ? '⏸' : '▶';
  if (playing) scheduleTick();
  else clearTimeout(playTimer);
}}

function scheduleTick() {{
  playTimer = setTimeout(() => {{
    if (!playing) return;
    if (currentTick >= ticks.length - 1) {{ playing = false; playBtn.textContent = '▶'; return; }}
    renderTick(currentTick + 1);
    scheduleTick();
  }}, playSpeed);
}}

function stepOne(dir) {{ renderTick(currentTick + dir); }}
function stepBack() {{ renderTick(0); }}
function stepFwd() {{ renderTick(ticks.length - 1); }}
function onSlider(v) {{ renderTick(parseInt(v)); }}
function setSpeed(v) {{ playSpeed = parseInt(v); }}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('load', () => {{
  initSVG();
  renderTick(0);
}});
window.addEventListener('resize', () => {{
  initSVG();
  renderTick(currentTick);
}});
</script>
</body>
</html>"""
