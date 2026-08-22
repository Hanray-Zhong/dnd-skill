import assert from "node:assert/strict";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  computeReachability,
  coordinateLabel,
  fingerprint,
  movementBudget,
  summarizePath
} from "../public/src/engine.js";
import {
  largeAuthorityScene,
  smallAuthorityScene,
  withoutSecrets
} from "../fixtures/authoritative-scenes.mjs";
import { projectForAudience } from "./project-state.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicRoot = path.join(root, "public");

async function allFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const fullPath = path.join(directory, entry.name);
    return entry.isDirectory() ? allFiles(fullPath) : [fullPath];
  }));
  return nested.flat();
}

const fullProjection = projectForAudience(smallAuthorityScene, smallAuthorityScene.audienceId);
const noSecretsProjection = projectForAudience(withoutSecrets(smallAuthorityScene), smallAuthorityScene.audienceId);
assert.deepEqual(fullProjection, noSecretsProjection, "秘密内容改变了玩家投影");

const largeProjection = projectForAudience(largeAuthorityScene, largeAuthorityScene.audienceId);
assert.equal(largeProjection.grid.width, 50);
assert.equal(largeProjection.grid.height, 50);
assert.equal(fullProjection.readOnly, true);
assert.equal(fullProjection.grid.feetPerCell, 5);
assert.equal(fullProjection.grid.coordinateStyle, "letters-numbers");

const player = fullProjection.entities.find((entity) => entity.id === "pc-aria");
const beforeDigest = fingerprint(fullProjection);
const normalTree = computeReachability(fullProjection, player.id, movementBudget(player, "normal"));
const dashTree = computeReachability(fullProjection, player.id, movementBudget(player, "dash"));
assert(dashTree.costByCell.size > normalTree.costByCell.size, "疾走范围没有扩大");
assert(!normalTree.costByCell.has("11,6"), "L7 不应在普通移动预算内");
assert(dashTree.costByCell.has("11,6"), "L7 应在疾走预算内");
assert(dashTree.costByCell.has("5,6"), "隐藏敌人的权威占地错误地阻挡了 F7");
assert(!dashTree.costByCell.has("3,6"), "可见盟友占地没有阻挡 D7");
assert(!dashTree.costByCell.has("9,5"), "可见敌人占地没有阻挡 J6");

const summary = summarizePath(fullProjection, player.id, "dash", dashTree, { x: 11, y: 6 });
assert(summary, "未生成 L7 路径");
assert(summary.costFeet >= summary.distanceFeet, "困难地形消耗低于格距");
assert(summary.risks.length > 0, "路径未标出可见敌人的明显借机攻击风险");
assert.equal(summary.costFeet, dashTree.costByCell.get("11,6"), "路径不是树中的最低消耗");
assert.equal(fingerprint(fullProjection), beforeDigest, "预览算法改变了输入状态");

const publicFiles = await allFiles(publicRoot);
const textFiles = publicFiles.filter((filename) => !filename.endsWith(".png"));
const publicText = (await Promise.all(textFiles.map((filename) => readFile(filename, "utf8")))).join("\n");
for (const forbidden of [
  "gm-lurker-f7",
  "潜伏者",
  "gm-trap-e5",
  "落石触发板",
  "gm-secret-passage-north",
  "尚未发现的暗门",
  "gm-stress-hidden",
  "压力图隐藏敌人",
  "gm-stress-trap"
]) {
  assert(!publicText.includes(forbidden), `玩家包泄露秘密标记：${forbidden}`);
}
assert(!publicText.includes("draggable="), "玩家包包含拖拽入口");
assert(!/fetch\([^)]*method\s*:\s*["'](?:POST|PUT|PATCH|DELETE)/i.test(publicText), "玩家包包含网络写请求");

const staticSvg = await readFile(path.join(publicRoot, "artifacts", "static-fallback.svg"), "utf8");
assert(staticSvg.includes("只读静态战术地图"));
assert(staticSvg.includes("最低移动消耗路径"));
assert(!staticSvg.includes("<script"));

const results = {
  passed: true,
  checks: 18,
  projectionIsolation: "秘密实体、陷阱和秘密通道与无秘密基线产生完全相同的玩家投影",
  readOnlyDigest: beforeDigest,
  smallMap: {
    normalBudgetFeet: movementBudget(player, "normal"),
    dashBudgetFeet: movementBudget(player, "dash"),
    normalReachableCells: normalTree.costByCell.size,
    dashReachableCells: dashTree.costByCell.size,
    target: coordinateLabel({ x: 11, y: 6 }),
    pathDistanceFeet: summary.distanceFeet,
    pathCostFeet: summary.costFeet,
    pathRemainingFeet: summary.remainingFeet,
    visibleRiskCount: summary.risks.length
  },
  largeMap: {
    dimensions: "50×50",
    publicEntities: largeProjection.entities.length,
    publicBarriers: largeProjection.barriers.length
  }
};
await writeFile(
  path.join(publicRoot, "artifacts", "verification-results.json"),
  `${JSON.stringify(results, null, 2)}\n`
);
console.log(JSON.stringify(results, null, 2));
