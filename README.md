# DB Benchmark Research

A reproducible benchmarking project for evaluating relational, time-series, and analytical database systems on an industrial-scale dataset.

The project compares:

- PostgreSQL
- TimescaleDB
- ClickHouse
- StarRocks

The work focuses on three main areas:

1. **Read/query performance**
2. **Ingestion performance**
3. **Distributed ClickHouse scaling**

The benchmark was developed as part of data warehousing research at **FAU FAPS**.

---

## 1. Project Motivation

Industrial data platforms may contain tens of millions of time-series and process records.

Choosing a database for such workloads cannot be based only on general database characteristics. Different systems behave differently depending on:

- query type,
- aggregation complexity,
- time-window selectivity,
- joins,
- sorting,
- analytical/window functions,
- ingestion batch size,
- indexing and physical table design,
- concurrency,
- and distributed architecture.

This project therefore evaluates multiple database systems using the **same dataset and benchmark workload** wherever possible.

The goal is not simply to determine which database is "fastest", but to understand:

> **Which database architecture performs well for which type of industrial workload, and why?**

---

## 2. Systems Under Test

| Database | Role |
|---|---|
| PostgreSQL 16 | Relational baseline |
| TimescaleDB | PostgreSQL-based time-series database |
| ClickHouse | Column-oriented analytical database |
| StarRocks | Distributed analytical database |

The databases are deployed using Docker to provide a controlled and reproducible environment.

For the main single-node experiments, database resources were limited to:

```text
8 vCPU
32 GB RAM
```

---

## 3. Dataset

The primary benchmark dataset contains industrial process execution data.

### `tensoryze.processexecution`

Approximately:

```text
66,156,940 rows
```

The table contains measurements and metadata including:

```text
id
hash
timestamp
time_key
date_key
namespace_id
_value
_field
_value_str
created_at
updated_at
part_variant_id
```

A second table is used for join workloads.

### `tensoryze.partquality`

Approximately:

```text
2,577,037 rows
```

It contains part-level quality information such as:

```text
part_id
quality
rework
last_station
error_code
timestamp
namespace_id
part_variant_id
```

---

## 4. Benchmark Architecture

The project follows a common benchmark pipeline:

```text
                     Industrial Dataset
                            |
                            v
                 +---------------------+
                 | Benchmark Framework |
                 +----------+----------+
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
     PostgreSQL        TimescaleDB        ClickHouse
                                              |
                                              v
                                          StarRocks
                            |
                            v
                     Result CSV Files
                            |
                            v
                         Analysis
```

The benchmark framework executes equivalent workloads against each supported database through database-specific adapters.

---

## 5. Query Benchmark

The main read benchmark contains **57 query workloads**.

These workloads cover multiple database operations rather than relying on a single synthetic query.

### Basic reads

Examples include:

```text
count_rows
timestamp_range_sanity
per_part_read
time_range_read
count_time_window
partquality_read
```

### Time-series aggregation

```text
avg_5min
min_max_5min
count_namespace_5min
group_time_namespace_field
group_time_part
```

### Grouping and aggregation

```text
group_by_namespace
group_by_field
group_by_namespace_field
group_by_part
nested_grouping
group_having_large_parts
```

### Sorting and Top-K

```text
top_parts
order_by_timestamp_desc
order_by_part_timestamp
order_by_value_desc
```

### Distinct workloads

```text
distinct_parts_5min
distinct_namespace_field
distinct_fields_per_namespace
```

### Analytical / window workloads

```text
latest_per_part
latest_10_per_part
rolling_avg
lag_value
row_number
rank_parts_by_count
rank_values_per_part
running_count_by_bucket
value_difference
cumulative_avg_per_part
cumulative_count_per_part
```

### Join workloads

```text
join_avg_partquality
join_raw_partquality
join_time_filtered
join_group_field
exists_partquality
```

### Filtering

```text
filter_numeric_value
filter_not_null
filter_multiple_conditions
filter_order_timestamp
filter_order_value
filter_field_not_null
```

### Selectivity tests

The same time-series workload is tested over different time ranges:

```text
1 hour
6 hours
1 day
7 days
30 days
```

This helps evaluate how each database responds as the amount of scanned data increases.

---

## 6. Benchmark Methodology

The benchmark runner:

1. connects to the selected database,
2. samples representative IDs where required,
3. builds the common query workload,
4. executes each query multiple times,
5. records execution latency,
6. reports the median latency,
7. collects storage information,
8. exports results to CSV.

Example:

```bash
python benchmark.py --target clickhouse
```

The exact available CLI options can be inspected with:

```bash
python benchmark.py --help
```

Results are written to the benchmark results directory.

```text
benchmark/results/
```

---

# ClickHouse Optimization Research

ClickHouse was investigated in more detail because its physical table design can significantly affect analytical workloads.

The optimization work was performed incrementally so that structural and query-level changes could be evaluated separately.

---

## 7. Original ClickHouse Design

The initial table used a conventional MergeTree configuration:

```sql
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (id, timestamp)
```

This provided the baseline for later optimization experiments.

---

## 8. Stage 1 - Physical Table Optimization

The table structure was redesigned for the workload.

Optimizations included:

- `LowCardinality` for repeated categorical columns,
- timestamp compression using `Delta` and `ZSTD`,
- monthly partitioning,
- ordering optimized for time-window and namespace workloads.

The optimized ordering became:

```sql
ORDER BY (
    toStartOfFiveMinutes(timestamp),
    namespace_id,
    id,
    timestamp
)
```

This reduced storage compared with the original ClickHouse table while improving several analytical workloads.

---

## 9. Stage 2 - Projection Optimization

A projection was added for queries that access data by part ID and timestamp:

```sql
PROJECTION proj_id_timestamp
(
    SELECT *
    ORDER BY (id, timestamp)
)
```

The final optimized table therefore combines:

```text
Time-oriented base ordering
+
ID-oriented projection
```

This allows ClickHouse to use different physical organizations depending on the query.

The trade-off is additional storage because the projection stores another physical representation of the data.

---

## 10. Stage 3 - Query-Level Optimization

Several query-level optimizations were investigated individually.

Experiments included:

- `argMax` alternatives for latest-record queries,
- semi-join alternatives,
- PREWHERE strategies,
- window-order optimizations,
- aggregation-in-order settings,
- early filtering,
- alternative query formulations.

An optimization was only considered useful when experimental measurements justified the change.

Several theoretically promising rewrites were rejected because they either:

- increased latency,
- increased memory consumption,
- or did not improve the execution plan.

This was intentional: the project keeps the benchmark based on measured behavior rather than assuming that a syntactic rewrite is automatically an optimization.

---

# Ingestion Benchmark

## 11. Continuous Ingestion

Read performance is only one part of an industrial data warehouse.

A separate benchmark evaluates continuous synthetic ingestion using Sparkplug-like records.

The benchmark tests different batch sizes:

```text
1
10
100
1000
```

The workload uses acknowledgement per batch.

This is important when interpreting the results: the experiment measures **synchronous acknowledgement-per-batch ingestion**, not the theoretical maximum bulk-loading throughput of each database.

The results show the strong effect of batching.

For example, larger batches substantially increase throughput because database/network overhead is amortized across more records.

---

# Distributed ClickHouse Experiments

The project was extended from single-node benchmarking to distributed ClickHouse experiments.

Two different horizontal-scaling strategies were investigated:

```text
1. Sharding
2. Full-copy reader scaling
```

These experiments answer different questions.

---

## 12. Two-Node ClickHouse Environment

Two ClickHouse servers were configured.

```text
Node 1
192.168.209.185

Node 2
192.168.209.86
```

Both nodes used:

```text
ClickHouse 26.7.4.58
```

Bidirectional connectivity between the nodes was verified.

A cluster configuration named:

```text
faps_2shards
```

was created.

Conceptually:

```text
                  ClickHouse Cluster
                         |
               +---------+---------+
               |                   |
               v                   v
            Node 1              Node 2
            Shard 1             Shard 2
```

---

## 13. Sharding Experiment

A local optimized MergeTree table was created on each node.

```text
tensoryze.processexecution_local_dist
```

A Distributed table was then created:

```sql
ENGINE = Distributed(
    'faps_2shards',
    'tensoryze',
    'processexecution_local_dist',
    cityHash64(id)
)
```

Rows are assigned to shards according to:

```text
cityHash64(id)
```

The resulting distribution was almost exactly balanced:

```text
Shard 1: ~33.09 million rows
Shard 2: ~33.07 million rows
```

or approximately:

```text
50.01%
49.99%
```

Conceptually:

```text
             66.16M process rows
                     |
              cityHash64(id)
                     |
             +-------+-------+
             |               |
             v               v
          Node 1          Node 2
         ~33.09M         ~33.07M
          rows             rows
```

The `partquality` dataset was also sharded so that join workloads could execute using corresponding local data.

---

## 14. Sharding Results

The distributed benchmark demonstrated an important result:

> **Sharding does not automatically make every query faster.**

Some analytical workloads benefited significantly because computation could be performed independently on both shards.

Examples of workloads that improved included:

```text
5-minute aggregation
namespace + field aggregation
numeric sorting
distinct namespace/field workloads
some join aggregations
```

However, other workloads became slower.

Examples include:

```text
very cheap count queries
latest-record-per-part queries
some window functions
some high-cardinality distributed operations
```

The reason is that distributed execution introduces additional work:

```text
Query
  |
  +-------> Node 1
  |
  +-------> Node 2
              |
              v
       partial results
              |
              v
       network transfer
              |
              v
          final merge
              |
              v
            result
```

Parallel execution helps only when the work saved by splitting the query is larger than the additional coordination and merging cost.

---

# Replicated Reader Scaling

## 15. Why Test Full Copies?

Sharding attempts to accelerate a query by dividing its data across machines.

But another important production problem is:

> What happens when multiple users or applications query the database simultaneously?

For this experiment, the complete optimized dataset was copied to Node 2.

Therefore:

```text
Node 1                       Node 2
------                       ------
66.16M rows                  66.16M rows
FULL DATA                    FULL DATA
```

This is different from the sharding experiment.

### Sharding

```text
                One Query
                   |
            +------+------+
            |             |
            v             v
         Node 1         Node 2
         50% data       50% data
```

### Full-copy readers

```text
Reader 1 ----------------> Node 1
                           100% data

Reader 2 ----------------> Node 2
                           100% data
```

The purpose is to increase **concurrent read capacity**.

---

## 16. Concurrent Reader Workload

Running the complete 57-query benchmark concurrently proved too expensive.

Two readers would require:

```text
57 queries
x 5 repetitions
x 2 readers
----------------
570 query executions
```

The experiment was stopped after approximately **28 minutes** before completion.

A smaller representative concurrency workload was therefore created using **8 queries already present in the benchmark**.

No new SQL workload was introduced.

The selected queries were:

```text
count_rows
time_range_read
avg_5min
group_by_part
order_by_timestamp_desc
rank_parts_by_count
join_avg_partquality
filter_multiple_conditions
```

These cover:

```text
counting
large reads
time-series aggregation
grouping
sorting
analytical ranking
joins
filtering
```

Each reader executes:

```text
8 queries x 3 repetitions = 24 executions
```

---

## 17. Reader Scaling Results

The measured concurrency results were:

| Readers | Nodes | Query Executions | Wall Time | Throughput |
|---:|---:|---:|---:|---:|
| 1 | 1 | 24 | 72.329 s | 0.332 q/s |
| 2 | 1 | 48 | 91.162 s | 0.527 q/s |
| 2 | 2 | 48 | 72.354 s | 0.663 q/s |
| 4 | 1 | 96 | 149.475 s | 0.642 q/s |
| 4 | 2 | 96 | 118.829 s | 0.808 q/s |

### Two readers

```text
SAME NODE

Reader 1 ---\
             +----> Node 1
Reader 2 ---/

91.162 s
0.527 q/s
```

versus:

```text
TWO NODES

Reader 1 --------> Node 1
Reader 2 --------> Node 2

72.354 s
0.663 q/s
```

Using two nodes reduced workload completion time by approximately:

```text
20.6%
```

and increased measured throughput by approximately:

```text
25.8%
```

### Four readers

```text
SAME NODE

Reader 1 ---\
Reader 2 ----\
              +----> Node 1
Reader 3 ----/
Reader 4 ---/

149.475 s
0.642 q/s
```

versus:

```text
TWO NODES

Reader 1 ---\
             +----> Node 1
Reader 2 ---/

Reader 3 ---\
             +----> Node 2
Reader 4 ---/

118.829 s
0.808 q/s
```

Using two nodes reduced workload completion time by approximately:

```text
20.5%
```

and increased measured throughput by approximately:

```text
25.9%
```

---

## 18. What the Distributed Experiments Show

The two experiments demonstrate two different forms of horizontal scaling.

### Sharding

Best understood as:

```text
Split DATA and COMPUTATION
for one analytical workload
across multiple nodes.
```

Potential advantage:

```text
less work per node
+
parallel execution
```

Potential cost:

```text
network communication
+
distributed coordination
+
result merging
```

### Replicated readers

Best understood as:

```text
Duplicate DATA
and distribute independent CLIENTS
across multiple nodes.
```

Potential advantage:

```text
more aggregate read capacity
+
less contention per node
```

The measured representative concurrency workload showed approximately **26% higher throughput** when concurrent readers were distributed across two full-data nodes instead of sharing one node.

---

# Important Experimental Notes

The distributed experiments should be interpreted within their experimental scope.

### Distributed query limitation

One correlated `EXISTS` workload was not supported in the tested remote/distributed ClickHouse configuration.

Therefore, the sharded result set is not a completely identical 57/57 execution.

### Reader benchmark

The concurrency experiment uses the documented **8-query representative subset**, not the full 57-query benchmark.

### Manual reader routing

Readers were explicitly routed to Node 1 or Node 2 during the experiment.

No external load balancer was evaluated.

### Full-copy reader nodes

The full copies were created manually for the experiment.

The current experiment should therefore be described as:

> **full-copy reader scaling**

rather than automatic ClickHouse replication.

---

# Repository Structure

A simplified repository structure is:

```text
DB-Benchmark-Research/
|
+-- benchmark/
|   |
|   +-- benchmark.py
|   +-- queries.py
|   +-- config.py
|   +-- reader_benchmark.py
|   +-- adapters/
|   +-- results/
|
+-- ingestion/
|
+-- docker-compose.yml
|
+-- README.md
```

The exact structure may evolve as additional experiments are added.

---

# Running the Project

## Requirements

The project uses Docker-based database deployments.

Typical requirements include:

```text
Docker
Docker Compose
Python
```

Clone the repository:

```bash
git clone <repository-url>
cd DB-Benchmark-Research
```

Start the database environment according to the repository's Docker Compose configuration.

For environments using Docker Compose v1:

```bash
docker-compose up -d
```

For environments using Compose v2:

```bash
docker compose up -d
```

Run the benchmark from the benchmark environment or Python environment configured by the project.

For example:

```bash
python benchmark/benchmark.py --help
```

Check the CLI help for the currently supported targets and options before starting a benchmark.

---

# Benchmarking Principles

The project follows several principles intended to keep comparisons meaningful.

### Controlled resources

Databases are evaluated under defined CPU and memory limits.

### Same workload

Equivalent queries are used across databases wherever database semantics allow it.

### Repetition

Queries are repeated and median latency is used to reduce sensitivity to individual outliers.

### Measured optimizations

Optimizations are accepted based on experimental results rather than assumptions.

### Workload-specific conclusions

The project does not assume that one database is universally superior.

Instead, conclusions are tied to the tested workload.

---

# Current Research Direction

The current benchmark covers:

```text
                    Database Evaluation
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
        READS           INGESTION        DISTRIBUTION
          |                 |                 |
      57-query          batch-size       ClickHouse
      workload          experiments       scaling
                                              |
                                    +---------+---------+
                                    |                   |
                                 Sharding         Full-copy readers
```

The next step is to strengthen the concurrency measurements through repeated workload-level trials and analyze variability, median completion time, throughput, and scaling efficiency.

---

# Disclaimer

Benchmark results are specific to the tested:

- dataset,
- hardware,
- resource limits,
- database versions,
- schemas,
- query workload,
- configuration,
- and benchmark methodology.

They should not be interpreted as universal performance rankings of the database systems.

---

## Author

**Moneeb Ali Karrar**

M.Sc. Artificial Intelligence  
Friedrich-Alexander-Universität Erlangen-Nürnberg (FAU)

Research work conducted in the context of data warehousing benchmarking at **FAU FAPS**.
