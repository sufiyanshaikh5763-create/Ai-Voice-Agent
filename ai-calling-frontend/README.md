# TalkAor — AI Voice-Calling Agent SaaS Platform (Frontend)

TalkAor is an AI voice-calling SaaS platform designed to automate client inbound and outbound calls, appointment scheduling, and inquiry management.

This repository contains the complete frontend solution:
1. **Existing TalkAor Landing Page** — Preserved in pure HTML, CSS, and Vanilla JavaScript with WebGL audio soundwave shader background.
2. **TalkAor Client Dashboard** — A modern, production-grade B2B SaaS application built with **React**, **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, **shadcn/ui**, **Framer Motion**, and **TanStack React Query**.

---

## ⚡ Quick Start (Mock Demo)

The dashboard can run with demo data by setting `NEXT_PUBLIC_API_MODE=mock` in `.env.local`:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser:
- **`/`** — The public **TalkAor Landing Page** (WebGL soundwave, features, catalog, pricing, FAQ).
- **`/login`** — The client dashboard login portal.
- **`/dashboard`** — The protected, role-based client dashboard.

---

## 🔑 Demo Accounts & Authentication

Two demo accounts with instant 1-click buttons are provided on `/login`:

| Account | Role | Email | Password | Permissions Summary |
|---|---|---|---|---|
| **Sarah Jenkins** | `CLIENT_ADMIN` | `admin@talkaor.com` | `admin123` | Full CRUD on Appointments, Customers, Agents, Staff; Audio Recordings & Transcripts; Edit Profile |
| **David Miller** | `CLIENT_STAFF` | `staff@talkaor.com` | `staff123` | Appointment management; View-only Customers/Agents; No staff access; Audio/Transcripts redacted |

> **Quick Switcher**: Inside the dashboard header, there is an instant **"Admin View / Staff View"** toggle button that allows real-time role switching during stakeholder demos without re-entering credentials.

---

## 🗂️ Project Structure

```
TalkAor/
│
├── existing-landing-page/            # 100% Preserved original landing page files
│   ├── index.html                    # Public landing page
│   ├── style.css                     # Landing page styling & WebGL canvas styles
│   ├── script.js                     # Vanilla JS controller & WebGL shader
│   ├── login.html
│   └── signup.html
│
├── public/                           # Static assets served by Next.js
│   ├── landing.html                  # Landing page served at http://localhost:3000/
│   ├── style.css
│   └── script.js
│
├── app/                              # Next.js App Router (Dashboard & Login)
│   ├── layout.tsx                    # Root HTML layout with Providers & Toaster
│   ├── globals.css                   # Dark glass design tokens, animations, scrollbars
│   ├── page.tsx                      # Root route handler
│   ├── login/
│   │   └── page.tsx                  # Client login screen with demo shortcuts
│   │
│   └── dashboard/                    # Protected client dashboard (Auth Guard)
│       ├── layout.tsx                # Persistent sidebar, header, mobile drawer
│       ├── page.tsx                  # Dashboard Home overview & statistics
│       ├── appointments/page.tsx     # Appointments (3D Flip Stack + Table view)
│       ├── customers/page.tsx        # Customers directory & CRUD
│       ├── calls/page.tsx            # Telephony call logs, audio & transcripts
│       ├── cancellations/page.tsx    # Cancellations audit log (read-only)
│       ├── agents/page.tsx           # AI Voice Agents deployment & JSON config
│       ├── staff/page.tsx            # Team management (CLIENT_ADMIN only)
│       └── business-profile/page.tsx # Organization settings & timezone config
│
├── components/
│   ├── ui/
│   │   ├── case-study-flip-stack.tsx # @componentry/case-study-flip-stack (Appointment Roster)
│   │   ├── button.tsx                # Glassmorphic button variants
│   │   ├── badge.tsx                 # Status badges
│   │   ├── dialog.tsx                # Accessible Radix modal dialogs
│   │   ├── dropdown-menu.tsx         # Action & profile menus
│   │   ├── pagination.tsx            # Reusable pagination component
│   │   ├── confirm-dialog.tsx        # Reusable confirmation dialog
│   │   ├── skeleton.tsx              # Skeletons for lists & flip stack
│   │   ├── empty-state.tsx           # Empty state placeholders with CTAs
│   │   ├── error-banner.tsx          # Structured API error display
│   │   └── ...
│   │
│   ├── dashboard/                    # Sidebar, Header, StatsCard
│   └── appointments/                 # Flip Stack, Table, Create/Edit, Cancel, Reschedule, History
│
├── lib/
│   ├── api/                          # Typed API Service Layer (Calls FastAPI or Mock)
│   │   ├── client.ts                 # HTTP client, 401 TOKEN_EXPIRED auto-refresh, baseURL
│   │   ├── auth.ts
│   │   ├── appointments.ts
│   │   ├── customers.ts
│   │   ├── calls.ts
│   │   ├── cancellations.ts
│   │   ├── agents.ts
│   │   ├── users.ts
│   │   ├── clients.ts
│   │   └── dashboard.ts
│   │
│   ├── mock/                         # Stateful Mock Service Layer
│   │   ├── db.ts                     # Realistic seed data
│   │   ├── storage.ts                # localStorage stateful persistence & SSR memory store
│   │   ├── auth.ts
│   │   ├── appointments.ts
│   │   ├── customers.ts
│   │   ├── calls.ts
│   │   ├── cancellations.ts
│   │   ├── agents.ts
│   │   ├── users.ts
│   │   ├── clients.ts
│   │   └── dashboard.ts
│   │
│   ├── types/index.ts                # Comprehensive TypeScript data models
│   └── auth/auth-context.tsx         # Auth Context, session restore, role guards
│
├── tailwind.config.ts                # Tailwind design tokens (brand orange, dark glass)
├── next.config.mjs                   # Rewrites '/' to landing page, image domains
└── package.json
```

---

## 🎨 Visual Design & UI System

The dashboard visual design is inspired by the **Admin Dashboard V7** dark glassmorphic design language:
- **Color Palette**:
  - Dark Charcoal Canvas (`#090a0f` / `#0d0f15`)
  - Glass Containers (`rgba(20, 22, 32, 0.75)` with `backdrop-filter: blur(16px)` and `border: 1px solid rgba(255,255,255,0.08)`)
  - TalkAor Vibrant Brand Orange (`#f97316` / `#ea580c` with glowing shadows `shadow-glow-orange`)
  - Status Indicators (Emerald `#10b981` for active/completed, Amber `#f59e0b` for rescheduled, Rose `#f43f5e` for cancelled)
- **Framer Motion Micro-interactions**: Hover lifts on cards (`whileHover={{ y: -4 }}`), smooth fade-in transitions.
- **Responsiveness**: Floating sidebar rail on desktop, smooth overlay drawer on mobile and tablets.

---

## 🃏 Appointment Experience: CaseStudyFlipStack & Table

The appointments view (`/dashboard/appointments`) features two presentation modes:

1. **Card Stack (Default)**:
   - Uses `@componentry/case-study-flip-stack` as the visual and interaction foundation.
   - Adapted specifically for TalkAor bookings: displays customer name, phone, day of week, date, time, service, status badge, assigned voice agent/staff, notes, and action buttons.
   - Supports 3D perspective scroll flipping and interactive step controls (Next / Previous card buttons) for desktop and mobile devices.

2. **Table Mode**:
   - Clean, high-density data table displaying identical appointment records.
   - Columns: Customer, Date & Day, Time, Service, Status, Actions.

3. **Operations**:
   - **Create**: Modal dialog with searchable customer selector, date (`YYYY-MM-DD`), time (`HH:MM:SS`), service list, and notes.
   - **Edit**: Modify customer details, service, and status.
   - **Cancel**: Separate operation (`POST /api/v1/appointments/{id}/cancel`) with confirmation dialog, optional reason input, and toast notification.
   - **Reschedule**: Separate operation (`POST /api/v1/appointments/{id}/reschedule`) with new date, new time, optional reason, and toast notification.
   - **Audit Timeline**: View chronological event history showing who performed the action (Staff Member or AI Agent), previous values, new values, and timestamps.

---

## 🛡️ Role-Based Permission Matrix

| Resource | `CLIENT_ADMIN` | `CLIENT_STAFF` | Implementation Details |
|---|---|---|---|
| **Dashboard Overview** | View | View | Full metric visibility |
| **Appointments** | Full CRUD, Cancel, Reschedule | Full CRUD, Cancel, Reschedule | Shared operational access |
| **Customers** | Full CRUD (Create, Edit, Delete) | View Only | Create/Edit/Delete buttons hidden for staff. 409 `CUSTOMER_HAS_RECORDS` handled on delete. |
| **Voice Calls** | View + Audio Recording + Transcript | View Only (Summary & metadata) | Audio player & speech transcripts completely redacted for staff. |
| **Cancellations** | View | View | Read-only historical ledger |
| **AI Agents** | Full CRUD (Create, Edit, Delete) | View Only | Configuration JSON viewer accessible to both; modifications admin-only. |
| **Staff Management** | Full CRUD (Invite, Edit, Deactivate) | No Access | Hidden from sidebar for staff. Direct route navigation renders "Access Restricted". Admin cannot alter own role/active status. |
| **Business Profile** | View & Edit | View Only | Business name, phone, address, timezone editable by admin. Email and status read-only. |

---

## 🔌 Connecting to the FastAPI Backend

### 1. Environment Variable Configuration

Create `.env.local` in this frontend directory:

```env
# "mock" uses demo data; blank or "live" uses the real API.
NEXT_PUBLIC_API_MODE=live
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
```

Requests use the real FastAPI backend unless `NEXT_PUBLIC_API_MODE=mock`. See the repository-root `README.md` for the complete local setup steps.

### 2. Automatic Token Expiry & Refresh Handling (Requirement #20)

`lib/api/client.ts` includes an automated interceptor:
- If a request returns `401 Unauthorized` with `error_code: "TOKEN_EXPIRED"`:
  1. Automatically pauses pending requests.
  2. Calls `POST /api/v1/auth/refresh` using the stored refresh token.
  3. Updates the access token in storage.
  4. Retries the original request once.
  5. If the refresh fails, clears session state and redirects to `/login`.

---

## 📋 Required FastAPI Endpoints for Backend Developer

Below are the exact API specifications expected by the frontend:

### Authentication
- `POST /api/v1/auth/login`
  - Body: `{ "email": "...", "password": "..." }`
  - Response: `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer", "user": { "id": "...", "name": "...", "email": "...", "role": "CLIENT_ADMIN" | "CLIENT_STAFF", "client_id": "...", "is_active": true } }`
- `GET /api/v1/auth/me`
  - Headers: `Authorization: Bearer <token>`
  - Response: User object
- `POST /api/v1/auth/refresh`
  - Body: `{ "refresh_token": "..." }`
  - Response: `{ "access_token": "...", "token_type": "bearer" }`

### Dashboard Summary
- `GET /api/v1/dashboard/summary`
  - Response: Statistics object with `total_appointments`, `today_appointments`, `scheduled_appointments`, `cancelled_appointments`, `completed_appointments`, `total_customers`, `total_agents`, `active_agents`, `total_calls`, `calls_today`, `weekly_stats`, `recent_calls`, `upcoming_appointments`.

### Appointments
- `GET /api/v1/appointments?status=&date=&date_from=&date_to=&customer=&page=&limit=`
  - Response: `{ "data": Appointment[], "pagination": { "page": 1, "limit": 20, "total": 100, "total_pages": 5 } }`
- `POST /api/v1/appointments`
  - Body: `{ "customer_name": "...", "customer_phone": "...", "customer_email": "...", "date": "YYYY-MM-DD", "time": "HH:MM:SS", "service": "...", "notes": "..." }`
- `PATCH /api/v1/appointments/{id}`
  - Body: `{ "customer_name": "...", "customer_phone": "...", "customer_email": "...", "service": "...", "status": "...", "notes": "..." }`
- `POST /api/v1/appointments/{id}/cancel`
  - Body: `{ "reason": "..." }`
  - Response: `{ "message": "...", "appointment": { ... } }`
- `POST /api/v1/appointments/{id}/reschedule`
  - Body: `{ "new_date": "YYYY-MM-DD", "new_time": "HH:MM:SS", "reason": "..." }`
  - Response: `{ "message": "...", "appointment": { ... } }`
- `GET /api/v1/appointments/{id}/history`
  - Response: Array of `{ "id": "...", "event": "...", "old_value": "...", "new_value": "...", "actor": "...", "actor_type": "staff" | "ai_agent", "timestamp": "..." }`

### Customers
- `GET /api/v1/customers?search=&page=&limit=`
- `POST /api/v1/customers`
- `PATCH /api/v1/customers/{id}`
- `DELETE /api/v1/customers/{id}`
  - If customer has associated records, return HTTP `409 Conflict`:
    `{ "success": false, "message": "Cannot delete customer with active bookings.", "error_code": "CUSTOMER_HAS_RECORDS" }`

### Voice Calls
- `GET /api/v1/calls?status=&agent=&customer=&direction=&date=&page=&limit=`
- `GET /api/v1/calls/{id}`

### Cancellations
- `GET /api/v1/cancellations?customer=&source=&date_from=&date_to=&page=&limit=`

### AI Agents
- `GET /api/v1/agents?status=&page=&limit=`
- `POST /api/v1/agents`
- `PATCH /api/v1/agents/{id}`
- `DELETE /api/v1/agents/{id}`

### Staff (Users)
- `GET /api/v1/users?role=&is_active=&page=&limit=`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{id}` (Must forbid modifying own role or active status)

### Business Profile (Clients)
- `GET /api/v1/clients/me`
- `PATCH /api/v1/clients/me`

---

## 🛠️ Verification & Build Check

To run a production compilation and typecheck:

```bash
npm run build
```

All routes compile cleanly to static and dynamic pages with zero TypeScript errors.
