// THROWAWAY：确定性方格寻路内核。输入必须已经完成玩家知识投影。

const DIRECTIONS = [
  { dx: 0, dy: -1, diagonal: false },
  { dx: 1, dy: 0, diagonal: false },
  { dx: 0, dy: 1, diagonal: false },
  { dx: -1, dy: 0, diagonal: false },
  { dx: 1, dy: -1, diagonal: true },
  { dx: 1, dy: 1, diagonal: true },
  { dx: -1, dy: 1, diagonal: true },
  { dx: -1, dy: -1, diagonal: true }
];

export function cellKey(x, y) {
  return `${x},${y}`;
}

export function parseCellKey(key) {
  const [x, y] = key.split(",").map(Number);
  return { x, y };
}

export function columnLabel(index) {
  let value = index + 1;
  let label = "";
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}

export function coordinateLabel(position) {
  return `${columnLabel(position.x)}${position.y + 1}`;
}

export function movementBudget(entity, mode) {
  const speed = entity.movement?.speedFeet ?? 0;
  const used = entity.movement?.usedFeet ?? 0;
  return Math.max(0, speed * (mode === "dash" ? 2 : 1) - used);
}

export function fingerprint(value) {
  const input = JSON.stringify(value);
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.freeze(value);
  Object.values(value).forEach(deepFreeze);
  return value;
}

function edgeKey(a, b) {
  const first = cellKey(a.x, a.y);
  const second = cellKey(b.x, b.y);
  return first < second ? `${first}|${second}` : `${second}|${first}`;
}

function footprint(anchor, sizeCells) {
  const cells = [];
  for (let dy = 0; dy < sizeCells; dy += 1) {
    for (let dx = 0; dx < sizeCells; dx += 1) {
      cells.push({ x: anchor.x + dx, y: anchor.y + dy });
    }
  }
  return cells;
}

function makeContext(scene, mover) {
  const blockedCells = new Set();
  for (const entity of scene.entities) {
    if (entity.id === mover.id || entity.blocksMovement === false) continue;
    for (const occupied of footprint(entity.position, entity.sizeCells ?? 1)) {
      blockedCells.add(cellKey(occupied.x, occupied.y));
    }
  }

  const blockedEdges = new Set(scene.barriers
    .filter((barrier) => barrier.kind === "wall" || !barrier.open)
    .map((barrier) => edgeKey(barrier.a, barrier.b)));
  const terrain = new Map(scene.terrain.map((entry) => [cellKey(entry.x, entry.y), entry.multiplier]));
  return { scene, mover, blockedCells, blockedEdges, terrain };
}

function inBounds(scene, position, sizeCells) {
  return position.x >= 0 && position.y >= 0
    && position.x + sizeCells <= scene.grid.width
    && position.y + sizeCells <= scene.grid.height;
}

function canOccupy(context, anchor) {
  const size = context.mover.sizeCells ?? 1;
  if (!inBounds(context.scene, anchor, size)) return false;
  return footprint(anchor, size)
    .every((position) => !context.blockedCells.has(cellKey(position.x, position.y)));
}

function cardinalSweepClear(context, from, to) {
  const size = context.mover.sizeCells ?? 1;
  for (let dy = 0; dy < size; dy += 1) {
    for (let dx = 0; dx < size; dx += 1) {
      const source = { x: from.x + dx, y: from.y + dy };
      const target = { x: to.x + dx, y: to.y + dy };
      if (context.blockedEdges.has(edgeKey(source, target))) return false;
    }
  }
  return true;
}

function canStep(context, from, to, diagonal) {
  if (!canOccupy(context, to)) return false;
  if (!diagonal) return cardinalSweepClear(context, from, to);
  if (!context.scene.grid.preventCornerCutting) return true;

  const viaX = { x: to.x, y: from.y };
  const viaY = { x: from.x, y: to.y };
  return canOccupy(context, viaX)
    && canOccupy(context, viaY)
    && cardinalSweepClear(context, from, viaX)
    && cardinalSweepClear(context, viaX, to)
    && cardinalSweepClear(context, from, viaY)
    && cardinalSweepClear(context, viaY, to);
}

function stepCost(scene, terrain, destination, diagonal, parity) {
  let base = scene.grid.feetPerCell;
  let nextParity = parity;
  if (diagonal && scene.grid.diagonalRule === "alternating-5-10") {
    base = parity === 0 ? 5 : 10;
    nextParity = parity === 0 ? 1 : 0;
  }
  const multiplier = terrain.get(cellKey(destination.x, destination.y)) ?? 1;
  return { cost: base * multiplier, distance: base, nextParity };
}

class MinHeap {
  constructor() {
    this.items = [];
  }

  push(item) {
    this.items.push(item);
    let index = this.items.length - 1;
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (!this.less(this.items[index], this.items[parent])) break;
      [this.items[index], this.items[parent]] = [this.items[parent], this.items[index]];
      index = parent;
    }
  }

  pop() {
    if (this.items.length === 0) return null;
    const result = this.items[0];
    const last = this.items.pop();
    if (this.items.length > 0) {
      this.items[0] = last;
      let index = 0;
      while (true) {
        const left = index * 2 + 1;
        const right = left + 1;
        let smallest = index;
        if (left < this.items.length && this.less(this.items[left], this.items[smallest])) smallest = left;
        if (right < this.items.length && this.less(this.items[right], this.items[smallest])) smallest = right;
        if (smallest === index) break;
        [this.items[index], this.items[smallest]] = [this.items[smallest], this.items[index]];
        index = smallest;
      }
    }
    return result;
  }

  less(a, b) {
    return a.cost < b.cost
      || (a.cost === b.cost && a.hops < b.hops)
      || (a.cost === b.cost && a.hops === b.hops && a.id < b.id);
  }

  get length() {
    return this.items.length;
  }
}

function stateId(position, parity) {
  return `${position.x},${position.y},${parity}`;
}

export function computeReachability(scene, entityId, budgetFeet = Number.POSITIVE_INFINITY) {
  const mover = scene.entities.find((entity) => entity.id === entityId);
  if (!mover?.movement) throw new Error(`实体 ${entityId} 没有移动数据`);
  const context = makeContext(scene, mover);
  const startParity = scene.grid.diagonalStartParity ?? 0;
  const startId = stateId(mover.position, startParity);
  const distances = new Map([[startId, 0]]);
  const states = new Map([[startId, {
    id: startId,
    x: mover.position.x,
    y: mover.position.y,
    parity: startParity,
    cost: 0,
    distanceFeet: 0,
    hops: 0
  }]]);
  const previous = new Map();
  const bestStateByCell = new Map();
  const queue = new MinHeap();
  queue.push(states.get(startId));
  let expandedStates = 0;

  while (queue.length > 0) {
    const current = queue.pop();
    if (current.cost !== distances.get(current.id) || current.cost > budgetFeet) continue;
    expandedStates += 1;
    const currentCell = cellKey(current.x, current.y);
    const previousBest = bestStateByCell.get(currentCell);
    if (!previousBest || current.cost < previousBest.cost) bestStateByCell.set(currentCell, current);

    for (const direction of DIRECTIONS) {
      const target = { x: current.x + direction.dx, y: current.y + direction.dy };
      if (!canStep(context, current, target, direction.diagonal)) continue;
      const step = stepCost(scene, context.terrain, target, direction.diagonal, current.parity);
      const nextCost = current.cost + step.cost;
      if (nextCost > budgetFeet) continue;
      const nextId = stateId(target, step.nextParity);
      const knownCost = distances.get(nextId);
      if (knownCost !== undefined && knownCost <= nextCost) continue;
      const nextState = {
        id: nextId,
        x: target.x,
        y: target.y,
        parity: step.nextParity,
        cost: nextCost,
        distanceFeet: current.distanceFeet + step.distance,
        hops: current.hops + 1
      };
      distances.set(nextId, nextCost);
      states.set(nextId, nextState);
      previous.set(nextId, current.id);
      queue.push(nextState);
    }
  }

  const costByCell = new Map([...bestStateByCell].map(([key, state]) => [key, state.cost]));
  return {
    entityId,
    budgetFeet,
    startId,
    costByCell,
    bestStateByCell,
    previous,
    states,
    expandedStates
  };
}

export function pathTo(tree, target) {
  const targetState = tree.bestStateByCell.get(cellKey(target.x, target.y));
  if (!targetState) return null;
  const path = [];
  let currentId = targetState.id;
  while (currentId) {
    const state = tree.states.get(currentId);
    path.push({
      x: state.x,
      y: state.y,
      cost: state.cost,
      distanceFeet: state.distanceFeet
    });
    currentId = tree.previous.get(currentId);
  }
  return path.reverse();
}

function adjacentThreatClear(blockedEdges, moverCell, enemyCell) {
  const dx = Math.abs(moverCell.x - enemyCell.x);
  const dy = Math.abs(moverCell.y - enemyCell.y);
  if (dx + dy === 1) return !blockedEdges.has(edgeKey(moverCell, enemyCell));
  if (dx === 1 && dy === 1) {
    const cornerA = { x: moverCell.x, y: enemyCell.y };
    const cornerB = { x: enemyCell.x, y: moverCell.y };
    const routeA = !blockedEdges.has(edgeKey(moverCell, cornerA))
      && !blockedEdges.has(edgeKey(cornerA, enemyCell));
    const routeB = !blockedEdges.has(edgeKey(moverCell, cornerB))
      && !blockedEdges.has(edgeKey(cornerB, enemyCell));
    return routeA || routeB;
  }
  return true;
}

function threatenedAt(scene, blockedEdges, mover, anchor, enemy) {
  for (const moverCell of footprint(anchor, mover.sizeCells ?? 1)) {
    for (const enemyCell of footprint(enemy.position, enemy.sizeCells ?? 1)) {
      const cellsAway = Math.max(
        Math.abs(moverCell.x - enemyCell.x),
        Math.abs(moverCell.y - enemyCell.y)
      );
      if (cellsAway * scene.grid.feetPerCell > (enemy.reachFeet ?? 5)) continue;
      if (cellsAway <= 1 && !adjacentThreatClear(blockedEdges, moverCell, enemyCell)) continue;
      return true;
    }
  }
  return false;
}

export function analyzeOpportunityRisks(scene, entityId, path) {
  if (!path || path.length < 2) return [];
  const mover = scene.entities.find((entity) => entity.id === entityId);
  const enemies = scene.entities.filter((entity) => entity.kind === "enemy" && entity.reachFeet);
  const blockedEdges = new Set(scene.barriers
    .filter((barrier) => barrier.kind === "wall" || !barrier.open)
    .map((barrier) => edgeKey(barrier.a, barrier.b)));
  const events = [];
  for (let index = 1; index < path.length; index += 1) {
    const from = path[index - 1];
    const to = path[index];
    for (const enemy of enemies) {
      if (threatenedAt(scene, blockedEdges, mover, from, enemy)
        && !threatenedAt(scene, blockedEdges, mover, to, enemy)) {
        events.push({
          enemyId: enemy.id,
          enemyLabel: enemy.label,
          from: { x: from.x, y: from.y },
          to: { x: to.x, y: to.y },
          message: `离开 ${enemy.label} 的 ${enemy.reachFeet} 尺触及范围`
        });
      }
    }
  }
  return events;
}

export function summarizePath(scene, entityId, mode, tree, target) {
  const entity = scene.entities.find((candidate) => candidate.id === entityId);
  const path = pathTo(tree, target);
  if (!path) return null;
  const last = path.at(-1);
  const budgetFeet = movementBudget(entity, mode);
  return {
    path,
    target: coordinateLabel(target),
    distanceFeet: last.distanceFeet,
    costFeet: last.cost,
    remainingFeet: budgetFeet - last.cost,
    risks: analyzeOpportunityRisks(scene, entityId, path)
  };
}
