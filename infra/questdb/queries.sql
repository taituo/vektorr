-- Example queries for monitoring

-- Latest decisions
SELECT * FROM decisions ORDER BY timestamp DESC LIMIT 20;

-- Decision breakdown (last 1 day)
SELECT reason, count() AS n
FROM decisions
WHERE timestamp > now() - 1d
GROUP BY reason
ORDER BY n DESC;

-- Event latency (avg/max) per match, last 1 hour
SELECT match_id, avg(latency_ms) AS avg_ms, max(latency_ms) AS max_ms
FROM events
WHERE timestamp > now() - 1h
GROUP BY match_id
ORDER BY max_ms DESC;

-- Odds latency (avg/max) per match, last 1 hour
SELECT match_id, avg(latency_ms) AS avg_ms, max(latency_ms) AS max_ms
FROM odds
WHERE timestamp > now() - 1h
GROUP BY match_id
ORDER BY max_ms DESC;

-- P95 latency (if supported by your QuestDB version)
-- SELECT match_id, approx_percentile(latency_ms, 0.95) AS p95_ms
-- FROM events
-- WHERE timestamp > now() - 1h
-- GROUP BY match_id;

-- TPS distribution
SELECT tps_label, count() AS n
FROM decisions
WHERE timestamp > now() - 1d
GROUP BY tps_label
ORDER BY n DESC;

-- Recent bet signals
SELECT * FROM decisions
WHERE can_bet = 1
ORDER BY timestamp DESC
LIMIT 50;

-- Execution log (last 1 day)
SELECT status, reason, count() AS n
FROM executions
WHERE timestamp > now() - 1d
GROUP BY status, reason
ORDER BY n DESC;
