---
name: financegpt-frontend-code-review
description: >
  Standard + review guide for the FinanceGPT frontend (Next.js App Router + React + TypeScript
  + Tailwind CSS). Trigger: when writing or reviewing frontend code, components, hooks, pages,
  or API calls, or evaluating UI quality (typing, responsive, accessibility, UX).
license: Apache-2.0
metadata:
  author: financegpt
  version: "1.0"
---

## When to Use

- Writing OR reviewing any code under `frontend/` (components, hooks, pages, lib, context).
- Ensuring the UI is responsive (mobile + laptop), accessible, intuitive, and professional.
- Verifying TypeScript strictness, Next.js App Router conventions, and clean data-fetching.

This skill is the single source of truth for the frontend standard: generate code that already
satisfies it, and review against it.

## Critical Patterns (Must Enforce)

1. **Strict TypeScript (no `any`)**
   - `tsc --noEmit` must pass with `strict: true`. Never use `any`; use `unknown` + narrowing,
     precise types, or generics. Type every prop, hook return, and API payload.
   - Props via explicit `type`/`interface`; no implicit `any` on callbacks/events.
2. **Next.js App Router discipline**
   - Server Components by default; add `"use client"` ONLY to components that use state, effects,
     event handlers, or browser APIs. Keep the client boundary as low in the tree as possible.
   - Secrets NEVER in the client. Only `NEXT_PUBLIC_*` env vars reach the browser; the API base
     URL is public, tokens/keys are not baked into the bundle.
   - Use `next/font` for fonts, `next/link` for navigation, `next/image` where images matter.
3. **Component design**
   - Small, single-responsibility components; extract when a file exceeds ~150 lines or mixes
     concerns. Presentational vs container separation where it helps.
   - No business logic in components — put API calls in `lib/`, shared state in `context/`.
   - Lists need stable `key`s (never the array index when items can reorder).
4. **Responsive, mobile-first (REQUIRED)**
   - Tailwind mobile-first: base styles for phones, `sm:`/`md:`/`lg:` to scale up. Every screen
     must look right at ~375px AND on a laptop. No fixed pixel widths that overflow mobile.
   - Tap targets ≥ 44px; avoid hover-only affordances (touch has no hover).
5. **Accessibility (a11y)**
   - Semantic HTML (`button`, `nav`, `main`, `form`, `label`). Inputs have associated `label`s.
   - Interactive elements are keyboard-operable and focus-visible; icon-only buttons need
     `aria-label`. Sufficient color contrast. Respect `prefers-reduced-motion` for animations.
6. **Data fetching & state**
   - All network calls go through a single typed API client (`lib/api.ts`); components never
     `fetch` ad-hoc. Every async UI has explicit **loading, error, and empty** states.
   - Handle failures gracefully (user-friendly message, no unhandled promise rejections).
   - Don't put server state in global state unnecessarily; keep local state local.
7. **Design system & consistency**
   - Reuse tokens (colors, spacing, radius) from the Tailwind config / CSS variables — no random
     hex values or magic spacing. Consistent radius, shadows, and typography scale.
   - Shared primitives (`Button`, `Input`, `Spinner`) instead of re-styling ad-hoc.
8. **Performance**
   - Avoid unnecessary re-renders (stable callbacks with `useCallback` where passed to memoized
     children; `useMemo` for expensive derivations only). Don't prematurely optimize.
   - No large libraries for trivial needs. Lazy-load heavy, non-critical UI.
9. **Security**
   - Never render untrusted HTML with `dangerouslySetInnerHTML`. Render Markdown via a safe
     renderer (react-markdown) — no raw HTML passthrough.
   - Auth token stored deliberately (documented trade-off); never logged; sent only as
     `Authorization: Bearer` to our API.

## Project-Specific Conventions

- **API contract** (backend `/api/v1`): `POST /auth/signup` `{email,password,full_name?}` and
  `POST /auth/login` `{email,password}` → `{access_token, refresh_token, user_id, email}`;
  `POST /chat` `{message, session_id?}` + `Authorization: Bearer <token>` → `{response,
  session_id, agent_used}`. Keep these types in `lib/types.ts` and mirror them exactly.
- **Auth**: token + user in a client `AuthContext`; protected pages redirect to `/login` when
  unauthenticated (after hydration, not during SSR). Login/signup redirect to `/chat` if authed.
- **Language**: user-facing copy in Spanish (target users are Spanish speakers); code, identifiers,
  and comments in English.
- **Structure**: `src/app/` routes, `src/components/{chat,layout,ui}`, `src/lib/`, `src/context/`.

## Review Methodology

1. **Read whole files**, not isolated diffs.
2. **Severity-rank**: 🔴 Blocker (broken/insecure/inaccessible-core-flow) → 🟠 Major (violates a
   standard / breaks responsive or a11y) → 🟡 Minor (style/consistency). Lead with blockers.
3. **Verify responsive + a11y explicitly** — mentally render at 375px and tab through with a
   keyboard. These are first-class, not afterthoughts.
4. **Don't be a zealot**: accept pragmatic simple code; don't invent unrealistic edge cases.
5. **Anchor findings** to `file:line` with a concrete fix.

## Commands

```bash
cd frontend
npm run typecheck   # tsc --noEmit (strict) — must pass
npm run lint        # next lint
npm run build       # production build must succeed
```

## Output Format (for reviews)

- **Summary**: 1–3 lines + verdict (APPROVE / CHANGES REQUESTED).
- **Findings**: grouped by severity as `severity — file:line — problem — fix`.
- **Checklist**: the Critical Patterns marked ✅/⚠️/❌ (call out responsive + a11y).

## Anti-patterns to Flag

- `any`, `@ts-ignore` without justification, `as` casts hiding real type errors.
- `"use client"` on the whole page when only a leaf needs it.
- Ad-hoc `fetch` in components; missing loading/error/empty states.
- Non-responsive fixed widths; hover-only controls; missing `aria-label` on icon buttons.
- Inline magic colors/spacing instead of design tokens; array-index keys on dynamic lists.
- Secrets or tokens in `NEXT_PUBLIC_*`; tokens written to logs.
