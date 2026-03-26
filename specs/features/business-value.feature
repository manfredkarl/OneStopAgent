@business-value
Feature: Business Value Assessment
  As an Azure seller
  I want the Business Value Agent to evaluate the proposed solution against value drivers
  So that I can build a compelling business case for the customer

  Background:
    Given I am authenticated as an Azure seller
    And I have an active project with requirements, architecture, and service selections

  # ──────────────────────────────────────────────────
  # Rule: Value Driver Evaluation
  # ──────────────────────────────────────────────────
  Rule: The agent evaluates solutions against standard and custom value drivers

    @happy-path @api
    # FRD-BUSINESS-VALUE §2.1, §3.2
    Scenario: Evaluate all five standard value drivers
      Given the project context includes a cloud migration architecture
      When the Business Value Agent is invoked
      Then the response contains ValueDrivers for:
        | driver                  |
        | Cost Savings            |
        | Revenue Growth          |
        | Operational Efficiency  |
        | Time-to-Market          |
        | Risk Reduction          |
      And each driver has a qualitative impact description of 2-4 sentences
      And each driver has a confidence level of "conservative", "moderate", or "optimistic"
      And overallConfidence is set based on the lowest confidence among top 3 drivers

    @happy-path @api
    # FRD-BUSINESS-VALUE §4.1
    Scenario: Quantify cost savings using cost estimate comparison
      Given the project has a costEstimate with monthlyCost $32,000
      And the customer's current hosting costs $50,000 per month
      When the Business Value Agent evaluates Cost Savings
      Then the quantifiedEstimate says "Estimated 36% reduction in monthly infrastructure costs"
      And supporting benchmark IDs include relevant cross-industry benchmarks

    @happy-path @api
    # FRD-BUSINESS-VALUE §2.2
    Scenario: Identify custom value drivers from project context
      Given the project requirements mention "sustainability" and "carbon footprint reduction"
      When the Business Value Agent scans the context
      Then a custom driver is added with isCustom true
      And the custom driver name relates to sustainability
      And no more than 3 custom drivers are generated

    @edge-case @api
    # FRD-BUSINESS-VALUE §4.1
    Scenario: Omit quantified estimate when no credible data supports it
      Given the project architecture uses a novel pattern with no matching benchmarks
      When the Business Value Agent evaluates Revenue Growth
      Then the Revenue Growth driver includes only qualitative impact text
      And quantifiedEstimate is omitted

    @happy-path @api
    # FRD-BUSINESS-VALUE §4.2
    Scenario Outline: Confidence level based on benchmark coverage
      Given the solution matches benchmarks at the "<coverage>" level
      When the Business Value Agent assigns confidence
      Then the driver confidence is "<confidence>"

      Examples:
        | coverage                                    | confidence   |
        | Low end of range with multiple sources      | conservative |
        | Midpoint with at least one source           | moderate     |
        | High end extrapolated from loose benchmarks | optimistic   |

  # ──────────────────────────────────────────────────
  # Rule: Benchmark References
  # ──────────────────────────────────────────────────
  Rule: The agent references industry benchmarks from the knowledge base

    @happy-path @api
    # FRD-BUSINESS-VALUE §5.2
    Scenario: Reference cross-industry cloud migration benchmarks
      Given the project involves an on-premises to Azure migration
      When the Business Value Agent generates the assessment
      Then the benchmarks array includes BM-001 "TCO reduction 30-40% over 3 years"
      And the source is "Forrester Total Economic Impact, 2023"

    @happy-path @api
    # FRD-BUSINESS-VALUE §5.2
    Scenario: Reference industry-specific benchmarks for healthcare
      Given the project requirements specify industry "Healthcare"
      And the architecture involves EHR modernization
      When the Business Value Agent generates the assessment
      Then the benchmarks include BM-006 "Compliance audit preparation time 50-70% reduction"
      And the source is "HIMSS Analytics, 2023"

  # ──────────────────────────────────────────────────
  # Rule: Executive Summary Generation
  # ──────────────────────────────────────────────────
  Rule: The agent generates a concise executive-ready summary

    @happy-path @api
    # FRD-BUSINESS-VALUE §6.1, §6.2
    Scenario: Executive summary follows required structure
      When the Business Value Agent generates the assessment
      Then the executiveSummary is 100 to 200 words as a single prose paragraph
      And it opens with the strategic opportunity statement
      And it highlights the top 2-3 value drivers with quantified estimates
      And it references industry benchmarks
      And it closes with the required projection disclaimer

    @happy-path @api
    # FRD-BUSINESS-VALUE §4.3
    Scenario: Executive summary includes mandatory disclaimer
      When the Business Value Agent generates the executiveSummary
      Then the summary contains the phrase "based on industry benchmarks and comparable deployments and are subject to validation during implementation planning"

    @happy-path @api
    # FRD-BUSINESS-VALUE §4.3
    Scenario: All quantified estimates use required prefix
      When the Business Value Agent generates value drivers
      Then every quantifiedEstimate string begins with "Estimated" or "Projected"

  # ──────────────────────────────────────────────────
  # Rule: Error Handling
  # ──────────────────────────────────────────────────
  Rule: The agent handles errors and degraded inputs gracefully

    @error @api
    # FRD-BUSINESS-VALUE §8
    Scenario: Missing required project context returns error
      Given the ProjectContext is missing architecture and services
      When the Business Value Agent is invoked
      Then a 400 error is returned with code "INVALID_INPUT"
      And the message says "Required project context is incomplete"

    @error @api
    # FRD-BUSINESS-VALUE §8
    Scenario: No value drivers identified returns partial response
      Given the project has minimal context that yields no meaningful driver impacts
      When the Business Value Agent generates the assessment
      Then the response is 200 with code "NO_DRIVERS_IDENTIFIED"
      And the message says "The assessment could not identify meaningful value drivers"

    @error @api
    # FRD-BUSINESS-VALUE §8
    Scenario: Benchmark knowledge base unavailable degrades gracefully
      Given the benchmark knowledge base is unreachable
      When the Business Value Agent generates the assessment
      Then the assessment is generated without benchmark references
      And a note says "Quantified estimates may be less precise"

  # ──────────────────────────────────────────────────
  # Rule: Edge Cases
  # ──────────────────────────────────────────────────
  Rule: The agent handles edge cases in business context

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.1
    Scenario: No cost estimate available omits cost-comparison quantification
      Given the costEstimate is absent from ProjectContext
      When the Business Value Agent evaluates Cost Savings
      Then the driver includes only qualitative impact based on architecture patterns
      And the executive summary appends "Cost savings projections could not be quantified"

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.2
    Scenario: Conflicting value drivers are both included transparently
      Given the solution requires higher upfront costs but projects long-term savings
      When the Business Value Agent evaluates the drivers
      Then both the cost increase and the long-term savings drivers are included
      And the executive summary acknowledges the trade-off

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.3
    Scenario: Niche industry caps confidence at low
      Given the project industry is "Agriculture" which has no matching benchmarks
      When the Business Value Agent generates the assessment
      Then only cross-industry benchmarks are used
      And overallConfidence is capped at "low"
      And the executive summary notes limited industry-specific data

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.4
    Scenario: No benchmarks match yields purely qualitative assessment
      Given no benchmarks match the solution's use case or architecture patterns
      When the Business Value Agent generates the assessment
      Then all supportingBenchmarkIds arrays are empty
      And quantifiedEstimate is omitted from all drivers
      And overallConfidence is "low"

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.5
    Scenario: Minimal requirements input produces generic assessment
      Given the requirements contain only the industry field with no pain points or objectives
      When the Business Value Agent generates the assessment
      Then a generic assessment is produced based on architecture patterns
      And overallConfidence is capped at "low"
      And the summary notes "based on limited input"

    @edge-case @api
    # FRD-BUSINESS-VALUE §9.6
    Scenario: Single-service architecture limits quantification scope
      Given the project uses only "Azure App Service" as a single service
      When the Business Value Agent evaluates all five standard drivers
      Then quantification is limited to drivers directly supported by that service
      And no custom drivers are generated
