import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

const projectRoot = resolve(process.cwd());
const backendDir = resolve(projectRoot, "../backend");

const pythonCandidates = [
  resolve(backendDir, ".venv", "Scripts", "python.exe"),
  resolve(backendDir, ".venv", "bin", "python"),
];

const selectedPython =
  pythonCandidates.find((candidate) => existsSync(candidate)) ||
  (process.platform === "win32" ? "py" : "python");

if (!existsSync(resolve(backendDir, ".venv", "Scripts", "python.exe")) && !existsSync(resolve(backendDir, ".venv", "bin", "python"))) {
  console.warn("[api] backend virtualenv python not found, falling back to system python launcher");
}

console.log(`[api] using python: ${selectedPython}`);

function run(command, args, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
      ...options,
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += String(chunk);
    });

    child.stderr?.on("data", (chunk) => {
      stderr += String(chunk);
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolveRun({ stdout, stderr });
        return;
      }

      rejectRun(new Error(`${command} ${args.join(" ")} exited with code ${code ?? "unknown"}\n${stderr || stdout}`.trim()));
    });

    child.on("error", (error) => {
      rejectRun(error);
    });
  });
}

async function ensureDevPortAvailable() {
  if (process.platform !== "win32") {
    return;
  }

  const script = [
    "$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1",
    "if ($null -eq $listener) { Write-Output 'FREE'; exit 0 }",
    "$process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue",
    "if ($null -eq $process) { Write-Output 'OCCUPIED unknown'; exit 0 }",
    "$path = $process.Path",
    "$name = $process.ProcessName",
    "$isAvera = ($name -like 'avera-backend*') -or ($path -like '*AveraDesk*') -or ($path -like '*com.avera.desk*')",
    "if ($isAvera) { Stop-Process -Id $process.Id -Force -ErrorAction Stop; Write-Output ('STOPPED ' + $process.Id + ' ' + $name + ' ' + $path); exit 0 }",
    "Write-Output ('OCCUPIED ' + $process.Id + ' ' + $name + ' ' + $path)",
  ].join('; ');

  const { stdout } = await run("powershell", ["-NoProfile", "-Command", script], {
    cwd: projectRoot,
  });

  const result = stdout.trim();
  if (result.startsWith("STOPPED ")) {
    console.log(`[api] cleared stale backend on port 8000: ${result.slice("STOPPED ".length)}`);
    return;
  }

  if (result.startsWith("OCCUPIED ")) {
    throw new Error(`Port 8000 is already in use by another process: ${result.slice("OCCUPIED ".length)}`);
  }
}

const args = [
  "-m",
  "uvicorn",
  "main:app",
  "--app-dir",
  backendDir,
  "--reload",
  "--reload-dir",
  backendDir,
  "--host",
  "127.0.0.1",
  "--port",
  "8000",
];

void (async () => {
  try {
    await ensureDevPortAvailable();
  } catch (error) {
    console.error("[api] failed to prepare backend port:", error instanceof Error ? error.message : String(error));
    process.exit(1);
  }

  const child = spawn(selectedPython, args, {
    stdio: "inherit",
    shell: false,
    env: {
      ...process.env,
      KEYRING_SERVICE: process.env.KEYRING_SERVICE || "avera_desk_dev",
    },
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });

  child.on("error", (err) => {
    console.error("[api] failed to launch backend:", err.message);
    process.exit(1);
  });
})();
