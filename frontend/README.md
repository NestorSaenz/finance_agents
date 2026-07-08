# Safi — Frontend

Responsive chat UI for the Safi assistant. **Next.js (App Router) + React +
TypeScript + Tailwind CSS**. Talks to the FastAPI backend under `/api/v1`.

## Requirements

- Node.js 18.18+ (or 20+)
- The backend running (see the repo root). Default local origin: `http://localhost:8000`.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set API_URL if the backend isn't on :8000
npm run dev                        # http://localhost:3000
```

Requests to `/api/*` are proxied to `API_URL` by `next.config.mjs`, so there is no
CORS setup and the JWT travels in the `Authorization` header.

## Scripts

```bash
npm run dev        # dev server
npm run build      # production build
npm run start      # serve the production build
npm run typecheck  # tsc --noEmit (strict) — must pass
npm run lint       # next lint
```

## Structure

```
src/
├── app/                 # routes: / (redirect), /login, /signup, /chat
├── components/
│   ├── auth/            # AuthScreen (login/signup form)
│   ├── chat/            # ChatView, MessageBubble, ChatInput, EmptyState, TypingIndicator
│   ├── layout/          # Header
│   └── ui/              # Button, Input, Spinner, Logo (design-system primitives)
├── context/AuthContext  # session state (token + user), login/signup/logout
└── lib/                 # api client (typed), shared types
```

## Standard

Code follows the `financegpt-frontend-code-review` skill: strict TypeScript (no
`any`), mobile-first responsive, accessible, a single typed API client with
loading/error/empty states, and design tokens (no magic colors/spacing).

## Auth

The token + user are kept in `localStorage` via `AuthContext`; protected pages
redirect to `/login` after hydration. Login/signup hit the backend's Supabase-JWT
endpoints and redirect to `/chat`.
