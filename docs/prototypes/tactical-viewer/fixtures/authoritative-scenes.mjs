// THROWAWAY：DM 权威夹具。run.sh 只发布 public/，本文件绝不能进入玩家包。

const cell = (x, y, multiplier = 2) => ({ x, y, multiplier, knowledge: "public" });

function verticalBarrier(boundaryX, yStart, yEnd, doorRows = new Map()) {
  const barriers = [];
  for (let y = yStart; y < yEnd; y += 1) {
    const door = doorRows.get(y);
    barriers.push({
      id: `v-${boundaryX}-${y}`,
      a: { x: boundaryX - 1, y },
      b: { x: boundaryX, y },
      kind: door ? "door" : "wall",
      open: door?.open ?? false,
      label: door?.label,
      knowledge: "public"
    });
  }
  return barriers;
}

function horizontalBarrier(boundaryY, xStart, xEnd, doorColumns = new Map()) {
  const barriers = [];
  for (let x = xStart; x < xEnd; x += 1) {
    const door = doorColumns.get(x);
    barriers.push({
      id: `h-${x}-${boundaryY}`,
      a: { x, y: boundaryY - 1 },
      b: { x, y: boundaryY },
      kind: door ? "door" : "wall",
      open: door?.open ?? false,
      label: door?.label,
      knowledge: "public"
    });
  }
  return barriers;
}

export const smallAuthorityScene = {
  id: "crypt-crossing",
  title: "灰烬墓室交叉口",
  authorityRevision: "map-r17",
  projectionRevision: "player-aria-r17",
  audienceId: "player:aria",
  grid: {
    width: 14,
    height: 10,
    feetPerCell: 5,
    coordinateStyle: "letters-numbers",
    diagonalRule: "every-square-5",
    preventCornerCutting: true
  },
  terrain: [
    cell(3, 4), cell(4, 4), cell(5, 4),
    cell(4, 5), cell(5, 5), cell(4, 6), cell(5, 6),
    cell(9, 7), cell(10, 7), cell(11, 7)
  ],
  barriers: [
    ...verticalBarrier(7, 0, 9, new Map([[5, { open: true, label: "敞开的橡木门" }]])),
    ...horizontalBarrier(3, 1, 6, new Map([[3, { open: false, label: "关闭的铁门" }]])),
    {
      id: "gm-secret-passage-north",
      a: { x: 11, y: 2 },
      b: { x: 11, y: 3 },
      kind: "secret-door",
      open: false,
      knowledge: "hidden",
      publicWhenUnknown: "wall",
      gmNote: "尚未发现的暗门"
    }
  ],
  entities: [
    {
      id: "pc-aria",
      label: "艾拉",
      kind: "player",
      position: { x: 2, y: 6 },
      sizeCells: 1,
      blocksMovement: true,
      movement: { speedFeet: 30, usedFeet: 5 },
      conditions: ["专注"],
      knowledge: { audiences: ["player:aria"], relation: "self" }
    },
    {
      id: "ally-borin",
      label: "博林",
      kind: "ally",
      position: { x: 3, y: 6 },
      sizeCells: 1,
      blocksMovement: true,
      conditions: ["正常"],
      knowledge: { audiences: ["player:aria"], relation: "ally" }
    },
    {
      id: "enemy-goblin-a",
      label: "哥布林 A",
      kind: "enemy",
      position: { x: 9, y: 5 },
      sizeCells: 1,
      reachFeet: 5,
      blocksMovement: true,
      conditions: ["可见"],
      knowledge: { audiences: ["player:aria"], relation: "hostile" }
    },
    {
      id: "enemy-ogre-a",
      label: "食人魔 A",
      kind: "enemy",
      position: { x: 10, y: 1 },
      sizeCells: 2,
      reachFeet: 5,
      blocksMovement: true,
      conditions: ["可见"],
      knowledge: { audiences: ["player:aria"], relation: "hostile" }
    },
    {
      id: "gm-lurker-f7",
      label: "潜伏者",
      kind: "enemy",
      position: { x: 5, y: 6 },
      sizeCells: 1,
      reachFeet: 5,
      blocksMovement: true,
      conditions: ["隐藏"],
      knowledge: { audiences: [], relation: "hostile" },
      gmNote: "此占地若进入玩家算法会改变可达范围"
    }
  ],
  privateFeatures: [
    { id: "gm-trap-e5", kind: "trap", position: { x: 4, y: 4 }, label: "落石触发板" }
  ],
  controllableByAudience: { "player:aria": ["pc-aria"] },
  fallbackTarget: { x: 11, y: 6 },
  benchmarkTarget: { x: 11, y: 6 }
};

function buildLargeAuthorityScene() {
  const terrain = [];
  for (let y = 0; y < 50; y += 1) {
    for (let x = 0; x < 50; x += 1) {
      if ((x * 17 + y * 31) % 47 < 4 && !(x < 12 && y > 39)) {
        terrain.push(cell(x, y));
      }
    }
  }

  const barriers = [];
  [10, 20, 30, 40].forEach((boundary, index) => {
    barriers.push(...verticalBarrier(
      boundary,
      0,
      50,
      new Map([8, 25, 42].map((row, doorIndex) => [
        row,
        { open: true, label: `纵向通道 ${index + 1}.${doorIndex + 1}` }
      ]))
    ));
  });
  [15, 35].forEach((boundary, index) => {
    barriers.push(...horizontalBarrier(
      boundary,
      0,
      50,
      new Map([5, 15, 25, 35, 45].map((column, doorIndex) => [
        column,
        { open: true, label: `横向通道 ${index + 1}.${doorIndex + 1}` }
      ]))
    ));
  });

  const players = [
    ["pc-large-1", "艾拉", 2, 46],
    ["pc-large-2", "博林", 4, 44],
    ["pc-large-3", "塞拉", 6, 46],
    ["pc-large-4", "德温", 8, 44]
  ].map(([id, label, x, y], index) => ({
    id,
    label,
    kind: "player",
    position: { x, y },
    sizeCells: 1,
    blocksMovement: true,
    movement: { speedFeet: index === 3 ? 35 : 30, usedFeet: index * 5 },
    conditions: index === 1 ? ["中毒"] : ["正常"],
    knowledge: { audiences: ["player:aria"], relation: index === 0 ? "self" : "ally" }
  }));

  const enemies = [
    [14, 43], [18, 40], [24, 30], [27, 27], [33, 18], [37, 12], [44, 7], [46, 41]
  ].map(([x, y], index) => ({
    id: `enemy-large-${index + 1}`,
    label: `可见敌人 ${index + 1}`,
    kind: "enemy",
    position: { x, y },
    sizeCells: index === 4 ? 2 : 1,
    reachFeet: index === 4 ? 10 : 5,
    blocksMovement: true,
    conditions: ["可见"],
    knowledge: { audiences: ["player:aria"], relation: "hostile" }
  }));

  return {
    id: "stress-grid-50",
    title: "50×50 压力地图",
    authorityRevision: "map-stress-r3",
    projectionRevision: "player-aria-stress-r3",
    audienceId: "player:aria",
    grid: {
      width: 50,
      height: 50,
      feetPerCell: 5,
      coordinateStyle: "letters-numbers",
      diagonalRule: "every-square-5",
      preventCornerCutting: true
    },
    terrain,
    barriers,
    entities: [
      ...players,
      ...enemies,
      {
        id: "gm-stress-hidden",
        label: "压力图隐藏敌人",
        kind: "enemy",
        position: { x: 7, y: 43 },
        sizeCells: 1,
        reachFeet: 5,
        blocksMovement: true,
        conditions: ["隐藏"],
        knowledge: { audiences: [], relation: "hostile" }
      }
    ],
    privateFeatures: [
      { id: "gm-stress-trap", kind: "trap", position: { x: 5, y: 42 }, label: "压力图陷阱" }
    ],
    controllableByAudience: { "player:aria": players.map((entity) => entity.id) },
    fallbackTarget: { x: 9, y: 41 },
    benchmarkTarget: { x: 9, y: 41 }
  };
}

export const largeAuthorityScene = buildLargeAuthorityScene();

export function withoutSecrets(scene) {
  return {
    ...scene,
    barriers: scene.barriers.map((barrier) => barrier.knowledge === "hidden"
      ? {
          id: `wall-${barrier.a.x}-${barrier.a.y}-${barrier.b.x}-${barrier.b.y}`,
          a: barrier.a,
          b: barrier.b,
          kind: "wall",
          open: false,
          knowledge: "public"
        }
      : barrier),
    entities: scene.entities.filter((entity) => entity.knowledge.audiences.length > 0),
    privateFeatures: []
  };
}
