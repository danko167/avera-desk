use std::fs;

use serde::Deserialize;
use tauri::{AppHandle, Manager};

use crate::diagnostics::append_bootstrap_log;

const WINDOW_DIMENSIONS_CONFIG_FILENAME: &str = "window-dimensions.json";

const STARTUP_WINDOW_WIDTH_FALLBACK: f64 = 480.0;
const STARTUP_WINDOW_HEIGHT_FALLBACK: f64 = 720.0;
const STARTUP_WINDOW_MIN_WIDTH_FALLBACK: f64 = 480.0;
const STARTUP_WINDOW_MIN_HEIGHT_FALLBACK: f64 = 640.0;
const SETTINGS_WINDOW_WIDTH_FALLBACK: f64 = 480.0;
const SETTINGS_WINDOW_HEIGHT_FALLBACK: f64 = 720.0;
const SETTINGS_WINDOW_MIN_WIDTH_FALLBACK: f64 = 480.0;
const SETTINGS_WINDOW_MIN_HEIGHT_FALLBACK: f64 = 640.0;

const EMBEDDED_DIMENSIONS_JSON: &str = include_str!("../window-dimensions.json");

#[derive(Clone, Copy)]
pub struct WindowDimensions {
    pub width: f64,
    pub height: f64,
    pub min_width: f64,
    pub min_height: f64,
}

#[derive(Default, Deserialize)]
#[serde(default)]
struct WindowDimensionsConfigFile {
    startup: WindowDimensionsConfigEntry,
    settings: WindowDimensionsConfigEntry,
}

#[derive(Default, Deserialize)]
#[serde(default)]
struct WindowDimensionsConfigEntry {
    width: Option<f64>,
    height: Option<f64>,
    min_width: Option<f64>,
    min_height: Option<f64>,
}

fn parse_config_f64(value: Option<f64>, default: f64) -> f64 {
    match value {
        Some(parsed) if parsed.is_finite() && parsed > 0.0 => parsed,
        _ => default,
    }
}

fn apply_window_dimension_overrides(
    defaults: WindowDimensions,
    override_values: &WindowDimensionsConfigEntry,
) -> WindowDimensions {
    let width = parse_config_f64(override_values.width, defaults.width);
    let height = parse_config_f64(override_values.height, defaults.height);
    let min_width = parse_config_f64(override_values.min_width, defaults.min_width).min(width);
    let min_height = parse_config_f64(override_values.min_height, defaults.min_height).min(height);

    WindowDimensions {
        width,
        height,
        min_width,
        min_height,
    }
}

fn embedded_window_dimensions_config() -> Option<WindowDimensionsConfigFile> {
    serde_json::from_str::<WindowDimensionsConfigFile>(EMBEDDED_DIMENSIONS_JSON).ok()
}

fn default_startup_window_dimensions() -> WindowDimensions {
    let fallback = WindowDimensions {
        width: STARTUP_WINDOW_WIDTH_FALLBACK,
        height: STARTUP_WINDOW_HEIGHT_FALLBACK,
        min_width: STARTUP_WINDOW_MIN_WIDTH_FALLBACK,
        min_height: STARTUP_WINDOW_MIN_HEIGHT_FALLBACK,
    };

    if let Some(config) = embedded_window_dimensions_config() {
        return apply_window_dimension_overrides(fallback, &config.startup);
    }

    fallback
}

fn default_settings_window_dimensions() -> WindowDimensions {
    let fallback = WindowDimensions {
        width: SETTINGS_WINDOW_WIDTH_FALLBACK,
        height: SETTINGS_WINDOW_HEIGHT_FALLBACK,
        min_width: SETTINGS_WINDOW_MIN_WIDTH_FALLBACK,
        min_height: SETTINGS_WINDOW_MIN_HEIGHT_FALLBACK,
    };

    if let Some(config) = embedded_window_dimensions_config() {
        return apply_window_dimension_overrides(fallback, &config.settings);
    }

    fallback
}

fn window_dimensions_config_candidates(app: &AppHandle) -> Vec<std::path::PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(config_dir) = app.path().app_config_dir() {
        candidates.push(config_dir.join(WINDOW_DIMENSIONS_CONFIG_FILENAME));
    }

    if let Ok(data_dir) = app.path().app_data_dir() {
        candidates.push(data_dir.join(WINDOW_DIMENSIONS_CONFIG_FILENAME));
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join(WINDOW_DIMENSIONS_CONFIG_FILENAME));
    }

    #[cfg(debug_assertions)]
    {
        if let Ok(cwd) = std::env::current_dir() {
            candidates.push(cwd.join(WINDOW_DIMENSIONS_CONFIG_FILENAME));
            candidates.push(cwd.join("src-tauri").join(WINDOW_DIMENSIONS_CONFIG_FILENAME));
        }
    }

    candidates
}

fn load_window_dimensions_config(app: &AppHandle) -> Option<WindowDimensionsConfigFile> {
    for path in window_dimensions_config_candidates(app) {
        if !path.is_file() {
            continue;
        }

        let raw = match fs::read_to_string(&path) {
            Ok(raw) => raw,
            Err(error) => {
                append_bootstrap_log(&format!(
                    "window dimensions config read failed at {}: {error}",
                    path.display()
                ));
                continue;
            }
        };

        match serde_json::from_str::<WindowDimensionsConfigFile>(&raw) {
            Ok(config) => {
                append_bootstrap_log(&format!(
                    "window dimensions config loaded from {}",
                    path.display()
                ));
                return Some(config);
            }
            Err(error) => {
                append_bootstrap_log(&format!(
                    "window dimensions config parse failed at {}: {error}",
                    path.display()
                ));
            }
        }
    }

    None
}

pub fn startup_window_dimensions(app: &AppHandle) -> WindowDimensions {
    let defaults = default_startup_window_dimensions();
    load_window_dimensions_config(app)
        .map(|config| apply_window_dimension_overrides(defaults, &config.startup))
        .unwrap_or(defaults)
}

pub fn settings_window_dimensions(app: &AppHandle) -> WindowDimensions {
    let defaults = default_settings_window_dimensions();
    load_window_dimensions_config(app)
        .map(|config| apply_window_dimension_overrides(defaults, &config.settings))
        .unwrap_or(defaults)
}
