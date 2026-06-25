# HXY Wellness Menu Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a first usable three-end HXY wellness menu prototype for customer ordering, admin catalog editing, and technician service execution.

**Architecture:** Keep the prototype inside the existing htops wellness H5/API surface. Persist the editable catalog as JSONB in PostgreSQL, let customer and technician pages read the same catalog, and reuse existing wellness order APIs for order creation and status updates.

**Tech Stack:** FastAPI, PostgreSQL JSONB, static HTML/CSS/JavaScript, nginx reverse proxy.

---

### Task 1: Catalog API

**Files:**
- Modify: `api/main.py`

**Steps:**
1. Add a default catalog with categories, projects, 清泡调补养 fields, service steps, technician notes, and scripts.
2. Add `wellness_catalogs` table creation to `ensure_wellness_tables()`.
3. Add `GET /api/v1/wellness/catalog`.
4. Add `PUT /api/v1/wellness/catalog` with server-side token protection.
5. Run `python3 -m py_compile api/main.py`.

### Task 2: Customer Page

**Files:**
- Create/modify: `docs/wellness-order.html`

**Steps:**
1. Replace hard-coded menu data with catalog loading.
2. Add category navigation, project cards, project detail sheet, options, add-ons, 清泡调补养, and cart confirmation.
3. Submit orders through `POST /api/v1/wellness/orders`.
4. Run inline JavaScript parse verification.

### Task 3: Admin Page

**Files:**
- Create: `docs/wellness-admin.html`

**Steps:**
1. Add simple password gate for prototype access.
2. Load catalog from `GET /api/v1/wellness/catalog`.
3. Add project editor, preview, duplicate, down-shelf, and raw JSON editor.
4. Publish with `PUT /api/v1/wellness/catalog` and `X-Wellness-Admin-Token`.
5. Run inline JavaScript parse verification.

### Task 4: Technician Page

**Files:**
- Create: `docs/wellness-technician.html`
- Modify: `docs/wellness-staff.html`

**Steps:**
1. Add technician service view using orders plus catalog service metadata.
2. Show customer selections, 清泡调补养, service steps, technician notes, and scripts.
3. Update order status with token-protected staff endpoint.
4. Keep legacy staff page compatible with the token requirement.
5. Run inline JavaScript parse verification.

### Task 5: Deployment

**Files:**
- Modify: `ops/nginx/htops-wellness-h5.conf`

**Steps:**
1. Expose `/wellness-admin.html` and `/wellness-technician.html`.
2. Copy nginx config to `/etc/nginx/sites-available/htops-wellness-h5`.
3. Run `nginx -t`.
4. Reload nginx.
5. Restart `htops-wellness-api.service`.
6. Verify catalog API and all public pages over local and public routes.
