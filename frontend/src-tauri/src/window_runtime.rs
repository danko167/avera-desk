use tauri::{
    AppHandle, LogicalSize, Manager, Size, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};

use crate::diagnostics::append_bootstrap_log;
use crate::window_dimensions::{settings_window_dimensions, startup_window_dimensions};

const MAIN_WINDOW_WIDTH: f64 = 460.0;
const MAIN_WINDOW_COLLAPSED_HEIGHT: f64 = 260.0;
const MAIN_WINDOW_EXPANDED_HEIGHT: f64 = MAIN_WINDOW_COLLAPSED_HEIGHT * 2.7;

fn position_bottom_right(window: &tauri::WebviewWindow, margin_right: u32, margin_bottom: u32) {
    let Ok(Some(monitor)) = window.current_monitor() else {
        return;
    };
    let Ok(win_size) = window.outer_size() else {
        return;
    };

    let scale = monitor.scale_factor();
    let screen = monitor.size();
    let origin = monitor.position();

    let mr = (margin_right as f64 * scale) as i32;
    let mb = (margin_bottom as f64 * scale) as i32;

    let x = origin.x + screen.width as i32 - win_size.width as i32 - mr;
    let y = origin.y + screen.height as i32 - win_size.height as i32 - mb;

    let _ = window.set_position(tauri::PhysicalPosition::new(x, y));
}

fn reveal_window(window: &tauri::WebviewWindow) {
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
}

fn hide_window(window: &tauri::WebviewWindow) {
    let _ = window.hide();
    let _ = window.unminimize();
}

pub fn hide_main_window(window: &tauri::WebviewWindow) {
    hide_window(window);
}

fn hide_settings_window(window: &tauri::WebviewWindow) {
    hide_window(window);
}

fn hide_manual_window(window: &tauri::WebviewWindow) {
    hide_window(window);
}

#[cfg(debug_assertions)]
fn window_webview_url(window_label: &str) -> WebviewUrl {
    let mut url = url::Url::parse("http://localhost:1420").expect("valid dev frontend URL");
    url.query_pairs_mut().append_pair("window", window_label);
    WebviewUrl::External(url)
}

#[cfg(not(debug_assertions))]
fn window_webview_url(_window_label: &str) -> WebviewUrl {
    WebviewUrl::App("index.html".into())
}

pub fn show_main_window_internal(app: &AppHandle) {
    if let Some(startup_window) = app.get_webview_window("startup") {
        if matches!(startup_window.is_visible(), Ok(true)) {
            let _ = startup_window.unminimize();
            let _ = startup_window.set_focus();
            return;
        }
    }

    if let Some(window) = app.get_webview_window("main") {
        position_bottom_right(&window, 10, 60);
        reveal_window(&window);
    }
}

pub fn show_main_window_if_hidden(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if matches!(window.is_visible(), Ok(false)) {
            show_main_window_internal(app);
        }
    }
}

pub fn set_main_window_expanded(app: &AppHandle, expanded: bool) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };

    let target_height = if expanded {
        MAIN_WINDOW_EXPANDED_HEIGHT
    } else {
        MAIN_WINDOW_COLLAPSED_HEIGHT
    };

    let _ = window.set_size(Size::Logical(LogicalSize::new(
        MAIN_WINDOW_WIDTH,
        target_height,
    )));
    position_bottom_right(&window, 10, 60);
}

pub fn complete_startup_setup(app: AppHandle) {
    append_bootstrap_log("command complete_startup_setup invoked");
    if let Some(startup_window) = app.get_webview_window("startup") {
        let _ = startup_window.hide();
        append_bootstrap_log("command complete_startup_setup: requested startup hide");
    }

    if let Some(main_window) = app.get_webview_window("main") {
        position_bottom_right(&main_window, 10, 60);
        reveal_window(&main_window);
        append_bootstrap_log("command complete_startup_setup: main window shown");
    }
}

pub fn open_startup_window(app: AppHandle) -> Result<(), String> {
    if let Some(startup_window) = app.get_webview_window("startup") {
        reveal_window(&startup_window);
        return Ok(());
    }

    Err("Startup window is not available".to_string())
}

pub fn create_startup_window(app: &tauri::App) -> Result<(), tauri::Error> {
    if let Some(existing) = app.get_webview_window("startup") {
        reveal_window(&existing);
        return Ok(());
    }

    let dimensions = startup_window_dimensions(app.handle());

    let mut startup_builder =
        WebviewWindowBuilder::new(app, "startup", window_webview_url("startup"))
            .title("Avera Setup")
            .inner_size(dimensions.width, dimensions.height)
            .min_inner_size(dimensions.min_width, dimensions.min_height)
            .resizable(true)
            .maximizable(false)
            .minimizable(true)
            .initialization_script("window.__AVERA_WINDOW_LABEL = 'startup';")
            .center();

    startup_builder = startup_builder.decorations(false);

    let startup_window = startup_builder.build()?;

    startup_window.on_window_event(move |event| {
        if let WindowEvent::CloseRequested { .. } = event {
            append_bootstrap_log("startup window: close requested");
        }
    });

    reveal_window(&startup_window);
    Ok(())
}

pub fn create_settings_window(app: &AppHandle, activate: bool) -> Result<(), tauri::Error> {
    if let Some(existing) = app.get_webview_window("settings") {
        append_bootstrap_log("create_settings_window: focusing existing settings window");
        if activate {
            reveal_window(&existing);
        }
        return Ok(());
    }

    append_bootstrap_log("create_settings_window: building new settings window");

    let dimensions = settings_window_dimensions(app);

    let mut settings_builder =
        WebviewWindowBuilder::new(app, "settings", window_webview_url("settings"))
            .title("Avera Settings")
            .inner_size(dimensions.width, dimensions.height)
            .min_inner_size(dimensions.min_width, dimensions.min_height)
            .resizable(true)
            .maximizable(false)
            .minimizable(true)
            .visible(false)
            .initialization_script("window.__AVERA_WINDOW_LABEL = 'settings';")
            .center();

    settings_builder = settings_builder.decorations(false);

    append_bootstrap_log("create_settings_window: before build()");

    let settings_window = match settings_builder.build() {
        Ok(window) => window,
        Err(error) => {
            append_bootstrap_log(&format!("create_settings_window: build() failed: {error}"));
            return Err(error);
        }
    };

    append_bootstrap_log("create_settings_window: build() ok");

    let settings_window_for_events = settings_window.clone();
    settings_window.on_window_event(move |event| {
        if let WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            hide_settings_window(&settings_window_for_events);
        }
    });

    if activate {
        reveal_window(&settings_window);
    }

    append_bootstrap_log("create_settings_window: settings window created");

    Ok(())
}

pub fn open_settings_window(app: AppHandle) -> Result<(), String> {
    append_bootstrap_log("command open_settings_window invoked");
    if let Err(error) = create_settings_window(&app, true) {
        append_bootstrap_log(&format!("command open_settings_window: failed: {error}"));
        return Err(error.to_string());
    }

    append_bootstrap_log("command open_settings_window: success");

    Ok(())
}

pub fn create_manual_window(app: &AppHandle, activate: bool) -> Result<(), tauri::Error> {
    if let Some(existing) = app.get_webview_window("manual") {
        append_bootstrap_log("create_manual_window: focusing existing manual window");
        if activate {
            reveal_window(&existing);
        }
        return Ok(());
    }

    append_bootstrap_log("create_manual_window: building new manual window");

    let dimensions = settings_window_dimensions(app);

    let mut manual_builder =
        WebviewWindowBuilder::new(app, "manual", window_webview_url("manual"))
            .title("Avera Guide")
            .inner_size(dimensions.width, dimensions.height)
            .min_inner_size(dimensions.min_width, dimensions.min_height)
            .resizable(true)
            .maximizable(false)
            .minimizable(true)
            .visible(false)
            .initialization_script("window.__AVERA_WINDOW_LABEL = 'manual';")
            .center();

    manual_builder = manual_builder.decorations(false);

    append_bootstrap_log("create_manual_window: before build()");

    let manual_window = match manual_builder.build() {
        Ok(window) => window,
        Err(error) => {
            append_bootstrap_log(&format!("create_manual_window: build() failed: {error}"));
            return Err(error);
        }
    };

    append_bootstrap_log("create_manual_window: build() ok");

    let manual_window_for_events = manual_window.clone();
    manual_window.on_window_event(move |event| {
        if let WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            hide_manual_window(&manual_window_for_events);
        }
    });

    if activate {
        reveal_window(&manual_window);
    }

    append_bootstrap_log("create_manual_window: manual window created");

    Ok(())
}

pub fn open_manual_window(app: AppHandle) -> Result<(), String> {
    if let Err(error) = create_manual_window(&app, true) {
        append_bootstrap_log(&format!("command open_manual_window: failed: {error}"));
        return Err(error.to_string());
    }

    append_bootstrap_log("command open_manual_window: success");

    Ok(())
}
