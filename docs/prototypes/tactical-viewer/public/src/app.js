import {
  computeReachability,
  coordinateLabel,
  deepFreeze,
  fingerprint,
  movementBudget,
  summarizePath
} from "./engine.js";
import { renderMap } from "./render-map.js";

const app = document.querySelector("#app");
const variants = [
  { key: "A", name: "地图优先" },
  { key: "B", name: "路线工作台" },
  { key: "C", name: "安静棋桌" }
];
const params = new URLSearchParams(location.search);
const initialVariant = variants.some(({ key }) => key === params.get("variant")) ? params.get("variant") : "A";
const initialMap = params.get("map") === "large" ? "large" : "small";

const viewer = {
  variant: initialVariant,
  mapKey: initialMap,
  scene: null,
  sceneDigest: null,
  selectedId: null,
  mode: "normal",
  target: null,
  tree: null,
  summary: null,
  benchmarkResults: null,
  notice: "点击自己的棋子开始只读预览。",
  mapApi: null,
  metrics: { generationMs: null, highlightMs: null, pathMs: null, cacheHit: false },
  treeCache: new Map()
};

function mapLink(mapKey) {
  const next = new URLSearchParams(location.search);
  next.set("variant", viewer.variant);
  next.set("map", mapKey);
  return `?${next.toString()}`;
}

function controlsMarkup() {
  return `
    <div class="control-cluster" aria-label="移动模式">
      <button class="mode-button ${viewer.mode === "normal" ? "active" : ""}" data-mode="normal">普通移动</button>
      <button class="mode-button ${viewer.mode === "dash" ? "active" : ""}" data-mode="dash">疾走</button>
    </div>
    <div class="control-cluster" aria-label="地图大小">
      <a class="map-button ${viewer.mapKey === "small" ? "active" : ""}" href="${mapLink("small")}">14×10</a>
      <a class="map-button ${viewer.mapKey === "large" ? "active" : ""}" href="${mapLink("large")}">50×50</a>
    </div>`;
}

function mapLegendMarkup() {
  return `
    <div class="map-legend" aria-label="地图图例">
      <span><i class="swatch normal"></i>普通可达</span>
      <span><i class="swatch dash"></i>仅疾走可达</span>
      <span><i class="swatch terrain"></i>困难地形</span>
      <span><i class="swatch risk"></i>明显风险</span>
    </div>`;
}

function commonHeader(compact = false) {
  return `
    <header class="viewer-header ${compact ? "compact" : ""}">
      <div>
        <p class="eyebrow">THROWAWAY · 本地只读玩家投影</p>
        <h1>${viewer.scene.title}</h1>
        <p class="revision">${viewer.scene.projectionRevision} · ${viewer.scene.grid.feetPerCell} 尺方格 · 对角每格 5 尺</p>
      </div>
      <div class="header-controls">${controlsMarkup()}</div>
    </header>`;
}

function shellMarkup() {
  if (viewer.variant === "B") {
    return `
      <div class="prototype-shell variant-b">
        ${commonHeader()}
        <section class="budget-ribbon" id="selection-panel"></section>
        <section class="route-workbench">
          <div class="map-panel"><div id="map-root"></div>${mapLegendMarkup()}</div>
          <aside class="state-rail"><h2>预览状态</h2><pre id="state-panel"></pre></aside>
        </section>
        <section class="route-dock"><div id="path-panel"></div></section>
      </div>`;
  }
  if (viewer.variant === "C") {
    return `
      <div class="prototype-shell variant-c">
        ${commonHeader(true)}
        <section class="quiet-stage">
          <div class="map-panel"><div id="map-root"></div></div>
          <aside class="floating-summary">
            <div id="selection-panel"></div>
            <div id="path-panel"></div>
          </aside>
        </section>
        <details class="state-drawer"><summary>查看完整预览状态</summary><pre id="state-panel"></pre></details>
      </div>`;
  }
  return `
    <div class="prototype-shell variant-a">
      ${commonHeader()}
      <section class="map-first-layout">
        <div class="map-panel"><div id="map-root"></div>${mapLegendMarkup()}</div>
        <aside class="inspector">
          <section id="selection-panel"></section>
          <section id="path-panel"></section>
          <section><h2>完整预览状态</h2><pre id="state-panel"></pre></section>
        </aside>
      </section>
    </div>`;
}

function switcherMarkup() {
  const current = variants.find(({ key }) => key === viewer.variant);
  return `
    <nav class="prototype-switcher" aria-label="抛弃式原型布局切换" data-prototype-only>
      <button data-variant-step="-1" aria-label="上一个布局">←</button>
      <span><strong>${current.key}</strong> — ${current.name}</span>
      <button data-variant-step="1" aria-label="下一个布局">→</button>
    </nav>`;
}

function diagnosticsMarkup() {
  return `
    <details class="benchmark-diagnostics" ${viewer.benchmarkResults ? "open" : ""} data-prototype-only>
      <summary>性能诊断（原型专用）</summary>
      <button data-run-benchmark>运行 20 轮基准</button>
      <pre id="benchmark-panel">${viewer.benchmarkResults ? "" : "尚未运行。"}</pre>
    </details>`;
}

function selectedEntity() {
  return viewer.scene.entities.find((entity) => entity.id === viewer.selectedId) ?? null;
}

function renderSelectionPanel() {
  const panel = document.querySelector("#selection-panel");
  const entity = selectedEntity();
  if (!entity) {
    panel.innerHTML = `
      <p class="section-kicker">移动预算</p>
      <h2>选择你的棋子</h2>
      <p class="muted">点击带亮边的玩家棋子。这里只计算预览，不会改变位置。</p>`;
    return;
  }
  const normal = movementBudget(entity, "normal");
  const dash = movementBudget(entity, "dash");
  const active = movementBudget(entity, viewer.mode);
  panel.innerHTML = `
    <p class="section-kicker">${coordinateLabel(entity.position)} · ${entity.sizeCells === 1 ? "中型" : `${entity.sizeCells}×${entity.sizeCells} 占地`}</p>
    <div class="entity-heading"><h2>${entity.label}</h2><span class="status-chip">${entity.conditions.join(" · ")}</span></div>
    <div class="budget-meter"><span style="width:${Math.min(100, (active / Math.max(dash, 1)) * 100)}%"></span></div>
    <dl class="metric-grid">
      <div><dt>速度</dt><dd>${entity.movement.speedFeet} 尺</dd></div>
      <div><dt>已使用</dt><dd>${entity.movement.usedFeet} 尺</dd></div>
      <div><dt>普通剩余</dt><dd>${normal} 尺</dd></div>
      <div><dt>疾走剩余</dt><dd>${dash} 尺</dd></div>
    </dl>`;
}

function renderPathPanel() {
  const panel = document.querySelector("#path-panel");
  if (!viewer.summary) {
    panel.innerHTML = `
      <p class="section-kicker">最低合法消耗路径</p>
      <h2>尚未选择目标格</h2>
      <p class="muted">${viewer.notice}</p>
      <p class="knowledge-warning">仅依据玩家知识投影；未知信息不会参与可达范围、路径或风险提示。</p>`;
    return;
  }
  const summary = viewer.summary;
  const riskMarkup = summary.risks.length > 0
    ? `<ul class="risk-list">${summary.risks.map((risk) => `<li>${risk.message}：${coordinateLabel(risk.from)} → ${coordinateLabel(risk.to)}</li>`).join("")}</ul>`
    : `<p class="no-risk">未发现明显借机攻击风险；这不代表不存在未知风险。</p>`;
  panel.innerHTML = `
    <p class="section-kicker">目标 ${summary.target}</p>
    <h2>路径预览</h2>
    <dl class="route-metrics">
      <div><dt>格距</dt><dd>${summary.distanceFeet} 尺</dd></div>
      <div><dt>移动消耗</dt><dd>${summary.costFeet} 尺</dd></div>
      <div><dt>剩余</dt><dd>${summary.remainingFeet} 尺</dd></div>
    </dl>
    <p class="route-coordinates">${summary.path.map(coordinateLabel).join(" → ")}</p>
    ${riskMarkup}
    <p class="read-only-note">预览没有提交入口；最终移动仍须回到对话确认。</p>`;
}

function relevantState() {
  const entity = selectedEntity();
  return {
    readOnly: viewer.scene.readOnly,
    authorityRevision: viewer.scene.authorityRevision,
    projectionRevision: viewer.scene.projectionRevision,
    authoritySnapshotUnchanged: fingerprint(viewer.scene) === viewer.sceneDigest,
    selectedEntity: entity ? {
      id: entity.id,
      coordinate: coordinateLabel(entity.position),
      speedFeet: entity.movement.speedFeet,
      usedFeet: entity.movement.usedFeet,
      sizeCells: entity.sizeCells,
      conditions: entity.conditions
    } : null,
    movementMode: viewer.mode,
    budgetFeet: entity ? movementBudget(entity, viewer.mode) : null,
    reachableCellCount: viewer.tree?.costByCell.size ?? 0,
    target: viewer.summary?.target ?? null,
    path: viewer.summary?.path.map(coordinateLabel) ?? [],
    visibleRisks: viewer.summary?.risks.map((risk) => risk.message) ?? [],
    timingsMs: viewer.metrics
  };
}

function renderStatePanel() {
  document.querySelector("#state-panel").textContent = JSON.stringify(relevantState(), null, 2);
}

function renderPanels() {
  renderSelectionPanel();
  renderPathPanel();
  renderStatePanel();
}

function buildMap() {
  const started = performance.now();
  viewer.mapApi = renderMap(document.querySelector("#map-root"), viewer.scene, {
    showThreatZones: viewer.variant === "A",
    onEntityClick: selectToken,
    onCellClick: previewTarget
  });
  viewer.metrics.generationMs = performance.now() - started;
  if (viewer.selectedId) {
    viewer.mapApi.markSelected(viewer.selectedId);
    viewer.mapApi.drawReachable(viewer.tree, movementBudget(selectedEntity(), "normal"), viewer.mode);
    viewer.mapApi.drawPath(viewer.summary, selectedEntity());
    viewer.mapApi.markTarget(viewer.target);
  }
}

function bindControls() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });
  document.querySelectorAll("[data-variant-step]").forEach((button) => {
    button.addEventListener("click", () => cycleVariant(Number(button.dataset.variantStep)));
  });
  document.querySelector("[data-run-benchmark]").addEventListener("click", (event) => {
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "运行中…";
    viewer.benchmarkResults = benchmark(20);
    document.querySelector("#benchmark-panel").textContent = JSON.stringify(viewer.benchmarkResults, null, 2);
    event.currentTarget.textContent = "重新运行 20 轮基准";
    event.currentTarget.disabled = false;
  });
}

function renderShell() {
  app.innerHTML = shellMarkup() + diagnosticsMarkup() + switcherMarkup();
  document.body.dataset.variant = viewer.variant;
  bindControls();
  buildMap();
  renderPanels();
  if (viewer.benchmarkResults) {
    document.querySelector("#benchmark-panel").textContent = JSON.stringify(viewer.benchmarkResults, null, 2);
  }
}

function treeFor(entity, mode, useCache = true) {
  const budget = movementBudget(entity, mode);
  const cacheKey = `${viewer.scene.projectionRevision}:${entity.id}:${mode}`;
  if (useCache && viewer.treeCache.has(cacheKey)) {
    viewer.metrics.cacheHit = true;
    return viewer.treeCache.get(cacheKey);
  }
  viewer.metrics.cacheHit = false;
  const tree = computeReachability(viewer.scene, entity.id, budget);
  if (useCache) viewer.treeCache.set(cacheKey, tree);
  return tree;
}

function selectToken(entityId) {
  const entity = viewer.scene.entities.find((candidate) => candidate.id === entityId && candidate.selectable);
  if (!entity) return;
  const started = performance.now();
  viewer.selectedId = entityId;
  viewer.target = null;
  viewer.summary = null;
  viewer.tree = treeFor(entity, viewer.mode);
  viewer.mapApi.markSelected(entityId);
  viewer.mapApi.markTarget(null);
  viewer.mapApi.drawPath(null, entity);
  viewer.mapApi.drawReachable(viewer.tree, movementBudget(entity, "normal"), viewer.mode);
  viewer.metrics.highlightMs = performance.now() - started;
  viewer.notice = `已显示 ${viewer.tree.costByCell.size} 个可达格；点击高亮格预览路径。`;
  renderPanels();
}

function setMode(mode) {
  if (!new Set(["normal", "dash"]).has(mode)) return;
  viewer.mode = mode;
  viewer.target = null;
  viewer.summary = null;
  if (viewer.selectedId) selectToken(viewer.selectedId);
  renderShell();
}

function previewTarget(target) {
  if (!viewer.selectedId || !viewer.tree) return;
  const cost = viewer.tree.costByCell.get(`${target.x},${target.y}`);
  if (cost === undefined) {
    viewer.notice = `${coordinateLabel(target)} 超出当前移动预算或被墙体、门、占地阻挡。`;
    viewer.target = null;
    viewer.summary = null;
    viewer.mapApi.markTarget(null);
    viewer.mapApi.drawPath(null, selectedEntity());
    renderPanels();
    return;
  }
  const started = performance.now();
  viewer.target = target;
  viewer.summary = summarizePath(viewer.scene, viewer.selectedId, viewer.mode, viewer.tree, target);
  viewer.mapApi.markTarget(target);
  viewer.mapApi.drawPath(viewer.summary, selectedEntity());
  viewer.metrics.pathMs = performance.now() - started;
  viewer.notice = `已预览到 ${coordinateLabel(target)} 的最低移动消耗路径。`;
  renderPanels();
}

function setVariant(key) {
  viewer.variant = key;
  const next = new URLSearchParams(location.search);
  next.set("variant", key);
  next.set("map", viewer.mapKey);
  history.replaceState(null, "", `?${next.toString()}`);
  renderShell();
}

function cycleVariant(step) {
  const index = variants.findIndex(({ key }) => key === viewer.variant);
  setVariant(variants[(index + step + variants.length) % variants.length].key);
}

function distribution(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const percentile = (fraction) => sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * fraction) - 1)];
  return {
    median: Number(percentile(0.5).toFixed(3)),
    p95: Number(percentile(0.95).toFixed(3)),
    min: Number(sorted[0].toFixed(3)),
    max: Number(sorted.at(-1).toFixed(3))
  };
}

function farthestReachable(tree) {
  let result = null;
  for (const [key, cost] of tree.costByCell) {
    if (!result || cost > result.cost || (cost === result.cost && key < result.key)) result = { key, cost };
  }
  const [x, y] = result.key.split(",").map(Number);
  return { x, y };
}

function benchmark(iterations = 20) {
  const generation = [];
  const highlight = [];
  const pathPreview = [];
  const precomputeAllPlayers = [];
  const host = document.createElement("div");
  host.className = "benchmark-host";
  document.body.append(host);
  const entity = viewer.scene.entities.find((candidate) => candidate.selectable && candidate.movement);
  let lastTree;
  let lastTarget;
  let precomputedPayloadBytes = 0;
  for (let index = 0; index < iterations; index += 1) {
    let started = performance.now();
    const api = renderMap(host, viewer.scene, { showThreatZones: true });
    api.svg.getBoundingClientRect();
    generation.push(performance.now() - started);

    started = performance.now();
    lastTree = computeReachability(viewer.scene, entity.id, movementBudget(entity, "dash"));
    api.drawReachable(lastTree, movementBudget(entity, "normal"), "dash");
    api.svg.getBoundingClientRect();
    highlight.push(performance.now() - started);

    lastTarget = lastTree.costByCell.has(`${viewer.scene.benchmarkTarget.x},${viewer.scene.benchmarkTarget.y}`)
      ? viewer.scene.benchmarkTarget
      : farthestReachable(lastTree);
    started = performance.now();
    const summary = summarizePath(viewer.scene, entity.id, "dash", lastTree, lastTarget);
    api.drawPath(summary, entity);
    api.svg.getBoundingClientRect();
    pathPreview.push(performance.now() - started);

    started = performance.now();
    const fullTrees = [];
    for (const playerId of viewer.scene.controllableEntityIds) {
      fullTrees.push(computeReachability(viewer.scene, playerId, Number.POSITIVE_INFINITY));
    }
    precomputeAllPlayers.push(performance.now() - started);
    precomputedPayloadBytes = new TextEncoder().encode(JSON.stringify(fullTrees.map((tree) => ({
      entityId: tree.entityId,
      costs: [...tree.costByCell],
      parents: [...tree.previous]
    })))).length;
  }
  host.remove();
  return {
    map: viewer.mapKey,
    dimensions: `${viewer.scene.grid.width}×${viewer.scene.grid.height}`,
    iterations,
    visibleInput: {
      cells: viewer.scene.grid.width * viewer.scene.grid.height,
      terrainCells: viewer.scene.terrain.length,
      barriers: viewer.scene.barriers.length,
      entities: viewer.scene.entities.length,
      controllablePlayers: viewer.scene.controllableEntityIds.length
    },
    visibleProjectionBytes: new TextEncoder().encode(JSON.stringify(viewer.scene)).length,
    revisionRenderMs: distribution(generation),
    clickHighlightMs: distribution(highlight),
    pathPreviewMs: distribution(pathPreview),
    precomputeAllFullTreesMs: distribution(precomputeAllPlayers),
    precomputeAllFullTreesPayloadBytes: precomputedPayloadBytes,
    selectedReachableCells: lastTree.costByCell.size,
    selectedExpandedStates: lastTree.expandedStates,
    benchmarkTarget: coordinateLabel(lastTarget)
  };
}

async function load() {
  const response = await fetch(`./data/${viewer.mapKey}-scene.json`, { cache: "no-store" });
  if (!response.ok) throw new Error(`无法读取玩家投影：HTTP ${response.status}`);
  viewer.scene = deepFreeze(await response.json());
  viewer.sceneDigest = fingerprint(viewer.scene);
  renderShell();
  window.__TACTICAL_PROTOTYPE__ = {
    ready: true,
    getState: () => structuredClone(relevantState()),
    getSceneDigest: () => ({ before: viewer.sceneDigest, after: fingerprint(viewer.scene) }),
    select: (entityId) => selectToken(entityId),
    setMode,
    preview: (coordinate) => previewTarget(coordinate),
    benchmark
  };
}

window.addEventListener("keydown", (event) => {
  if (!new Set(["ArrowLeft", "ArrowRight"]).has(event.key)) return;
  const tag = document.activeElement?.tagName;
  if (new Set(["INPUT", "TEXTAREA"]).has(tag) || document.activeElement?.isContentEditable) return;
  cycleVariant(event.key === "ArrowLeft" ? -1 : 1);
});

load().catch((error) => {
  app.innerHTML = `<section class="fatal-error"><h1>原型无法启动</h1><pre>${error.message}</pre></section>`;
});
