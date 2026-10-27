# CloudPilot — Frontend

The frontend in `frontend/` is a single-page application built with **React 18,
TypeScript (strict), Vite, Tailwind CSS and Radix UI** primitives in the shadcn/ui
style. It talks to the backend only through the REST API under `/api/v1`.

## Screens

| Route | Page | What it shows |
|---|---|---|
| `/login` | `pages/auth/LoginPage` | Email/password sign-in and a one-click **Try Demo** button |
| `/` | `pages/overview/OverviewPage` | KPI row (month-to-date spend, potential savings, optimisation score, connected clouds), multi-cloud spend chart, top cost drivers, latest agent findings |
| `/resources` | `pages/resources/ResourcesPage` | Inventory as a provider → region → service tree; per-resource metrics and cost trend |
| `/costs` | `pages/costs/CostsPage` | Breakdown by provider / service / region, daily time series with a selectable time range, anomaly timeline |
| `/recommendations` | `pages/recommendations/RecommendationsPage` | Agent findings filterable by agent and status; accept / reject / snooze; **"How this was calculated"** on every card |
| `/forecast` | `pages/forecast/ForecastPage` | Prophet projection at 30/60/90 days with its uncertainty band, the budget line, an overrun verdict, and the budget control (admin) |
| `/chat` | `pages/chat/ChatPage` | The Cloud Advisor: sessions, answers with citation chips, and the trace of live data it looked up |
| `/settings` | `pages/settings/SettingsPage` | Tabs: **Cloud Accounts**, **Pricing** (the full rate card with provenance and age), **Profile**, **Audit Log** |
| `/settings/connect` | `pages/settings/ConnectCloudPage` | Wizard for connecting an Azure, AWS or GCP account |

Every route except `/login` is wrapped in `ProtectedRoute` and rendered inside
`AppShell` (sidebar, top bar, command palette). Unknown paths redirect to `/`.
**⌘K / Ctrl+K** opens the command palette for keyboard navigation.

## Source layout

```
frontend/src/
├── App.tsx            routes, QueryClient, session bootstrap, error boundary
├── pages/             one folder per screen (table above)
├── components/
│   ├── layout/        AppShell, Sidebar, TopBar, CommandPalette, PageHeader
│   ├── domain/        CloudPilot-specific widgets: RecommendationCard, CalculationBasis,
│   │                  RateCardPanel, ForecastChart, CostBreakdownChart, OptimizationScore,
│   │                  ChatBubble, CitationChip, AgentBadge, ProviderBadge, …
│   ├── ui/            generic Radix-based primitives (button, card, dialog, tabs, toast, …)
│   └── auth/          LoginForm, ProtectedRoute
├── hooks/             one TanStack Query hook module per API area
│                      (useCosts, useRecommendations, useForecast, usePricing, useChat, …)
├── stores/            Zustand stores: auth, cloud, ui
├── lib/               api client, token handling, pricing helpers, constants, utils
└── types/             API response types mirroring the backend's Pydantic schemas
```

## State management

| Kind of state | Owner | Notes |
|---|---|---|
| **Server state** (costs, recommendations, forecasts…) | TanStack Query | `staleTime` 30 s, one retry, no refetch on window focus. Mutations invalidate the queries they affect |
| **Session** (current user, auth status) | Zustand `auth.store` | |
| **UI state** (sidebar, palette, filters) | Zustand `ui.store`, `cloud.store` | |

Pages never call `axios` directly; they use the hooks in `hooks/`, so caching and
invalidation rules live in one place per API area.

## Authentication flow

- The **access token is held in memory only** (`lib/auth.ts`), never in `localStorage`,
  so an XSS payload cannot read a persisted token.
- The **refresh token is an HttpOnly cookie**; the axios instance sends it with
  `withCredentials: true`.
- `lib/api.ts` injects `Authorization: Bearer …` on every request. On a **401** it
  refreshes once and replays the request. Concurrent 401s share a single in-flight
  refresh promise, because refresh tokens are single-use and rotate on every call: two
  parallel refreshes would invalidate each other.
- On page load, `SessionBootstrap` calls `loadSession()` to restore the session from the
  cookie. That call is also de-duplicated: React StrictMode runs effects twice in
  development, and the second bootstrap used to consume an already-rotated token, sign
  the user out and lose the deep link they had opened. `e2e/auth.spec.ts` covers it.

## Showing where numbers come from

Two components carry the platform's "no unexplained figures" principle into the UI:

- **`CalculationBasis`** renders a recommendation's `metadata`. For rightsizing it shows
  both SKUs' hourly rates, the hours and node count, the arithmetic, and, for each rate,
  its source (`azure_retail_api`, `aws_price_list` or `published_list_price`), the meter
  or page it was read from, and the snapshot date. For a cost anomaly it shows the
  expected versus the actual billed amount.
- **`RateCardPanel`** (Settings → Pricing) lists the whole rate card from
  `GET /api/v1/pricing/catalog`, with the share that is API-verified and a staleness
  warning once the snapshot is more than 90 days old.

## Honest empty and error states

The UI distinguishes "no data" from "not configured" from "failed", and says which:

- No budget set → the Forecast page shows **"Not set"**, not a default figure.
- Ollama unavailable → the chat shows the backend's explicit *"model unavailable"*
  notice, not an answer.
- A render crash → `ErrorBoundary` shows a recoverable error screen instead of a blank
  page.

## Testing

| Suite | Tool | Where | Run with |
|---|---|---|---|
| Unit / component | Vitest + Testing Library (jsdom) | `src/**/*.test.ts(x)`: API client refresh logic, pricing helpers, `CalculationBasis`, `ConfirmDialog`, `ChatPage`, `ErrorBoundary`, utils | `pnpm test` (CI runs it) |
| End-to-end | Playwright (Chromium) | `e2e/*.spec.ts` | `make e2e`, against a running, seeded stack |

The e2e specs each guard a bug that reached a running app:

| Spec | Guards |
|---|---|
| `auth.spec.ts` | redirect when signed out, wrong password refused, demo sign-in, deep link surviving the session bootstrap |
| `budget.spec.ts` | the Forecast page and the overrun alert agreeing about the tenant's budget |
| `pricing-provenance.spec.ts` | a rightsizing saving traceable to a published rate on screen |
| `advisor.spec.ts` | the Advisor saying "model unavailable" instead of inventing an answer |
| `costs.spec.ts` | the cost aggregates rendering identically on a cold and a cached load |

See [development.md → End-to-end tests](development.md#end-to-end-tests) for setup.

## Conventions

- PascalCase component files, camelCase hooks and utils, `@/` import alias.
- Strict TypeScript with no `any`; API types live in `types/api.ts`.
- Tailwind utilities only; no per-component CSS files.
- Animation with Framer Motion. Components that sit inside `AnimatePresence` with
  `mode="popLayout"` must forward their ref (see `RecommendationCard`), or the exit
  animation cannot measure them.

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:5173
pnpm typecheck && pnpm lint && pnpm test
pnpm build
```
