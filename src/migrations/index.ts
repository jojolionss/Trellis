/**
 * Migration manifests for Trellis versions
 *
 * Each version's migrations are stored in separate JSON files under manifests/
 * Format: manifests/{version}.json (e.g., manifests/0.1.9.json)
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { MigrationItem, MigrationManifest } from "../types/migration.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MANIFESTS_DIR = path.join(__dirname, "manifests");

/**
 * Cache for loaded manifests
 */
let manifestCache: Record<string, MigrationManifest> | null = null;

/**
 * Load all migration manifests from JSON files
 */
function loadManifests(): Record<string, MigrationManifest> {
  if (manifestCache) {
    return manifestCache;
  }

  const manifests: Record<string, MigrationManifest> = {};

  // Check if manifests directory exists
  if (!fs.existsSync(MANIFESTS_DIR)) {
    manifestCache = manifests;
    return manifests;
  }

  // Load all JSON files from manifests directory
  const files = fs.readdirSync(MANIFESTS_DIR).filter((f) => f.endsWith(".json"));

  for (const file of files) {
    try {
      const filePath = path.join(MANIFESTS_DIR, file);
      const content = fs.readFileSync(filePath, "utf-8");
      const manifest = JSON.parse(content) as MigrationManifest;

      // Use version from manifest as key
      if (manifest.version) {
        manifests[manifest.version] = manifest;
      }
    } catch {
      // Skip invalid manifest files
      console.warn(`Warning: Failed to load migration manifest ${file}`);
    }
  }

  manifestCache = manifests;
  return manifests;
}

/**
 * Compare two semver versions
 * Returns: -1 if a < b, 0 if a == b, 1 if a > b
 */
function compareVersions(a: string, b: string): number {
  const parseVersion = (v: string): number[] =>
    v.split(".").map((n) => parseInt(n, 10) || 0);

  const aParts = parseVersion(a);
  const bParts = parseVersion(b);
  const maxLen = Math.max(aParts.length, bParts.length);

  for (let i = 0; i < maxLen; i++) {
    const aVal = aParts[i] ?? 0;
    const bVal = bParts[i] ?? 0;
    if (aVal < bVal) return -1;
    if (aVal > bVal) return 1;
  }
  return 0;
}

/**
 * Get all migrations needed to upgrade from one version to another
 *
 * @param fromVersion - Current installed version
 * @param toVersion - Target version to upgrade to
 * @returns Array of migration items to apply, in version order
 */
export function getMigrationsForVersion(
  fromVersion: string,
  toVersion: string
): MigrationItem[] {
  const manifests = loadManifests();

  // Get all versions that have migrations
  const versions = Object.keys(manifests).sort(compareVersions);

  // Filter to versions > fromVersion and <= toVersion
  const applicableVersions = versions.filter((v) => {
    const afterFrom = compareVersions(v, fromVersion) > 0;
    const atOrBeforeTo = compareVersions(v, toVersion) <= 0;
    return afterFrom && atOrBeforeTo;
  });

  // Collect all migrations from applicable versions
  const allMigrations: MigrationItem[] = [];
  for (const version of applicableVersions) {
    const manifest = manifests[version];
    if (manifest) {
      allMigrations.push(...manifest.migrations);
    }
  }

  return allMigrations;
}

/**
 * Check if there are any pending migrations between versions
 */
export function hasPendingMigrations(
  fromVersion: string,
  toVersion: string
): boolean {
  return getMigrationsForVersion(fromVersion, toVersion).length > 0;
}

/**
 * Get human-readable summary of pending migrations
 */
export function getMigrationSummary(
  fromVersion: string,
  toVersion: string
): { renames: number; deletes: number } {
  const migrations = getMigrationsForVersion(fromVersion, toVersion);
  return {
    renames: migrations.filter((m) => m.type === "rename").length,
    deletes: migrations.filter((m) => m.type === "delete").length,
  };
}

/**
 * Get all registered migration versions
 */
export function getAllMigrationVersions(): string[] {
  const manifests = loadManifests();
  return Object.keys(manifests).sort(compareVersions);
}

/**
 * Get ALL migrations from all manifests (regardless of version)
 * Used for detecting orphaned migrations that should have been applied
 */
export function getAllMigrations(): MigrationItem[] {
  const manifests = loadManifests();
  const allMigrations: MigrationItem[] = [];
  for (const manifest of Object.values(manifests)) {
    allMigrations.push(...manifest.migrations);
  }
  return allMigrations;
}

/**
 * Clear the manifest cache (useful for testing)
 */
export function clearManifestCache(): void {
  manifestCache = null;
}
