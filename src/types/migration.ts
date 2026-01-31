/**
 * Migration types for Trellis update command
 *
 * These types support intelligent migration during updates,
 * handling file renames, deletions, and user modification detection.
 */

/**
 * A single migration action (rename, rename-dir, or delete)
 */
export interface MigrationItem {
  /** Type of migration action */
  type: "rename" | "rename-dir" | "delete";
  /** Source path (relative to project root) */
  from: string;
  /** Target path for renames (relative to project root) */
  to?: string;
  /** Human-readable description of the change */
  description?: string;
}

/**
 * Migration manifest for a specific version
 */
export interface MigrationManifest {
  /** Target version this migration upgrades to */
  version: string;
  /** List of migration actions */
  migrations: MigrationItem[];
}

/**
 * Classification of how a migration should be handled
 */
export type MigrationClassification =
  | "auto" // Unmodified by user, can auto-migrate
  | "confirm" // Modified by user, needs confirmation
  | "conflict" // Both old and new files exist
  | "skip"; // Old file doesn't exist, nothing to do

/**
 * Classified migration item with its determined action
 */
export interface ClassifiedMigrationItem extends MigrationItem {
  classification: MigrationClassification;
}

/**
 * Result of classifying all migrations
 */
export interface ClassifiedMigrations {
  /** Unmodified files - safe to auto-migrate */
  auto: MigrationItem[];
  /** User-modified files - need confirmation */
  confirm: MigrationItem[];
  /** Conflict - both old and new exist */
  conflict: MigrationItem[];
  /** Skip - old file doesn't exist */
  skip: MigrationItem[];
}

/**
 * Result of executing migrations
 */
export interface MigrationResult {
  /** Number of files renamed */
  renamed: number;
  /** Number of files deleted */
  deleted: number;
  /** Number of files skipped (user choice or no action needed) */
  skipped: number;
  /** Number of conflicts encountered */
  conflicts: number;
}

/**
 * User action choice for migration confirmation
 */
export type MigrationAction =
  | "rename" // Proceed with rename anyway
  | "backup-rename" // Backup original, then rename
  | "skip" // Skip this migration
  | "view-diff"; // View the diff first

/**
 * Template hashes storage structure
 * Maps relative file paths to their SHA256 hashes
 */
export type TemplateHashes = Record<string, string>;
