// Prevents a console window from opening alongside the app on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar_manager;

use sidecar_manager::{find_free_loopback_port, generate_token, SidecarConfig, SidecarManager};
use std::sync::Arc;
use tauri::{Manager, State};

struct AppState {
    // Arc because the supervisor thread outlives this call and needs the same
    // retry budget the rest of the app sees.
    sidecar_manager: Arc<SidecarManager>,
}

/// Hand the window the address and token of the backend this shell started.
///
/// The frontend calls this before its first request. Until now it returned a
/// hardcoded port and an empty token, and nothing on the frontend called it at
/// all.
#[tauri::command]
fn get_sidecar_config(state: State<'_, AppState>) -> Result<SidecarConfig, String> {
    Ok(state.sidecar_manager.config.clone())
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

    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init());

    // The updater has no mobile implementation, and this is a Windows desktop
    // app, so the gate is documentation more than a real branch.
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    }

    builder
        .setup(|app| {
            let handle = app.handle().clone();
            let state: State<'_, AppState> = handle.state();

            // Start the backend and keep it supervised. Failing here is fatal
            // and worth saying so loudly: a window with no backend behind it
            // looks like every feature is broken.
            state.sidecar_manager.spawn(&handle)?;
            Ok(())
        })
        .manage(AppState {
            sidecar_manager: Arc::new(manager),
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_config])
        .build(tauri::generate_context!())
        .expect("error while running AIDSE Tauri application")
        .run(|app, event| {
            // Windows does not take a child down with its parent, so closing
            // the window used to leave the backend running: a 390 MB process
            // still holding its port, one more after every launch.
            if let tauri::RunEvent::Exit = event {
                let state: State<'_, AppState> = app.state();
                state.sidecar_manager.shutdown();
            }
        });
}
