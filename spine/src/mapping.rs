use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde_yaml::Value;
use std::collections::HashMap;
use std::path::Path;
use std::{fs, io};

use crate::match_id::canonical_match_id;

pub struct MatchResolution {
    pub match_id: String,
    pub is_new: bool,
    pub home: String,
    pub away: String,
}

pub struct MatchResolver {
    by_provider: HashMap<String, String>,
    by_canonical: HashMap<String, String>,
    team_mapper: Option<TeamMapper>,
}

impl MatchResolver {
    pub fn new() -> Self {
        Self {
            by_provider: HashMap::new(),
            by_canonical: HashMap::new(),
            team_mapper: load_team_mapper(),
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
        let (home_norm, away_norm) = if let Some(mapper) = &self.team_mapper {
            (mapper.normalize(home), mapper.normalize(away))
        } else {
            (home.trim().to_string(), away.trim().to_string())
        };

        let key = provider_key(provider, provider_match_id);
        if let Some(match_id) = self.by_provider.get(&key) {
            return MatchResolution {
                match_id: match_id.clone(),
                is_new: false,
                home: home_norm,
                away: away_norm,
            };
        }

        let canonical = canonical_match_id(&home_norm, &away_norm, kickoff);
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
            home: home_norm,
            away: away_norm,
        }
    }
}

fn provider_key(provider: &str, provider_match_id: &str) -> String {
    format!("{}|{}", provider, provider_match_id)
}

pub struct TeamMapper {
    team_map: HashMap<String, String>,
}

impl TeamMapper {
    pub fn from_path(path: &str) -> Result<Self> {
        let raw = fs::read_to_string(path)
            .with_context(|| format!("read team mappings {}", path))?;
        let value: Value =
            serde_yaml::from_str(&raw).with_context(|| format!("parse team mappings {}", path))?;
        let mut team_map: HashMap<String, String> = HashMap::new();

        let teams = value
            .get("TEAMS")
            .and_then(|v| v.as_mapping())
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "TEAMS missing"))?;

        for (key, val) in teams.iter() {
            let canonical = match key.as_str() {
                Some(s) => s.trim().to_string(),
                None => continue,
            };
            if canonical.is_empty() {
                continue;
            }
            insert_team(&mut team_map, &canonical, &canonical);
            if let Some(list) = val.as_sequence() {
                for entry in list.iter() {
                    if let Some(variant) = entry.as_str() {
                        insert_team(&mut team_map, variant, &canonical);
                    }
                }
            }
        }

        Ok(Self { team_map })
    }

    pub fn normalize(&self, name: &str) -> String {
        let key = name.trim().to_lowercase();
        if key.is_empty() {
            return name.trim().to_string();
        }
        self.team_map
            .get(&key)
            .cloned()
            .unwrap_or_else(|| name.trim().to_string())
    }
}

fn insert_team(map: &mut HashMap<String, String>, variant: &str, canonical: &str) {
    let key = variant.trim().to_lowercase();
    if key.is_empty() {
        return;
    }
    map.insert(key, canonical.to_string());
}

fn load_team_mapper() -> Option<TeamMapper> {
    let path = std::env::var("TEAM_MAPPINGS_PATH").unwrap_or_else(|_| "mappings.yaml".to_string());
    if !Path::new(&path).exists() {
        return None;
    }
    match TeamMapper::from_path(&path) {
        Ok(mapper) => Some(mapper),
        Err(err) => {
            eprintln!("team mappings load failed ({}): {}", path, err);
            None
        }
    }
}
