use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
};

use serde::Serialize;
use tauri::AppHandle;
#[cfg(not(debug_assertions))]
use tauri::Manager;

#[cfg(not(debug_assertions))]
const STARTUP_LOG_FILENAME: &str = "desktop-startup.log";
const BOOTSTRAP_LOG_FILENAME: &str = "avera-desk-bootstrap.log";
#[cfg(debug_assertions)]
const STARTUP_LOG_FALLBACK_FILENAME: &str = "avera-desk-startup.log";

#[derive(Serialize)]
pub struct StartupDiagnosticsPaths {
    pub bootstrap_log_path: String,
    pub startup_log_path: String,
}

#[cfg(debug_assertions)]
fn bootstrap_log_path() -> PathBuf {
    workspace_debug_log_dir().join(BOOTSTRAP_LOG_FILENAME)
}

#[cfg(not(debug_assertions))]
fn bootstrap_log_path() -> PathBuf {
    std::env::temp_dir().join(BOOTSTRAP_LOG_FILENAME)
}

pub fn bootstrap_log_path_for_diagnostics() -> PathBuf {
    bootstrap_log_path()
}

#[cfg(debug_assertions)]
fn workspace_debug_log_dir() -> PathBuf {
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.ends_with("src-tauri") {
            if let Some(parent) = cwd.parent() {
                return parent.join(".dev-logs");
            }
        }

        if cwd.join("src-tauri").is_dir() {
            return cwd.join(".dev-logs");
        }

        return cwd.join(".dev-logs");
    }

    std::env::temp_dir()
}

fn sanitize_log_message(message: &str) -> String {
    let collapsed = message.replace(['\r', '\n'], " ");

    #[cfg(debug_assertions)]
    {
        collapsed
    }

    #[cfg(not(debug_assertions))]
    {
        collapsed
            .split_whitespace()
            .map(redact_token)
            .collect::<Vec<_>>()
            .join(" ")
    }
}

#[cfg(not(debug_assertions))]
fn redact_token(token: &str) -> String {
    let trimmed = token.trim_matches(|c: char| ",;()[]{}\"'".contains(c));

    if looks_like_secret(trimmed) || looks_like_path(trimmed) {
        return token.replacen(trimmed, "[redacted]", 1);
    }

    token.to_string()
}

#[cfg(not(debug_assertions))]
fn looks_like_secret(token: &str) -> bool {
    let lowered = token.to_ascii_lowercase();

    token.starts_with("sk-")
        || lowered.contains("api_key")
        || lowered.contains("apikey")
        || lowered.contains("token=")
        || lowered.contains("authorization")
        || lowered == "bearer"
}

#[cfg(not(debug_assertions))]
fn looks_like_path(token: &str) -> bool {
    token.contains(":\\")
        || token.starts_with("\\\\")
        || token.starts_with('/')
        || token.contains("/Users/")
        || token.contains("/home/")
        || token.contains("AppData\\")
}

pub fn append_bootstrap_log(message: &str) {
    let path = bootstrap_log_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }

    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let line = sanitize_log_message(message);
        let _ = writeln!(file, "{}", line);
    }
}

pub fn install_bootstrap_panic_hook() {
    let log_path = bootstrap_log_path();
    std::panic::set_hook(Box::new(move |panic_info| {
        if let Some(parent) = log_path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log_path) {
            let line = sanitize_log_message(&format!("panic: {panic_info}"));
            let _ = writeln!(file, "{}", line);
        }
    }));
}

#[cfg(not(debug_assertions))]
fn startup_log_path(app: &AppHandle) -> PathBuf {
    match app.path().app_data_dir() {
        Ok(dir) => {
            let _ = fs::create_dir_all(&dir);
            dir.join(STARTUP_LOG_FILENAME)
        }
        Err(_) => std::env::temp_dir().join("avera-desk-startup.log"),
    }
}

#[cfg(debug_assertions)]
fn startup_log_path(_app: &AppHandle) -> PathBuf {
    workspace_debug_log_dir().join(STARTUP_LOG_FALLBACK_FILENAME)
}

pub fn append_startup_log(app: &AppHandle, message: &str) {
    #[cfg(not(debug_assertions))]
    {
        let path = startup_log_path(app);
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
            let line = sanitize_log_message(message);
            let _ = writeln!(file, "{}", line);
        }
    }

    #[cfg(debug_assertions)]
    {
        let _ = app;
        let _ = message;
    }
}

pub fn startup_log_path_any(app: &AppHandle) -> PathBuf {
    startup_log_path(app)
}
