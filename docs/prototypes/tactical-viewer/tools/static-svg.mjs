import {
  computeReachability,
  coordinateLabel,
  movementBudget,
  summarizePath
} from "../public/src/engine.js";

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function center(position, cellSize, margin, sizeCells = 1) {
  return {
    x: margin + (position.x + sizeCells / 2) * cellSize,
    y: margin + (position.y + sizeCells / 2) * cellSize
  };
}

function barrierGeometry(barrier, cellSize, margin) {
  const vertical = barrier.a.x !== barrier.b.x;
  const x = vertical
    ? margin + Math.max(barrier.a.x, barrier.b.x) * cellSize
    : margin + barrier.a.x * cellSize;
  const y = vertical
    ? margin + barrier.a.y * cellSize
    : margin + Math.max(barrier.a.y, barrier.b.y) * cellSize;
  return {
    x1: x,
    y1: y,
    x2: vertical ? x : x + cellSize,
    y2: vertical ? y + cellSize : y
  };
}

export function renderStaticSvg(scene) {
  const cellSize = 48;
  const margin = 38;
  const panelWidth = 390;
  const mapWidth = margin * 2 + scene.grid.width * cellSize;
  const height = margin * 2 + scene.grid.height * cellSize;
  const width = mapWidth + panelWidth;
  const entity = scene.entities.find((candidate) => candidate.selectable && candidate.movement);
  const normalBudget = movementBudget(entity, "normal");
  const dashBudget = movementBudget(entity, "dash");
  const tree = computeReachability(scene, entity.id, dashBudget);
  const summary = summarizePath(scene, entity.id, "dash", tree, scene.fallbackTarget);
  if (!summary) throw new Error("静态回退目标在疾走预算内不可达");

  const chunks = [];
  chunks.push(`<?xml version="1.0" encoding="UTF-8"?>`);
  chunks.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">`);
  chunks.push(`<title id="title">${escapeXml(scene.title)}的只读静态战术地图</title>`);
  chunks.push(`<desc id="desc">五尺方格，显示玩家棋子、可见敌人、墙门、困难地形、疾走可达范围以及到 ${summary.target} 的示例最低移动消耗路径。</desc>`);
  chunks.push(`<style>
    .bg{fill:#151918}.cell{fill:#252b26;stroke:#4b534b;stroke-width:1}.coord{fill:#b9b09b;font:700 12px system-ui;text-anchor:middle}
    .terrain{fill:#62654a;stroke:#9a9b6e;stroke-dasharray:4 3}.normal{fill:#59d9d244;stroke:#59d9d2}.dash{fill:#efb35b44;stroke:#efb35b;stroke-dasharray:5 3}
    .wall{stroke:#eee6d7;stroke-width:7}.door{stroke:#efb35b;stroke-width:4;stroke-dasharray:9 11}.token{stroke-width:3}.player{fill:#1c736f;stroke:#b6fff9}.ally{fill:#44634a;stroke:#bce8c1}.enemy{fill:#823e38;stroke:#ffc1ba}
    .tokenText{fill:#fff;font:800 11px system-ui;text-anchor:middle;paint-order:stroke;stroke:#111;stroke-width:3}.route{fill:none;stroke:#fff;stroke-width:6;stroke-linecap:round;stroke-linejoin:round}.risk{stroke:#f26d62;stroke-width:10;stroke-dasharray:7 6}
    .panel{fill:#202624}.heading{fill:#f3eee3;font:600 25px Georgia,serif}.label{fill:#efb35b;font:800 11px system-ui;letter-spacing:1px}.body{fill:#ded8c9;font:14px system-ui}.muted{fill:#aaa28f;font:12px system-ui}.code{fill:#c7d7cd;font:12px ui-monospace,monospace}.rule{stroke:#485149}.legend{fill:#ded8c9;font:12px system-ui}
  </style>`);
  chunks.push(`<rect class="bg" width="${width}" height="${height}"/>`);

  for (let y = 0; y < scene.grid.height; y += 1) {
    for (let x = 0; x < scene.grid.width; x += 1) {
      chunks.push(`<rect class="cell" x="${margin + x * cellSize}" y="${margin + y * cellSize}" width="${cellSize}" height="${cellSize}"/>`);
    }
  }
  for (let x = 0; x < scene.grid.width; x += 1) {
    chunks.push(`<text class="coord" x="${margin + (x + 0.5) * cellSize}" y="${margin - 10}">${coordinateLabel({ x, y: -1 }).replace("0", "")}</text>`);
  }
  for (let y = 0; y < scene.grid.height; y += 1) {
    chunks.push(`<text class="coord" x="${margin - 17}" y="${margin + (y + 0.62) * cellSize}">${y + 1}</text>`);
  }
  for (const terrain of scene.terrain) {
    chunks.push(`<rect class="terrain" x="${margin + terrain.x * cellSize + 2}" y="${margin + terrain.y * cellSize + 2}" width="${cellSize - 4}" height="${cellSize - 4}"/>`);
  }
  for (const [key, cost] of tree.costByCell) {
    const [x, y] = key.split(",").map(Number);
    chunks.push(`<rect class="${cost > normalBudget ? "dash" : "normal"}" x="${margin + x * cellSize + 3}" y="${margin + y * cellSize + 3}" width="${cellSize - 6}" height="${cellSize - 6}" rx="6"/>`);
  }
  for (const barrier of scene.barriers) {
    const line = barrierGeometry(barrier, cellSize, margin);
    chunks.push(`<line class="${barrier.kind === "door" && barrier.open ? "door" : "wall"}" x1="${line.x1}" y1="${line.y1}" x2="${line.x2}" y2="${line.y2}"/>`);
  }

  const routePoints = summary.path.map((position) => {
    const point = center(position, cellSize, margin, entity.sizeCells);
    return `${point.x},${point.y}`;
  }).join(" ");
  chunks.push(`<polyline class="route" points="${routePoints}"/>`);
  for (const risk of summary.risks) {
    const from = center(risk.from, cellSize, margin, entity.sizeCells);
    const to = center(risk.to, cellSize, margin, entity.sizeCells);
    chunks.push(`<line class="risk" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"/>`);
  }
  for (const token of scene.entities) {
    const size = token.sizeCells ?? 1;
    const inset = 6;
    const tokenCenter = center(token.position, cellSize, margin, size);
    chunks.push(`<rect class="token ${token.kind}" x="${margin + token.position.x * cellSize + inset}" y="${margin + token.position.y * cellSize + inset}" width="${size * cellSize - inset * 2}" height="${size * cellSize - inset * 2}" rx="11"/>`);
    chunks.push(`<text class="tokenText" x="${tokenCenter.x}" y="${tokenCenter.y + 4}">${escapeXml(token.label)}</text>`);
  }

  const panelX = mapWidth + 24;
  chunks.push(`<rect class="panel" x="${mapWidth}" y="0" width="${panelWidth}" height="${height}"/>`);
  chunks.push(`<text class="label" x="${panelX}" y="44">STATIC SVG · 只读回退</text>`);
  chunks.push(`<text class="heading" x="${panelX}" y="78">${escapeXml(scene.title)}</text>`);
  chunks.push(`<text class="muted" x="${panelX}" y="104">${escapeXml(scene.projectionRevision)} · 玩家知识投影</text>`);
  chunks.push(`<line class="rule" x1="${panelX}" y1="125" x2="${width - 24}" y2="125"/>`);
  chunks.push(`<text class="label" x="${panelX}" y="155">${escapeXml(entity.label)} · 疾走路径预览</text>`);
  chunks.push(`<text class="body" x="${panelX}" y="184">目标 ${summary.target}　格距 ${summary.distanceFeet} 尺</text>`);
  chunks.push(`<text class="body" x="${panelX}" y="209">消耗 ${summary.costFeet} 尺　剩余 ${summary.remainingFeet} 尺</text>`);
  const routeLabels = summary.path.map(coordinateLabel);
  const routeLines = [routeLabels.slice(0, 6), routeLabels.slice(6)];
  routeLines.filter((line) => line.length > 0).forEach((line, index) => {
    chunks.push(`<text class="code" x="${panelX}" y="${239 + index * 21}">${escapeXml(line.join(" → "))}</text>`);
  });
  chunks.push(`<text class="body" x="${panelX}" y="280">明显风险：${summary.risks.length}</text>`);
  summary.risks.forEach((risk, index) => {
    chunks.push(`<text class="muted" x="${panelX}" y="${305 + index * 22}">${escapeXml(risk.message)}</text>`);
  });
  chunks.push(`<line class="rule" x1="${panelX}" y1="350" x2="${width - 24}" y2="350"/>`);
  chunks.push(`<text class="legend" x="${panelX}" y="382">■ 青色：普通移动可达</text>`);
  chunks.push(`<text class="legend" x="${panelX}" y="406">■ 琥珀：仅疾走可达</text>`);
  chunks.push(`<text class="legend" x="${panelX}" y="430">■ 灰绿：困难地形（×2 消耗）</text>`);
  chunks.push(`<text class="legend" x="${panelX}" y="454">━ 白线：最低移动消耗路径</text>`);
  chunks.push(`<text class="legend" x="${panelX}" y="478">━ 红段：离开可见敌人触及范围</text>`);
  chunks.push(`<text class="muted" x="${panelX}" y="520">未知信息不参与本图；此图不提交移动。</text>`);
  chunks.push(`</svg>`);
  return chunks.join("\n");
}
