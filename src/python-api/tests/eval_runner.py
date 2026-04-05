"""
OneStopAgent Evaluation Runner
Runs full pipeline scenarios, evaluates quality, produces structured report.
Optionally uses LLM-as-judge for deep quality evaluation.

Usage:
    python -m tests.eval_runner                    # Run against localhost:8000
    python -m tests.eval_runner --url https://...  # Run against deployed instance
    python -m tests.eval_runner --scenarios nike    # Run single scenario
    python -m tests.eval_runner --judge             # Enable LLM quality judge
"""

import argparse
import json
import time
import sys
import os
import re
import httpx
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Scenarios ────────────────────────────────────────────────────

SCENARIOS = {
    "nike": {
        "description": "AI-powered customer engagement platform for Nike's retail operations",
        "customer_name": "Nike",
        "active_agents": ["business_value", "architect", "cost", "roi"],
        "expected": {
            "industry_contains": ["consumer", "retail", "goods", "manufacturing", "footwear", "apparel"],
            "min_employees": 50000,
            "min_revenue": 40_000_000_000,
            "bv_min_drivers": 2,
            "bv_min_annual_value": 100_000,
            "arch_min_components": 3,
            "arch_has_mermaid": True,
            "cost_min_monthly": 1000,
            "cost_max_monthly": 500_000,
            "roi_positive": True,
        },
    },
    "siemens": {
        "description": "Predictive maintenance platform using IoT and AI for Siemens manufacturing lines",
        "customer_name": "Siemens",
        "active_agents": ["business_value", "architect", "cost", "roi"],
        "expected": {
            "industry_contains": ["manufacturing", "industrial", "technology", "conglomerate"],
            "min_employees": 200000,
            "min_revenue": 50_000_000_000,
            "bv_min_drivers": 2,
            "bv_min_annual_value": 100_000,
            "arch_min_components": 3,
            "arch_has_mermaid": True,
            "cost_min_monthly": 1000,
            "cost_max_monthly": 500_000,
            "roi_positive": True,
        },
    },
    "startup": {
        "description": "AI chatbot for customer support automation",
        "customer_name": "",  # No company - should use defaults
        "active_agents": ["business_value", "architect", "cost", "roi"],
        "expected": {
            "bv_min_drivers": 1,
            "bv_min_annual_value": 10_000,
            "arch_min_components": 2,
            "arch_has_mermaid": True,
            "cost_min_monthly": 100,
            "cost_max_monthly": 100_000,
            "roi_positive": True,
        },
    },
}

# ── Data classes ─────────────────────────────────────────────────


@dataclass
class Finding:
    severity: str  # "error", "warning", "info"
    agent: str
    message: str
    details: Optional[str] = None


@dataclass
class AgentResult:
    agent: str
    status: str  # "success", "error", "skipped", "needs_info"
    content: str = ""
    data: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    duration_s: float = 0.0


@dataclass
class ScenarioResult:
    scenario: str
    status: str  # "pass", "fail", "partial"
    agent_results: dict = field(default_factory=dict)  # agent_name -> AgentResult
    findings: list = field(default_factory=list)
    total_duration_s: float = 0.0
    error: Optional[str] = None


class LLMJudge:
    """Uses Azure OpenAI to evaluate agent output quality."""

    ENDPOINT = os.environ.get(
        "AZURE_OPENAI_ENDPOINT",
        "https://demopresentations.services.ai.azure.com",
    )
    DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4")
    API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

    AGENT_PROMPTS = {
        "pm": (
            "You are evaluating the Project Manager agent's output for an Azure solution scoping tool.\n"
            "The PM brainstorms use cases based on the customer scenario.\n\n"
            "Evaluate:\n"
            "1. RELEVANCE: Are the suggested use cases relevant to this company/industry?\n"
            "2. SPECIFICITY: Does it reference real Azure services, not vague 'cloud' talk?\n"
            "3. COMPLETENESS: Does it cover multiple angles (cost savings, revenue, efficiency)?\n"
            "4. REALISM: Would a real Azure seller find this useful for a customer meeting?\n"
        ),
        "business_value": (
            "You are evaluating the Business Value agent's output.\n"
            "It should quantify value drivers with dollar amounts based on company size.\n\n"
            "Evaluate:\n"
            "1. MATH: Do the calculations make sense? (hours × rate = cost, etc.)\n"
            "2. SCALE: Are dollar amounts proportional to the company size? "
            "A $50B-revenue company should see 7-9 figure impacts, not $10K.\n"
            "3. DRIVERS: Are there at least 2 concrete value drivers with numbers?\n"
            "4. REALISM: Would a CFO find these estimates credible? Not too high (>$1B for a single AI project), not too low?\n"
            "5. METHODOLOGY: Does it explain its calculation approach?\n"
        ),
        "architect": (
            "You are evaluating the System Architect agent's output.\n"
            "It should produce an Azure architecture for the described solution.\n\n"
            "Evaluate:\n"
            "1. FIT: Does the architecture match the use case described? (e.g., IoT for predictive maintenance)\n"
            "2. AZURE SERVICES: Are real, appropriate Azure services named? (not generic 'database')\n"
            "3. DIAGRAM: Is there a Mermaid diagram that shows component relationships?\n"
            "4. COMPLETENESS: Does it cover data layer, compute, AI/ML, networking, security?\n"
            "5. ISOLATION: The output should NOT contain business value data (dollar amounts, ROI, drivers).\n"
            "   If you see value drivers or dollar calculations, flag as CRITICAL regression.\n"
        ),
        "cost": (
            "You are evaluating the Cost Specialist agent's output.\n"
            "It should estimate Azure costs for the proposed architecture.\n\n"
            "Evaluate:\n"
            "1. ALIGNMENT: Do the costed services match the architecture? (same services, not different ones)\n"
            "2. BREAKDOWN: Is there a per-service cost breakdown with monthly/annual figures?\n"
            "3. RANGE: Are costs reasonable for the scale? Enterprise AI: $5K-$200K/mo typically.\n"
            "4. SPECIFICS: Are SKUs, tiers, or instance sizes mentioned? Not just 'Azure OpenAI: $X'.\n"
            "5. COMPLETENESS: Are all major architecture components costed?\n"
        ),
        "roi": (
            "You are evaluating the ROI agent's output and dashboard data.\n"
            "It should combine business value and costs into ROI analysis.\n\n"
            "Evaluate:\n"
            "1. MATH: Does ROI% ≈ (Annual Benefits - Annual Costs) / Annual Costs × 100?\n"
            "   Check if the numbers add up roughly.\n"
            "2. PAYBACK: Is payback period reasonable? (3-24 months typical for enterprise AI)\n"
            "3. COHERENCE: Do annual benefits come from the BV agent's numbers?\n"
            "   Do annual costs come from the Cost agent's numbers?\n"
            "4. CONFIDENCE: Is the confidence level justified given assumptions?\n"
            "5. CREDIBILITY: Would a C-level exec find this ROI analysis convincing?\n"
        ),
        "cross_agent": (
            "You are evaluating the coherence across ALL agents in an Azure solution scoping pipeline.\n"
            "The pipeline is: PM use cases → BV value drivers → Architect design → Cost estimate → ROI.\n\n"
            "Evaluate:\n"
            "1. THREAD: Does the architecture address the PM's suggested use cases?\n"
            "2. BV→ARCH ALIGNMENT: Does the architecture enable the value drivers identified by BV?\n"
            "3. ARCH→COST MATCH: Are the same Azure services in the architecture and cost breakdown?\n"
            "4. COST→ROI FLOW: Do the ROI numbers incorporate both BV benefits and Cost expenses?\n"
            "5. NARRATIVE: Does the entire pipeline tell a coherent story from idea to ROI?\n"
            "6. NO DATA LEAKS: Architect output should NOT contain BV dollar amounts.\n"
        ),
    }

    def __init__(self):
        self.token = os.environ.get("AZURE_OPENAI_TOKEN", "")
        if not self.token:
            try:
                import subprocess
                self.token = subprocess.check_output(
                    ["az", "account", "get-access-token",
                     "--resource", "https://cognitiveservices.azure.com",
                     "--query", "accessToken", "-o", "tsv"],
                    text=True,
                ).strip()
            except Exception:
                pass
        self.client = httpx.Client(timeout=120.0)

    def _call_llm(self, system: str, user: str) -> str:
        """Call Azure OpenAI and return the response text."""
        url = (
            f"{self.ENDPOINT}/openai/deployments/{self.DEPLOYMENT}"
            f"/chat/completions?api-version={self.API_VERSION}"
        )
        resp = self.client.post(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_completion_tokens": 1500,
            },
        )
        if resp.status_code != 200:
            return f"[LLM judge error: {resp.status_code} {resp.text[:200]}]"
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def judge_agent(self, agent: str, scenario_desc: str, company: str,
                    output: str, all_outputs: dict[str, str] | None = None) -> list[Finding]:
        """Judge a single agent's output quality. Returns findings."""
        if not output.strip():
            return []

        system_prompt = self.AGENT_PROMPTS.get(agent, "")
        if not system_prompt:
            return []

        system_prompt += (
            "\n\nRespond with a JSON object:\n"
            '{"score": 1-10, "issues": [{"severity": "error"|"warning"|"info", "message": "..."}], '
            '"summary": "one-line quality summary"}\n'
            "Only flag real problems. Score 7+ means acceptable quality."
        )

        if agent == "cross_agent":
            user_content = f"**Scenario**: {scenario_desc}\n**Company**: {company or 'Generic startup'}\n\n"
            for agent_name, agent_output in (all_outputs or {}).items():
                user_content += f"### {agent_name} output:\n{agent_output[:4000]}\n\n"
        else:
            user_content = (
                f"**Scenario**: {scenario_desc}\n"
                f"**Company**: {company or 'Generic startup'}\n\n"
                f"**Agent output**:\n{output[:8000]}"
            )

        try:
            raw = self._call_llm(system_prompt, user_content)
            return self._parse_judge_response(raw, agent)
        except Exception as e:
            return [Finding("warning", f"judge_{agent}", f"LLM judge failed: {e}")]

    def _parse_judge_response(self, raw: str, agent: str) -> list[Finding]:
        """Parse structured JSON from LLM judge response."""
        findings: list[Finding] = []
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw.strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            brace_match = re.search(r'\{[^{}]*"score"[^{}]*\}', raw, re.DOTALL)
            if brace_match:
                try:
                    data = json.loads(brace_match.group())
                except json.JSONDecodeError:
                    findings.append(Finding("info", f"judge_{agent}",
                        f"Judge score: unparseable | Raw: {raw[:200]}"))
                    return findings
            else:
                findings.append(Finding("info", f"judge_{agent}",
                    f"Judge response (raw): {raw[:300]}"))
                return findings

        score = data.get("score", 0)
        summary = data.get("summary", "")
        issues = data.get("issues", [])

        # Add score as info finding
        score_label = "✅" if score >= 7 else "⚠️" if score >= 4 else "❌"
        findings.append(Finding("info", f"judge_{agent}",
            f"{score_label} Quality score: {score}/10 — {summary}"))

        # Add specific issues
        for issue in issues:
            sev = issue.get("severity", "info")
            msg = issue.get("message", "")
            if sev in ("error", "warning", "info") and msg:
                findings.append(Finding(sev, f"judge_{agent}", msg))

        return findings


class EvalRunner:
    def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "eval-runner",
                 use_judge: bool = False):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"x-user-id": self.user_id},
            timeout=300.0,  # 5 min timeout for LLM calls
        )
        self.results: list[ScenarioResult] = []
        self.judge = LLMJudge() if use_judge else None

    def run_all(self, scenario_names: list[str] | None = None):
        """Run all (or specified) scenarios."""
        scenarios = scenario_names or list(SCENARIOS.keys())
        print(f"\n{'='*60}")
        print(f"  OneStopAgent Evaluation Runner")
        print(f"  {len(scenarios)} scenario(s) | {self.base_url}")
        print(f"{'='*60}\n")

        for name in scenarios:
            if name not in SCENARIOS:
                print(f"⚠️  Unknown scenario: {name}, skipping")
                continue
            result = self.run_scenario(name, SCENARIOS[name])
            self.results.append(result)
            self._print_scenario_summary(result)

        self._write_report()

    def run_scenario(self, name: str, scenario: dict) -> ScenarioResult:
        """Run a single scenario through the full pipeline."""
        print(f"\n{'─'*50}")
        print(f"🔄 Scenario: {name}")
        print(f"   {scenario['description'][:80]}")
        print(f"{'─'*50}")

        result = ScenarioResult(scenario=name, status="pass")
        start = time.time()
        expected = scenario.get("expected", {})

        try:
            # ── Step 0: Check server health ──
            health = self.client.get("/health")
            if health.status_code != 200:
                result.status = "fail"
                result.error = f"Server not healthy: {health.status_code}"
                return result

            # ── Step 1: Company search (if customer name provided) ──
            company_profile = None
            if scenario.get("customer_name"):
                print(f"   🔍 Searching company: {scenario['customer_name']}")
                company_profile = self._search_company(scenario["customer_name"], expected, result)

            # ── Step 2: Create project ──
            print(f"   📁 Creating project...")
            project_id = self._create_project(scenario, company_profile)
            if not project_id:
                result.status = "fail"
                result.error = "Failed to create project"
                return result

            # ── Step 3: Send initial message → PM brainstorm ──
            print(f"   💬 Starting conversation...")
            messages = self._chat(project_id, scenario["description"])
            self._analyze_pm_response(messages, result)

            # Check for errors in PM — abort early if auth/LLM failed
            if any(f.severity == "error" for f in result.findings):
                result.status = "fail"
                result.error = "PM agent failed — likely auth or LLM issue"
                return result

            # ── Step 4: Send "proceed" → get shared assumptions form ──
            print(f"   ➡️  Proceeding past PM...")
            messages = self._chat(project_id, "proceed")

            # Handle assumptions (shared or BV-specific)
            assumption_msg = self._find_message_by_type(messages, "assumptions_input")
            if assumption_msg:
                print(f"   📝 Submitting assumptions (step={assumption_msg.get('metadata', {}).get('step', '?')})...")
                assumptions = assumption_msg.get("metadata", {}).get("assumptions", [])
                values = self._build_default_assumptions(assumptions)
                messages = self._chat(project_id, json.dumps(values))

            # After assumptions → BV should run; look for BV result or second assumptions form
            bv_assumption = self._find_message_by_type(messages, "assumptions_input")
            if bv_assumption and bv_assumption.get("metadata", {}).get("step") in ("business_value", "bv"):
                print(f"   📝 Submitting BV assumptions...")
                bv_assumptions = bv_assumption.get("metadata", {}).get("assumptions", [])
                bv_values = self._build_default_assumptions(bv_assumptions)
                messages = self._chat(project_id, json.dumps(bv_values))

            self._analyze_bv_response(messages, expected, result)

            # ── Step 5: Approve BV → Architect ──
            if self._has_content_from(messages, "business_value") or self._needs_approval(messages, "business_value"):
                print(f"   ✅ Approving BV → Architect...")
                messages = self._chat(project_id, "proceed")
                self._analyze_architect_response(messages, expected, result)

                # ── Step 6: Approve Architect → Cost ──
                if self._has_content_from(messages, "architect") or self._needs_approval(messages, "architect"):
                    print(f"   ✅ Approving Architect → Cost...")
                    messages = self._chat(project_id, "proceed")

                    # Cost might need its own assumptions
                    cost_assumption_msg = self._find_message_by_type(messages, "assumptions_input")
                    if cost_assumption_msg:
                        print(f"   📝 Submitting cost assumptions...")
                        cost_assumptions = cost_assumption_msg.get("metadata", {}).get("assumptions", [])
                        cost_values = self._build_default_assumptions(cost_assumptions)
                        messages = self._chat(project_id, json.dumps(cost_values))

                    self._analyze_cost_response(messages, expected, result)

                    # ── Step 7: Approve Cost → ROI ──
                    if self._has_content_from(messages, "cost") or self._needs_approval(messages, "cost"):
                        print(f"   ✅ Approving Cost → ROI...")
                        messages = self._chat(project_id, "proceed")
                        self._analyze_roi_response(messages, expected, result)

        except httpx.TimeoutException:
            result.status = "fail"
            result.error = "Timeout — server took too long to respond"
            result.findings.append(Finding("error", "pipeline", "Request timed out after 300s"))
        except Exception as e:
            result.status = "fail"
            result.error = str(e)
            result.findings.append(Finding("error", "pipeline", f"Unexpected error: {e}"))

        result.total_duration_s = round(time.time() - start, 1)

        # ── LLM-as-Judge evaluation ──
        if self.judge and any(ar.content for ar in result.agent_results.values()):
            self._run_judge(name, scenario, result)

        # Determine overall status from findings
        has_errors = any(f.severity == "error" for f in result.findings)
        has_warnings = any(f.severity == "warning" for f in result.findings)
        if has_errors:
            result.status = "fail"
        elif has_warnings:
            result.status = "partial"

        return result

    # ── API helpers ──────────────────────────────────────────────

    def _search_company(self, name: str, expected: dict, result: ScenarioResult) -> dict | None:
        try:
            resp = self.client.get("/api/company/search", params={"q": name})
            if resp.status_code != 200:
                result.findings.append(Finding("warning", "company_search", f"Search returned {resp.status_code}"))
                return None
            data = resp.json()
            # API returns a list of results; take the first one
            profile = data[0] if isinstance(data, list) and len(data) > 0 else data if isinstance(data, dict) else {}
            ar = AgentResult(agent="company_search", status="success", data=profile)

            # Evaluate company profile
            if not profile.get("employeeCount"):
                ar.findings.append(Finding("warning", "company_search", f"No employee count found for {name}"))
            elif expected.get("min_employees") and profile["employeeCount"] < expected["min_employees"]:
                ar.findings.append(Finding("warning", "company_search",
                    f"Employee count {profile['employeeCount']} seems low for {name} "
                    f"(expected >={expected['min_employees']})"))

            if not profile.get("annualRevenue"):
                ar.findings.append(Finding("warning", "company_search", f"No revenue data found for {name}"))
            elif expected.get("min_revenue") and profile["annualRevenue"] < expected["min_revenue"]:
                ar.findings.append(Finding("warning", "company_search",
                    f"Revenue ${profile['annualRevenue']:,.0f} seems low for {name} "
                    f"(expected >=${expected['min_revenue']:,.0f})"))

            if profile.get("industry"):
                industry_lower = profile["industry"].lower()
                if expected.get("industry_contains"):
                    if not any(kw in industry_lower for kw in expected["industry_contains"]):
                        ar.findings.append(Finding("warning", "company_search",
                            f"Industry '{profile['industry']}' doesn't match expected "
                            f"{expected['industry_contains']}"))

            confidence = profile.get("confidence", "low")
            if confidence == "low" and name:
                ar.findings.append(Finding("warning", "company_search",
                    f"Low confidence for well-known company {name}"))

            result.agent_results["company_search"] = ar
            result.findings.extend(ar.findings)
            return profile
        except Exception as e:
            result.findings.append(Finding("error", "company_search", f"Search failed: {e}"))
            return None

    def _create_project(self, scenario: dict, company_profile: dict | None) -> str | None:
        body = {
            "description": scenario["description"],
            "customer_name": scenario.get("customer_name", ""),
            "active_agents": [a.replace("_", "-") for a in scenario.get("active_agents", [])],
        }
        if company_profile:
            body["company_profile"] = company_profile
        try:
            resp = self.client.post("/api/projects", json=body)
            if resp.status_code == 200:
                return resp.json().get("projectId")
            return None
        except Exception:
            return None

    def _chat(self, project_id: str, message: str) -> list[dict]:
        """Send a chat message and get all response messages as JSON array."""
        resp = self.client.post(
            f"/api/projects/{project_id}/chat",
            json={"message": message},
        )
        if resp.status_code != 200:
            print(f"      ⚠️  Chat returned {resp.status_code}")
            return []
        data = resp.json()
        msgs = data if isinstance(data, list) else []
        # Debug: show message type breakdown
        types = {}
        for m in msgs:
            t = (m.get("metadata") or {}).get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        type_str = ", ".join(f"{k}:{v}" for k, v in sorted(types.items()))
        preview = message[:40] + "..." if len(message) > 40 else message
        print(f"      📨 {len(msgs)} msgs for '{preview}' [{type_str}]")
        return msgs

    def _find_message_by_type(self, messages: list[dict], msg_type: str) -> dict | None:
        for msg in messages:
            if msg.get("metadata", {}).get("type") == msg_type:
                return msg
        return None

    def _find_messages_by_type(self, messages: list[dict], msg_type: str) -> list[dict]:
        return [m for m in messages if m.get("metadata", {}).get("type") == msg_type]

    def _needs_approval(self, messages: list[dict], step: str) -> bool:
        """Check if the last messages indicate an approval gate."""
        for msg in reversed(messages):
            content = msg.get("content", "").lower()
            meta = msg.get("metadata", {})
            if (meta.get("step") == step
                    and ("proceed" in content or "approve" in content
                         or "decision" in content or "refine" in content)):
                return True
            if "skip" in content and "refine" in content and step in content:
                return True
        # If we got agent_result for the step, there's likely an approval gate after
        for msg in messages:
            if (msg.get("metadata", {}).get("type") == "agent_result"
                    and msg.get("metadata", {}).get("step") == step):
                return True
        return False

    def _has_content_from(self, messages: list[dict], step: str) -> bool:
        """Check if we received meaningful content from a given pipeline step."""
        for msg in messages:
            meta = msg.get("metadata", {}) or {}
            content = msg.get("content", "") or ""
            # Check for agent_result type
            if meta.get("type") == "agent_result" and meta.get("step") == step:
                return True
            # Check for substantial content from the step's agent
            agent = msg.get("agent_id", "") or ""
            if step.replace("_", "") in agent.replace("_", "").replace("-", "") and len(content) > 50:
                return True
            # Check metadata step match with content
            if meta.get("step") == step and len(content) > 50:
                return True
        return False

    def _build_default_assumptions(self, assumptions: list[dict]) -> list[dict]:
        """Use default values for all assumptions."""
        return [
            {
                "id": a.get("id", ""),
                "label": a.get("label", a.get("id", "")),
                "value": a.get("default", a.get("value", 100)),
                "unit": a.get("unit", ""),
            }
            for a in assumptions
        ]

    # ── Analysis methods ─────────────────────────────────────────

    def _analyze_pm_response(self, messages: list[dict], result: ScenarioResult):
        ar = AgentResult(agent="pm", status="success")
        # Reconstruct PM content — tokens are individual chars, pm_response has full text
        pm_response_msgs = [m for m in messages
                            if m.get("metadata", {}).get("type") == "pm_response"]
        pm_token_msgs = [m for m in messages
                         if m.get("metadata", {}).get("type") == "agent_token"
                         and m.get("agent_id") == "pm"]
        if pm_response_msgs:
            content = " ".join(m.get("content", "") for m in pm_response_msgs)
        elif pm_token_msgs:
            content = "".join(m.get("content", "") for m in pm_token_msgs)
        else:
            pm_messages = [m for m in messages if m.get("agent_id") == "pm"]
            content = " ".join(m.get("content", "") for m in pm_messages)

        if not content.strip():
            ar.status = "error"
            ar.findings.append(Finding("error", "pm", "No PM response received — agent may be stuck"))
        else:
            ar.content = content[:4000]
            if len(content) < 50:
                ar.findings.append(Finding("warning", "pm", "PM response suspiciously short"))
            if "error" in content.lower() or "failed" in content.lower():
                ar.findings.append(Finding("error", "pm",
                    f"PM response contains error: {content[:200]}"))
        result.agent_results["pm"] = ar
        result.findings.extend(ar.findings)

    def _analyze_bv_response(self, messages: list[dict], expected: dict, result: ScenarioResult):
        ar = AgentResult(agent="business_value", status="success")
        bv_msgs = self._find_messages_by_type(messages, "agent_result")
        bv_msg = next(
            (m for m in bv_msgs if m.get("metadata", {}).get("step") == "business_value"),
            None,
        )

        if not bv_msg:
            err = next(
                (m for m in messages
                 if m.get("metadata", {}).get("type") == "agent_error"
                 and m.get("metadata", {}).get("step") == "business_value"),
                None,
            )
            if err:
                ar.status = "error"
                ar.findings.append(Finding("error", "business_value",
                    f"BV agent failed: {err.get('content', '')[:200]}"))
            else:
                ar.status = "skipped"
                ar.findings.append(Finding("info", "business_value",
                    "No BV result in response (may be in next step)"))
        else:
            content = bv_msg.get("content", "")
            ar.content = content[:4000]

            if "driver" not in content.lower() and "value" not in content.lower():
                ar.findings.append(Finding("warning", "business_value",
                    "BV output doesn't mention value drivers"))

            if "$" not in content:
                ar.findings.append(Finding("warning", "business_value",
                    "BV output has no dollar figures — may lack quantification"))

            if ("impact" not in content.lower()
                    and "range" not in content.lower()
                    and "annual" not in content.lower()):
                ar.findings.append(Finding("warning", "business_value",
                    "BV output doesn't mention impact range"))

            if "error" in content.lower()[:100] or "failed" in content.lower()[:100]:
                ar.status = "error"
                ar.findings.append(Finding("error", "business_value",
                    f"BV output looks like an error: {content[:200]}"))

        result.agent_results["business_value"] = ar
        result.findings.extend(ar.findings)

    def _analyze_architect_response(self, messages: list[dict], expected: dict,
                                     result: ScenarioResult):
        ar = AgentResult(agent="architect", status="success")
        arch_msgs = self._find_messages_by_type(messages, "agent_result")
        arch_msg = next(
            (m for m in arch_msgs if m.get("metadata", {}).get("step") == "architect"),
            None,
        )

        if not arch_msg:
            err = next(
                (m for m in messages
                 if m.get("metadata", {}).get("type") == "agent_error"
                 and m.get("metadata", {}).get("step") == "architect"),
                None,
            )
            if err:
                ar.status = "error"
                ar.findings.append(Finding("error", "architect",
                    f"Architect failed: {err.get('content', '')[:200]}"))
            else:
                ar.status = "skipped"
        else:
            content = arch_msg.get("content", "")
            ar.content = content[:8000]

            if (expected.get("arch_has_mermaid")
                    and "mermaid" not in content.lower()
                    and "flowchart" not in content.lower()):
                ar.findings.append(Finding("warning", "architect",
                    "Architecture output missing Mermaid diagram"))

            azure_keywords = ["azure", "cosmos", "openai", "app service",
                              "function", "storage", "sql"]
            found_azure = sum(1 for kw in azure_keywords if kw in content.lower())
            if found_azure < 2:
                ar.findings.append(Finding("warning", "architect",
                    f"Only {found_azure} Azure service mentions — architecture may be too generic"))

            # REGRESSION CHECK: BV data leaking into architect
            bv_leak_keywords = ["value driver", "annual impact",
                                "cost reduction driver", "revenue uplift driver"]
            for kw in bv_leak_keywords:
                if kw in content.lower():
                    ar.findings.append(Finding("error", "architect",
                        f"REGRESSION: Architect output contains BV data: '{kw}' found. "
                        f"BV/architect isolation broken."))

            if "layer" not in content.lower() and "tier" not in content.lower():
                ar.findings.append(Finding("warning", "architect",
                    "Architecture doesn't describe layers"))

        result.agent_results["architect"] = ar
        result.findings.extend(ar.findings)

    def _analyze_cost_response(self, messages: list[dict], expected: dict,
                                result: ScenarioResult):
        ar = AgentResult(agent="cost", status="success")
        cost_msgs = self._find_messages_by_type(messages, "agent_result")
        cost_msg = next(
            (m for m in cost_msgs if m.get("metadata", {}).get("step") == "cost"),
            None,
        )

        if not cost_msg:
            err = next(
                (m for m in messages
                 if m.get("metadata", {}).get("type") == "agent_error"
                 and m.get("metadata", {}).get("step") == "cost"),
                None,
            )
            if err:
                ar.status = "error"
                ar.findings.append(Finding("error", "cost",
                    f"Cost agent failed: {err.get('content', '')[:200]}"))
            else:
                ar.status = "skipped"
        else:
            content = cost_msg.get("content", "")
            ar.content = content[:4000]

            if "$" not in content:
                ar.findings.append(Finding("warning", "cost",
                    "Cost output has no dollar figures"))

            if "month" not in content.lower() and "annual" not in content.lower():
                ar.findings.append(Finding("warning", "cost",
                    "Cost output doesn't show monthly or annual breakdown"))

            if "service" not in content.lower() and "component" not in content.lower():
                ar.findings.append(Finding("warning", "cost",
                    "Cost output missing per-service breakdown"))

        result.agent_results["cost"] = ar
        result.findings.extend(ar.findings)

    def _analyze_roi_response(self, messages: list[dict], expected: dict,
                               result: ScenarioResult):
        ar = AgentResult(agent="roi", status="success")

        dashboard_msg = self._find_message_by_type(messages, "roi_dashboard")
        roi_result_msgs = self._find_messages_by_type(messages, "agent_result")
        roi_msg = next(
            (m for m in roi_result_msgs if m.get("metadata", {}).get("step") == "roi"),
            None,
        )

        if not roi_msg and not dashboard_msg:
            err = next(
                (m for m in messages
                 if m.get("metadata", {}).get("type") == "agent_error"
                 and m.get("metadata", {}).get("step") == "roi"),
                None,
            )
            if err:
                ar.status = "error"
                ar.findings.append(Finding("error", "roi",
                    f"ROI agent failed: {err.get('content', '')[:200]}"))
            else:
                ar.status = "skipped"
                ar.findings.append(Finding("warning", "roi", "No ROI result received"))
        else:
            if roi_msg:
                ar.content = roi_msg.get("content", "")[:4000]

            if dashboard_msg:
                dashboard = dashboard_msg.get("metadata", {}).get("dashboard", {})
                ar.data = dashboard
                # Ensure judge has content even if no separate roi_msg
                if not ar.content:
                    ar.content = json.dumps(dashboard, indent=2, default=str)[:4000]

                # REGRESSION: Check confidenceLevel is string
                conf = dashboard.get("confidenceLevel")
                if isinstance(conf, dict):
                    ar.findings.append(Finding("error", "roi",
                        "REGRESSION: confidenceLevel is a dict, not a string "
                        "— will crash React frontend"))
                elif conf and conf not in ("high", "moderate", "low"):
                    ar.findings.append(Finding("warning", "roi",
                        f"Unexpected confidence level: '{conf}'"))

                # Check ROI plausibility
                roi_pct = dashboard.get("roiPercent")
                roi_run_rate = dashboard.get("roiRunRate")
                if roi_pct is not None:
                    # Only warn if BOTH Year 1 AND steady-state are negative
                    # (negative Year 1 alone is normal for complex projects with adoption ramp)
                    if expected.get("roi_positive") and roi_pct < 0 and (roi_run_rate is None or roi_run_rate < 0):
                        ar.findings.append(Finding("warning", "roi",
                            f"ROI is negative both Year 1 ({roi_pct:.1f}%) and "
                            f"steady-state ({roi_run_rate:.1f}%) — project may not be viable"))
                    elif roi_pct > 10000:
                        ar.findings.append(Finding("warning", "roi",
                            f"ROI is extremely high ({roi_pct}%) — may lack credibility"))

                payback = dashboard.get("paybackMonths")
                if payback is not None and payback > 60:
                    ar.findings.append(Finding("warning", "roi",
                        f"Payback is {payback} months (>5 years) — hard to justify"))

                # Check JSON serializability (the original crash)
                try:
                    json.dumps(dashboard, default=str)
                except TypeError as e:
                    ar.findings.append(Finding("error", "roi",
                        f"Dashboard is NOT JSON-serializable: {e}"))

                # Check for nested dicts in React-rendered fields
                react_fields = [
                    "confidenceLevel", "roiPercent", "roiDisplayText", "paybackMonths",
                    "monthlySavings", "annualImpact", "methodology", "warning",
                ]
                for field_name in react_fields:
                    val = dashboard.get(field_name)
                    if isinstance(val, dict):
                        ar.findings.append(Finding("error", "roi",
                            f"REGRESSION: dashboard['{field_name}'] is a dict "
                            f"— will crash React"))

                drivers = dashboard.get("drivers", [])
                if not drivers:
                    ar.findings.append(Finding("warning", "roi",
                        "Dashboard has no drivers"))

                projection = dashboard.get("projection", {})
                if not projection.get("cumulative"):
                    ar.findings.append(Finding("warning", "roi",
                        "Dashboard missing projection data"))

            else:
                ar.findings.append(Finding("warning", "roi",
                    "No ROI dashboard in response — only text output"))

        result.agent_results["roi"] = ar
        result.findings.extend(ar.findings)

    # ── LLM Judge integration ────────────────────────────────────

    def _run_judge(self, name: str, scenario: dict, result: ScenarioResult):
        """Run LLM-as-judge on each agent output + cross-agent coherence."""
        print(f"   🧑‍⚖️ Running LLM quality judge...")
        desc = scenario["description"]
        company = scenario.get("customer_name", "")

        # Collect all outputs for cross-agent check
        all_outputs: dict[str, str] = {}
        agents_to_judge = ["pm", "business_value", "architect", "cost", "roi"]

        for agent in agents_to_judge:
            ar = result.agent_results.get(agent)
            if ar and ar.content:
                all_outputs[agent] = ar.content

        # Judge each agent individually
        for agent, output in all_outputs.items():
            print(f"      ⚖️  Judging {agent}...")
            findings = self.judge.judge_agent(agent, desc, company, output)
            for f in findings:
                result.findings.append(f)
                # Also attach to the agent result
                if agent in result.agent_results:
                    result.agent_results[agent].findings.append(f)

        # Cross-agent coherence check (the key part — does BV+Cost+ROI add up?)
        if len(all_outputs) >= 3:
            print(f"      ⚖️  Judging cross-agent coherence...")
            findings = self.judge.judge_agent(
                "cross_agent", desc, company, "", all_outputs=all_outputs
            )
            # Create a synthetic agent result for cross-agent findings
            cross_ar = AgentResult(agent="cross_agent_coherence", status="evaluated")
            cross_ar.findings = findings
            result.agent_results["cross_agent_coherence"] = cross_ar
            result.findings.extend(findings)

        judge_errors = sum(1 for f in result.findings if f.agent.startswith("judge_") and f.severity == "error")
        judge_warns = sum(1 for f in result.findings if f.agent.startswith("judge_") and f.severity == "warning")
        print(f"   🧑‍⚖️ Judge done: {judge_errors} errors, {judge_warns} warnings")

    # ── Reporting ────────────────────────────────────────────────

    def _print_scenario_summary(self, result: ScenarioResult):
        icon = {"pass": "✅", "fail": "❌", "partial": "⚠️"}.get(result.status, "❓")
        print(f"\n{icon} {result.scenario}: {result.status.upper()} ({result.total_duration_s}s)")
        if result.error:
            print(f"   💥 {result.error}")

        for agent_name, ar in result.agent_results.items():
            status_icon = {"success": "✅", "error": "❌", "skipped": "⏭️",
                           "needs_info": "❓"}.get(ar.status, "❓")
            print(f"   {status_icon} {agent_name}: {ar.status}")
            for f in ar.findings:
                sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
                    f.severity, "⚪")
                print(f"      {sev_icon} {f.message}")

    def _write_report(self):
        """Write structured report to file."""
        report_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(report_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(report_dir, f"eval_report_{timestamp}.md")

        total_findings = sum(len(r.findings) for r in self.results)
        errors = sum(1 for r in self.results for f in r.findings if f.severity == "error")
        warnings = sum(1 for r in self.results for f in r.findings
                       if f.severity == "warning")
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")

        lines = [
            f"# OneStopAgent Evaluation Report",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Server**: {self.base_url}",
            f"**Scenarios**: {len(self.results)} ({passed} passed, {failed} failed)",
            f"**Findings**: {total_findings} ({errors} errors, {warnings} warnings)",
            "",
            "## Summary",
            "",
            "| Scenario | Status | Duration | Errors | Warnings |",
            "|----------|--------|----------|--------|----------|",
        ]
        for r in self.results:
            errs = sum(1 for f in r.findings if f.severity == "error")
            warns = sum(1 for f in r.findings if f.severity == "warning")
            icon = {"pass": "✅", "fail": "❌", "partial": "⚠️"}.get(r.status, "❓")
            lines.append(
                f"| {icon} {r.scenario} | {r.status} | {r.total_duration_s}s "
                f"| {errs} | {warns} |")

        for r in self.results:
            lines.append(f"\n## Scenario: {r.scenario}")
            if r.error:
                lines.append(f"\n**Error**: {r.error}")
            lines.append("")
            for agent_name, ar in r.agent_results.items():
                status_icon = {"success": "✅", "error": "❌", "skipped": "⏭️"}.get(
                    ar.status, "❓")
                lines.append(f"### {status_icon} {agent_name} ({ar.status})")
                if ar.content:
                    lines.append(
                        f"\n<details><summary>Output preview</summary>\n\n"
                        f"```\n{ar.content[:500]}\n```\n</details>\n")
                for f in ar.findings:
                    sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
                        f.severity, "⚪")
                    lines.append(f"- {sev_icon} **{f.severity.upper()}**: {f.message}")
                    if f.details:
                        lines.append(f"  - {f.details}")
                lines.append("")

        # Known regressions section
        lines.append("## Regression Check Summary")
        regression_checks = [
            ("ROI confidence dict", "roi", "confidenceLevel is a dict"),
            ("Architect BV data leak", "architect", "BV data"),
            ("Dashboard JSON serialization", "roi", "NOT JSON-serializable"),
        ]
        for check_name, agent, pattern in regression_checks:
            found = any(
                pattern.lower() in f.message.lower()
                for r in self.results
                for f in r.findings
                if f.agent == agent
            )
            icon = "❌ REGRESSION" if found else "✅ CLEAN"
            lines.append(f"- {icon}: {check_name}")

        report_content = "\n".join(lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        # Also write JSON for programmatic use
        json_path = os.path.join(report_dir, f"eval_report_{timestamp}.json")
        json_data = {
            "timestamp": timestamp,
            "server": self.base_url,
            "summary": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "warnings": warnings,
            },
            "scenarios": [],
        }
        for r in self.results:
            scenario_data = {
                "name": r.scenario,
                "status": r.status,
                "duration_s": r.total_duration_s,
                "error": r.error,
                "agents": {},
                "findings": [
                    {"severity": f.severity, "agent": f.agent, "message": f.message}
                    for f in r.findings
                ],
            }
            for agent_name, ar in r.agent_results.items():
                scenario_data["agents"][agent_name] = {
                    "status": ar.status,
                    "findings": [
                        {"severity": f.severity, "message": f.message}
                        for f in ar.findings
                    ],
                }
            json_data["scenarios"].append(scenario_data)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str)

        print(f"\n{'='*60}")
        print(f"  📄 Report: {report_path}")
        print(f"  📊 JSON:   {json_path}")
        print(f"{'='*60}")

        # Final summary
        print(f"\n  {'✅' if failed == 0 else '❌'} {passed}/{len(self.results)} scenarios passed")
        print(f"  🔴 {errors} errors | 🟡 {warnings} warnings")

        if errors > 0:
            print("\n  Top errors:")
            seen: set[str] = set()
            for r in self.results:
                for f in r.findings:
                    if f.severity == "error" and f.message not in seen:
                        seen.add(f.message)
                        print(f"    🔴 [{f.agent}] {f.message}")


def main():
    parser = argparse.ArgumentParser(description="OneStopAgent Evaluation Runner")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend URL")
    parser.add_argument("--scenarios", nargs="*", help="Specific scenarios to run")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-judge quality evaluation")
    args = parser.parse_args()

    runner = EvalRunner(base_url=args.url, use_judge=args.judge)
    runner.run_all(args.scenarios)

    # Exit with error code if any scenario failed
    if any(r.status == "fail" for r in runner.results):
        sys.exit(1)


if __name__ == "__main__":
    main()
