use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use serde::{Deserialize, Serialize};

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
        // Exhaust the budget, then backdate the last restart beyond the window
        // so the next attempt is treated as a fresh incident rather than part
        // of the same crash loop.
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
}
