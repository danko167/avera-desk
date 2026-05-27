mod attention;
mod backend_runtime;
mod diagnostics;
mod tray_runtime;
mod triggers;
mod window_runtime;
mod window_dimensions;

use tauri::{
    AppHandle,
    Manager, RunEvent, WindowEvent,
};
use tauri::Emitter;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

use crate::attention::{AttentionBroker, AttentionEvent};
use crate::backend_runtime::{manage_backend_state, stop_packaged_backend};
#[cfg(not(debug_assertions))]
use crate::backend_runtime::{start_packaged_backend, store_backend_child};
use crate::diagnostics::{
    StartupDiagnosticsPaths, append_bootstrap_log, append_startup_log,
    bootstrap_log_path_for_diagnostics, install_bootstrap_panic_hook, startup_log_path_any,
};
use crate::tray_runtime::setup_tray;
use crate::window_runtime::{
    complete_startup_setup as complete_startup_setup_impl,
    create_manual_window,
    create_settings_window,
    create_startup_window,
    open_manual_window as open_manual_window_impl,
    hide_main_window,
    open_settings_window as open_settings_window_impl,
    open_startup_window as open_startup_window_impl,
    set_main_window_expanded as set_main_window_expanded_impl,
    show_main_window_if_hidden,
    show_main_window_internal,
};

#[tauri::command]
fn log_startup_diagnostic(app: AppHandle, message: String) -> StartupDiagnosticsPaths {
    let bootstrap_path = bootstrap_log_path_for_diagnostics();
    let startup_path = startup_log_path_any(&app);
    let line = format!("frontend: {message}");

    append_bootstrap_log(&line);
    append_startup_log(&app, &line);

    StartupDiagnosticsPaths {
        bootstrap_log_path: bootstrap_path.display().to_string(),
        startup_log_path: startup_path.display().to_string(),
    }
}

fn push_to_talk_shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::CONTROL), Code::Space)
}

fn emit_shortcut_event(app: &AppHandle, event_name: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit(event_name, ());
    }
}

fn register_push_to_talk_shortcut(
    app: &AppHandle,
) -> Result<(), tauri_plugin_global_shortcut::Error> {
    let app_handle = app.clone();
    app.global_shortcut()
        .on_shortcut(push_to_talk_shortcut(), move |_app, _shortcut, event| {
            let event_name = match event.state() {
                ShortcutState::Pressed => Some("global-ptt-start"),
                ShortcutState::Released => Some("global-ptt-stop"),
            };

            if let Some(event_name) = event_name {
                emit_shortcut_event(&app_handle, event_name);
            }
        })
}

#[tauri::command]
fn show_main_window(app: AppHandle) {
    show_main_window_internal(&app);
}

#[tauri::command]
fn complete_startup_setup(app: AppHandle) {
    complete_startup_setup_impl(app);
}

#[tauri::command]
fn open_startup_window(app: AppHandle) -> Result<(), String> {
    open_startup_window_impl(app)
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    append_bootstrap_log("command quit_app invoked");
    app.exit(0);
}

#[tauri::command]
fn open_settings_window(app: AppHandle) -> Result<(), String> {
    open_settings_window_impl(app)
}

#[tauri::command]
fn open_manual_window(app: AppHandle) -> Result<(), String> {
    append_bootstrap_log("command open_manual_window invoked");
    open_manual_window_impl(app)
}

#[tauri::command]
fn set_main_window_expanded(app: AppHandle, expanded: bool) {
    set_main_window_expanded_impl(&app, expanded);
}

fn handle_attention_event(app: &tauri::AppHandle, event: AttentionEvent) {
    println!("attention triggered by {}", event.source);
    show_main_window_if_hidden(app);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit("attention-event", &event.source);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    append_bootstrap_log("run() entered");
    install_bootstrap_panic_hook();
    append_bootstrap_log("bootstrap panic hook installed");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_positioner::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            show_main_window,
            complete_startup_setup,
            quit_app,
            open_settings_window,
            open_manual_window,
            open_startup_window,
            set_main_window_expanded,
            log_startup_diagnostic
        ])
        .setup(|app| {
            append_bootstrap_log("setup() entered");
            manage_backend_state(app);

            #[cfg(not(debug_assertions))]
            {
                append_startup_log(app.handle(), "setup start");
                append_bootstrap_log("startup log append attempted");

                let child = match start_packaged_backend(app.handle()) {
                    Ok(child) => child,
                    Err(error) => {
                        append_bootstrap_log(&format!("backend startup failed: {error}"));
                        append_startup_log(
                            app.handle(),
                            &format!("backend startup failed: {error}"),
                        );
                        return Err(error);
                    }
                };

                append_startup_log(app.handle(), "backend launch completed");
                append_bootstrap_log("backend launch completed");
                store_backend_child(app, child)?;
            }

            register_push_to_talk_shortcut(app.handle())?;
            #[cfg(not(debug_assertions))]
            append_startup_log(app.handle(), "shortcuts registered");
            append_bootstrap_log("push-to-talk shortcut registered");

            let broker = AttentionBroker::spawn(app.handle().clone(), handle_attention_event);
            #[cfg(not(debug_assertions))]
            append_startup_log(app.handle(), "attention broker started");
            append_bootstrap_log("attention broker started");

            let countdown_handle = broker.source(triggers::countdown::SOURCE);
            let tray_handle = broker.source("trigger.tray");
            let tray_calendar_handle = broker.source("trigger.tray.calendar");

            #[cfg(debug_assertions)]
            triggers::dev_http::spawn(broker.source(triggers::dev_http::SOURCE));

            if let Some(window) = app.get_webview_window("main") {
                let window_to_hide = window.clone();

                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        hide_main_window(&window_to_hide);
                        triggers::countdown::arm(&countdown_handle);
                    }
                });
            }

            setup_tray(app, tray_handle, tray_calendar_handle)?;

            if let Some(main_window) = app.get_webview_window("main") {
                hide_main_window(&main_window);
            }

            create_startup_window(app)?;
            append_bootstrap_log("startup setup window shown on startup");

            if let Err(error) = create_manual_window(app.handle(), false) {
                append_bootstrap_log(&format!("manual window pre-create failed: {error}"));
            }

            if let Err(error) = create_settings_window(app.handle(), false) {
                append_bootstrap_log(&format!("settings window pre-create failed: {error}"));
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .unwrap_or_else(|error| {
            append_bootstrap_log(&format!("build failed: {error}"));
            panic!("error while building tauri application: {error}");
        });

    append_bootstrap_log("tauri build() completed");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            append_bootstrap_log("run loop exit event received");
            stop_packaged_backend(app_handle);
        }
    });
}