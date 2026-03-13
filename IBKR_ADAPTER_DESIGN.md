# IBKR Adapter Design

## Purpose

The IBKR adapter is responsible for communicating with Interactive Brokers and translating external execution data into a normalized internal representation used by the Trading Journal system.

The adapter isolates the rest of the application from IBKR‑specific APIs and data structures. This ensures the core system remains stable even if the IBKR integration layer changes.

---

# Architecture Position

The adapter sits between the external broker API and the internal import service.

IBKR API
→ IBKR Adapter
→ Normalized Execution DTO
→ Import Service
→ TradeFill

The adapter must not contain business logic related to trades or PnL calculations.

Its responsibility is limited to:

- connecting to IBKR
- retrieving execution data
- translating that data into internal structures

---

# Adapter Responsibilities

The adapter must:

- connect to IBKR
- request execution history
- normalize execution fields
- return a list of execution DTOs
- handle connection errors
- avoid leaking IBKR‑specific objects outside the adapter

The adapter must NOT:

- create database records
- match trades
- calculate PnL
- mutate internal domain models

Those responsibilities belong to the service layer.

---

# Recommended Library

The recommended Python client library is:

ib_insync

Reasons:

- mature wrapper around the official IB API
- supports both sync and async workflows
- widely used in trading systems

Alternative libraries may be considered later if necessary.

---

# Adapter Interface

The adapter should expose a simple interface.

Example:

```python
class IBKRAdapter:

    async def fetch_executions(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> list[ExecutionDTO]:
        ...
```

This method returns normalized execution objects.

---

# Execution DTO

The adapter returns execution records using a normalized internal data structure.

Example:

```python
class ExecutionDTO:
    external_fill_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float | None
    execution_time: datetime
```

This structure represents a broker‑agnostic execution record.

No IBKR‑specific fields should leak beyond this structure.

---

# Field Mapping

IBKR execution fields should map into the DTO as follows:

| IBKR Field | DTO Field        |
| ---------- | ---------------- |
| execId     | external_fill_id |
| symbol     | symbol           |
| side       | side             |
| shares     | quantity         |
| price      | price            |
| commission | commission       |
| time       | execution_time   |

---

# Time Normalization

All timestamps must be normalized to UTC before leaving the adapter.

This ensures consistency with the database layer, which already enforces UTC timestamps.

---

# Error Handling

The adapter must distinguish between two types of errors.

## Connection Errors

Examples:

- TWS not running
- network failure
- authentication failure

These should raise a connection‑level exception.

## Data Errors

Examples:

- malformed execution record
- missing fields

These should be logged and skipped.

The adapter should continue returning valid executions.

---

# Import Boundaries

The adapter only returns execution DTOs.

The adapter must not:

- create trades
- create fills
- perform matching logic
- interact with the database

All import logic must remain in the service layer.

---

# Example Flow

Example execution import flow:

1. User triggers manual import
2. Import service calls IBKRAdapter
3. Adapter fetches executions
4. Adapter returns normalized DTO list
5. Import service processes DTOs
6. Service creates fills and updates trades

---

# Future Extensions

The adapter should eventually support:

- options executions
- multi‑leg strategies
- multiple IBKR accounts
- incremental execution sync
- commission reconciliation

These features are outside the scope of version 1.

---

# Summary

The IBKR adapter is a thin integration layer responsible for:

- communicating with IBKR
- translating execution data
- returning normalized execution DTOs

It must remain isolated from the business logic and database layers.
