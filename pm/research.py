"""
/research command — feature research pipeline with RICE scoring.

Phases:
  1. Idea Discovery — gather vault ideas, project themes, and generate candidates
  2. Research       — per-idea competitive analysis, funnel relevance, and effort sizing
  3. RICE Scoring   — rank all ideas and write final doc to Obsidian vault

Output: Areas/Discovery + Research/Feature Research YYYY-MM-DD.md
"""
import glob
import json
import os
import subprocess
from datetime import date
from pathlib import Path

from pm import vault
from pm.config import VAULT_PATH

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"

OUTPUT_DIR = VAULT_PATH / "Areas" / "Discovery + Research"


# ── Claude subprocess helpers ────────────────────────────────────────────────

def _find_claude():
    matches = sorted(glob.glob(
        "/Users/reidgilbertson/Library/Application Support/Claude/claude-code/*/claude"
    ))
    if not matches:
        print("Error: claude CLI not found.")
        return None
    return matches[-1]


def _call_claude(claude_bin, prompt_text, label=None):
    """Run a non-interactive Claude call. Returns stdout string or None on error."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    if label:
        print(f"  {DIM}{label}...{RESET}", end="", flush=True)

    r = subprocess.run(
        [claude_bin, "-p", prompt_text],
        capture_output=True, text=True, env=env,
        stdin=subprocess.DEVNULL,
    )

    if label:
        if r.returncode == 0:
            print(f" {GREEN}done{RESET}")
        else:
            print(f" {YELLOW}failed{RESET}")

    if r.returncode != 0:
        print(f"  {YELLOW}Error: {r.stderr[:200].strip()}{RESET}")
        return None
    return r.stdout.strip()


def _parse_json_response(raw, context=""):
    """Strip markdown fences and parse JSON. Returns dict/list or None."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first line (```json or ```) and last ``` line
        raw = "\n".join(lines[1:])
        if raw.rstrip().endswith("```"):
            raw = "\n".join(raw.rstrip().split("\n")[:-1])
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"  {YELLOW}Warning: JSON parse failed{' for ' + context if context else ''}: {e}{RESET}")
        return None


# ── Context builders ─────────────────────────────────────────────────────────

def _cars_architecture_context():
    return """
Engine Cars Architecture (B2B corporate travel platform):
- Search: members (React) → cars-search-service (SAPI, Lambda) → cars-gw (gRPC :4040) → Priceline/Amadeus/Hertz
- Booking: members → he-api (Rails) → BookingProcessorWorker → engine-booking-api/cars-service (Kotlin gRPC) → cars-gw → supplier
- Key services: cars-search-service (search, external team), cars-gw (supplier gateway), engine-booking-api (booking orchestration), he-api (payments/trips/Rails)
- Shared contracts: proto packages require publishing new version before services can consume changes

T-shirt effort guide:
  S = 1 week  — single layer, UI-only or small config change
  M = 3 weeks — 2–3 layers, no new contracts needed
  L = 6 weeks — cross-service, touches shared contracts or external team
  XL = 12 weeks — new supplier, new protocol, or major architectural change

Feature change map:
  New search filter      → members, cars-search-service, cars-gw transform, supplier converter (L)
  New booking field      → members, he-api, engine-booking-api, cars-gw, supplier (L)
  New booking operation  → proto contracts + all layers above (XL)
  UI/UX improvement      → members only (S–M)
  New content endpoint   → cars-gw + supplier (M)
""".strip()


def _funnel_context():
    return """
Car Rental Funnel (Engine, Feb 2026):
  Step 1: Click - Search Cars
  Step 2: View - Car Search Results
  Step 3: Click - Car Option
  Step 4: View - Car Checkout
  Step 5: Click - Complete Car Booking

Current metrics:
  Overall funnel: ~1.99% attach rate (searches → bookings, week of Feb 16)
  GBV: ~$371K/week | ~1,123 bookings/week
  TAM gap: 77% of active accounts have never booked a car
  Key drop-off points: Step 2→3 (results to clicking an option) and Step 4→5 (checkout abandonment)
""".strip()


# ── Phase 1: Idea Discovery ──────────────────────────────────────────────────

def _phase1_discover_ideas(claude_bin, manual_ideas=None):
    """Gather inputs, generate candidate ideas via Claude, confirm with user."""
    print(f"\n{BOLD}{CYAN}Phase 1: Idea Discovery{RESET}")

    vault_ideas = vault.get_ideas()
    project_data = vault.get_project_tasks()
    active_projects = list(project_data.keys())[:12]

    print(f"  {DIM}{len(vault_ideas)} vault idea(s), {len(active_projects)} active project(s){RESET}")

    vault_text    = "\n".join(f"- {i}" for i in vault_ideas) or "None"
    projects_text = "\n".join(f"- {p}" for p in active_projects) or "None"
    manual_text   = "\n".join(f"- {i}" for i in (manual_ideas or [])) or "None"

    prompt = f"""You are helping a PM research and prioritize feature ideas for Engine's your product area product (B2B corporate travel platform).

ARCHITECTURE CONTEXT:
{_cars_architecture_context()}

FUNNEL CONTEXT:
{_funnel_context()}

EXISTING VAULT IDEAS (include all of these verbatim):
{vault_text}

CURRENTLY ACTIVE PROJECTS (avoid duplicating these):
{projects_text}

USER-PROVIDED IDEAS (include verbatim):
{manual_text}

TASK: Produce a consolidated list of 8–12 feature ideas to research. Include:
1. All vault ideas verbatim (source: "vault")
2. User-provided ideas verbatim if any (source: "input")
3. 3–5 ideas from competitive analysis of Kayak, Turo, Enterprise, Hertz.com, Expedia Cars, Hopper (source: "competitive")
4. 2–3 ideas driven by the funnel drop-off data above (source: "data")

Exclude anything clearly already in-flight as an active project.

Output ONLY valid JSON, no markdown, no explanation:
{{"ideas": [{{"title": "...", "source": "vault|input|competitive|data", "brief": "One sentence on the opportunity"}}]}}"""

    raw = _call_claude(claude_bin, prompt, label="Generating candidate ideas")
    data = _parse_json_response(raw, context="idea discovery")
    if not data:
        return None

    ideas = data.get("ideas", [])
    if not ideas:
        print(f"  {YELLOW}No ideas returned.{RESET}")
        return None

    # Print for review
    print(f"\n{BOLD}Candidate ideas ({len(ideas)}):{RESET}\n")
    source_color = {"vault": CYAN, "input": GREEN, "competitive": YELLOW, "data": YELLOW}
    for i, idea in enumerate(ideas, 1):
        color = source_color.get(idea.get("source", ""), DIM)
        print(f"  {i:2}. {idea['title']}")
        print(f"      {DIM}[{idea.get('source', '?')}] {idea.get('brief', '')}{RESET}")
    print()

    # User selection
    try:
        selection = input("Keep which? (Enter = all, or e.g. 1,3,5-8): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None

    if not selection:
        confirmed = ideas
    else:
        indices = set()
        for part in selection.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                indices.update(range(int(lo.strip()), int(hi.strip()) + 1))
            elif part.isdigit():
                indices.add(int(part))
        confirmed = [ideas[i - 1] for i in sorted(indices) if 1 <= i <= len(ideas)]

    print(f"\n{GREEN}✓{RESET} Proceeding with {len(confirmed)} idea(s).")
    return confirmed


# ── Phase 2: Per-Idea Research ───────────────────────────────────────────────

def _research_one_idea(claude_bin, idea):
    """Research a single idea. Returns a research block dict."""
    title = idea["title"]
    brief = idea.get("brief", "")
    source = idea.get("source", "")

    prompt = f"""You are a product researcher evaluating a feature idea for Engine's your product area product (B2B corporate travel platform, B2B-focused enterprise segment).

ARCHITECTURE CONTEXT:
{_cars_architecture_context()}

FUNNEL CONTEXT:
{_funnel_context()}

IDEA:
Title: {title}
Brief: {brief}
Source: {source}

TASK: Research this idea across three dimensions.

1. COMPETITIVE: What do Kayak, Turo, Hertz.com, Enterprise.com, Expedia Cars, and Hopper currently offer for this? Is Engine missing it entirely, partially, or at parity? Name specific product features you've observed.

2. FUNNEL RELEVANCE: Which funnel step does this most impact? What direction (higher CTR on options, lower checkout abandonment, etc.)? Rate potential impact as Low / Medium / High with one line of rationale.

3. EFFORT: T-shirt size using the architecture guide above. Name the specific systems that would be touched and why. Be conservative — multi-layer changes are often harder than they look.

# TODO: When LogRocket MCP is available, add session replay query here
# to surface UX friction patterns per idea (e.g., rage-clicks near car cards, filter drop-offs)

Output ONLY valid JSON, no markdown, no explanation:
{{
  "idea": "{title}",
  "competitive": {{
    "summary": "What competitors do and how Engine compares (2–3 sentences)",
    "gap": "Specific gap or 'parity' if Engine already has it"
  }},
  "funnel_relevance": {{
    "step": "Most relevant funnel step name",
    "impact_direction": "How this affects that step's conversion",
    "potential_impact": "Low|Medium|High — one-line rationale"
  }},
  "effort": {{
    "size": "S|M|L|XL",
    "weeks": 1,
    "rationale": "Which systems are touched and why",
    "key_systems": ["system1", "system2"]
  }}
}}"""

    raw = _call_claude(claude_bin, prompt, label=f"Researching '{title}'")
    block = _parse_json_response(raw, context=title)
    if not block:
        return {"idea": title, "error": "Research failed", "raw": (raw or "")[:300]}
    return block


def _phase2_research_all(claude_bin, ideas):
    """Run research for each confirmed idea sequentially."""
    print(f"\n{BOLD}{CYAN}Phase 2: Research ({len(ideas)} ideas){RESET}")
    blocks = []
    for idea in ideas:
        block = _research_one_idea(claude_bin, idea)
        blocks.append(block)
    return blocks


# ── Phase 3: RICE Scoring + Doc Generation ──────────────────────────────────

def _phase3_rice_score(claude_bin, research_blocks):
    """Score all research blocks with RICE. Returns ranked list."""
    research_json = json.dumps(research_blocks, indent=2)

    prompt = f"""You are scoring feature ideas for a your product area product at Engine (B2B corporate travel).

COMPANY CONTEXT:
- Current: ~1.99% attach rate, ~$9M GBV/year, 77% of accounts never booked cars
- Audience: B2B corporate travel managers and employees, primarily US

RICE SCORING RULES:
  R (Reach): % of active car bookers affected per quarter (0–100)
    High (70–100): affects every user on search/results page
    Medium (30–69): affects checkout or a meaningful segment
    Low  (5–29):  affects edge cases or power users only

  I (Impact): GBV/conversion lift potential on a 1–10 scale
    10 = step-change; 5 = meaningful lift; 1 = marginal

  C (Confidence): quality of evidence (0–100)
    90+: proven by multiple competitors + funnel data
    60–89: strong competitive evidence
    30–59: reasonable hypothesis
    <30:  speculative

  E (Effort): engineering weeks — S=1, M=3, L=6, XL=12

  RICE = (R × I × C/100) / E

RESEARCH DATA:
{research_json}

TASK:
1. For each idea, assign R, I, C, E scores with one-line rationale each
2. Calculate RICE score
3. Sort by RICE descending, assign rank

Output ONLY valid JSON, no markdown, no explanation:
{{
  "ranked": [
    {{
      "rank": 1,
      "idea": "...",
      "rice_score": 42.0,
      "R": 60, "I": 7, "C": 80, "E": 3,
      "R_rationale": "...",
      "I_rationale": "...",
      "C_rationale": "...",
      "E_rationale": "..."
    }}
  ]
}}"""

    raw = _call_claude(claude_bin, prompt, label="RICE scoring")
    return _parse_json_response(raw, context="RICE scoring")


def _build_markdown_doc(ideas, research_blocks, rice_data, today_str):
    """Assemble the final Obsidian markdown document."""
    research_by_title = {b.get("idea", ""): b for b in research_blocks}
    ranked = rice_data.get("ranked", [])

    lines = [
        f"# Feature Research — {today_str}",
        "",
        f"_Generated by `pm.py research` on {today_str}. Scored with RICE framework._",
        "",
        "---",
        "",
        "## Ranked Summary",
        "",
        "| Rank | Idea | RICE | R | I | C | E |",
        "|------|------|-----:|--:|--:|--:|--:|",
    ]

    for item in ranked:
        lines.append(
            f"| {item['rank']} | {item['idea']} | **{item['rice_score']:.1f}** "
            f"| {item['R']} | {item['I']} | {item['C']} | {item['E']} |"
        )

    lines += ["", "---", "", "## Deep Dives", ""]

    for item in ranked:
        title = item["idea"]
        r = research_by_title.get(title, {})
        comp   = r.get("competitive", {})
        funnel = r.get("funnel_relevance", {})
        effort = r.get("effort", {})

        effort_label = (
            f"**{effort.get('size', '?')}** ({effort.get('weeks', '?')} weeks)"
            f" | Systems: {', '.join(effort.get('key_systems', ['?']))}"
        )

        rice_line = (
            f"R={item['R']} × I={item['I']} × C={item['C']}% ÷ E={item['E']}"
            f" = **{item['rice_score']:.1f}**"
        )

        lines += [
            f"### {item['rank']}. {title} — RICE: {item['rice_score']:.1f}",
            "",
            "**Competitive Landscape**",
            "",
            comp.get("summary", "_No data_"),
            "",
            f"_Gap: {comp.get('gap', 'Unknown')}_",
            "",
            "**Funnel Impact**",
            "",
            f"- Step: {funnel.get('step', 'Unknown')}",
            f"- Direction: {funnel.get('impact_direction', 'Unknown')}",
            f"- Potential: {funnel.get('potential_impact', 'Unknown')}",
            "",
            "**Effort Estimate**",
            "",
            effort_label,
            "",
            f"_{effort.get('rationale', '')}_",
            "",
            "**RICE Breakdown**",
            "",
            rice_line,
            "",
            f"- R={item['R']}: {item.get('R_rationale', '')}",
            f"- I={item['I']}: {item.get('I_rationale', '')}",
            f"- C={item['C']}%: {item.get('C_rationale', '')}",
            f"- E={item['E']}: {item.get('E_rationale', '')}",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────────────

def run_research(manual_ideas=None):
    claude_bin = _find_claude()
    if not claude_bin:
        return

    today_str   = date.today().isoformat()
    output_file = OUTPUT_DIR / f"Feature Research {today_str}.md"

    # Phase 1 — discover and confirm ideas
    confirmed = _phase1_discover_ideas(claude_bin, manual_ideas=manual_ideas)
    if not confirmed:
        print(f"{YELLOW}No ideas confirmed. Exiting.{RESET}")
        return

    # Phase 2 — research each idea
    research_blocks = _phase2_research_all(claude_bin, confirmed)

    # Phase 3 — RICE scoring
    print(f"\n{BOLD}{CYAN}Phase 3: RICE Scoring + Document{RESET}")
    rice_data = _phase3_rice_score(claude_bin, research_blocks)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not rice_data:
        # Fallback: save raw research as JSON
        print(f"  {YELLOW}RICE scoring failed — saving raw research.{RESET}")
        output_file.write_text(
            f"# Feature Research — {today_str}\n\n"
            f"_RICE scoring failed. Raw research data below._\n\n"
            f"```json\n{json.dumps(research_blocks, indent=2)}\n```\n"
        )
        print(f"\n{GREEN}✓{RESET} Saved (raw) → {output_file}")
        return

    # Build and save markdown doc
    doc = _build_markdown_doc(confirmed, research_blocks, rice_data, today_str)
    output_file.write_text(doc)

    # Print ranked summary
    ranked = rice_data.get("ranked", [])
    print(f"\n{BOLD}{CYAN}{'━' * 60}{RESET}")
    print(f"{BOLD}Feature Research — {today_str}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 60}{RESET}\n")
    print(f"  {'#':<4} {'RICE':<8} Idea")
    print(f"  {'─'*4} {'─'*8} {'─'*42}")
    for item in ranked:
        print(f"  {item['rank']:<4} {item['rice_score']:<8.1f} {item['idea']}")
    print(f"\n{DIM}Saved → {output_file}{RESET}")
