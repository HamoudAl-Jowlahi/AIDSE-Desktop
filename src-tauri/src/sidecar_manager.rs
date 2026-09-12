use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use rand::RngCore;
use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// What the frontend needs in order to talk to the sidecar.
///
/// The token is generated per launch and never leaves this process pair, so the
/// window can prove it is the shell and anything else on the machine cannot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidecarConfig {
    pub host: String,
    pub port: u16,
    pub token: String,
}

pub struct SidecarManager {
    pub config: SidecarConfig,
    retry_count: Arc<Mutex<u32>>,
    last_restart: Arc<Mutex<Option<Instant>>>,
    max_retries: u32,
    reset_window: Duration,
}

/// A free TCP port on loopback, asked for by binding port 0 and reading back
/// what the OS assigned.
///
/// The shell used to hardcode 8010. When something else already held it the
/// sidecar moved to 8011 and the window kept talking to 8010, so the whole app
/// failed with "not found" errors that looked like missing data.
pub fn find_free_loopback_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|addr| addr.port())
        .unwrap_or(8010)
}

/// 256 bits of OS randomness, hex encoded.
pub fn generate_token() -> String {
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

impl SidecarManager {
    pub fn new(host: String, port: u16, token: String) -> Self {
        Self {
            config: SidecarConfig { host, port, token },
            retry_count: Arc::new(Mutex::new(0)),
            last_restart: Arc::new(Mutex::new(None)),
            max_retries: 3,
            reset_window: Duration::from_secs(60),
        }
    }

    /// Start the bundled backend, passing it the host, port and token.
    ///
    /// Nothing here existed before: this struct carried restart bookkeeping for
    /// a process it never launched, so the Tauri build shipped a shell with no
    /// backend behind it.
    pub fn spawn(&self, app: &AppHandle) -> Result<(), String> {
        let (mut rx, _child) = app
            .shell()
            .sidecar("aidse-backend")
            .map_err(|e| format!("sidecar binary not found: {e}"))?
            .args([
                "--host",
                &self.config.host,
                "--port",
                &self.config.port.to_string(),
                "--token",
                &self.config.token,
            ])
            .spawn()
            .map_err(|e| format!("could not start the AIDSE backend: {e}"))?;

        // Drain the sidecar's output. Without a reader the pipe fills and the
        // child blocks once it has logged enough.
        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stderr(line) => {
                        log::warn!("[sidecar] {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Stdout(line) => {
                        log::info!("[sidecar] {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Terminated(payload) => {
                        log::error!("[sidecar] exited: {:?}", payload.code);
                        break;
                    }
                    _ => {}
                }
            }
        });

        Ok(())
    }

    pub fn should_restart(&self) -> bool {
        let mut count = self.retry_count.lock().unwrap();
        let mut last = self.last_restart.lock().unwrap();
        let now = Instant::now();

        if let Some(last_time) = *last {
            if now.duration_since(last_time) > self.reset_window {
                *count = 0;
            }
        }

        if *count < self.max_retries {
            *count += 1;
            *last = Some(now);
            true
        } else {
            false
        }
    }

    pub fn reset_retry_count(&self) {
        let mut count = self.retry_count.lock().unwrap();
        *count = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manager() -> SidecarManager {
        SidecarManager::new("127.0.0.1".to_string(), 8010, String::new())
    }

    #[test]
    fn should_restart_stops_after_max_retries() {
        let m = manager();
        assert!(m.should_restart(), "first restart must be allowed");
        assert!(m.should_restart(), "second restart must be allowed");
        assert!(m.should_restart(), "third restart must be allowed");
        assert!(
            !m.should_restart(),
            "a fourth consecutive crash must be refused, or a crashing sidecar loops forever"
        );
    }

    #[test]
    fn reset_clears_the_counter() {
        let m = manager();
        while m.should_restart() {}
        assert!(!m.should_restart());

        m.reset_retry_count();
        assert!(
            m.should_restart(),
            "after a healthy run the budget must be available again"
        );
    }

    #[test]
    fn counter_resets_once_the_window_has_passed() {
        let m = manager();
        while m.should_restart() {}
        assert!(!m.should_restart());

        {
            let mut last = m.last_restart.lock().unwrap();
            *last = Some(Instant::now() - m.reset_window - Duration::from_secs(1));
        }

        assert!(
            m.should_restart(),
            "a crash long after the previous one must not count against the old budget"
        );
    }

    #[test]
    fn token_is_256_bits_of_hex_and_never_repeats() {
        let a = generate_token();
        let b = generate_token();
        assert_eq!(a.len(), 64, "256 bits hex-encoded is 64 characters");
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b, "each launch must get its own token");
    }

    #[test]
    fn allocated_port_is_usable() {
        let port = find_free_loopback_port();
        assert!(port >= 1024, "must not hand back a privileged port");
        // The OS released it when the probe listener dropped, so it binds again.
        TcpListener::bind(("127.0.0.1", port)).expect("port was not actually free");
    }
}
