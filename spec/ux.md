# UX and design system

GovWren should feel like a well-made professional tool: calm, quick, and exact. People come to it for serious work, often reluctantly, so the design has two jobs. For the requester it must make the right thing the easy thing. For the governance team it must make a large amount of structured information readable at a glance.

## Design principles

1. **Answer first.** Every page leads with the answer to the question that brought the person there: *may I?*, *what do I owe?*, *what needs my decision?*, *where do we stand?*
2. **Short by default, deep on demand.** Lists are dense and scannable. Detail opens beside them, not instead of them.
3. **Show the reasoning.** A tier, a route, or a requirement is never a bare label. One click shows what produced it.
4. **The URL is the state.** Filters, sort, tabs, and the open record all live in the URL. Back works, and every view can be shared.
5. **Standing is always visible.** Wherever a record appears, so do its tier and its standing with governance.
6. **Keyboard first, mouse friendly.** Everything is reachable by keyboard. Queues are fastest with keys.
7. **Honest states.** Missing is shown as missing, lapsed as lapsed, automatic as automatic.
8. **Accessible.** WCAG 2.2 AA in every palette and mode.

## Identity

### The mark

The logo is a **stylized wren**: a compact, rounded body with the short, sharply cocked tail that makes a wren recognizable in silhouette. It is drawn from a few geometric strokes in a single color so that it holds at 16 pixels as a favicon and scales to a hero. The upturned tail is drawn so that, with the line of the back, it also reads as a **check mark**: the bird and the approval in one shape.

- Supplied as SVG in three forms: the mark alone, the mark with the wordmark beside it, and a single-color version for print and dark backgrounds.
- The wordmark sets *Gov* in regular weight and *Wren* in semibold, in the interface font.
- Clear space equal to the height of the tail on every side.

An adopting organization replaces the mark and wordmark with its own. "GovWren" then appears only as a small "Powered by GovWren" link in the footer, which can be turned off.

### Voice

Plain words, short sentences, no jargon the requester did not bring with them. The interface says "May I use this?" and "What we need from you", and never "Submit intake artifact". Buttons name their outcome ("Approve with conditions"), errors say what to do next, and empty states teach.

## Visual language

### Tokens

All visual values are CSS custom properties defined once in `tokens.css`. Colors are `light-dark()` pairs in `oklch()`, so each has a day and a night value side by side and the two stay balanced.

- **Surfaces:** `--bg`, `--surface-1..3`, `--border`, `--border-strong`, and `--control-border` for the edge of form fields, which must reach 3:1 against the page
- **Text:** `--text`, `--text-muted`, `--text-subtle`, `--text-inverse`
- **Accent:** `--accent`, `--accent-hover`, `--accent-strong`, `--accent-soft`, `--on-accent`
- **Standing:** `--ok`, `--warn`, `--danger`, `--info`, `--neutral`, each with a `-soft` tint
- **Tier:** `--tier-1..4`, an ordinal ramp in one hue (see below)
- **Record types:** `--rec-usecase`, `--rec-system`, `--rec-model`, `--rec-dataset`, `--rec-vendor`, each with a `-soft` tint
- **Series:** `--series-0..5`, categorical colors for charts
- **Spacing:** 4 px base scale (`--space-1` = 4 px … `--space-10` = 64 px)
- **Radius:** `--radius-s` 6 px, `--radius-m` 10 px, `--radius-l` 16 px
- **Elevation:** three shadow levels, deeper in dark mode
- **Motion:** 120, 200, and 320 ms durations, all disabled under `prefers-reduced-motion`

### Tier and standing are different things

A high-risk use that has been reviewed and approved is not a problem; it is the system working. So tier and standing never share colors.

- **Tier** uses its own ordinal ramp in a single hue (plum), light to deep, always with a glyph of one to four bars and the tier's name. It reads as *how much is at stake*.
- **Standing** uses the conventional green, amber, and red, always with an icon and a word. It reads as *is this in order*.

Color is never the only signal for either.

| Standing | Color | Mark |
|---|---|---|
| Approved | Green | ● |
| Approved with conditions | Green | ◐ |
| In review, submitted | Blue | ◔ |
| With requester | Amber | ↩ |
| Lapsed, suspended | Red | ! |
| Declined | Red, quiet | ✕ |
| Draft, withdrawn, retired | Grey | ○ |

### Record types

Each record type has one hue and one icon, used consistently in chips, list rows, graph nodes, and page headers. A test keeps record hues well away from the standing colors and the tier ramp in every palette.

| Record | Hue | Icon idea |
|---|---|---|
| Use case | Blue | Target |
| AI system | Teal | Window with a spark |
| Model | Violet | Stacked layers |
| Dataset | Ochre | Cylinder |
| Vendor | Slate | Storefront |

### Typography

- **Font:** the platform's system UI stack. Nothing to download. Tabular numerals in tables and figures.
- **Scale:** 12 / 13 / 14 (body) / 16 / 18 / 20 / 24 / 30 / 36 px.
- **Weights:** 400, 500, 600.

### Themes: mode and palette

Appearance has two independent choices, under **Appearance** in the top bar and in the command palette.

- **Mode:** light, dark, or follow the system.
- **Palette:** a named set of colors with a day and a night version. The organization sets the default; each person may choose another, remembered in their browser.

| Palette | By day | After dark |
|---|---|---|
| **Wren** (default) | Warm paper neutrals, ink text, a juniper-green accent, a thin russet rule | Warm charcoal, soft juniper accent |
| **Slate** | Cool white and grey, cobalt accent; the conventional enterprise look | Blue-black surfaces, bright cobalt accent |
| **Garnet** | Neutral greys with a deep red accent, for the many institutions whose colors are red | Near-black with a softened garnet accent |

Every palette and mode is checked for AA contrast by sampling the rendered text of the main pages against its real background.

### Branding

An organization makes GovWren its own in **Admin → Appearance**, with a live preview and no file editing:

- product name and organization name,
- logo for light and dark backgrounds, and a favicon,
- default palette, and optionally its own accent color,
- from wave 6, a full custom palette, a message and image on the sign-in page, footer links, an email header, and its own words for key terms ("use case" may be "AI project"; "unit" may be "department").

The server generates `theme.css` from these settings. A chosen accent is checked for contrast against its backgrounds before it can be saved, lightened automatically for dark mode, and given readable text on top. Uploaded images are size-limited, type-checked, and, for SVG, sanitized.

## Information architecture

```text
Top bar:  [mark / product name]  [ ⌘K Search… ]  [+ New request]  [🔔] [appearance] [me]

Sidebar:  Home
          Catalog
          Inventory     Use cases · AI systems · Models · Datasets · Vendors
          Reviews       Queue · Sessions                       (reviewers, governance)
          Oversight     Attestations · Incidents · Exceptions · Actions
          Assurance     Risks · Controls · Frameworks · Policies · Evidence
          Reports       Dashboard · Portfolio · Reports
          ───────────
          Admin         Program · People and units · Appearance · System
```

- Each person sees only the sections their roles use. A member sees Home, Catalog, and their own records under Inventory.
- **Command palette (⌘K or Ctrl-K):** find any record by reference or name, jump to a page, or run an action ("New request", "Report an incident", "Switch to dark").
- The sidebar collapses to icons on narrow screens and becomes a drawer on a phone. Requesting, attesting, and reviewing all work on a phone; administration assumes a larger screen.

## Key screens

| Screen | Purpose | Highlights |
|---|---|---|
| **Home** | What I owe and what is waiting on others | One list, overdue first: tasks, conditions, attestations, drafts, requests in progress. A large "May I use…?" search. For governance, queue counts and what is at risk of running late |
| **Catalog** | May I use this tool? | Search-first cards with standing, permitted data shown as a simple scale, and terms. "Register my use" on each. "Not here? Ask for it" |
| **New request** | The intake form | One section at a time with a progress rail. A side panel shows the likely tier, the factors behind it, and the reviews it would need, updating as answers change. Saves continuously |
| **Use case** | Everything about one use | Header with reference, tier, standing, owners, and next date. Tabs: Overview, Answers, Reviews, Conditions, Links, Risks and controls, Evidence, History. A "why this tier" panel |
| **AI system, Model, Dataset, Vendor** | One record in context | The same header and tabs, with what each type adds: agent profile, model card, agreements. "Used by" and "Depends on" lists |
| **Dependency graph** | How things connect | A focused graph around one record, with a list fallback. Inherited risks and incidents marked on the nodes they reach |
| **Review queue** | Work through reviews | Split view: the queue on the left with age and due date; the request on the right with the reviewer's part highlighted. Keyboard to move, claim, and record a finding |
| **Decision packet** | Decide | Request summary, tier reasons, each finding, proposed conditions as one editable list, objections called out, related history. Outcome buttons with a required rationale |
| **Session** | Run a committee meeting | Agenda of packets in order; decide each; minutes at the end |
| **Attestation** | Confirm what is true | For an owner, their records with three choices each and "confirm all unchanged". For a steward, the unit's list, an add form, and the attestation |
| **Incident** | Record and resolve | Timeline, linked records, severity, actions, and what was learned |
| **Framework** | Readiness | The five-state summary bar, the requirement tree with states, and the controls and evidence behind any requirement |
| **Dashboard** | Where the program stands | Portfolio by tier and standing, requests and decisions over time, turnaround against target, coverage, and what is overdue, each tile linking to the records behind it |
| **Admin: Program** | Shape the program | Form builder with preview; scoring model editor showing which records would change tier; rules editor; vocabularies; condition templates |
| **Admin: Appearance** | Brand it | Names, logos, palette, and accent with a live preview and contrast results |

## Components

Each is a small ES module that returns DOM. There is no virtual DOM and no templating library.

- **Layout:** app shell, sidebar, top bar, page header, split view, drawer, modal, tabs
- **Records:** record chip (icon, reference, name), tier badge with a reasons popover, standing pill, owner list, completeness meter
- **Data display:** data table (sortable, column chooser, dense mode, saved views), definition list, stat tile, timeline, activity feed, empty state, skeleton
- **Forms:** the form renderer (every question type, conditional visibility, validation, autosave), record picker, person picker, unit picker, file drop, date picker
- **Workflow:** task card, finding selector, condition list editor, decision bar, discussion thread with requester-visible and internal comments
- **Feedback:** toast with undo, inline alert, due-date badge, progress bar
- **Charts (SVG):** bar, stacked bar, line, donut, heatmap, and the five-state readiness bar, each with a table behind it
- **Graph:** a focused node-link view with a list fallback

## Interaction details

- **Tier badge:** clicking it opens the reasons: each factor, its level, the answer that set it, and any floor. An overridden tier shows both values and the reason.
- **Due dates:** shown as relative time with the date on hover; amber inside the warning window; red when past.
- **Autosave:** forms save a moment after each change and say so quietly. Nothing is lost by closing a tab.
- **Undo:** reversible actions (claiming a task, adding a link, dismissing a notice) show a toast with Undo. Decisions and attestations are not undoable; they ask for confirmation and are superseded, never erased.
- **History:** every record's History tab shows changes as a readable timeline ("Tier changed from Moderate to High by … because …"), filterable by kind, with an "as of" date control from wave 5.
- **Empty states teach:** an empty inventory explains how to add the first record or import a spreadsheet; an empty queue says so plainly and shows what is coming due.
- **Printing:** dossiers, decision packets, and reports have print styles and produce clean PDFs from the browser's print dialog.

## Accessibility checklist

- Landmarks, headings in order, and a skip link
- A visible focus ring (2 px, offset) in every palette and mode
- Every control reachable and operable by keyboard; no traps in drawers or modals
- `aria-live` announcements for saves, async results, and workflow actions
- Form errors tied to their fields and summarized at the top
- Charts and graphs have tabular alternatives
- Targets at least 24 × 24 px
- Respects `prefers-reduced-motion` and `prefers-contrast`
- An automated audit runs over every documented screen, and a manual screen-reader script is run before each release

## Performance budgets

| Budget | Target |
|---|---|
| App shell JS and CSS (gzipped) | ≤ 100 KB |
| Each part loaded on first use (gzipped) | ≤ 40 KB |
| First meaningful render on a laptop | < 1 s |
| List API response (p95) at 10,000 records | < 200 ms |
| Record page API response (p95) | < 200 ms |
| Search response (p95) | < 200 ms |
| Tier indicator update after an answer | < 50 ms (computed in the browser) |
| Next item in a queue after an action | < 100 ms (prefetched) |
| Demo organization build | < 60 s |
