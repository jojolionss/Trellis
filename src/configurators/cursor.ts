import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { getCursorTemplatePath } from "../templates/extract.js";
import { ensureDir, writeFile } from "../utils/file-writer.js";

/**
 * Files to exclude when copying templates
 */
const EXCLUDE_PATTERNS = [".d.ts", ".d.ts.map", ".js", ".js.map", "__pycache__"];

/**
 * Check if a file should be excluded
 */
function shouldExclude(filename: string): boolean {
  for (const pattern of EXCLUDE_PATTERNS) {
    if (filename.endsWith(pattern) || filename === pattern) {
      return true;
    }
  }
  return false;
}

/**
 * Recursively copy directory, excluding build artifacts
 */
async function copyDirFiltered(src: string, dest: string, skipExisting = false): Promise<void> {
  ensureDir(dest);

  for (const entry of readdirSync(src)) {
    if (shouldExclude(entry)) {
      continue;
    }

    const srcPath = path.join(src, entry);
    const destPath = path.join(dest, entry);
    const stat = statSync(srcPath);

    if (stat.isDirectory()) {
      await copyDirFiltered(srcPath, destPath, skipExisting);
    } else {
      // Skip if file exists and skipExisting is true
      if (skipExisting && existsSync(destPath)) {
        continue;
      }
      const content = readFileSync(srcPath, "utf-8");
      await writeFile(destPath, content);
    }
  }
}

/**
 * Install agents to ~/.cursor/agents/ (global - shared across all projects)
 */
async function installGlobalAgents(globalCursorDir: string, templatePath: string): Promise<void> {
  const agentsTemplatePath = path.join(templatePath, "agents");
  const agentsDestPath = path.join(globalCursorDir, "agents");

  if (!existsSync(agentsTemplatePath)) {
    return;
  }

  // Skip existing to avoid overwriting user customizations
  await copyDirFiltered(agentsTemplatePath, agentsDestPath, true);
}

/**
 * Install hooks to ~/.cursor/hooks/ (global - shared across all projects)
 */
async function installGlobalHooks(globalCursorDir: string, templatePath: string): Promise<void> {
  const hooksTemplatePath = path.join(templatePath, "hooks");
  const hooksDestPath = path.join(globalCursorDir, "hooks");

  if (!existsSync(hooksTemplatePath)) {
    return;
  }

  // Skip existing to avoid overwriting user customizations
  await copyDirFiltered(hooksTemplatePath, hooksDestPath, true);
}

/**
 * Install commands to ~/.cursor/commands/ (global - shared across all projects)
 */
async function installGlobalCommands(globalCursorDir: string, templatePath: string): Promise<void> {
  const commandsTemplatePath = path.join(templatePath, "commands");
  const commandsDestPath = path.join(globalCursorDir, "commands");

  if (!existsSync(commandsTemplatePath)) {
    return;
  }

  // Skip existing to avoid overwriting user customizations
  await copyDirFiltered(commandsTemplatePath, commandsDestPath, true);
}

/**
 * Create project-level hooks.json to enable hooks for this project
 * Uses absolute paths to global hooks
 */
function createProjectHooksJson(projectCursorDir: string, globalCursorDir: string): void {
  const hooksJsonPath = path.join(projectCursorDir, "hooks.json");

  // Use absolute paths to global hooks (forward slashes for cross-platform)
  const globalHooksDir = path.join(globalCursorDir, "hooks").replace(/\\/g, "/");
  
  const hooksConfig = {
    version: 1,
    hooks: {
      sessionStart: [
        { command: `python "${globalHooksDir}/session-start.py"` }
      ],
      subagentStop: [
        {
          matcher: "check",
          command: `python "${globalHooksDir}/ralph-loop.py"`,
          loop_limit: 5
        }
      ]
    }
  };

  writeFileSync(hooksJsonPath, JSON.stringify(hooksConfig, null, 2), "utf-8");
}

/**
 * Install MCP server to ~/.cursor/mcp-servers/ (global, as it's a background process)
 */
async function installGlobalMcpServer(globalCursorDir: string, templatePath: string): Promise<void> {
  const mcpTemplatePath = path.join(templatePath, "mcp-servers", "trellis-context");
  const mcpDestPath = path.join(globalCursorDir, "mcp-servers", "trellis-context");

  if (!existsSync(mcpTemplatePath)) {
    return;
  }

  // Skip if already installed
  if (existsSync(path.join(mcpDestPath, "server.py"))) {
    return;
  }

  ensureDir(mcpDestPath);

  for (const entry of readdirSync(mcpTemplatePath)) {
    const srcPath = path.join(mcpTemplatePath, entry);
    const destPath = path.join(mcpDestPath, entry);

    if (statSync(srcPath).isFile()) {
      const content = readFileSync(srcPath, "utf-8");
      writeFileSync(destPath, content, "utf-8");
    }
  }
}

/**
 * Register MCP server in ~/.cursor/mcp.json (global)
 */
function registerGlobalMcp(globalCursorDir: string): void {
  const mcpJsonPath = path.join(globalCursorDir, "mcp.json");
  let mcpConfig: {
    mcpServers?: Record<
      string,
      { command: string; args?: string[]; env?: Record<string, string> }
    >;
  } = { mcpServers: {} };

  if (existsSync(mcpJsonPath)) {
    try {
      mcpConfig = JSON.parse(readFileSync(mcpJsonPath, "utf-8"));
      if (!mcpConfig.mcpServers) {
        mcpConfig.mcpServers = {};
      }
    } catch {
      mcpConfig = { mcpServers: {} };
    }
  }

  // Add trellis-context if not present
  const servers = mcpConfig.mcpServers!;
  if (!servers["trellis-context"]) {
    const serverPath = path.join(globalCursorDir, "mcp-servers", "trellis-context", "server.py");
    servers["trellis-context"] = {
      command: "python",
      args: [serverPath.replace(/\\/g, "/")],
    };

    writeFileSync(mcpJsonPath, JSON.stringify(mcpConfig, null, 2), "utf-8");
  }
}

/**
 * Configure Cursor - Global installation with project-level activation
 *
 * Global components (installed to ~/.cursor/, first time only):
 * - agents/ - Subagent definitions (implement, check, debug, research, plan)
 * - hooks/ - Hook scripts (session-start.py, ralph-loop.py)
 * - commands/ - Slash commands (trellis-start, trellis-finish-work, etc.)
 * - mcp-servers/trellis-context/ - MCP server for context injection
 * - mcp.json - MCP server registration
 *
 * Project components (installed to .cursor/):
 * - hooks.json - Hook configuration (enables hooks for this project)
 *
 * Why global installation:
 * - Agents/commands/hooks are the same for all projects
 * - Avoids duplication across projects
 * - Still works on project-specific .trellis/ data
 * - hooks.json is project-level to enable/disable per project
 */
export async function configureCursor(cwd: string): Promise<void> {
  const userHome = homedir();
  const globalCursorDir = path.join(userHome, ".cursor");
  const projectCursorDir = path.join(cwd, ".cursor");
  const templatePath = getCursorTemplatePath();

  // Ensure directories exist
  ensureDir(globalCursorDir);
  ensureDir(projectCursorDir);

  // === Global installation (first time, skip if exists) ===

  // 1. Install agents globally
  await installGlobalAgents(globalCursorDir, templatePath);

  // 2. Install hooks globally
  await installGlobalHooks(globalCursorDir, templatePath);

  // 3. Install commands globally
  await installGlobalCommands(globalCursorDir, templatePath);

  // 4. Install MCP server globally
  await installGlobalMcpServer(globalCursorDir, templatePath);

  // 5. Register MCP in global mcp.json
  registerGlobalMcp(globalCursorDir);

  // === Project-level activation ===

  // 6. Create project hooks.json to enable hooks for this project
  createProjectHooksJson(projectCursorDir, globalCursorDir);
}
