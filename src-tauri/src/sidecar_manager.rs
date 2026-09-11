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
