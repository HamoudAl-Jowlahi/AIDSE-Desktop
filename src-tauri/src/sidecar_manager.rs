use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};

use rand::RngCore;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

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

    /// Resolve the bundled backend executable inside the installed resources.
    ///
    /// The path has to match what the bundler lays down. tauri.conf.json maps
    /// `"../dist/aidse-backend": "backend/"`, and a directory source with a
    /// trailing-slash target copies the directory's *contents*, so the tree
    /// installs as `backend/aidse-backend.exe` beside `backend/_internal` —
    /// not `backend/aidse-backend/aidse-backend.exe`. Getting this wrong is
    /// invisible until launch, where it reads as "every feature is broken".
    fn backend_path(app: &AppHandle) -> Result<PathBuf, String> {
        let backend = app
            .path()
            .resource_dir()
            .map_err(|e| format!("could not locate the app resources: {e}"))?
            .join("backend")
            .join("aidse-backend.exe");

        if !backend.is_file() {
            return Err(format!(
                "the AIDSE backend is missing from this installation, expected at {}",
                backend.display()
            ));
        }
        Ok(backend)
    }

    /// Launch the backend once, returning the child handle.
    ///
    /// Started by path rather than through Tauri's sidecar mechanism, because
    /// externalBin copies a single file while PyInstaller produces a directory:
    /// a launcher stub plus a 790 MB _internal tree it loads its Python DLL
    /// from. Shipping only the stub gave "Failed to load Python DLL", so the
    /// sidecar configuration could never have worked. The whole tree ships as
    /// a resource instead.
    ///
    /// std::process::Command keeps this on the Rust side, so the webview needs
    /// no shell permission for the backend to start.
    fn launch(&self, backend: &PathBuf) -> Result<Child, String> {
        let working_dir = backend
            .parent()
            .ok_or_else(|| "backend path has no parent directory".to_string())?;

        Command::new(backend)
            .args([
                "--host",
                &self.config.host,
                "--port",
                &self.config.port.to_string(),
                "--token",
                &self.config.token,
            ])
            // The working directory must be the backend's own folder so the
            // launcher stub finds _internal beside it.
            .current_dir(working_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("could not start the AIDSE backend: {e}"))
    }

    /// Start the backend and keep it running.
    ///
    /// The restart policy below was written, unit-tested, and then never
    /// called: the manager tracked retries for a process nothing supervised.
    /// If the backend died the window simply stopped working, with no restart
    /// and nothing logged. This is the supervisor that was missing.
    pub fn spawn(self: &Arc<Self>, app: &AppHandle) -> Result<(), String> {
        let backend = Self::backend_path(app)?;
        let child = self.launch(&backend)?;

        log::info!(
            "AIDSE backend started (pid {}) on port {}",
            child.id(),
            self.config.port
        );

        let manager = Arc::clone(self);
        std::thread::spawn(move || {
            let mut child = child;
            loop {
                match child.wait() {
                    Ok(status) if status.success() => {
                        log::info!("AIDSE backend exited normally; not restarting.");
                        return;
                    }
                    Ok(status) => log::error!("AIDSE backend exited with {status}"),
                    Err(e) => {
                        log::error!("lost track of the AIDSE backend: {e}");
                        return;
                    }
                }

                if !manager.should_restart() {
                    log::error!(
                        "AIDSE backend crashed repeatedly; giving up rather than \
                         looping. Restart the application."
                    );
                    return;
                }

                // A backend that stays up past the reset window counts as
                // healthy, so an isolated crash months later gets a full budget.
                match manager.launch(&backend) {
                    Ok(next) => {
                        log::warn!("restarted the AIDSE backend (pid {})", next.id());
                        child = next;
                    }
                    Err(e) => {
                        log::error!("could not restart the AIDSE backend: {e}");
                        return;
                    }
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
