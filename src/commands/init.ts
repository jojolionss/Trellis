import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import chalk from "chalk";
import figlet from "figlet";
import inquirer from "inquirer";
import { configureClaude } from "../configurators/claude.js";
import { configureCursor } from "../configurators/cursor.js";
// TODO: Re-enable when OpenCode support is stable
// import {
//   configureOpenCode,
//   configureOpenCodeAgents,
// } from "../configurators/opencode.js";
import { createWorkflowStructure } from "../configurators/workflow.js";
import { DIR_NAMES, PATHS } from "../constants/paths.js";
import { VERSION } from "../cli/index.js";
import { agentsMdContent } from "../templates/markdown/index.js";
import {
  setWriteMode,
  writeFile,
  type WriteMode,
} from "../utils/file-writer.js";
import {
  detectProjectType,
  type ProjectType,
} from "../utils/project-detector.js";
import { initializeHashes } from "../utils/template-hash.js";

interface InitOptions {
  cursor?: boolean;
  claude?: boolean;
  // opencode?: boolean;  // TODO: Re-enable when OpenCode support is stable
  yes?: boolean;
  user?: string;
  force?: boolean;
  skipExisting?: boolean;
}

interface InitAnswers {
  tools: string[];
}

export async function init(options: InitOptions): Promise<void> {
  const cwd = process.cwd();

  // Generate ASCII art banner dynamically using FIGlet "Rebel" font
  const banner = figlet.textSync("Trellis", { font: "Rebel" });
  console.log(chalk.cyan(`\n${banner.trimEnd()}`));
  console.log(
    chalk.gray(
      "\n   All-in-one AI framework & toolkit for Claude Code & Cursor\n",
    ),
  );

  // Set write mode based on options
  let writeMode: WriteMode = "ask";
  if (options.force) {
    writeMode = "force";
    console.log(chalk.gray("Mode: Force overwrite existing files\n"));
  } else if (options.skipExisting) {
    writeMode = "skip";
    console.log(chalk.gray("Mode: Skip existing files\n"));
  }
  setWriteMode(writeMode);

  // Detect developer name from git config or options
  let developerName = options.user;
  if (!developerName) {
    // Only detect from git if current directory is a git repo
    const isGitRepo = fs.existsSync(path.join(cwd, ".git"));
    if (isGitRepo) {
      try {
        developerName = execSync("git config user.name", {
          cwd,
          encoding: "utf-8",
        }).trim();
      } catch {
        // Git not available or no user.name configured
      }
    }
  }

  if (developerName) {
    console.log(chalk.blue("👤 Developer:"), chalk.gray(developerName));
  } else if (!options.yes) {
    // Ask for developer name if not detected and not in yes mode
    console.log(
      chalk.gray(
        "\nTrellis supports team collaboration - each developer has their own\n" +
          `workspace directory (${PATHS.WORKSPACE}/{name}/) to track AI sessions.\n` +
          "Tip: Usually this is your git username (git config user.name).\n",
      ),
    );
    developerName = await askInput("Your name: ");
    while (!developerName) {
      console.log(chalk.yellow("Name is required"));
      developerName = await askInput("Your name: ");
    }
    console.log(chalk.blue("👤 Developer:"), chalk.gray(developerName));
  }

  // Detect project type (silent - no output)
  const detectedType = detectProjectType(cwd);

  let tools: string[];
  let projectType: ProjectType = detectedType;

  if (options.yes) {
    // Default: both Cursor and Claude
    tools = ["cursor", "claude"];
    // Treat unknown as fullstack
    if (detectedType === "unknown") {
      projectType = "fullstack";
    }
  } else if (options.cursor || options.claude) {
    // Use flags
    tools = [];
    if (options.cursor) {
      tools.push("cursor");
    }
    if (options.claude) {
      tools.push("claude");
    }
    // TODO: Re-enable when OpenCode support is stable
    // if (options.opencode) {
    //   tools.push("opencode");
    // }
    // Treat unknown as fullstack
    if (detectedType === "unknown") {
      projectType = "fullstack";
    }
  } else {
    // Interactive mode
    const questions: {
      type: string;
      name: string;
      message: string;
      choices?: { name: string; value: string; checked?: boolean }[];
      default?: boolean | string;
      when?: (answers: InitAnswers) => boolean;
    }[] = [
      {
        type: "checkbox",
        name: "tools",
        message: "Select AI tools to configure:",
        choices: [
          { name: "Cursor", value: "cursor", checked: true },
          { name: "Claude Code", value: "claude", checked: true },
          // TODO: Re-enable when OpenCode support is stable
          // { name: "OpenCode", value: "opencode", checked: false },
        ],
      },
    ];

    const answers = await inquirer.prompt<InitAnswers>(questions);
    tools = answers.tools;

    // Treat unknown as fullstack
    if (detectedType === "unknown") {
      projectType = "fullstack";
    }
  }

  // TODO: Re-enable when OpenCode support is stable
  // const enableOpenCodeAgents = tools.includes("opencode");

  if (tools.length === 0) {
    console.log(
      chalk.yellow("No tools selected. At least one tool is required."),
    );
    return;
  }

  // Silent - no "Configuring" output

  // Create workflow structure with project type
  // Multi-agent is enabled by default
  console.log(chalk.blue("📁 Creating workflow structure..."));
  await createWorkflowStructure(cwd, { projectType, multiAgent: true });

  // Write version file for update tracking
  const versionPath = path.join(cwd, DIR_NAMES.WORKFLOW, ".version");
  fs.writeFileSync(versionPath, VERSION);

  // Configure selected tools by copying entire directories (dogfooding)
  if (tools.includes("cursor")) {
    console.log(chalk.blue("📝 Configuring Cursor..."));
    await configureCursor(cwd);
  }

  if (tools.includes("claude")) {
    console.log(
      chalk.blue("📝 Configuring Claude Code (commands, agents, hooks)..."),
    );
    await configureClaude(cwd);
  }

  // TODO: Re-enable when OpenCode support is stable
  // if (tools.includes("opencode")) {
  //   console.log(chalk.blue("📝 Configuring OpenCode..."));
  //   await configureOpenCode(cwd);
  //
  //   if (enableOpenCodeAgents) {
  //     console.log(chalk.blue("🤖 Configuring OpenCode agents..."));
  //     await configureOpenCodeAgents(cwd);
  //   }
  // }

  // Create root files (skip if exists)
  await createRootFiles(cwd);

  // Initialize template hashes for modification tracking
  const hashedCount = initializeHashes(cwd);
  if (hashedCount > 0) {
    console.log(
      chalk.gray(`📋 Tracking ${hashedCount} template files for updates`),
    );
  }

  // Initialize developer identity (silent - no output)
  if (developerName) {
    try {
      const scriptPath = path.join(cwd, PATHS.SCRIPTS, "init-developer.sh");
      execSync(`bash "${scriptPath}" "${developerName}"`, {
        cwd,
        stdio: "pipe", // Silent
      });

      // Create bootstrap feature to guide user through filling guidelines
      const bootstrapScriptPath = path.join(
        cwd,
        PATHS.SCRIPTS,
        "create-bootstrap.sh",
      );
      execSync(`bash "${bootstrapScriptPath}" "${projectType}"`, {
        cwd,
        stdio: "pipe", // Silent
      });
    } catch {
      // Silent failure - user can run init-developer.sh manually
    }
  }

  // Print "What We Solve" section
  printWhatWeSolve();
}

/**
 * Simple readline-based input (no flickering like inquirer)
 */
function askInput(prompt: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function createRootFiles(cwd: string): Promise<void> {
  const agentsPath = path.join(cwd, "AGENTS.md");

  // Write AGENTS.md from template
  const agentsWritten = await writeFile(agentsPath, agentsMdContent);
  if (agentsWritten) {
    console.log(chalk.blue("📄 Created AGENTS.md"));
  }
}

/**
 * Print "What We Solve" section showing Trellis value proposition
 * Styled like a meme/rant to resonate with developer pain points
 */
function printWhatWeSolve(): void {
  console.log(
    chalk.gray("\nSound familiar? ") +
      chalk.bold("You'll never say these again!!\n"),
  );

  // Pain point 1: Bug loop → Thinking Guides + Ralph Loop
  console.log(chalk.gray("✗ ") + '"Fix A → break B → fix B → break A..."');
  console.log(
    chalk.green("  ✓ ") +
      chalk.white("Thinking Guides + Ralph Loop: Think first, verify after"),
  );
  // Pain point 2: Instructions ignored/forgotten → Sub-agents + per-agent spec injection
  console.log(
    chalk.gray("✗ ") +
      '"Wrote CLAUDE.md, AI ignored it. Reminded AI, it forgot 5 turns later."',
  );
  console.log(
    chalk.green("  ✓ ") +
      chalk.white("Spec Injection: Rules enforced per task, not per chat"),
  );
  // Pain point 3: Missing connections → Cross-Layer Guide
  console.log(chalk.gray("✗ ") + '"Code works but nothing connects..."');
  console.log(
    chalk.green("  ✓ ") +
      chalk.white("Cross-Layer Guide: Map data flow before coding"),
  );
  // Pain point 4: Code explosion → Plan Agent
  console.log(chalk.gray("✗ ") + '"Asked for a button, got 9000 lines"');
  console.log(
    chalk.green("  ✓ ") +
      chalk.white("Plan Agent: Rejects and splits oversized tasks"),
  );

  console.log("");
}
