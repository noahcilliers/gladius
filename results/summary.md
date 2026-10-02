# Benchmark summary (2026-10-02 13:17:22)

| Metric | Value |
|---|---|
| Disk: base + 4 adapters | 2.14 GB (vs 10.1 GB as separate models) |
| Adapters total | 119 MB |
| Peak RAM (server + router) | 3.31 GB (41% of an 8 GB laptop) |
| Routing accuracy, held-out | 94% (n=35) |
| Routing accuracy, leave-one-out | 95% |
| Router latency | 16 ms mean, 26 ms p95 |
| Cache-hit latency | 2.6 ms |
| Adapter swap overhead | under 50 ms, within run-to-run noise (no reload) |
| Speed, base | 6.3 tok/s, first token 1137 ms |
| Speed, math adapter | 7.6 tok/s |
| Speed, techwriter adapter | 7.0 tok/s |
| Speed, creative adapter | 7.6 tok/s |
| Speed, coding adapter | 7.8 tok/s |
| math accuracy | base 80% · router 90% · oracle 100% |
| SQL adapter (dropped) | 73% vs base 93% on 15 single-table questions; 80% vs 90% on the original 10 |
