use std::{
    process::{Child, Command, Stdio},
    sync::Mutex,
};

#[cfg(all(not(debug_assertions), target_os = "windows"))]
use std::os::windows::process::CommandExt;
#[cfg(not(debug_assertions))]
use std::time::Duration;

#[cfg(not(debug_assertions))]
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager};

use crate::diagnostics::append_bootstrap_log;
#[cfg(not(debug_assertions))]
use crate::diagnostics::append_startup_log;

#[cfg(not(debug_assertions))]
const BUNDLED_BACKEND_NAME: &str = "backend/avera-backend.bin";
#[cfg(not(debug_assertions))]
const BACKEND_HEALTHCHECK_URL: &str = "http://127.0.0.1:8000/health";
#[cfg(not(debug_assertions))]
const BACKEND_STARTUP_RETRIES: usize = 40;
#[cfg(not(debug_assertions))]
const BACKEND_STARTUP_DELAY_MS: u64 = 250;

#[cfg(all(not(debug_assertions), target_os = "windows"))]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub struct BackendProcess(pub Mutex<Option<Child>>);

pub fn manage_backend_state(app: &tauri::App) {
    app.manage(BackendProcess(Mutex::new(None)));
    append_bootstrap_log("backend state managed");
}

#[cfg(not(debug_assertions))]
fn backend_binary_path(app: &AppHandle) -> Result<std::path::PathBuf, Box<dyn std::error::Error>> {
    let mut candidates: Vec<std::path::PathBuf> = Vec::new();

    if let Ok(path) = app.path().resolve(BUNDLED_BACKEND_NAME, BaseDirectory::Resource) {
        candidates.push(path);
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join(BUNDLED_BACKEND_NAME));
    }

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("resources").join(BUNDLED_BACKEND_NAME));
            candidates.push(exe_dir.join(BUNDLED_BACKEND_NAME));
        }
    }

    for candidate in candidates {
        append_bootstrap_log(&format!("checking backend candidate: {}", candidate.display()));
        if candidate.is_file() {
            return Ok(candidate);
        }
    }

    Err("Bundled backend executable not found in expected resource locations".into())
}

#[cfg(not(debug_assertions))]
fn runtime_backend_path(app: &AppHandle) -> Result<std::path::PathBuf, Box<dyn std::error::Error>> {
    let runtime_file_name = format!("avera-backend-{}.exe", std::process::id());
    let path = backend_data_dir(app)?.join(runtime_file_name);
    Ok(path)
}

#[cfg(not(debug_assertions))]
fn materialize_runtime_backend(app: &AppHandle, bundled_backend_path: &std::path::Path) -> Result<std::path::PathBuf, Box<dyn std::error::Error>> {
    let runtime_path = runtime_backend_path(app)?;
    std::fs::copy(bundled_backend_path, &runtime_path)?;
    Ok(runtime_path)
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn stop_stale_packaged_backends(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let backend_dir = backend_data_dir(app)?;
    let escaped_dir = backend_dir.display().to_string().replace('"', "``\"");

    let script = format!(
        "$targetDir = \"{}\"; \
         Get-Process | \
         Where-Object {{ $_.Path -and $_.Path.StartsWith($targetDir, [System.StringComparison]::OrdinalIgnoreCase) -and $_.ProcessName -like 'avera-backend*' }} | \
         Stop-Process -Force -ErrorAction SilentlyContinue; \
         exit 0",
        escaped_dir,
    );

    let status = Command::new("powershell")
        .args(["-NoProfile", "-Command", &script])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;

    if !status.success() {
        return Err("failed to stop stale packaged backend processes".into());
    }

    Ok(())
}

#[cfg(not(debug_assertions))]
fn backend_data_dir(app: &AppHandle) -> Result<std::path::PathBuf, Box<dyn std::error::Error>> {
    let path = app.path().app_data_dir()?.join("backend");
    std::fs::create_dir_all(&path)?;
    Ok(path)
}

#[cfg(not(debug_assertions))]
fn wait_for_backend() -> Result<(), Box<dyn std::error::Error>> {
    append_bootstrap_log("waiting for backend healthcheck");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(400))
        .build()?;

    for _ in 0..BACKEND_STARTUP_RETRIES {
        match client.get(BACKEND_HEALTHCHECK_URL).send() {
            Ok(response) if response.status().is_success() => {
                append_bootstrap_log("backend healthcheck succeeded");
                return Ok(());
            }
            _ => std::thread::sleep(Duration::from_millis(BACKEND_STARTUP_DELAY_MS)),
        }
    }

    append_bootstrap_log("backend healthcheck timed out");
    Err("Timed out waiting for packaged backend to start".into())
}

#[cfg(not(debug_assertions))]
pub fn start_packaged_backend(app: &AppHandle) -> Result<Child, Box<dyn std::error::Error>> {
    append_bootstrap_log("resolving backend binary path");
    let backend_path = backend_binary_path(app).map_err(|error| {
        append_bootstrap_log(&format!("backend path resolve failed: {error}"));
        error
    })?;
    append_bootstrap_log(&format!("backend binary path resolved: {}", backend_path.display()));

    let runtime_backend_path = materialize_runtime_backend(app, &backend_path).map_err(|error| {
        append_bootstrap_log(&format!("runtime backend materialization failed: {error}"));
        error
    })?;
    append_bootstrap_log(&format!("runtime backend path: {}", runtime_backend_path.display()));

    let data_dir = backend_data_dir(app).map_err(|error| {
        append_bootstrap_log(&format!("backend data dir failed: {error}"));
        error
    })?;
    append_bootstrap_log(&format!("backend data dir resolved: {}", data_dir.display()));

    #[cfg(target_os = "windows")]
    {
        append_bootstrap_log("stopping stale packaged backends before spawn");
        if let Err(error) = stop_stale_packaged_backends(app) {
            append_bootstrap_log(&format!("stale backend cleanup failed: {error}"));
        }
    }

    append_startup_log(app, &format!("backend path: {}", runtime_backend_path.display()));
    append_startup_log(app, &format!("backend data dir: {}", data_dir.display()));

    let mut command = Command::new(runtime_backend_path);
    command
        .env("AVERA_DESK_RUNTIME", "packaged")
        .env("AVERA_DESK_DATA_DIR", &data_dir)
        .env("KEYRING_SERVICE", "avera_desk")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    append_bootstrap_log("spawning backend process");
    let child = command.spawn().map_err(|error| {
        append_bootstrap_log(&format!("backend spawn failed: {error}"));
        Box::new(error) as Box<dyn std::error::Error>
    })?;
    append_startup_log(app, "backend process spawned");
    append_bootstrap_log("backend process spawned");
    wait_for_backend()?;
    append_startup_log(app, "backend healthcheck succeeded");
    Ok(child)
}

#[cfg(not(debug_assertions))]
pub fn store_backend_child(app: &tauri::App, child: Child) -> Result<(), String> {
    let state = app.state::<BackendProcess>();
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Failed to lock backend process state".to_string())?;
    *guard = Some(child);
    append_bootstrap_log("backend child stored in state");
    Ok(())
}

pub fn stop_packaged_backend(app: &AppHandle) {
    #[cfg(not(debug_assertions))]
    append_startup_log(app, "stopping packaged backend");

    let Some(state) = app.try_state::<BackendProcess>() else {
        return;
    };

    let Ok(mut guard) = state.0.lock() else {
        return;
    };

    if let Some(child) = guard.as_mut() {
        #[cfg(target_os = "windows")]
        {
            let child_id = child.id();
            let status = Command::new("taskkill")
                .args(["/PID", &child_id.to_string(), "/T", "/F"])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();

            if let Err(error) = status {
                append_bootstrap_log(&format!("taskkill failed for backend pid {child_id}: {error}"));
                #[cfg(not(debug_assertions))]
                append_startup_log(app, &format!("taskkill failed for backend pid {child_id}: {error}"));
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            let _ = child.kill();
        }

        let _ = child.wait();
    }

    *guard = None;
}
