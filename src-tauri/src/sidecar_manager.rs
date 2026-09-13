use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
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
    /// The backend currently running, so closing the window can stop it.
    ///
    /// Windows does not kill a child when its parent goes, so without this the
    /// backend outlived every session: closing the app left a 390 MB process
    /// holding a port, and launching again started another beside it.
    child: Arc<Mutex<Option<Child>>>,
    /// Set once the app is on its way out, so the supervisor does not read a
    /// deliberate kill as a crash and restart what we just stopped.
    shutting_down: Arc<AtomicBool>,
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
            child: Arc::new(Mutex::new(None)),
            shutting_down: Arc::new(AtomicBool::new(false)),
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
        *self.child.lock().unwrap() = Some(child);

        let manager = Arc::clone(self);
        std::thread::spawn(move || {
            loop {
                // Polled rather than blocked on wait(): the child lives behind
                // a mutex that shutdown() has to be able to take, and a
                // blocking wait would hold that lock until the process died —
                // which is exactly when shutdown needs it.
                let status = loop {
                    if manager.shutting_down.load(Ordering::SeqCst) {
                        return;
                    }
                    let polled = {
                        let mut guard = manager.child.lock().unwrap();
                        match guard.as_mut() {
                            Some(child) => child.try_wait(),
                            // shutdown() took it; nothing left to supervise.
                            None => return,
                        }
                    };
                    match polled {
                        Ok(Some(status)) => break status,
                        Ok(None) => std::thread::sleep(Duration::from_millis(500)),
                        Err(e) => {
                            log::error!("lost track of the AIDSE backend: {e}");
                            return;
                        }
                    }
                };

                if manager.shutting_down.load(Ordering::SeqCst) {
                    return;
                }

                if status.success() {
                    log::info!("AIDSE backend exited normally; not restarting.");
                    return;
                }
                log::error!("AIDSE backend exited with {status}");

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
                        *manager.child.lock().unwrap() = Some(next);
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

    /// Stop the backend. Called when the app exits.
    ///
    /// Without it the backend survives the window that started it, because on
    /// Windows a child is not killed with its parent. Every run left one
    /// behind, which is how eight of them ended up resident at once.
    pub fn shutdown(&self) {
        self.shutting_down.store(true, Ordering::SeqCst);

        let child = self.child.lock().unwrap().take();
        if let Some(mut child) = child {
            let pid = child.id();
            match child.kill() {
                // Already gone is a success: the goal is that it is not running.
                Ok(()) | Err(_) => {
                    let _ = child.wait();
                    log::info!("AIDSE backend (pid {pid}) stopped with the app.");
                }
            }
        }
    }

    /// Whether shutdown() has been called. The supervisor checks this so a
    /// deliberate kill is never mistaken for a crash worth restarting.
    pub fn is_shutting_down(&self) -> bool {
        self.shutting_down.load(Ordering::SeqCst)
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

    /// A child that will outlive the test unless something kills it.
    fn long_running_child() -> Child {
        Command::new("cmd")
            .args(["/C", "ping -n 120 127.0.0.1"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("could not start the stand-in child process")
    }

    #[test]
    fn shutdown_actually_kills_the_backend() {
        // Closing the window used to leave the backend running, because on
        // Windows a child is not taken down with its parent. This is that bug.
        let m = manager();
        *m.child.lock().unwrap() = Some(long_running_child());

        let started = Instant::now();
        m.shutdown();
        let elapsed = started.elapsed();

        // shutdown() waits for the process after killing it, so it can only
        // return promptly if the kill worked. Without it, this waits 120 s.
        assert!(
            elapsed < Duration::from_secs(15),
            "shutdown took {elapsed:?}; the child was not killed, only waited on"
        );
        assert!(
            m.child.lock().unwrap().is_none(),
            "shutdown must release the child so nothing tries to supervise it"
        );
    }

    #[test]
    fn shutdown_stops_the_supervisor_from_restarting() {
        let m = manager();
        assert!(!m.is_shutting_down());

        m.shutdown();

        assert!(
            m.is_shutting_down(),
            "the supervisor reads this flag; without it a deliberate kill looks              like a crash and the backend is restarted on the way out"
        );
    }

    #[test]
    fn shutdown_is_safe_with_no_backend_running() {
        // Startup can fail before anything is spawned, and exit still runs.
        let m = manager();
        m.shutdown();
        m.shutdown();
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
