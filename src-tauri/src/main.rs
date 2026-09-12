// Prevents a console window from opening alongside the app on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar_manager;

use sidecar_manager::{find_free_loopback_port, generate_token, SidecarConfig, SidecarManager};
use std::sync::Mutex;
use tauri::{Manager, State};

struct AppState {
    sidecar_manager: Mutex<SidecarManager>,
}

/// Hand the window the address and token of the backend this shell started.
///
/// The frontend calls this before its first request. Until now it returned a
/// hardcoded port and an empty token, and nothing on the frontend called it at
/// all.
#[tauri::command]
fn get_sidecar_config(state: State<'_, AppState>) -> Result<SidecarConfig, String> {
    let manager = state.sidecar_manager.lock().map_err(|e| e.to_string())?;
    Ok(manager.config.clone())
}

fn main() {
    // A fresh port and token per launch. The port stops a stale 8010 listener
    // from being mistaken for ours; the token means a process that cannot read
    // this shell's memory cannot call the API, even though it listens on
    // loopback where anything running as this user can reach it.
    let host = "127.0.0.1".to_string();
    let port = find_free_loopback_port();
    let token = generate_token();

    let manager = SidecarManager::new(host, port, token);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let state: State<'_, AppState> = handle.state();
            let manager = state
                .sidecar_manager
                .lock()
                .map_err(|e| e.to_string())?;

            // Start the backend. Failing here is fatal and worth saying so
            // loudly: a window with no backend behind it looks like every
            // feature is broken.
            manager.spawn(&handle)?;
            Ok(())
        })
        .manage(AppState {
            sidecar_manager: Mutex::new(manager),
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_config])
        .run(tauri::generate_context!())
        .expect("error while running AIDSE Tauri application");
}
