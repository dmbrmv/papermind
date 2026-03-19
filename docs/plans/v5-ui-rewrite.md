# PaperMind v5.0 — UI Rewrite Plan

## Why

The current Web UI (`static/index.html`, ~800 lines) is a vanilla HTML/CSS/JS
SPA that proved the concept but has fundamental limitations:

- No state management — globals (`previousView`, `selPopup`, `_paperCache`)
- Event conflicts — mouseup/mousedown/click interference kills popup features
- No routing — pushState works partially, browser back is unreliable
- No component lifecycle — popups, modals, detail views all fight for DOM space
- No build tooling — can't split code, tree-shake, or add TypeScript

## Architecture

### Option A: Next.js (React) + TypeScript

**Pros**: Rich ecosystem, SSR for SEO if needed, great routing, shadcn/ui components
**Cons**: Heavy, requires Node.js build step, overkill for a local tool

### Option B: Vite + React + TypeScript

**Pros**: Fast dev server, lightweight, TypeScript, great DX
**Cons**: SPA only (fine for our use case), needs Vite build step

### Option C: Vite + Svelte + TypeScript

**Pros**: Smallest bundle, reactive by default, less boilerplate than React
**Cons**: Smaller ecosystem, fewer component libraries

### Recommendation: **Option B — Vite + React + TypeScript**

React has the widest ecosystem for KaTeX rendering (`react-katex`),
markdown rendering (`react-markdown`), and component libraries.
Vite is fast and lightweight. TypeScript catches bugs early.

## Stack

- **Vite** — build tooling, dev server with HMR
- **React 18** — UI framework
- **TypeScript** — type safety
- **React Router** — client-side routing with browser history
- **react-markdown** + **remark-math** + **react-katex** — paper content rendering
- **Zustand** or **Jotai** — lightweight state management
- **Tailwind CSS** — utility-first styling (Claude warm palette as custom theme)
- **shadcn/ui** — accessible component primitives

## Features (matching current UI + fixing gaps)

### Core Views
- **Browse** — paper list with topic filter, search, pagination
- **Paper Detail** — title, abstract, rendered equations (KaTeX), rendered markdown content, clickable citations (orange=KB, blue=search), DOI links
- **Cite** — textarea for claim, auto-cite results with KB/external/ingested sections
- **Explain** — parameter lookup with LaTeX-rendered definitions
- **Sessions** — list with click-through to detail, entry cards with tags

### New Features (v5.0)
- **Text selection context menu** — proper React portal, no event conflicts
- **Paper summaries** — brief/summary/deep_dive tabs (requires ollama backend)
- **Citation graph visualization** — d3.js or react-force-graph for paper relationships
- **Keyboard navigation** — Cmd+K search, arrow keys for list navigation
- **Dark/light theme toggle** — CSS variables, system preference detection
- **Responsive design** — proper mobile layout, not just hiding sidebar

### API Contract

The REST API at `/api/v1/` is stable and well-tested (18 endpoints, 643 tests).
The UI is a pure consumer — no backend changes needed for v5.0.

Key endpoints used by the UI:
```
GET  /api/v1/papers                    → paper list
GET  /api/v1/papers/{id}               → paper detail
GET  /api/v1/search/scan?q=...         → search with scores
GET  /api/v1/stats                     → KB stats
GET  /api/v1/topics                    → topic list
GET  /api/v1/sessions                  → session list
GET  /api/v1/sessions/{id}             → session detail
POST /api/v1/analysis/explain          → parameter explain
POST /api/v1/analysis/auto-cite        → auto-cite
POST /api/v1/analysis/cite             → find references
POST /api/v1/analysis/bib-gap          → bibliography gap analysis
```

## Project Structure

```
papermind-ui/           # or papermind/ui/ subdirectory
├── src/
│   ├── components/     # reusable UI components
│   │   ├── PaperCard.tsx
│   │   ├── PaperDetail.tsx
│   │   ├── EquationBlock.tsx
│   │   ├── CitationLink.tsx
│   │   ├── SelectionPopup.tsx
│   │   ├── SearchBar.tsx
│   │   └── ExplainBox.tsx
│   ├── views/          # page-level views
│   │   ├── BrowseView.tsx
│   │   ├── CiteView.tsx
│   │   ├── SessionsView.tsx
│   │   └── ExplainView.tsx
│   ├── hooks/          # custom hooks
│   │   ├── useApi.ts
│   │   ├── usePapers.ts
│   │   └── useTextSelection.ts
│   ├── store/          # state management
│   │   └── appStore.ts
│   ├── api/            # typed API client
│   │   └── client.ts
│   ├── App.tsx
│   └── main.tsx
├── tailwind.config.ts  # Claude warm palette
├── vite.config.ts
├── tsconfig.json
└── package.json
```

## Deployment Options

1. **Bundled with papermind** — build static assets, serve from FastAPI
   `papermind serve --http` serves the built UI at `/`
2. **Standalone dev server** — `npm run dev` for development
3. **Docker** — Dockerfile with multi-stage build (Node for UI, Python for API)

## Migration Path

1. Scaffold Vite + React + TS project
2. Port Browse view first (simplest, most used)
3. Port Paper Detail with react-markdown + react-katex
4. Port Cite and Explain views
5. Add selection popup as React portal
6. Add paper summaries (ollama integration)
7. Build, bundle, serve from FastAPI
8. Remove old `static/index.html`

## Estimated Effort

- Scaffolding + Browse: 1 session
- Paper Detail + rendering: 1 session
- Cite + Explain + Sessions: 1 session
- Selection popup + summaries: 1 session
- Polish + deploy: 1 session

~5 focused sessions total.
