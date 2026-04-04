"""
OneStopAgent Evaluation Runner
Runs full pipeline scenarios, evaluates quality, produces structured report.

Usage:
    python -m tests.eval_runner                    # Run against localhost:8000
    python -m tests.eval_runner --url https://...  # Run against deployed instance
    python -m tests.eval_runner --scenarios nike    # Run single scenario
"""

import argparse
import json
import time
import sys
import os
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


class EvalRunner:
    def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "eval-runner"):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"x-user-id": self.user_id},
            timeout=300.0,  # 5 min timeout for LLM calls
        )
        self.results: list[ScenarioResult] = []

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
            ar.content = content[:500]
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
            ar.content = content[:1000]

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
            ar.content = content[:1500]

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
            ar.content = content[:1000]

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
                ar.content = roi_msg.get("content", "")[:1000]

            if dashboard_msg:
                dashboard = dashboard_msg.get("metadata", {}).get("dashboard", {})
                ar.data = dashboard

                # REGRESSION: Check confidenceLevel is string
                conf = dashboard.get("confidenceLevel")
                if isinstance(conf, dict):
                    ar.findings.append(Finding("error", "roi",
                        "REGRESSION: confidenceLevel is a dict, not a string "
                        "— will crash React frontend"))
                elif conf and conf not in ("high", "moderate", "low"):
                    ar.findings.append(Finding("warning", "roi",
                        f"Unexpected confidence level: '{conf}'"))

                # Check ROI is positive
                roi_pct = dashboard.get("roiPercent")
                if roi_pct is not None:
                    if expected.get("roi_positive") and roi_pct < 0:
                        ar.findings.append(Finding("warning", "roi",
                            f"ROI is negative ({roi_pct}%) — may be unrealistic"))
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
    args = parser.parse_args()

    runner = EvalRunner(base_url=args.url)
    runner.run_all(args.scenarios)

    # Exit with error code if any scenario failed
    if any(r.status == "fail" for r in runner.results):
        sys.exit(1)


if __name__ == "__main__":
    main()
