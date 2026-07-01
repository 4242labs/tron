# Playbook: Browser Testing (Devtools-class MCP + Automation-class MCP)

Canonical project-local reference for browser validation in `<PROJECT_NAME>`. Both MCPs are configured locally and invoked via the agent runtime's MCP layer. This playbook is the authoritative project-local guide — skills and agents point here. The shared-KB guideline at `{shared_knowledge_path}/reference/guidelines-browser-testing.md` is the parent doc; this file inherits its rules and adds project-specific URLs, accounts, and paths.

**When it's mandatory:** every block that touches UI or visible browser behavior. Full trigger rule in `../<META_REPO_NAME>/skills/skill-validate.md §3 Browser MCP Validation`.

---

## 1. Purpose

Browser MCPs give agents first-class access to a running browser: click, fill, screenshot, inspect DOM, read console, capture network, trace performance, run Lighthouse, throttle CPU / network, take heap snapshots, and attach to an existing session. Without them, UI validation is guesswork. With them, every acceptance criterion that involves a rendered surface has observable evidence.

---

## 2. Capability matrix

| Capability | Devtools-class MCP | Automation-class MCP |
|:-----------|:-------------------:|:--------------:|
| Navigate / click / fill / type | ✓ | ✓ |
| Screenshot (viewport + full page) | ✓ | ✓ |
| Console message capture | ✓ (primary) | ✓ |
| Network request list / inspect body | ✓ (primary) | ✓ |
| Performance trace + insight | ✓ (only) | — |
| CPU / network throttling | ✓ (only) | — |
| Heap snapshot | ✓ (only) | — |
| Attach to existing browser session | ✓ (only) | — |
| Lighthouse audit | ✓ (only) | — |
| DOM snapshot + accessibility tree | ✓ | ✓ (primary) |
| Multi-tab / tab handling | — | ✓ (only) |
| File upload | ✓ | ✓ |
| Dialog handling (alert / confirm / prompt) | ✓ | ✓ |
| Form fill (structured) | ✓ | ✓ |
| Viewport resize / emulation | ✓ | ✓ |
| Wait-for helpers (selector, network idle) | ✓ | ✓ |
| Keyboard + drag events | ✓ | ✓ |

**Devtools-class strengths:** deep tracing, throttling, Lighthouse, heap, attach-to-session — anything that needs DevTools-protocol access. **Automation-class strengths:** reproducible scripted flows, multi-tab journeys, accessibility-tree-first DOM reads.

**Current reference providers:**
- Devtools-class: Chrome DevTools MCP — https://github.com/GoogleChrome/chrome-devtools-mcp
- Automation-class: Playwright MCP — https://github.com/microsoft/playwright-mcp

These are the current best-in-class recommendations, not lock-in. Workflows reference capability classes, not provider names, so replacements drop in without rewriting workflows.

---

## 3. When to use which

- **Performance trace / CPU or network throttling / heap snapshot / Lighthouse / attach-to-session** → devtools-class MCP
- **Scripted multi-step user journey with assertions** (fill form → click submit → assert redirect → assert toast) → automation-class MCP
- **Multi-tab flow** (OAuth popup, referral link in second tab) → automation-class MCP
- **One-off probe of a rendered page** → either. Prefer devtools-class when debugging (richer DevTools surface); prefer automation-class when you want to save the script.
- **Accessibility-tree inspection** → automation-class (primary) or devtools-class.
- **Console error or network-request audit during a flow** → either.

---

## 4. Setup

Both MCPs are configured in the project's `.mcp.json`. Availability is assumed — no per-session setup required.

If an MCP call returns an authentication / startup error:
- First-pass fix: restart the browser instance the MCP controls, or re-open the session.
- Check the MCP config is loaded: the tool namespaces (e.g. `mcp__chrome-devtools__*`, `mcp__playwright__*`) must be available.
- If the MCP is genuinely unreachable → apply the MCP-failure fallback rule (§7).

---

## 5. Canonical test patterns

Each recipe lists the tool-call shape (abstract — actual parameters vary by tool schema) and the evidence-save path convention.

### R1 — Navigate and screenshot (both MCPs)

**Goal:** capture a baseline screenshot of a rendered route.

- Automation-class: `browser_navigate` → `browser_take_screenshot` → save to `<EVIDENCE_DIR>/b{id}-{check}-{timestamp}.png`.
- Devtools-class: `navigate_page` → `take_screenshot` → same save path.

### R2 — Fill form, submit, assert redirect (automation-class)

**Goal:** exercise a user flow and confirm outcome.

```
browser_navigate(url)
browser_fill_form({ fields: [...] })   // or browser_fill per field
browser_click(submit selector)
browser_wait_for({ selector: expected-landing-element })
browser_take_screenshot()              // evidence
browser_snapshot()                     // DOM assertion if needed
```

Save screenshot. If console errors occurred during the flow, capture with `browser_console_messages` and save alongside.

### R3 — Performance trace on page load (devtools-class)

**Goal:** profile a route and surface bottlenecks.

```
performance_start_trace()
navigate_page(url)
wait_for(idle condition)
performance_stop_trace()
performance_analyze_insight(trace)     // summarize
```

Save trace JSON to `<EVIDENCE_DIR>/b{id}-perf-{timestamp}.json`. Include the top-N insight findings in the block's VERIFIED lines.

### R4 — Console error audit during a flow (either)

**Goal:** ensure a flow produces no console errors or warnings.

- Devtools-class: `list_console_messages` before and after the flow; diff.
- Automation-class: `browser_console_messages` after the flow; inspect errors array.

Save a JSON dump of the console output. Any error = BLOCKER for the flow.

### R5 — Network request body inspection (either)

**Goal:** verify request payload or response shape.

- Devtools-class: `list_network_requests` → `get_network_request(id)` → inspect body.
- Automation-class: `browser_network_requests` → filter by URL → inspect.

Save as `<EVIDENCE_DIR>/b{id}-network-{timestamp}.json`.

### R6 — Lighthouse audit on a deployed URL (devtools-class)

**Goal:** pre-merge perf / a11y / best-practices score check.

```
lighthouse_audit(url, categories=[performance, accessibility, best-practices, seo])
```

Save report to `<EVIDENCE_DIR>/b{id}-lighthouse-{timestamp}.json`. Block merges on regressions relative to the prior baseline.

### R7 — Attach to existing dev-server session (devtools-class)

**Goal:** inspect a specific tab already open in the developer's browser without opening a new instance (useful when state must persist).

```
list_pages()                  // find the target page by URL
select_page(pageIdx)
take_snapshot()               // inspect DOM
take_screenshot()
```

---

## 6. Evidence-capture conventions

All evidence saves to `<EVIDENCE_DIR>` (project-specific — default `~/Downloads/`; gitignored or out of repo entirely). Configure automation-class MCP with `--output-dir <EVIDENCE_DIR>` so `browser_take_screenshot` lands there automatically. Devtools-class MCP may require passing an absolute `filePath` arg to `take_screenshot`.

**File naming:** `b{block-id}-{check}-{timestamp}.{ext}` — e.g.:
- `b01-02-t3-login-smoke-20260423-1530.png`
- `b02-01-t5-checkout-flow-20260423-1602.png`
- `b03-04-t7-console-20260423-1745.json`

**Timestamp format:** `YYYYMMDD-HHMM` (UTC is preferred; local is fine if consistent within a run).

**What to capture:**
- Screenshot per acceptance criterion that has a visible surface
- Console dump (errors + warnings) at the end of each flow
- Network request list for any flow that touches an API
- Perf trace when the performance gate is in scope
- Lighthouse report when perf regression is a risk

**Linkage into block docs:**
- `skill-validate.md §4 Acceptance Criteria Verification` — cite the evidence path in the Completion Report's Evidence column.
- `skill-validate.md §5 Post-Stage-2 Hand-off` User Verification List — cite the evidence path so the user can open the screenshot directly.
- Review cycles — browser evidence is required for any UI-touching block.

---

## 7. MCP-failure fallback rule

**Canonical text** (echoed verbatim in every skill + agent that invokes browser validation):

> If the devtools-class MCP fails, proceed with the automation-class MCP for the same validation. If the automation-class MCP fails, proceed with the devtools-class MCP. If both fail, stop — do not skip validation. Escalate to user.

Any workaround that "does the validation without either MCP" (e.g., manual curl + eyeballing, visual comparison from memory) is not a substitute and must not be recorded as evidence.

---

## 8. Troubleshooting

| Symptom | First-pass remediation |
|:--------|:-----------------------|
| MCP tool call returns "tool not available" | Check `.mcp.json` / the agent runtime's MCP panel; restart the MCP runtime if the tool namespace is absent |
| Browser never reaches the page (timeout) | Check the dev server is running (default `localhost:3000`); check target URL reachable via `curl` |
| Navigate succeeds but screenshot is blank | Add `wait_for` on a known selector before the screenshot; dev-mode bundlers can render late |
| Console returns unrelated noise | Capture only the relevant flow window; note the noise in evidence but don't treat as finding |
| Port collision on dev server | `lsof -i :<PORT>` → kill the offender; do **not** change the project port |
| Automation-class tab count drift between runs | `browser_tabs` to enumerate; close orphan tabs with `browser_close` |
| Devtools-class `attach_to_session` fails | The target tab's DevTools protocol slot may already be claimed — close DevTools UI on that tab and retry |

If troubleshooting takes more than one pass, apply the §7 fallback rule and note the failure in the block's evidence file.

---

**Last updated:** <SCAFFOLD_DATE> — initial scaffold from 42Agents template.
