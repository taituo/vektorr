use chrono::{DateTime, Utc};
use std::collections::HashMap;

use crate::match_id::canonical_match_id;

pub struct MatchResolution {
    pub match_id: String,
    pub is_new: bool,
}

pub struct MatchResolver {
    by_provider: HashMap<String, String>,
    by_canonical: HashMap<String, String>,
}

impl MatchResolver {
    pub fn new() -> Self {
        Self {
            by_provider: HashMap::new(),
            by_canonical: HashMap::new(),
        }
    }

    pub fn resolve(
        &mut self,
        provider: &str,
        provider_match_id: &str,
        home: &str,
        away: &str,
        kickoff: DateTime<Utc>,
    ) -> MatchResolution {
        let key = provider_key(provider, provider_match_id);
        if let Some(match_id) = self.by_provider.get(&key) {
            return MatchResolution {
                match_id: match_id.clone(),
                is_new: false,
            };
        }

        let canonical = canonical_match_id(home, away, kickoff);
        let match_id = self
            .by_canonical
            .get(&canonical)
            .cloned()
            .unwrap_or_else(|| canonical.clone());

        self.by_provider.insert(key, match_id.clone());
        self.by_canonical.entry(canonical).or_insert(match_id.clone());

        MatchResolution {
            match_id,
            is_new: true,
        }
    }
}

fn provider_key(provider: &str, provider_match_id: &str) -> String {
    format!("{}|{}", provider, provider_match_id)
}
