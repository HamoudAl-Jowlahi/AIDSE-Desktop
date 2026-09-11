mod sidecar_manager;

use sidecar_manager::{SidecarConfig, SidecarManager};
use std::sync::Mutex;
use tauri::State;

struct AppState {
    sidecar_manager: Mutex<SidecarManager>,
}

#[tauri::command]
fn get_sidecar_config(state: State<'_, AppState>) -> Result<SidecarConfig, String> {
    let manager = state.sidecar_manager.lock().map_err(|e| e.to_string())?;
    Ok(manager.config.clone())
}

fn main() {
    let host = "127.0.0.1".to_string();
    let port = 8010;
    let token = "".to_string(); // Will be populated in Phase 3 internal token isolation

    let manager = SidecarManager::new(host, port, token);

    tauri::Builder::default()
        .manage(AppState {
            sidecar_manager: Mutex::new(manager),
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_config])
        .run(tauri::generate_context!())
        .expect("error while running AIDSE Tauri application");
}
