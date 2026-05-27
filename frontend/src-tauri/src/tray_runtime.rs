use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};

use crate::{
    attention::AttentionSourceHandle,
    diagnostics::append_bootstrap_log,
    window_runtime::{open_manual_window, open_settings_window, show_main_window_internal},
};
#[cfg(not(debug_assertions))]
use crate::diagnostics::append_startup_log;

pub fn setup_tray(
    app: &tauri::App,
    tray_handle: AttentionSourceHandle,
    tray_calendar_handle: AttentionSourceHandle,
) -> Result<(), tauri::Error> {
    let app_version = app.package_info().version.to_string();
    let version_label = format!("Avera Desk v{app_version}");

    let open_item = MenuItem::with_id(app, "open", "Open Avera Desk", true, None::<&str>)?;
    let open_settings_item =
        MenuItem::with_id(app, "open-settings", "Settings", true, None::<&str>)?;
    let open_setup_guide_item = MenuItem::with_id(
        app,
        "open-setup-guide",
        "Open Manual",
        true,
        None::<&str>,
    )?;
    let shortcut_hint_item = MenuItem::with_id(
        app,
        "shortcut-hint",
        "Shortcut: Ctrl+Space (push-to-talk)",
        false,
        None::<&str>,
    )?;
    let version_item = MenuItem::with_id(app, "app-version", &version_label, false, None::<&str>)?;
    let info_separator = PredefinedMenuItem::separator(app)?;
    let action_separator = PredefinedMenuItem::separator(app)?;

    #[cfg(debug_assertions)]
    let trigger_attention_item =
        MenuItem::with_id(app, "trigger-attention", "Trigger attention", true, None::<&str>)?;
    #[cfg(debug_assertions)]
    let trigger_calendar_attention_item = MenuItem::with_id(
        app,
        "trigger-calendar-attention",
        "Trigger calendar attention",
        true,
        None::<&str>,
    )?;

    let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    #[cfg(debug_assertions)]
    let menu = Menu::with_items(
        app,
        &[
            &version_item,
            &shortcut_hint_item,
            &info_separator,
            &open_item,
            &open_settings_item,
            &open_setup_guide_item,
            &trigger_attention_item,
            &trigger_calendar_attention_item,
            &action_separator,
            &quit_item,
        ],
    )?;

    #[cfg(not(debug_assertions))]
    let menu = Menu::with_items(
        app,
        &[
            &version_item,
            &shortcut_hint_item,
            &info_separator,
            &open_item,
            &open_settings_item,
            &open_setup_guide_item,
            &action_separator,
            &quit_item,
        ],
    )?;

    #[cfg(not(debug_assertions))]
    let _ = (&tray_handle, &tray_calendar_handle);

    TrayIconBuilder::new()
        .tooltip("Avera Desk")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "open" => show_main_window_internal(app),
            "open-settings" => {
                if let Err(error) = open_settings_window(app.clone()) {
                    append_bootstrap_log(&format!("tray open-settings failed: {error}"));
                }
            }
            "open-setup-guide" => {
                if let Err(error) = open_manual_window(app.clone()) {
                    append_bootstrap_log(&format!("tray open-setup-guide failed: {error}"));
                }
            }
            #[cfg(debug_assertions)]
            "trigger-attention" => tray_handle.emit(),
            #[cfg(debug_assertions)]
            "trigger-calendar-attention" => tray_calendar_handle.emit(),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                show_main_window_internal(tray.app_handle());
            }
        })
        .build(app)?;

    #[cfg(not(debug_assertions))]
    append_startup_log(app.handle(), "tray created");
    append_bootstrap_log("tray created");

    Ok(())
}
