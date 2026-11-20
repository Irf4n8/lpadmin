# Module 9: Concurrency, Fan-Out & Race Conditions

Rewritten from live evidence. No release sign-off.

## MAM-C001 — High-Throughput Ticket Fan-Out: 1 Master Order to 500 Child Tickets

Status: **PARTIAL**

Five orders x 100 followers = 500 child positions; not one order to 500 distinct followers.

Evidence checks: LOAD-FIVE-BURST

## MAM-C002 — Concurrent Master Order Placement During Sub-Account Deposit Storm

Status: **PARTIAL**

GUI cash/entry overlaps tested; full deposit storm and internal snapshot isolation not instrumented.

Evidence checks: RACE-GUI-BALANCE-ENTRY-1, RACE-GUI-BALANCE-ENTRY-2, RACE-GUI-BALANCE-ENTRY-3

## MAM-C003 — Mass SL/TP Modification Fan-Out Across 500 Child Tickets

Status: **PARTIAL**

101 accounts modified; original 500 distinct child-ticket population and SLA not exercised.

Evidence checks: LIFE-PROTECTION-RETEST

## MAM-C004 — Simultaneous Order Close and Investor Disconnection

Status: **PARTIAL**

Related races tested; exact concurrent close/disconnect with contractual settlement policy still requires explicit verification.

Evidence checks: RACE-UNFOLLOW-OPEN-1, RACE-MASTER-CHILD-CLOSE

## MAM-C005 — Idempotency Key Deduplication on Master Block Order

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C006 — Database Row Locking on Sub-Account Balance Ledger

Status: **PARTIAL**

Observable ledger/margin invariants tested; database row-lock wait timing requires backend instrumentation.

Evidence checks: RACE-GUI-LEDGER-1, RACE-MARGIN-RESERVATION-1

## MAM-C007 — High-Frequency Tick Burst (500 ticks/sec) During Multi-Order Fan-Out

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C008 — Dead-Letter Queue (DLQ) Handling for Failed Child Order Submissions

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C009 — WebSocket Broadcast Fan-Out to 500 Connected Mobile Apps

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C010 — Memory Leak Profiling Under 100,000 Simulated Child Ticket Lifecycles

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C011 — 1,000 Sub-Accounts Ticket Fan-Out Stress Test

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C012 — Concurrent Child Order Mass Cancellation Across 1,000 Accounts

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C013 — Database Deadlock Prevention via Deterministic Account ID Sorting

Status: **PARTIAL**

No over-close in repeated races; database lock ordering cannot be inferred from API outcomes.

Evidence checks: RACE-MULTI-REDUCE-1, RACE-MULTI-REDUCE-2, RACE-MULTI-REDUCE-3

## MAM-C014 — Network Latency Variance Across Geographically Distributed Broker Nodes

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

## MAM-C015 — Distributed Lock (Redlock) Timeout on Allocation Service

Status: **BLOCKED**

Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.

Evidence checks: None; blocked

