/**
 * Trellis workflow templates
 *
 * These are GENERIC templates for user projects.
 * Do NOT use Trellis project's own .trellis/ directory (which may be customized).
 *
 * Directory structure:
 *   trellis/
 *   ├── scripts/
 *   │   ├── common/           # Shared utilities
 *   │   ├── multi-agent/      # Multi-agent pipeline scripts
 *   │   └── *.sh              # Main scripts
 *   ├── workflow.md           # Workflow guide
 *   ├── worktree.yaml         # Worktree configuration
 *   └── gitignore.txt         # .gitignore content
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function readTemplate(relativePath: string): string {
  return readFileSync(join(__dirname, relativePath), "utf-8");
}

// Common utilities
export const commonPathsScript = readTemplate("scripts/common/paths.sh");
export const commonDeveloperScript = readTemplate(
  "scripts/common/developer.sh",
);
export const commonGitContextScript = readTemplate(
  "scripts/common/git-context.sh",
);
export const commonWorktreeScript = readTemplate(
  "scripts/common/worktree.sh",
);
export const commonTaskQueueScript = readTemplate("scripts/common/task-queue.sh");
export const commonTaskUtilsScript = readTemplate(
  "scripts/common/task-utils.sh",
);
export const commonPhaseScript = readTemplate("scripts/common/phase.sh");
export const commonRegistryScript = readTemplate("scripts/common/registry.sh");

// Multi-agent scripts
export const multiAgentStartScript = readTemplate(
  "scripts/multi-agent/start.sh",
);
export const multiAgentCleanupScript = readTemplate(
  "scripts/multi-agent/cleanup.sh",
);
export const multiAgentStatusScript = readTemplate(
  "scripts/multi-agent/status.sh",
);
export const multiAgentCreatePrScript = readTemplate(
  "scripts/multi-agent/create-pr.sh",
);
export const multiAgentPlanScript = readTemplate(
  "scripts/multi-agent/plan.sh",
);

// Main scripts
export const initDeveloperScript = readTemplate("scripts/init-developer.sh");
export const getDeveloperScript = readTemplate("scripts/get-developer.sh");
export const taskScript = readTemplate("scripts/task.sh");
export const getContextScript = readTemplate("scripts/get-context.sh");
export const addSessionScript = readTemplate("scripts/add-session.sh");
export const createBootstrapScript = readTemplate(
  "scripts/create-bootstrap.sh",
);

// Configuration files
export const workflowMdTemplate = readTemplate("workflow.md");
export const worktreeYamlTemplate = readTemplate("worktree.yaml");
export const gitignoreTemplate = readTemplate("gitignore.txt");

/**
 * Get all script templates as a map of relative path to content
 */
export function getAllScripts(): Map<string, string> {
  const scripts = new Map<string, string>();

  // Common
  scripts.set("common/paths.sh", commonPathsScript);
  scripts.set("common/developer.sh", commonDeveloperScript);
  scripts.set("common/git-context.sh", commonGitContextScript);
  scripts.set("common/worktree.sh", commonWorktreeScript);
  scripts.set("common/task-queue.sh", commonTaskQueueScript);
  scripts.set("common/task-utils.sh", commonTaskUtilsScript);
  scripts.set("common/phase.sh", commonPhaseScript);
  scripts.set("common/registry.sh", commonRegistryScript);

  // Multi-agent
  scripts.set("multi-agent/start.sh", multiAgentStartScript);
  scripts.set("multi-agent/cleanup.sh", multiAgentCleanupScript);
  scripts.set("multi-agent/status.sh", multiAgentStatusScript);
  scripts.set("multi-agent/create-pr.sh", multiAgentCreatePrScript);
  scripts.set("multi-agent/plan.sh", multiAgentPlanScript);

  // Main
  scripts.set("init-developer.sh", initDeveloperScript);
  scripts.set("get-developer.sh", getDeveloperScript);
  scripts.set("task.sh", taskScript);
  scripts.set("get-context.sh", getContextScript);
  scripts.set("add-session.sh", addSessionScript);
  scripts.set("create-bootstrap.sh", createBootstrapScript);

  return scripts;
}
