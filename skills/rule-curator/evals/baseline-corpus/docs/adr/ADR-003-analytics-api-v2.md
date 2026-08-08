# ADR-003: Migrate analytics to API v2

Status: Accepted

## Context

The v1 analytics endpoint batches poorly and drops events under load.

## Decision

All analytics events POST to `https://api.habitsmith.com/v2/events`. The v1
endpoint is deprecated and returns HTTP 410 Gone after this migration. No client
may send to v1.

## Consequences

Clients must include the `X-Schema: 2` header. Old dashboards reading v1 tables
keep working off the historical export.
