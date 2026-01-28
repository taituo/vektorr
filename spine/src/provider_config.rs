use anyhow::{Context, Result};
use serde::Deserialize;
use serde_yaml::Value;
use std::fs;

#[derive(Debug, Default, Deserialize)]
pub struct ProviderConfig {
    pub sportmonks: Option<SportMonksConfig>,
    #[serde(rename = "odds_api")]
    pub odds_api: Option<OddsApiConfig>,
}

#[derive(Debug, Default, Deserialize)]
pub struct SportMonksConfig {
    pub token: Option<String>,
    pub leagues: Option<Vec<Value>>,
    pub base_url: Option<String>,
    pub poll_ms: Option<u64>,
}

#[derive(Debug, Default, Deserialize)]
pub struct OddsApiConfig {
    pub api_key: Option<String>,
    pub sports: Option<Vec<Value>>,
    pub regions: Option<String>,
    pub markets: Option<String>,
    pub base_url: Option<String>,
    pub poll_ms: Option<u64>,
}

pub fn load_provider_config(path: &str) -> Result<ProviderConfig> {
    let raw = fs::read_to_string(path).with_context(|| format!("read provider config {}", path))?;
    let cfg: ProviderConfig =
        serde_yaml::from_str(&raw).with_context(|| format!("parse provider config {}", path))?;
    Ok(cfg)
}

pub fn values_to_strings(values: Vec<Value>) -> Vec<String> {
    values
        .into_iter()
        .filter_map(|v| match v {
            Value::Null => None,
            Value::String(s) => Some(s),
            Value::Number(n) => Some(n.to_string()),
            Value::Bool(b) => Some(b.to_string()),
            _ => None,
        })
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}
