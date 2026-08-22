const entityFields = [
  "id", "label", "kind", "position", "sizeCells", "reachFeet",
  "blocksMovement", "movement", "conditions"
];

function pick(source, keys) {
  return Object.fromEntries(keys
    .filter((key) => source[key] !== undefined)
    .map((key) => [key, structuredClone(source[key])]));
}

function publicBarrier(barrier) {
  if (barrier.knowledge !== "hidden") {
    return pick(barrier, ["id", "a", "b", "kind", "open", "label"]);
  }
  if (barrier.publicWhenUnknown !== "wall") return null;
  return {
    id: `wall-${barrier.a.x}-${barrier.a.y}-${barrier.b.x}-${barrier.b.y}`,
    a: structuredClone(barrier.a),
    b: structuredClone(barrier.b),
    kind: "wall",
    open: false
  };
}

export function projectForAudience(authorityScene, audienceId) {
  const controllableEntityIds = authorityScene.controllableByAudience[audienceId] ?? [];
  const entities = authorityScene.entities
    .filter((entity) => entity.knowledge.audiences.includes(audienceId))
    .map((entity) => ({
      ...pick(entity, entityFields),
      selectable: controllableEntityIds.includes(entity.id)
    }));

  return {
    schemaVersion: "tactical-view-projection/v0-prototype",
    id: authorityScene.id,
    title: authorityScene.title,
    authorityRevision: authorityScene.authorityRevision,
    projectionRevision: authorityScene.projectionRevision,
    audienceId,
    readOnly: true,
    grid: structuredClone(authorityScene.grid),
    terrain: authorityScene.terrain
      .filter((entry) => entry.knowledge === "public")
      .map((entry) => pick(entry, ["x", "y", "multiplier"])),
    barriers: authorityScene.barriers.map(publicBarrier).filter(Boolean),
    entities,
    controllableEntityIds: [...controllableEntityIds],
    fallbackTarget: structuredClone(authorityScene.fallbackTarget),
    benchmarkTarget: structuredClone(authorityScene.benchmarkTarget)
  };
}
