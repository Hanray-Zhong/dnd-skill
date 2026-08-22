import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { largeAuthorityScene, smallAuthorityScene } from "../fixtures/authoritative-scenes.mjs";
import { projectForAudience } from "./project-state.mjs";
import { renderStaticSvg } from "./static-svg.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dataDirectory = path.join(root, "public", "data");
const artifactDirectory = path.join(root, "public", "artifacts");
await mkdir(dataDirectory, { recursive: true });
await mkdir(artifactDirectory, { recursive: true });

const small = projectForAudience(smallAuthorityScene, smallAuthorityScene.audienceId);
const large = projectForAudience(largeAuthorityScene, largeAuthorityScene.audienceId);
await Promise.all([
  writeFile(path.join(dataDirectory, "small-scene.json"), `${JSON.stringify(small, null, 2)}\n`),
  writeFile(path.join(dataDirectory, "large-scene.json"), `${JSON.stringify(large, null, 2)}\n`),
  writeFile(path.join(artifactDirectory, "static-fallback.svg"), renderStaticSvg(small))
]);

console.log(`已生成玩家投影：small=${small.entities.length} entities，large=${large.entities.length} entities`);
