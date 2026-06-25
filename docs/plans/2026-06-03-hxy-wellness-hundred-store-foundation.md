# HXY Wellness Hundred-Store Foundation

## Goal

Move the current wellness menu from a single-store HTML prototype toward a hundred-store operating surface without a full rewrite.

## First Slice

This slice adds the minimum foundation needed before scaling:

- store master data with stable `store_id`
- store-aware catalog lookup
- global default catalog plus per-store catalog versions
- customer/technician/admin pages that can read or publish by store
- backwards compatibility for existing links that only pass `store`

## Non-Goals

- no full React/Vue rewrite yet
- no payment flow
- no complex region/role hierarchy in this slice
- no replacement of existing order flow

## Product Model

For hundred-store scale, catalog management should follow:

```text
HQ default catalog
-> store catalog override
-> QR/customer page reads store catalog
-> order stores both store_id and store name
```

The system keeps the old `store` text for compatibility, but new flows should prefer `store_id`.

## API Shape

```text
GET  /api/v1/wellness/stores
GET  /api/v1/wellness/catalog?store_id=<id>
PUT  /api/v1/wellness/catalog?store_id=<id>
POST /api/v1/wellness/orders
GET  /api/v1/wellness/staff/orders?store_id=<id>
```

`store_id=default` or empty means HQ default catalog.

## UI Changes

- Customer page accepts `?store_id=` and reads the corresponding catalog.
- Admin page can choose HQ default or a store before loading/publishing catalog.
- Technician page can filter orders by store.

## Later Slices

- region and role hierarchy
- draft/review/publish/rollback workflow
- catalog diff view
- operation audit table
- store group batch publishing
- per-store price overrides instead of full catalog copies
