//! Optional local request-body ceiling. No conversation content is logged or discarded.
//!
//! Enabled only in the custom build's launcher via CODEX_MAX_REQUEST_BYTES.
//! Generation rolls over at 90%; compaction gets the remaining 10% of headroom.
use codex_protocol::error::CodexErr;
use codex_protocol::error::CodexErrorDetails;
use codex_protocol::error::Result;
use serde::Serialize;

const ERROR_PREFIX: &str = "[request-byte-budget]";

#[derive(Clone, Copy, Debug)]
struct Budget {
    maximum: usize,
}

impl Budget {
    fn parse(value: &str) -> Result<Self> {
        let maximum = value.parse::<usize>().map_err(|_| {
            CodexErr::InvalidRequest("CODEX_MAX_REQUEST_BYTES must be a positive byte count".into())
        })?;
        if maximum < 1024 {
            return Err(CodexErr::InvalidRequest(
                "CODEX_MAX_REQUEST_BYTES must be at least 1024".into(),
            ));
        }
        Ok(Self { maximum })
    }

    fn limit(self, compaction: bool) -> usize {
        if compaction {
            self.maximum
        } else {
            // Division first avoids overflow for unusually large configured limits.
            self.maximum - self.maximum / 10
        }
    }

    fn check(self, bytes: usize, compaction: bool) -> Result<()> {
        let limit = self.limit(compaction);
        tracing::info!(bytes, limit, compaction, "request byte budget checked");
        if bytes > limit {
            return Err(CodexErr::InvalidRequest(format!(
                "{ERROR_PREFIX} Serialized JSON body is {bytes} bytes; limit is {limit}. \
                 {} No oversized request was sent.",
                if compaction {
                    "Compaction itself exceeds the ceiling; shorten the large input or tool output."
                } else {
                    "Automatic compaction is required."
                }
            )));
        }
        Ok(())
    }
}

/// Call immediately before dispatch, after metadata and input transformations.
/// Measures the uncompressed JSON body; HTTP headers and TLS framing are excluded.
pub(crate) fn check<T: Serialize>(request: &T, compaction: bool, thread_id: &str) -> Result<()> {
    let Some(value) = std::env::var_os("CODEX_MAX_REQUEST_BYTES") else {
        return Ok(());
    };
    let value = value.to_str().ok_or_else(|| {
        CodexErr::InvalidRequest("CODEX_MAX_REQUEST_BYTES must be ASCII digits".into())
    })?;
    let budget = Budget::parse(value)?;
    let bytes = serde_json::to_vec(request)?.len();
    if let Some(directory) = std::env::var_os("CODEX_BYTE_GUARD_STATUS_DIR") {
        if let Err(error) = write_status(
            std::path::Path::new(&directory),
            thread_id,
            budget,
            bytes,
            compaction,
        ) {
            tracing::warn!(%error, "could not write local byte guard status");
        }
    }
    budget.check(bytes, compaction)
}

/// Only sizes and identifiers are stored; request contents and credentials never are.
fn write_status(
    directory: &std::path::Path,
    thread_id: &str,
    budget: Budget,
    bytes: usize,
    compaction: bool,
) -> std::io::Result<()> {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    let _guard = LOCK
        .lock()
        .map_err(|_| std::io::Error::other("status lock poisoned"))?;
    if thread_id.is_empty()
        || !thread_id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    {
        return Err(std::io::Error::other("invalid thread id"));
    }
    std::fs::create_dir_all(directory)?;
    let pid = std::process::id();
    let path = directory.join(format!("{thread_id}-{pid}.json"));
    let previous: serde_json::Value = std::fs::read(&path)
        .ok()
        .and_then(|raw| serde_json::from_slice(&raw).ok())
        .unwrap_or_default();
    let count = |key: &str| {
        previous
            .get(key)
            .and_then(serde_json::Value::as_u64)
            .unwrap_or(0)
    };
    let blocked = bytes > budget.limit(compaction);
    let updated_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(std::io::Error::other)?
        .as_secs_f64();
    let status = serde_json::json!({
        "schema": 1, "thread_id": thread_id, "pid": pid, "updated_at": updated_at,
        "request_bytes": bytes, "limit_bytes": budget.limit(compaction),
        "maximum_bytes": budget.maximum, "generation_limit_bytes": budget.limit(false),
        "compaction": compaction, "blocked": blocked,
        "checks": count("checks").saturating_add(1),
        "blocked_generation_checks": count("blocked_generation_checks").saturating_add(u64::from(blocked && !compaction)),
        "compaction_checks": count("compaction_checks").saturating_add(u64::from(compaction)),
        "last_blocked_bytes": if blocked { serde_json::json!(bytes) } else { previous.get("last_blocked_bytes").cloned().unwrap_or_default() }
    });
    let mut temporary = tempfile::NamedTempFile::new_in(directory)?;
    serde_json::to_writer(temporary.as_file_mut(), &status).map_err(std::io::Error::other)?;
    temporary.persist(path).map_err(|error| error.error)?;
    Ok(())
}

pub(crate) fn is_exceeded(error: &CodexErr) -> bool {
    matches!(error.details(), CodexErrorDetails::InvalidRequest(message) if message.starts_with(ERROR_PREFIX))
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;
    use serde_json::json;

    #[test]
    fn generation_leaves_compaction_headroom_and_accepts_exact_boundary() {
        let budget = Budget::parse("1000000").unwrap();
        assert_eq!(budget.limit(false), 900000);
        assert!(budget.check(900000, false).is_ok());
        assert!(is_exceeded(&budget.check(900001, false).unwrap_err()));
        assert!(budget.check(1000000, true).is_ok());
        assert!(is_exceeded(&budget.check(1000001, true).unwrap_err()));
    }

    #[test]
    fn counts_utf8_escaping_and_tools_in_complete_json() {
        assert_eq!(
            serde_json::to_vec(&json!({"input":"中"})).unwrap().len(),
            15
        );
        let body = json!({"input":"中\n\"", "tools":[{"description":"工具"}]});
        let encoded = serde_json::to_vec(&body).unwrap();
        assert_eq!(encoded.len(), serde_json::to_string(&body).unwrap().len());
        assert!(encoded.len() > "中\n\"".len() + "工具".len());
        let budget = Budget {
            maximum: encoded.len() - 1,
        };
        assert!(is_exceeded(&budget.check(encoded.len(), true).unwrap_err()));
    }

    #[test]
    fn invalid_setting_fails_closed_and_other_errors_are_not_retried() {
        for value in ["", "0", "-1", "abc", "1000"] {
            assert!(Budget::parse(value).is_err());
        }
        assert!(!is_exceeded(&CodexErr::InvalidRequest("HTTP 403".into())));
        assert!(!is_exceeded(&CodexErr::ContextWindowExceeded));
    }

    #[test]
    fn local_status_tracks_checks_without_request_content() {
        let directory = tempfile::tempdir().unwrap();
        let budget = Budget::parse("1000000").unwrap();
        for (bytes, compaction) in [(910000, false), (920000, true), (10000, false)] {
            write_status(directory.path(), "test-thread", budget, bytes, compaction).unwrap();
        }
        let path = directory
            .path()
            .join(format!("test-thread-{}.json", std::process::id()));
        let value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(value["checks"], 3);
        assert_eq!(value["blocked_generation_checks"], 1);
        assert_eq!(value["compaction_checks"], 1);
        assert_eq!(value["request_bytes"], 10000);
        assert_eq!(value["last_blocked_bytes"], 910000);
        assert_eq!(value["blocked"], false);
        assert!(write_status(directory.path(), "../escape", budget, 0, false).is_err());
    }
}
