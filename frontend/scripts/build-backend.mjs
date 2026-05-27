import { closeSync, copyFileSync, existsSync, mkdirSync, openSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

const projectRoot = resolve(process.cwd());
const backendDir = resolve(projectRoot, "../backend");
const resourceDir = resolve(projectRoot, "src-tauri", "resources", "backend");
const pyinstallerRoot = resolve(projectRoot, "src-tauri", "target", "pyinstaller");
const distPath = resolve(pyinstallerRoot, "dist");
const workPath = resolve(pyinstallerRoot, "build");
const specPath = resolve(pyinstallerRoot, "spec");
const scriptPath = resolve(backendDir, "main.py");
const legacyWorkspaceBackendExePath = resolve(resourceDir, "avera-backend.exe");
const bundledBackendPath = resolve(resourceDir, "avera-backend.bin");
const stagedBackendExePath = resolve(distPath, "avera-backend.exe");

const pythonCandidates = [
  resolve(backendDir, ".venv", "Scripts", "python.exe"),
  resolve(backendDir, ".venv", "bin", "python"),
];

const selectedPython =
  pythonCandidates.find((candidate) => existsSync(candidate)) ||
  (process.platform === "win32" ? "py" : "python");

function run(command, args, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      cwd: backendDir,
      stdio: "inherit",
      shell: false,
      ...options,
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolveRun();
        return;
      }
      rejectRun(new Error(`${command} ${args.join(" ")} exited with code ${code ?? "unknown"}`));
    });

    child.on("error", (error) => {
      rejectRun(error);
    });
  });
}

function delay(ms) {
  return new Promise((resolveDelay) => {
    setTimeout(resolveDelay, ms);
  });
}

async function ensurePyInstaller() {
  try {
    await run(selectedPython, ["-c", "import PyInstaller"]);
  } catch {
    await run(selectedPython, ["-m", "pip", "install", "pyinstaller"]);
  }
}

async function stopStaleWorkspaceBackend() {
  if (process.platform !== "win32") {
    return;
  }

  const escapedPath = legacyWorkspaceBackendExePath.replace(/'/g, "''");
  await run(
    "powershell",
    [
      "-NoProfile",
      "-Command",
      [
        `$target = '${escapedPath}';`,
        "Get-Process avera-backend -ErrorAction SilentlyContinue |",
        "Where-Object { $_.Path -and [string]::Equals($_.Path, $target, [System.StringComparison]::OrdinalIgnoreCase) } |",
        "Stop-Process -Force -ErrorAction SilentlyContinue;",
        "exit 0",
      ].join(" "),
    ],
    { cwd: projectRoot }
  );
}

async function replaceBundledBackend() {
  const maxAttempts = 12;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      rmSync(bundledBackendPath, { force: true });
      copyFileSync(stagedBackendExePath, bundledBackendPath);
      return;
    } catch (error) {
      if (attempt === maxAttempts) {
        throw error;
      }
      await delay(250 * attempt);
    }
  }
}

async function waitForReadableFile(filePath) {
  const maxAttempts = 20;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const handle = openSync(filePath, "r");
      closeSync(handle);
      return;
    } catch (error) {
      if (attempt === maxAttempts) {
        throw error;
      }
      await delay(300 * attempt);
    }
  }
}

async function buildBackend() {
  mkdirSync(resourceDir, { recursive: true });
  mkdirSync(distPath, { recursive: true });
  mkdirSync(workPath, { recursive: true });
  mkdirSync(specPath, { recursive: true });

  await stopStaleWorkspaceBackend();
  rmSync(legacyWorkspaceBackendExePath, { force: true });
  rmSync(bundledBackendPath, { force: true });
  rmSync(stagedBackendExePath, { force: true });

  const dataSeparator = process.platform === "win32" ? ";" : ":";
  const promptsDir = resolve(backendDir, "app", "prompts");

  await ensurePyInstaller();
  await run(selectedPython, [
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "avera-backend",
    "--distpath",
    distPath,
    "--workpath",
    workPath,
    "--specpath",
    specPath,
    "--paths",
    backendDir,
    "--add-data",
    `${promptsDir}${dataSeparator}app/prompts`,
    "--collect-submodules",
    "uvicorn",
    "--collect-submodules",
    "aiosqlite",
    "--collect-submodules",
    "keyring",
    scriptPath,
  ]);

  await replaceBundledBackend();
  await waitForReadableFile(bundledBackendPath);
}

buildBackend().catch((error) => {
  console.error("[build-backend] failed:", error.message);
  process.exit(1);
});
