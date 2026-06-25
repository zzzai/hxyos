# HXY Wellness P0 Operations System

## Priorities

1. Account and role permissions
2. Store management admin
3. Catalog publish workflow
4. Order status loop
5. Store operations dashboard

## Execution Order

The first implementation slice focuses on account and role permissions while preserving the legacy `hxy2024` token for temporary compatibility.

## P0 Role Model

Roles:

- `hq_admin`: all stores and all admin APIs
- `region_manager`: assigned region and stores
- `store_manager`: assigned store admin
- `frontdesk`: store orders and status updates
- `technician`: assigned store service view
- `readonly`: read-only dashboards

## First Slice

- create staff account and session tables
- seed a default `hq_admin`
- add login endpoint
- add role-aware auth helper
- allow legacy admin token as a temporary compatibility path
- expose `me` endpoint for frontends

## Later Slices

- replace static password login in admin/technician/staff pages
- store management CRUD
- draft/review/publish states
- order cancellation and exception states
- store dashboard APIs
