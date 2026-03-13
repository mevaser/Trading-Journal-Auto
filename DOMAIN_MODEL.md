# Trading Journal – Domain Model

## Overview

The system models trading activity using two core entities:

Trade
TradeFill

The design follows a **position container + execution events** pattern.

Trades represent positions.

Fills represent executions.

All metrics are derived from fills.

---

# Core Entities

## User

Represents a system account.

Fields:

- id
- username
- email
- password_hash
- created_at

Currently acts as a placeholder until authentication is implemented.

---

## Trade

Represents a trading position.

A trade aggregates multiple fills.

Example:

Buy 100 AAPL
Sell 50 AAPL
Sell 50 AAPL

All executions belong to the same trade.

---

### Trade Metadata

symbol
direction (LONG / SHORT)
strategy
asset_type
thesis
notes
tags

---

### Lifecycle Fields

status

Possible values:

open
partial
closed

---

opened_at
closed_at

---

### Derived Metrics

These fields are computed automatically from fills.

avg_entry_price
avg_exit_price

quantity_opened
quantity_closed

remaining_quantity

pnl_usd
pnl_pct

is_intraday

duration_days

---

### Legacy Fields

The following fields exist for backward compatibility:

entry_date
entry_price
quantity

exit_date
exit_price

portfolio_pct
estimates
stop_loss

These should eventually be deprecated.

---

## TradeFill

Represents an execution event.

Each fill updates the state of the trade.

Fields:

trade_id

fill_datetime

side

BUY
SELL

quantity

price

commission

source

Example sources:

manual
broker_api
import

external_fill_id

Used for broker synchronization.

---

# Trade State Transitions

Trade lifecycle:

open
↓
partial
↓
closed

State is derived automatically.

---

# Example Scenario

Trade:

AAPL long position

Fills:

1
BUY
100
180

2
SELL
40
185

3
SELL
60
190

Result:

Trade status = closed

avg_entry_price = 180
avg_exit_price = 188

PnL calculated automatically.

---

# MarketData

Stores daily close prices for benchmarks.

Fields:

date
symbol
close_price

Composite primary key:

date + symbol

Examples:

SPY
QQQ
BTCUSD

Purpose:

- benchmark comparison
- portfolio analytics
- strategy evaluation

---

# Key Domain Principle

The system **never trusts manually entered trade aggregates**.

All metrics are derived from fills.

This ensures:

- accurate PnL
- correct handling of partial exits
- broker synchronization
- future support for complex strategies

---

# Future Domain Extensions

The domain model is designed to support:

Options trading

Multi-leg positions

Spread strategies

Pair trading

Broker synchronization

Portfolio-level analytics

---

# Summary

The system is built around:

Trade → position container
TradeFill → execution events

Fills are the **source of truth**.
