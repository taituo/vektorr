use std::collections::{HashSet, VecDeque};
use std::time::Instant;
use tokio::time::Duration;

pub struct Deduper {
    cap: usize,
    set: HashSet<String>,
    queue: VecDeque<String>,
}

impl Deduper {
    pub fn new(cap: usize) -> Self {
        Self {
            cap,
            set: HashSet::new(),
            queue: VecDeque::new(),
        }
    }

    pub fn allow(&mut self, key: String) -> bool {
        if self.cap == 0 {
            return true;
        }
        if self.set.contains(&key) {
            return false;
        }
        self.set.insert(key.clone());
        self.queue.push_back(key);
        while self.queue.len() > self.cap {
            if let Some(old) = self.queue.pop_front() {
                self.set.remove(&old);
            }
        }
        true
    }
}

pub fn next_backoff(current: u64, max_backoff_ms: u64) -> u64 {
    let next = if current == 0 { 500 } else { current.saturating_mul(2) };
    if next > max_backoff_ms {
        max_backoff_ms
    } else {
        next
    }
}

pub fn poll_sleep_ms(base_ms: u64, min_interval_ms: u64, extra_ms: u64, loop_start: Instant) -> Duration {
    let target_ms = base_ms.max(min_interval_ms).max(extra_ms);
    let elapsed_ms = loop_start.elapsed().as_millis() as u64;
    let sleep_ms = target_ms.saturating_sub(elapsed_ms);
    Duration::from_millis(sleep_ms)
}
