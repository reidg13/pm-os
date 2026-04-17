---
description: "Run competitor UX analysis. Usage: /competitor-analysis [vertical] — defaults to your product area. Spawns parallel agents, captures screenshots + performance + PageSpeed + app reviews, compiles to Obsidian + Confluence."
allowed-tools: Bash, Agent, WebSearch, WebFetch, Write, Read, Glob, Edit
---

# Competitor UX Analysis

Run a comprehensive UX, performance, and accessibility analysis across competitors. Uses a lean agent strategy (N+2 agents instead of 2N), captures screenshots and metrics via Playwright, pulls real Core Web Vitals from PageSpeed Insights, mines app store reviews, and compiles into Obsidian + optionally Confluence.

## Configuration

**Default vertical: Car Rental.** This skill is optimized for your product area competitors. To adapt for another vertical, replace the competitor table and adjust the UX areas in the agent prompts below (e.g., hotels would analyze room search, rate comparison, cancellation policies instead of car type/extras/rental flow).

If the user provides an argument (e.g., `/competitor-analysis hotels`), ask them to provide a competitor list and key UX areas before proceeding. Do NOT guess competitors for other verticals.

### Car Rental Competitors (9)

| # | Competitor | URL | App (iOS) | Type |
|---|---|---|---|---|
| 1 | Enterprise | enterprise.com/en/home.html | Enterprise Rent-A-Car | Brand |
| 2 | Hertz | hertz.com/rentacar/reservation/ | Hertz Rental Car | Brand |
| 3 | Avis | avis.com/en/home | Avis Car Rental | Brand |
| 4 | Budget | budget.com/en/home | (responsive web only) | Brand |
| 5 | National | nationalcar.com/en/home.html | National Car Rental | Brand |
| 6 | Priceline | priceline.com/rental-cars/ | Priceline | Aggregator |
| 7 | Expedia | expedia.com/Cars | Expedia | Aggregator |
| 8 | Kayak | kayak.com/cars | KAYAK | Aggregator |
| 9 | Costco Travel | costcotravel.com/Rental-Cars | (via Costco app) | Aggregator |

### Known bot-detection issues

These competitors block automated access. Agents and scripts should expect failures:

| Competitor | Blocker | Impact |
|---|---|---|
| Hertz | Imperva anti-bot | WebFetch blocked, screenshots may be blank |
| Priceline | Press-and-hold interstitial | WebFetch blocked, screenshots show interstitial |
| Expedia | CAPTCHA ("Show us your human side") | WebFetch blocked, screenshots show CAPTCHA |
| Costco Travel | Connection drop for non-browsers | WebFetch blocked, Playwright may timeout |

---

## Quick mode

If the user says `--quick` or asks for a partial run, skip PageSpeed (slow — ~5 min), accessibility audit, and app store mining. Run only: 9 UX agents + 1 performance agent + screenshots script. Total: ~3 min instead of ~10 min.

**How to detect:** Check if `$ARGUMENTS` contains "quick" or "--quick". If so, set `QUICK_MODE=true` and skip steps 1c, Script 2, and Script 3 below. In the compilation step, omit the App Store, Accessibility, and PageSpeed sections and note "Quick mode — these sections skipped" in the Executive Summary.

---

## Agent Strategy (lean)

**Total agents: N+2** (not 2N). For 9 competitors = 11 agents.

| Agent | Count | Purpose |
|---|---|---|
| UX research | 9 (parallel) | One per competitor — UX deep dive |
| Performance + complaints | 1 | Searches ALL competitors for user-reported speed issues, review ratings, known bugs |
| App store mining | 1 | Pulls iOS/Android ratings, recent reviews mentioning UX friction, for all competitors |

The Playwright scripts (screenshots, perf metrics, PageSpeed, accessibility) run in the main thread via Bash, NOT as agents.

---

## Step 1 — Launch everything in parallel

### 1a. Spawn 9 UX research agents (parallel, background)

Each agent uses WebSearch and WebFetch. **Prompt template** (replace [COMPETITOR], [URL]):

```
Research the UX of [COMPETITOR] ([URL]) for your product area booking.

IMPORTANT: Most competitor sites block WebFetch (bot detection, CAPTCHAs). Attempt WebFetch ONCE on the main URL. If it fails or returns minimal/blocked content, IMMEDIATELY switch to WebSearch for the rest of the research. Do NOT retry WebFetch on the same domain. Search for UX teardowns, reviews, blog posts, FlyerTalk/Reddit threads, and competitor analysis articles.

Analyze these 8 areas with SPECIFIC details (exact labels, counts, names — not generalities):

1. **Search form** — every field (location, dates, times, age), input types (autocomplete, calendar, dropdown), defaults, one-way toggle mechanism, loyalty/discount code fields and their labels
2. **SRP** — card layout, exact info per result (image, type, features, price format), grouping method, results visible above fold
3. **Filters & sort** — every available filter name, sort options, filter UX (sidebar/top/modal), defaults
4. **Car detail** — expand vs navigate behavior, every extra/add-on with pricing, price breakdown structure, included vs optional
5. **Error states** — no results messaging, invalid input handling, sold-out behavior, session timeout, known bugs from user forums
6. **Booking flow** — exact number of steps/pages, info collected at each step, upsell placement, confirmation details
7. **Mobile** — app availability, mobile-specific features, responsive patterns
8. **Unique/notable** — loyalty program (tier names, earn rates, redemption), price guarantees, comparison tools, anything distinctive

REQUIRED minimums — your response MUST include:
- Exact number of booking steps
- Payment methods accepted
- Cancellation policy (free cancel terms + penalty amounts)
- Loyalty program tier names and key benefits
- At least 3 specific filter names
- At least 3 specific extras/add-ons with per-day pricing

Return structured markdown: H2 for competitor name, H3 for each area.
```

### 1b. Spawn 1 performance + complaints agent (parallel, background)

```
Research user-reported performance issues and website complaints for ALL of these your product area sites: Enterprise, Hertz, Avis, Budget, National, Priceline, Expedia, Kayak, Costco Travel.

For EACH competitor, use WebSearch to find:
1. User complaints about site speed, loading, freezing (search: "[competitor] website slow", "[competitor].com not loading", "site:[flyertalk.com OR reddit.com] [competitor] website")
2. Review site ratings (Trustpilot, SiteJabber, PissedConsumer) — note the star rating and review count
3. Known technical issues (FlyerTalk consolidated threads, GitHub webcompat issues)
4. Architecture clues (what framework, CDN, anti-bot service)
5. SimilarWeb/Semrush traffic data if available (monthly visits, bounce rate)

Return structured markdown with H3 per competitor, including:
- Review site rating (e.g., "Trustpilot: 2.1/5, 5,536 reviews")
- Top 3 user-reported performance issues
- Architecture (e.g., "React SPA + Akamai CDN + Imperva anti-bot")
- Monthly traffic estimate if found
- Overall assessment: Fast / Moderate / Slow / Problematic
```

### 1c. Spawn 1 app store review mining agent (parallel, background) — skip in quick mode

```
Research the mobile app UX for these your product area competitors by mining app store reviews and ratings:

Enterprise Rent-A-Car, Hertz Rental Car, Avis Car Rental, National Car Rental, Priceline, Expedia, KAYAK, Costco (travel section)

Note: Budget has no dedicated app. Costco Travel is inside the main Costco app.

For EACH app, use WebSearch to find:
1. Current iOS App Store rating and review count (search: "site:apps.apple.com [app name]")
2. Current Google Play Store rating and review count
3. Recent negative reviews mentioning UX problems (search: "[app name] app review slow crash booking")
4. Recent positive reviews mentioning good UX patterns
5. App size (MB) if available
6. Notable recent update changes

Return structured markdown with H3 per competitor, including:
- iOS rating / review count
- Android rating / review count
- Top 3 UX complaints from reviews
- Top 2 UX praises from reviews
- Notable app-specific features not on web
```

### 1d. Run Playwright scripts (main thread, parallel with agents)

While agents are running, execute these scripts via Bash. Each script is a real, runnable file.

**Prerequisites** — install deps once (skip if already installed):
```bash
cd ~/.claude/scripts && npm init -y 2>/dev/null; npm install playwright @axe-core/playwright 2>/dev/null
```

**Script 1: Screenshots + Performance Metrics** (~2 min)
```bash
node ~/.claude/scripts/competitor-screenshots-perf.js --out /tmp/competitor-screenshots
```
Captures 1440×900 screenshots and Navigation Timing API metrics (TTFB, DOM Interactive, DOM Complete, resource count, transfer size). Batches 3 at a time. Outputs markdown table to stdout, screenshots to `/tmp/competitor-screenshots/`.

Expect 4-5 failures (Hertz, Priceline, Expedia, Costco) due to bot detection — this is normal. The script auto-classifies screenshot quality: OK (>200KB), PARTIAL (50-200KB, likely bot page), BLOCKED (<50KB).

**Script 2: PageSpeed Insights** (~5 min for both strategies) — skip in quick mode OR if no API key

Before running, check if `PAGESPEED_API_KEY` env var is set:
```bash
echo $PAGESPEED_API_KEY
```
If empty/unset, **skip this script entirely** — the free tier quota is too low for reliable results (9 URLs × retries = quota exhausted). Note "PageSpeed skipped — no API key" in the compilation.

If set:
```bash
node ~/.claude/scripts/competitor-pagespeed.js --strategy mobile
```
Fetches CrUX field data (real-user LCP, INP, CLS) and Lighthouse lab scores (Performance, Accessibility, LCP, TBT, CLS, Speed Index). Run mobile only by default; add `--strategy both` for desktop too.

Rate limiting: Uses exponential backoff on 429 errors (20s → 40s → 80s, 3 retries per URL). With a key: 5s between calls, ~2 min total.

**Script 3: Accessibility audit** (~3 min) — skip in quick mode
```bash
node ~/.claude/scripts/competitor-a11y.js --out /tmp/competitor-a11y
```
Runs axe-core WCAG 2.1 AA audit. Counts violations by severity (critical/serious/moderate/minor), lists top 3 violation types per competitor. Full JSON results saved to `--out` dir for reference.

Expect same 4-5 bot-detection failures as screenshots. Sites that block navigation will show as ERROR.

---

## Step 2 — Compile

After all agents complete and scripts finish, compile into a single document. Handle missing data gracefully — if an agent or script failed, note "Data unavailable" in that cell rather than omitting the competitor.

### 2a. Build the document

Structure the output in this exact order:

**1. Executive Summary** (3-4 sentences)
- How many competitors analyzed, what data sources used, top-line finding

**2. Comparison Table**
- Rows = 8 UX areas + Performance tier + Accessibility grade
- Columns = competitors
- Each cell: 1-2 sentence summary with the most specific detail (not "good search form" but "6-field search with calendar picker and autocomplete")
- Use "N/A" for any cell where data was unavailable

**3. Performance Section**
Combine data from 3 sources into a unified view:
- **Playwright metrics table** — from Script 1 stdout. Copy the markdown table directly.
- **PageSpeed / Core Web Vitals table** — from Script 2 stdout. Copy the markdown table directly. (Skip if quick mode or no API key)
- **User complaints + architecture** — from the performance agent (Step 1b). Summarize per competitor: review ratings, top complaints, architecture stack, traffic estimate.
- **Performance tier ranking** — synthesize all 3 sources into tiers: Fast / Moderate / Slow / Problematic. Explain the ranking.
- **Performance takeaways for Engine** — what are the benchmarks to beat? Where are competitors weakest?

**4. App Store Section** (skip if quick mode)
- Ratings comparison table (iOS + Android, from app store agent)
- Top UX complaints across apps
- Mobile-specific features comparison
- Mobile opportunities for Engine

**5. Accessibility Section** (skip if quick mode)
- axe-core violation summary table — from Script 3 stdout
- Top violation types across competitors
- Accessibility opportunity assessment for Engine

**6. Competitor Detail Sections** (one H2 per competitor)
- Do NOT paste each agent's raw output (too verbose — ~3K words each). Instead, **condense** each competitor into ~300-400 words covering the 8 areas with the most specific details (field counts, step counts, exact pricing, filter names).
- Add a "Performance & Reviews" H3 to each with: Trustpilot rating, monthly traffic, top issue, and performance tier from the perf agent.
- Add screenshots: reference the file path for OK screenshots, note "Screenshot blocked by bot detection" for BLOCKED/PARTIAL ones (auto-classified by the script).

**7. Takeaways for Engine**
Synthesize across ALL data into actionable recommendations:
- Best practices to adopt (with specific competitor examples)
- Gaps Engine could exploit
- Features Engine is missing
- UX patterns to avoid (with specific competitor anti-examples)
- Performance benchmarks to target
- Accessibility opportunities (if audit was run)
- Mobile opportunities

### 2b. Save to Obsidian
```
/Users/reidgilbertson/Documents/Obsidian Vault/Areas/Discovery + Research/Competitor UX Analysis - [Vertical].md
```

Copy screenshots to the Obsidian attachments folder if they exist.

### 2c. Publish to Confluence (if applicable)
Ask the user: "Want me to publish this to Confluence? If so, which parent page?"

If yes:
- Create page as child of specified parent using `mcp__claude_ai_Atlassian__createConfluencePage`
- Note which screenshots need manual upload (Confluence MCP doesn't support attachment upload)
- Provide the page URL

---

## Step 3 — Verify

Read the output file and confirm:
- [ ] All competitors covered (note any with partial data and why)
- [ ] Comparison table complete with all rows/columns filled (or "N/A" with reason)
- [ ] Performance section has Playwright data + qualitative findings (+ PageSpeed if API key was set and not quick mode)
- [ ] App store ratings table present (if not quick mode)
- [ ] Accessibility audit results present (if not quick mode)
- [ ] Takeaways section has actionable recommendations with specific examples
- [ ] Screenshots referenced (note blocked ones with reason)

Report to the user: "Analysis complete. [X]/[Y] competitors fully captured. [Z] blocked by bot detection (list). Saved to [path]."
