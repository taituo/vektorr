use std::fs::File;
use std::io::{BufRead, BufReader};

use anyhow::{Context, Result};
use serde::de::DeserializeOwned;

pub fn read_jsonl<T: DeserializeOwned>(path: &str) -> Result<Vec<T>> {
    let file = File::open(path).with_context(|| format!("open {}", path))?;
    let reader = BufReader::new(file);
    let mut out = Vec::new();
    for (idx, line) in reader.lines().enumerate() {
        let line = line.with_context(|| format!("read line {}", idx + 1))?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let value = serde_json::from_str::<T>(line)
            .with_context(|| format!("parse json line {}", idx + 1))?;
        out.push(value);
    }
    Ok(out)
}
