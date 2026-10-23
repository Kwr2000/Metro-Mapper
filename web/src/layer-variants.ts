import type { Registry } from "./registry";

/** Alternative area scales (e.g. block group / tract) in a group never overlap on the map.
 * Switching scale keeps the same metric families turned on. */
export function switchLayerVariant(registry: Registry, visible: ReadonlySet<string>, group: string, key: string): Set<string> {
  const result = new Set(visible), layers = registry.layers.filter((l) => l.group === group && l.variant);
  const families = new Set(layers.filter((l) => visible.has(l.id)).map((l) => l.variant!.family));
  for (const layer of layers) {
    result.delete(layer.id);
    if (layer.variant!.key === key && families.has(layer.variant!.family)) result.add(layer.id);
  }
  return result;
}

export function normalizeLayerVariants(registry: Registry, visible: ReadonlySet<string>): Set<string> {
  let result = new Set(visible);
  for (const group of registry.groups) {
    const key = registry.layers.find((l) => l.group === group && l.variant && result.has(l.id))?.variant?.key;
    if (key) result = switchLayerVariant(registry, result, group, key);
  }
  return result;
}
