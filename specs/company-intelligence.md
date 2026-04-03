# Company Intelligence — Auto-Enrichment from Customer Name

**Status**: Design Draft
**Date**: 2026-04-03
**Author**: Copilot + Moritz Beutter

---

## The Idea

When a seller types a customer name (e.g., "Siemens") in the landing page,
the system immediately web-searches for the company profile and pre-loads
structured intelligence: employee count, revenue, industry, HQ, tech stack,
recent Azure/cloud initiatives. This data then:

1. **Displays** as a sticky company card in the chat (right side, always visible)
2. **Pre-fills** shared assumptions (spend, headcount, labor rates)
3. **Informs** every agent's prompts (industry-specific drivers, architecture patterns)
4. **Disambiguates** if needed (popup: "Did you mean Siemens AG or Siemens Healthineers?")

---

## Why This Matters

Today the seller manually provides all context: "500 employees, $3.5M spend,
manufacturing industry." This is:
- **Slow** — 2-3 minutes answering assumption questions
- **Inaccurate** — sellers guess or use round numbers
- **Generic** — agents don't know if it's a $5B enterprise or a $50M mid-market

With company intelligence:
- Assumptions are **pre-populated with real data** (Wikipedia, annual reports, LinkedIn)
- Industry is **auto-detected** (no need to pick from dropdown)
- Scale context **flows through the entire pipeline** (architecture sized for real load)
- Value drivers **reference actual company metrics** ("Siemens' $72B revenue...")

---

## Data Model

### CompanyProfile

```typescript
interface CompanyProfile {
  // Identity
  name: string;                    // "Siemens AG"
  legalName?: string;              // "Siemens Aktiengesellschaft"
  ticker?: string;                 // "SIE.DE"
  website?: string;                // "siemens.com"
  logoUrl?: string;                // for display

  // Firmographics
  industry: string;                // "Manufacturing & Technology"
  subIndustry?: string;            // "Industrial Automation"
  headquarters: string;            // "Munich, Germany"
  foundedYear?: number;            // 1847
  employeeCount?: number;          // 320,000
  employeeCountSource?: string;    // "LinkedIn 2025"

  // Financials
  annualRevenue?: number;          // 72_000_000_000
  revenueCurrency?: string;        // "EUR"
  fiscalYear?: string;             // "FY2025"
  revenueSource?: string;          // "Annual Report 2025"
  itSpendEstimate?: number;        // derived: revenue × industry IT ratio
  itSpendRatio?: number;           // 0.035 (3.5% for manufacturing)

  // Technology
  cloudProvider?: string;          // "Azure + AWS (multi-cloud)"
  knownAzureUsage?: string[];      // ["Azure IoT Hub", "Azure Digital Twins"]
  erp?: string;                    // "SAP S/4HANA"
  techStackNotes?: string;         // "Heavy Siemens Xcelerator ecosystem"

  // Recent initiatives
  recentNews?: Array<{
    headline: string;
    date: string;
    url?: string;
  }>;

  // Enrichment metadata
  confidence: 'high' | 'medium' | 'low';
  sources: string[];               // ["Wikipedia", "LinkedIn", "Annual Report"]
  enrichedAt: string;              // ISO timestamp
  disambiguated: boolean;          // true if user confirmed
}
```

### How It Maps to Shared Assumptions

```
CompanyProfile.employeeCount     → affected_employees (with heuristic)
CompanyProfile.itSpendEstimate   → current_annual_spend
CompanyProfile.industry          → industry (for BV benchmarks, arch patterns)
CompanyProfile.annualRevenue     → monthly_revenue (÷12)
CompanyProfile.employeeCount     → total_users (for platform sizing)
```

The mapping isn't 1:1 — we need heuristics:

| Profile Field | Assumption | Heuristic |
|---|---|---|
| employeeCount: 320,000 | affected_employees | **NOT** 320K. Use scope heuristic: if use case mentions "R&D", estimate 5-15% of total. If "all employees", use 100%. Default: 10% = 32,000. |
| annualRevenue × itSpendRatio | current_annual_spend | Industry IT spend ratios: Manufacturing 2-4%, Financial Services 7-10%, Tech 10-15%, Healthcare 4-6%. Apply ratio to revenue. |
| annualRevenue ÷ 12 | monthly_revenue | Direct division. Used for revenue uplift capping. |
| industry | industry | Direct mapping. Used for BV benchmark search, architect pattern selection. |

**Critical insight**: The seller should STILL see and edit these derived
assumptions. The pre-fill is a starting point, not a lock. The assumption
form shows: "Based on Siemens AG profile: ~32,000 affected staff (10% of
320K employees). Adjust if your scope is different."

---

## User Flow

### Happy Path

```
1. Seller types "Siemens" in customer name field
2. After 500ms debounce, frontend sends: GET /api/company/search?q=Siemens
3. Backend web-searches, finds multiple matches
4. If single high-confidence match:
   → Frontend shows company card inline (name, logo, industry, employees, revenue)
   → Card has "✓ Correct" and "✗ Not this company" buttons
5. If ambiguous (multiple companies):
   → Frontend shows disambiguation popup:
     "Did you mean?"
     • Siemens AG (Industrial Automation, 320K employees, €72B)
     • Siemens Healthineers (Medical Devices, 71K employees, €22B)
     • Siemens Energy (Energy Technology, 96K employees, €33B)
   → Seller clicks one
6. Selected profile loads into state
7. When seller clicks "Start":
   → Shared assumptions pre-filled from profile
   → Company card pins to right side of chat
   → All agents receive profile context in prompts
```

### Edge Cases

| Scenario | Handling |
|---|---|
| Unknown company ("Acme Corp") | Show "No public data found. You'll provide details manually." |
| Private company | Partial data (industry, maybe headcount from LinkedIn). Flag as "limited data". |
| Subsidiary vs parent | Disambiguation popup with both options |
| Misspelling | Fuzzy search (Levenshtein). Show "Did you mean...?" |
| Already a customer (MSX data) | Merge: MSX opportunity data + web profile. MSX wins on conflicts. |

---

## Architecture

### Backend: `/api/company/search`

```python
@app.get("/api/company/search")
async def search_company(q: str) -> list[CompanyProfile]:
    """Search for company profile by name. Returns top 3 matches."""
    # 1. Web search for "{q} company annual report employees revenue"
    results = await web_search(f"{q} company employees revenue annual report")

    # 2. Parse results into structured profiles
    profiles = await llm_extract_profiles(q, results)

    # 3. Compute derived fields (IT spend estimate, etc.)
    for p in profiles:
        p.itSpendEstimate = _estimate_it_spend(p.annualRevenue, p.industry)

    # 4. Rank by confidence and return top 3
    return sorted(profiles, key=lambda p: p.confidence, reverse=True)[:3]
```

### LLM Extraction Prompt

The key insight: we don't need perfect data. We need **good-enough data
that the seller can correct**. The LLM extracts structured fields from
web search snippets:

```
Given these web search results about "{company_name}", extract:
- Official company name
- Industry and sub-industry
- Headquarters location
- Employee count (with source year)
- Annual revenue (with currency and fiscal year)
- Known technology stack / cloud providers
- Recent digital transformation or cloud initiatives

Return ONLY valid JSON. If a field can't be determined, set it to null.
Do NOT guess — only extract what's explicitly stated in the sources.
```

### Frontend: Company Card Component

```tsx
// Sticky card on the right side of chat
<CompanyCard>
  <Logo src={profile.logoUrl} />
  <h3>Siemens AG</h3>
  <p className="industry">Manufacturing & Technology</p>

  <div className="metrics">
    <Metric label="Employees" value="320,000" source="LinkedIn 2025" />
    <Metric label="Revenue" value="€72B" source="Annual Report FY2025" />
    <Metric label="HQ" value="Munich, Germany" />
    <Metric label="Est. IT Spend" value="$2.5B" note="3.5% of revenue" />
  </div>

  <div className="tech">
    <Tag>Azure IoT Hub</Tag>
    <Tag>SAP S/4HANA</Tag>
    <Tag>Siemens Xcelerator</Tag>
  </div>

  <div className="news">
    <NewsItem>"Siemens expands Azure AI partnership for factory automation"</NewsItem>
  </div>

  <button onClick={edit}>Edit profile</button>
</CompanyCard>
```

Position: `position: sticky; top: 0;` in a right-side panel (alongside
or replacing the agent sidebar on chat pages). On mobile: collapsible
drawer.

---

## How It Flows Through Agents

### 1. Orchestrator — Pre-filled Assumptions

When shared assumptions are generated, if a company profile exists:

```python
async def _generate_shared_assumptions(self, state):
    profile = state.company_profile  # Set from frontend

    if profile:
        # Pre-compute assumptions from profile
        defaults = {
            "affected_employees": _scope_employees(profile, state.user_input),
            "current_annual_spend": profile.itSpendEstimate or None,
            "hourly_labor_rate": _estimate_labor_rate(profile.headquarters, profile.industry),
            "total_users": profile.employeeCount,
        }
        # Still ask user to confirm, but with smart defaults
        assumptions = self._generate_assumption_questions_with_defaults(state, defaults)
    else:
        assumptions = await self._generate_shared_assumptions_llm(state)
```

The assumption form shows: "Pre-filled from Siemens AG profile. Adjust as needed."

### 2. PM Agent — Contextual Brainstorm

```python
# In brainstorm_greeting prompt:
if state.company_profile:
    context += f"""
CUSTOMER PROFILE (verified from public sources):
- {profile.name}: {profile.industry}, {profile.employeeCount:,} employees
- Revenue: {profile.annualRevenue:,} {profile.revenueCurrency} ({profile.fiscalYear})
- Known tech: {', '.join(profile.knownAzureUsage or [])}
- Recent: {profile.recentNews[0].headline if profile.recentNews else 'N/A'}

Use this context to tailor your questions and scenarios specifically
to {profile.name}'s industry, scale, and technology landscape.
"""
```

### 3. Business Value Agent — Grounded Drivers

```python
# In Phase 2 prompt:
if state.company_profile:
    ceiling_block += f"""
CUSTOMER CONTEXT:
- {profile.name} has {profile.employeeCount:,} employees globally
- Annual revenue: {profile.annualRevenue:,} {profile.revenueCurrency}
- IT spend estimated at {profile.itSpendEstimate:,}/yr ({profile.itSpendRatio*100:.1f}% of revenue)
- Compute value drivers relative to THEIR scale, not generic benchmarks
"""
```

### 4. Architect Agent — Scale-Appropriate Design

```python
# In architecture prompt:
if state.company_profile:
    scale_context = f"""
CUSTOMER SCALE:
- {profile.employeeCount:,} employees, {profile.headquarters}
- Revenue: {profile.annualRevenue:,} — design for enterprise-grade
- Known tech: {', '.join(profile.knownAzureUsage or [])} — ensure compatibility
- ERP: {profile.erp or 'Unknown'} — consider integration requirements
"""
```

### 5. Cost Agent — Right-Sized Defaults

```python
# Usage assumption defaults informed by company size:
if profile.employeeCount > 50000:
    default_storage = 5000  # GB — enterprise scale
    default_requests = 500_000
elif profile.employeeCount > 5000:
    default_storage = 1000
    default_requests = 150_000
else:
    default_storage = 200
    default_requests = 50_000
```

### 6. ROI Agent — Revenue-Anchored Analysis

```python
# Revenue uplift becomes meaningful with real revenue:
if profile.annualRevenue:
    # "1% improvement on €72B revenue = €720M opportunity"
    # Realization factor prevents hallucination (25-50%)
    pass

# Baseline includes real IT spend, not guessed:
if profile.itSpendEstimate:
    # This replaces the manual "current_annual_spend" question
    pass
```

### 7. Presentation Agent — Branded Context

```python
# Slide data includes company profile:
data["company"] = {
    "name": profile.name,
    "industry": profile.industry,
    "employees": profile.employeeCount,
    "revenue": profile.annualRevenue,
    "knownAzure": profile.knownAzureUsage,
}
# Title slide: "Azure AI Platform for Siemens AG"
# Executive summary references actual metrics
```

---

## Labor Rate Estimation

Instead of asking "What's the hourly rate?", derive it:

```python
LABOR_RATE_BY_REGION = {
    "United States": {"tech": 95, "manufacturing": 75, "healthcare": 85},
    "Germany": {"tech": 85, "manufacturing": 70, "healthcare": 75},
    "India": {"tech": 35, "manufacturing": 25, "healthcare": 30},
    "United Kingdom": {"tech": 90, "manufacturing": 70, "healthcare": 80},
    # ... more regions
}

def _estimate_labor_rate(headquarters: str, industry: str) -> float:
    region = _normalize_region(headquarters)  # "Munich, Germany" → "Germany"
    industry_key = _normalize_industry(industry)
    rates = LABOR_RATE_BY_REGION.get(region, LABOR_RATE_BY_REGION["United States"])
    return rates.get(industry_key, 75)  # fallback: $75/hr
```

---

## Employee Scoping Heuristic

320,000 employees at Siemens doesn't mean 320,000 are affected by
an "R&D digital engineering platform." The scope depends on the use case:

```python
USE_CASE_SCOPE_RATIOS = {
    "r&d": 0.05,          # 5% of company = R&D staff
    "engineering": 0.10,   # 10%
    "manufacturing": 0.15, # 15% (factory workers)
    "all employees": 1.0,  # 100%
    "it": 0.03,           # 3% = IT department
    "sales": 0.08,        # 8%
    "customer service": 0.05,
    "supply chain": 0.07,
    "default": 0.10,      # 10% if unclear
}

def _scope_employees(profile: CompanyProfile, use_case: str) -> int:
    total = profile.employeeCount or 1000
    use_case_lower = use_case.lower()
    for keyword, ratio in USE_CASE_SCOPE_RATIOS.items():
        if keyword in use_case_lower:
            return int(total * ratio)
    return int(total * USE_CASE_SCOPE_RATIOS["default"])
```

This produces: "Siemens has 320K employees. For an R&D platform,
estimated ~16,000 affected staff (5%). Adjust if needed."

---

## IT Spend Estimation

Industry IT spend as % of revenue (Gartner 2024 benchmarks):

```python
IT_SPEND_RATIOS = {
    "financial services": 0.075,    # 7.5%
    "banking": 0.080,
    "insurance": 0.065,
    "technology": 0.120,            # 12%
    "software": 0.150,
    "healthcare": 0.045,            # 4.5%
    "manufacturing": 0.035,         # 3.5%
    "retail": 0.025,                # 2.5%
    "energy": 0.020,                # 2%
    "telecommunications": 0.055,    # 5.5%
    "government": 0.040,            # 4%
    "education": 0.035,
    "default": 0.040,               # 4% average
}

def _estimate_it_spend(revenue: float | None, industry: str) -> float | None:
    if not revenue:
        return None
    industry_lower = industry.lower()
    for key, ratio in IT_SPEND_RATIOS.items():
        if key in industry_lower:
            return revenue * ratio
    return revenue * IT_SPEND_RATIOS["default"]
```

For Siemens: €72B × 3.5% = €2.52B IT spend. This becomes the ceiling
for "current_annual_spend" assumptions (the seller's specific scope
will be much smaller, but we know the company-wide number).

---

## Disambiguation UX

When multiple companies match, show a clean popup:

```
┌─────────────────────────────────────────────┐
│  Which company do you mean?                  │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ 🏭 Siemens AG                        │   │
│  │ Industrial Automation · Munich        │   │
│  │ 320K employees · €72B revenue         │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ 🏥 Siemens Healthineers              │   │
│  │ Medical Devices · Erlangen            │   │
│  │ 71K employees · €22B revenue          │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ ⚡ Siemens Energy                     │   │
│  │ Energy Technology · Munich            │   │
│  │ 96K employees · €33B revenue          │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  [ None of these — I'll provide details ]    │
└─────────────────────────────────────────────┘
```

---

## Privacy & Data Considerations

- **Only public data**: Wikipedia, annual reports, press releases, LinkedIn
  company pages. No scraping of personal data.
- **Cached per session**: Profile stored in `state.company_profile`, not
  persisted beyond the session.
- **User can edit/override**: Every derived assumption is editable.
  Profile is a suggestion, not a mandate.
- **Source attribution**: Every metric shows its source ("LinkedIn 2025",
  "Annual Report FY2025") so the seller knows what to verify.
- **No PII**: Only company-level data (employee COUNT, not employee NAMES).

---

## Implementation Phases

### Phase 1: Search + Display (1-2 days)
- Backend: `/api/company/search` endpoint using DuckDuckGo + LLM extraction
- Frontend: debounced search on customer name input
- Frontend: disambiguation popup
- Frontend: basic company card (name, industry, employees, revenue)

### Phase 2: Assumption Pre-fill (1 day)
- Wire profile → shared assumptions defaults
- Show "Pre-filled from [Company] profile" in assumption form
- Add edit capability on derived values

### Phase 3: Agent Context (1 day)
- Pass profile to PM, BV, Architect, Cost, ROI, Presentation prompts
- Each agent references actual company metrics

### Phase 4: Sticky Card (0.5 day)
- Right-side floating company card in chat
- Sticky position, doesn't scroll
- Expandable/collapsible

### Phase 5: MSX Integration (future)
- Merge web profile with MSX opportunity data
- MSX wins on conflicts (seller's own data > public data)
- Show "MSX opportunity: $500K, Stage 2" alongside company profile

---

## Open Questions

1. **Search provider**: DuckDuckGo HTML search (current) or Bing API?
   DuckDuckGo is free but rate-limited. Bing API costs ~$7/1K queries.

2. **LLM cost per search**: Each company lookup = 1 LLM call (~$0.01).
   Acceptable? Cache popular companies?

3. **Data freshness**: Web results may be 6-12 months old. Show
   "Data as of [date]" and let seller update.

4. **Non-English companies**: Japanese, Chinese companies may have
   limited English web presence. Fall back to LinkedIn?

5. **Subsidiary handling**: "BMW" → BMW AG. But what about "BMW Financial
   Services" vs "BMW Manufacturing"? Need the use case context to decide.
