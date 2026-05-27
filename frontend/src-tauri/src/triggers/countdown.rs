use std::time::Duration;

use crate::attention::AttentionSourceHandle;

pub const SOURCE: &str = "trigger.countdown";
pub const DELAY: Duration = Duration::from_secs(10);

/// Call this whenever the window is hidden.
/// Each call cancels any previous pending countdown — the 10 s window
/// always starts fresh from the moment of the most recent hide.
pub fn arm(handle: &AttentionSourceHandle) {
    handle.schedule_latest(DELAY);
}
