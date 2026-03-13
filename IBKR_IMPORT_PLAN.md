# IBKR Import Plan

## Purpose

This document defines the first implementation phase of Interactive Brokers (IBKR) trade import for the Trading Journal system.

The goal of version 1 is to import execution data from IBKR into the existing Trade + Fill domain model safely and incrementally.

This is a design document only.  
It defines scope, mapping rules, and implementation boundaries before coding begins.

---

# 1. Goal of V1

Version 1 should allow the system to:

- connect to IBKR
- fetch execution-level trade data
- persist imported executions as `TradeFill` records
- create or associate `Trade` records as needed
- prevent duplicate imports
- trigger normal trade recalculation after import

Version 1 is intentionally limited.  
It focuses on reliable execution import, not full portfolio synchronization.

---

# 2. Existing Domain Context

The current system already supports:

- `Trade` as a position container
- `TradeFill` as execution events
- server-side recalculation of:
  - quantity opened
  - quantity closed
  - remaining quantity
  - average entry/exit price
  - pnl
  - duration
  - intraday classification

Because of this, the IBKR integration should import executions into the existing fill-driven model rather than creating a separate accounting path.

---

# 3. Scope of V1

## Included

- import stock executions from IBKR
- map executions into `TradeFill`
- create a `Trade` if no matching open trade exists
- attach fills to an existing open trade when appropriate
- mark imported fills with source metadata
- support manual import trigger
- support duplicate prevention

## Excluded

- options
- multi-leg positions
- pair trades
- portfolio cash tracking
- dividends
- corporate actions
- commissions reconciliation beyond fill-level import
- scheduled cron sync
- real-time streaming
- multi-account support
- full broker position reconciliation

---

# 4. Source of Truth

IBKR execution records are the external source of truth for imported fills.

Inside the Trading Journal system, `TradeFill` remains the internal source of truth.

Trade-level fields must continue to be derived from fills after each import.

---

# 5. Proposed Import Flow

## High-level flow

1. User triggers import manually
2. System connects to IBKR
3. System fetches execution records for a requested time window
4. Each execution is normalized into an internal import DTO
5. System checks whether the execution was already imported
6. If not imported:
   - find matching trade
   - create trade if needed
   - insert fill
   - recalculate trade
7. Return import summary

---

# 6. Data Mapping Strategy

## IBKR execution data → internal fill

Each imported execution should be mapped to a `TradeFill`.

### Required internal fields

- `trade_id`
- `fill_datetime`
- `side`
- `quantity`
- `price`
- `commission`
- `source`
- `external_fill_id`

### Mapping rules

#### fill_datetime

Mapped from IBKR execution timestamp.  
Must be normalized to UTC.

#### side

Mapped into internal enum:

- buy-like execution → `BUY`
- sell-like execution → `SELL`

#### quantity

Imported as absolute positive quantity.

#### price

Imported from execution price.

#### commission

Imported if available.  
If unavailable, default to `0` in V1.

#### source

Always set to:
ibkr

#### external_fill_id

Must contain a stable unique identifier from IBKR.  
This field is critical for duplicate prevention.

---

# 7. Trade Matching Rules

The system must decide whether an imported fill belongs to an existing trade or requires a new trade.

## V1 matching strategy

A fill should be attached to an existing trade only if all of the following are true:

- same symbol
- same direction context
- trade status is not `closed`
- trade belongs to the same user/account scope
- no ambiguity exists

If no suitable open trade exists, create a new trade.

V1 should favor safety over aggressive matching.

If trade matching is uncertain, the system should create a new trade rather than risk attaching a fill to the wrong trade.

---

# 8. Trade Creation Rules

When a new trade is created from imported data:

## Initial fields

Populate:

- `symbol`
- `direction`
- `asset_type`
- `opened_at`
- `status`

## Suggested defaults

- `strategy = null`
- `thesis = null`
- `notes = "Imported from IBKR"`
- `asset_type = "stock"`

Trade-level derived metrics must not be manually set during import.  
They must be computed through normal recalculation logic.

---

# 9. Duplicate Prevention

Duplicate prevention is mandatory.

## Rule

A fill must not be imported more than once.

## V1 duplicate key

Use `external_fill_id` as the primary duplicate detection key.

If `external_fill_id` already exists in the database, skip the fill.

## Recommended DB constraint

Eventually enforce uniqueness on:

- `source`
- `external_fill_id`

---

# 10. Recalculation Behavior

After each new fill insertion:

- recompute the affected trade
- update derived fields
- persist recalculated trade state

The import path must reuse the existing trade calculation service.

---

# 11. Import Trigger Design

## V1 approach

Start with a manual import trigger only.

Recommended options:

- service-level function callable from code
- internal API endpoint for testing/admin use

## Not yet included

- cron scheduler
- background worker
- automatic daily sync

---

# 12. Error Handling

The import process should distinguish between:

### Recoverable per-fill errors

Examples:

- malformed execution row
- missing required fields
- unknown side mapping

Behavior:

- skip the problematic fill
- record the error
- continue processing remaining fills

### Fatal import errors

Examples:

- cannot connect to IBKR
- authentication/session issue
- transport failure

Behavior:

- abort the import
- return clear failure summary

---

# 13. Logging and Import Summary

Each import run should produce a summary including:

- total executions received
- fills imported
- duplicates skipped
- fills failed
- trades created
- trades updated

---

# 14. V1 Technical Boundaries

Version 1 should avoid:

- changing the current domain model heavily
- introducing options-specific logic
- redesigning trade accounting
- implementing background orchestration too early

The purpose of V1 is to prove safe import into the current architecture.

---

# 15. Open Design Questions

These questions should be resolved before implementation starts:

1. Which IBKR client library will be used?
2. What exact IBKR execution identifier should be used as `external_fill_id`?
3. How should direction be inferred when importing fills into a new trade?
4. How should commissions behave if IBKR returns them separately?
5. Do we need an `ImportRun` table later for auditability?
6. Should account identifiers be stored in V1 or deferred?

---

# 16. Recommended Next Step

Before writing import code:

1. define import DTO
2. define IBKR adapter interface
3. define matching policy
4. define duplicate-check policy

Only after that should coding begin.

---

# 17. Summary

Version 1 of IBKR import should:

- import execution records only
- map them into `TradeFill`
- create or match `Trade` safely
- prevent duplicates using `external_fill_id`
- reuse existing recalculation logic
- be manually triggered first

This keeps the implementation small, testable, and aligned with the current architecture.
