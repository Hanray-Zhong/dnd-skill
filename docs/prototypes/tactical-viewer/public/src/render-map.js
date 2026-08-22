import { cellKey, coordinateLabel } from "./engine.js";

const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  return element;
}

function center(position, sizeCells, cellSize, margin) {
  return {
    x: margin + (position.x + sizeCells / 2) * cellSize,
    y: margin + (position.y + sizeCells / 2) * cellSize
  };
}

function drawCoordinateLabels(svg, scene, cellSize, margin) {
  for (let x = 0; x < scene.grid.width; x += 1) {
    const label = svgElement("text", {
      x: margin + (x + 0.5) * cellSize,
      y: margin - 10,
      class: "coordinate-label",
      "text-anchor": "middle"
    });
    label.textContent = coordinateLabel({ x, y: -1 }).replace("0", "");
    svg.append(label);
  }
  for (let y = 0; y < scene.grid.height; y += 1) {
    const label = svgElement("text", {
      x: margin - 10,
      y: margin + (y + 0.62) * cellSize,
      class: "coordinate-label",
      "text-anchor": "end"
    });
    label.textContent = String(y + 1);
    svg.append(label);
  }
}

function barrierLine(barrier, cellSize, margin) {
  const vertical = barrier.a.x !== barrier.b.x;
  const x = vertical
    ? margin + Math.max(barrier.a.x, barrier.b.x) * cellSize
    : margin + barrier.a.x * cellSize;
  const y = vertical
    ? margin + barrier.a.y * cellSize
    : margin + Math.max(barrier.a.y, barrier.b.y) * cellSize;
  return svgElement("line", {
    x1: x,
    y1: y,
    x2: vertical ? x : x + cellSize,
    y2: vertical ? y + cellSize : y,
    class: `barrier ${barrier.kind} ${barrier.open ? "open" : "closed"}`,
    "data-barrier-kind": barrier.kind,
    "aria-label": barrier.kind === "door"
      ? `${barrier.label ?? "门"}（${barrier.open ? "开启" : "关闭"}）`
      : "墙体"
  });
}

function renderThreatZones(layer, scene, cellSize, margin, showThreatZones) {
  if (!showThreatZones) return;
  for (const enemy of scene.entities.filter((entity) => entity.kind === "enemy" && entity.reachFeet)) {
    const reachCells = enemy.reachFeet / scene.grid.feetPerCell;
    const size = enemy.sizeCells ?? 1;
    layer.append(svgElement("rect", {
      x: margin + (enemy.position.x - reachCells) * cellSize,
      y: margin + (enemy.position.y - reachCells) * cellSize,
      width: (size + reachCells * 2) * cellSize,
      height: (size + reachCells * 2) * cellSize,
      rx: cellSize * 0.12,
      class: "threat-zone",
      "aria-label": `${enemy.label} 的明显触及范围`
    }));
  }
}

function tokenShape(entity, cellSize, margin) {
  const size = entity.sizeCells ?? 1;
  const tokenCenter = center(entity.position, size, cellSize, margin);
  const group = svgElement("g", {
    class: `token ${entity.kind} ${entity.selectable ? "selectable" : ""}`,
    "data-entity-id": entity.id,
    "data-coordinate": coordinateLabel(entity.position),
    role: entity.selectable ? "button" : "img",
    tabindex: entity.selectable ? 0 : -1,
    "aria-label": `${entity.label}，${coordinateLabel(entity.position)}${entity.selectable ? "，点击查看移动范围" : ""}`
  });
  const inset = cellSize * 0.11;
  group.append(svgElement("rect", {
    x: margin + entity.position.x * cellSize + inset,
    y: margin + entity.position.y * cellSize + inset,
    width: size * cellSize - inset * 2,
    height: size * cellSize - inset * 2,
    rx: Math.min(cellSize * 0.3, 14),
    class: "token-body"
  }));
  const initials = svgElement("text", {
    x: tokenCenter.x,
    y: tokenCenter.y + 5,
    "text-anchor": "middle",
    class: "token-initials"
  });
  initials.textContent = entity.label.slice(0, 2);
  group.append(initials);
  const name = svgElement("text", {
    x: tokenCenter.x,
    y: margin + (entity.position.y + size) * cellSize - 5,
    "text-anchor": "middle",
    class: "token-label"
  });
  name.textContent = entity.label;
  group.append(name);
  return group;
}

export function renderMap(container, scene, options = {}) {
  const cellSize = scene.grid.width >= 40 ? 28 : 56;
  const margin = scene.grid.width >= 40 ? 36 : 42;
  const width = margin * 2 + scene.grid.width * cellSize;
  const height = margin * 2 + scene.grid.height * cellSize;
  const svg = svgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "tactical-map",
    role: "group",
    "aria-label": `${scene.title}，${scene.grid.width}×${scene.grid.height} 个五尺方格`
  });
  const title = svgElement("title");
  title.textContent = `${scene.title} · 只读玩家知识投影`;
  svg.append(title);

  const baseLayer = svgElement("g", { class: "base-layer" });
  const terrainLayer = svgElement("g", { class: "terrain-layer" });
  const reachLayer = svgElement("g", { class: "reach-layer", "aria-label": "移动可达范围" });
  const threatLayer = svgElement("g", { class: "threat-layer", "aria-label": "明显触及范围" });
  const pathLayer = svgElement("g", { class: "path-layer", "aria-label": "路径预览" });
  const barrierLayer = svgElement("g", { class: "barrier-layer" });
  const tokenLayer = svgElement("g", { class: "token-layer" });

  for (let y = 0; y < scene.grid.height; y += 1) {
    for (let x = 0; x < scene.grid.width; x += 1) {
      const rect = svgElement("rect", {
        x: margin + x * cellSize,
        y: margin + y * cellSize,
        width: cellSize,
        height: cellSize,
        class: "grid-cell",
        "data-cell": coordinateLabel({ x, y }),
        role: "button",
        tabindex: -1,
        "aria-label": `格子 ${coordinateLabel({ x, y })}`
      });
      rect.addEventListener("click", () => options.onCellClick?.({ x, y }));
      baseLayer.append(rect);
    }
  }

  for (const terrain of scene.terrain) {
    terrainLayer.append(svgElement("rect", {
      x: margin + terrain.x * cellSize + 2,
      y: margin + terrain.y * cellSize + 2,
      width: cellSize - 4,
      height: cellSize - 4,
      class: "difficult-terrain",
      "aria-label": `${coordinateLabel(terrain)} 困难地形，移动消耗 ×${terrain.multiplier}`
    }));
  }

  renderThreatZones(threatLayer, scene, cellSize, margin, options.showThreatZones);
  scene.barriers.forEach((barrier) => barrierLayer.append(barrierLine(barrier, cellSize, margin)));
  for (const entity of scene.entities) {
    const token = tokenShape(entity, cellSize, margin);
    if (entity.selectable) {
      const activate = () => options.onEntityClick?.(entity.id);
      token.addEventListener("click", (event) => {
        event.stopPropagation();
        activate();
      });
      token.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    }
    tokenLayer.append(token);
  }

  svg.append(baseLayer, terrainLayer, reachLayer, threatLayer, pathLayer, barrierLayer, tokenLayer);
  drawCoordinateLabels(svg, scene, cellSize, margin);
  container.replaceChildren(svg);

  function drawReachable(tree, normalBudget, mode) {
    reachLayer.replaceChildren();
    for (const [key, cost] of tree.costByCell) {
      const position = key.split(",").map(Number);
      reachLayer.append(svgElement("rect", {
        x: margin + position[0] * cellSize + 3,
        y: margin + position[1] * cellSize + 3,
        width: cellSize - 6,
        height: cellSize - 6,
        rx: Math.min(8, cellSize * 0.12),
        class: mode === "dash" && cost > normalBudget ? "reachable dash-extra" : "reachable normal",
        "data-reachable-cell": coordinateLabel({ x: position[0], y: position[1] }),
        "data-cost": cost
      }));
    }
  }

  function drawPath(summary, entity) {
    pathLayer.replaceChildren();
    if (!summary) return;
    const size = entity.sizeCells ?? 1;
    const points = summary.path.map((position) => {
      const point = center(position, size, cellSize, margin);
      return `${point.x},${point.y}`;
    }).join(" ");
    pathLayer.append(svgElement("polyline", { points, class: "route-line" }));
    for (const position of summary.path) {
      const point = center(position, size, cellSize, margin);
      pathLayer.append(svgElement("circle", {
        cx: point.x,
        cy: point.y,
        r: Math.max(3, cellSize * 0.08),
        class: "route-step"
      }));
    }
    for (const risk of summary.risks) {
      const from = center(risk.from, size, cellSize, margin);
      const to = center(risk.to, size, cellSize, margin);
      pathLayer.append(svgElement("line", {
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        class: "risk-segment"
      }));
    }
  }

  function markSelected(entityId) {
    svg.querySelectorAll(".token").forEach((token) => {
      token.classList.toggle("selected", token.dataset.entityId === entityId);
    });
  }

  function markTarget(target) {
    svg.querySelectorAll(".grid-cell").forEach((gridCell) => {
      gridCell.classList.toggle("target", gridCell.dataset.cell === (target ? coordinateLabel(target) : ""));
    });
  }

  return {
    svg,
    drawReachable,
    drawPath,
    markSelected,
    markTarget,
    cellCount: scene.grid.width * scene.grid.height,
    terrainCount: scene.terrain.length,
    barrierCount: scene.barriers.length,
    entityCount: scene.entities.length
  };
}
