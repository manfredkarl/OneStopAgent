@envisioning
Feature: Envisioning Agent
  As an Azure seller with a vague customer opportunity
  I want the Envisioning Agent to suggest relevant scenarios, estimates, and architectures
  So that I can shape the opportunity with enriched context before proceeding

  Background:
    Given I am authenticated as an Azure seller
    And I have an active project

  # ──────────────────────────────────────────────────
  # Rule: Suggestion Matching
  # ──────────────────────────────────────────────────
  Rule: The Envisioning Agent matches knowledge base items to the seller's description

    @happy-path @api
    # FRD-ENVISIONING §3.2, §4.1
    Scenario: Match suggestions for a retail e-commerce description
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value                                                      |
        | userDescription | The customer wants to build an omnichannel e-commerce platform |
        | industryHints   | ["Retail"]                                                 |
      When the Envisioning Agent processes the input
      Then the response contains scenarios including "Digital Commerce Platform"
      And the response contains estimates including "Calgary Connected Commerce"
      And the response contains architectures including "Microservices-Based E-Commerce Platform"
      And each category returns at most 5 items ranked by relevanceScore descending
      And matchConfidence is "high" or "medium"

    @happy-path @api
    # FRD-ENVISIONING §4.1
    Scenario: Infer industry from description when industryHints not provided
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value                                                         |
        | userDescription | We need a claims processing automation solution for insurance |
      When the Envisioning Agent processes the input
      Then the inferred industry is "Financial Services"
      And the response includes "Intelligent Claims Processing" in scenarios
      And the response includes "Contoso Insurance Claims AI" in estimates

    @happy-path @api
    # FRD-ENVISIONING §4.2
    Scenario: Rank items by weighted keyword matching
      Given the PM Agent sends input with keywords ["e-commerce", "digital", "omnichannel"]
      When the Envisioning Agent matches against the knowledge base
      Then items with tag matches score weight 1.0
      And items with title matches score weight 0.8
      And items with description matches score weight 0.5
      And items with industry matches receive a 1.5 bonus
      And items with relevanceScore below 0.1 are excluded

    @edge-case @api
    # FRD-ENVISIONING §4.1
    Scenario: Multi-industry description returns results from all matched industries
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value                                                                   |
        | userDescription | Retail banking platform with e-commerce and insurance claims automation |
      When the Envisioning Agent processes the input
      Then the response includes items from both "Retail" and "Financial Services"
      And items are ranked by term frequency across both industries

    @edge-case @api
    # FRD-ENVISIONING §4.1
    Scenario: No industry detected defaults to Cross-Industry
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value                             |
        | userDescription | We need a modernization solution  |
      When the Envisioning Agent processes the input
      Then the agent applies "Cross-Industry" as the default filter
      And the response includes broader results like "Digital Transformation using AI"

  # ──────────────────────────────────────────────────
  # Rule: Selection Flow
  # ──────────────────────────────────────────────────
  Rule: The seller selects items and proceeds or rejects all suggestions

    @happy-path @ui
    # FRD-ENVISIONING §5.1, §5.2
    Scenario: Seller selects items and proceeds
      Given the Envisioning Agent has returned suggestions with 2 scenarios, 3 estimates, and 2 architectures
      When I select "Digital Commerce Platform" and "Calgary Connected Commerce"
      Then the "Proceed with Selected Items" button shows count "(2)"
      And the button is enabled
      When I click "Proceed with Selected Items"
      Then the selection is posted as an EnvisioningSelectionResponse
      And the enrichedContext includes inferredIndustry, inferredKeywords, and selected titles
      And the pipeline advances to the next agent

    @happy-path @ui
    # FRD-ENVISIONING §5.2
    Scenario: Proceed button is disabled when no items selected
      Given the Envisioning Agent has returned suggestions
      And no items are checked
      Then the "Proceed with Selected Items (0)" button is disabled and greyed out

    @happy-path @ui
    # FRD-ENVISIONING §7
    Scenario: Seller selects all available items
      Given the Envisioning Agent has returned 4 scenarios, 3 estimates, and 2 architectures
      When I select all 9 items
      Then the "Proceed with Selected Items (9)" button shows the total count
      And all items are forwarded to downstream agents

    @edge-case @api
    # FRD-ENVISIONING §7
    Scenario: Seller selects items from only one category
      Given the Envisioning Agent has returned suggestions across all categories
      When I select only "Microservices-Based E-Commerce Platform" from architectures
      And I click "Proceed with Selected Items"
      Then the selection response includes only architecture items
      And other categories contain empty arrays

  # ──────────────────────────────────────────────────
  # Rule: Rejection Flow
  # ──────────────────────────────────────────────────
  Rule: The seller can reject all suggestions and describe their own direction

    @happy-path @ui
    # FRD-ENVISIONING §5.3
    Scenario: Seller rejects all suggestions and provides own direction
      Given the Envisioning Agent has returned suggestions
      When I click "Describe your own direction"
      Then a free-text input area expands inline
      When I type "We need a custom IoT predictive maintenance solution for oil rigs"
      And I click "Submit"
      Then the response has empty selectedItems and sellerDirection populated
      And the PM Agent receives the seller's direction for downstream routing

    @edge-case @api
    # FRD-ENVISIONING §7
    Scenario: Re-invocation after rejection merges context
      Given I previously rejected all suggestions and described my own direction
      When the PM Agent re-invokes the Envisioning Agent
      Then the agent merges the original userDescription with the seller's sellerDirection
      And previous selections are cleared
      And a fresh set of suggestions is returned

  # ──────────────────────────────────────────────────
  # Rule: No-Match Fallback
  # ──────────────────────────────────────────────────
  Rule: The agent handles scenarios where no knowledge base items match

    @edge-case @api
    # FRD-ENVISIONING §4.3
    Scenario: No items match across any category
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value                                                  |
        | userDescription | Quantum computing simulation for particle physics lab |
      When the Envisioning Agent processes the input
      Then matchConfidence is "none"
      And scenarios, estimates, and architectures are all empty arrays
      And matchExplanation contains a message asking for more details
      And the frontend renders the explanation with a free-text input

  # ──────────────────────────────────────────────────
  # Rule: Error Handling & Edge Cases
  # ──────────────────────────────────────────────────
  Rule: The agent handles errors and edge cases gracefully

    @error @api
    # FRD-ENVISIONING §6
    Scenario: Knowledge base is unavailable
      Given the knowledge base service is temporarily down
      When the Envisioning Agent is invoked
      Then matchConfidence is "none"
      And the user-facing message says "The knowledge base is temporarily unavailable"
      And the seller is prompted to describe their scenario directly

    @error @api
    # FRD-ENVISIONING §6
    Scenario: Empty userDescription is provided
      Given the PM Agent sends input with an empty userDescription
      When the Envisioning Agent validates the input
      Then a validation error is returned
      And the message says "I need a description of the customer opportunity to find relevant suggestions"

    @edge-case @api
    # FRD-ENVISIONING §6, §7
    Scenario: Description exceeding 5000 characters is truncated silently
      Given the PM Agent sends a userDescription of 6000 characters
      When the Envisioning Agent processes the input
      Then the input is truncated to 5000 characters
      And processing continues without a user-facing warning

    @edge-case @api
    # FRD-ENVISIONING §7
    Scenario: Very short description returns low confidence with broader results
      Given the PM Agent sends the following input to the Envisioning Agent:
        | field           | value |
        | userDescription | IoT   |
      When the Envisioning Agent processes the input
      Then matchConfidence is "low"
      And broader results are returned
      And the agent prompts for more detail

    @edge-case @ui
    # FRD-ENVISIONING §7
    Scenario: Seller navigates away and returns to preserved selections
      Given the Envisioning Agent has returned suggestions
      And I have selected 2 items
      When I navigate away from the chat and return
      Then my previous selections are preserved in the chat message state
      And I can resume where I left off without re-triggering the agent

    @edge-case @api
    # FRD-ENVISIONING §7
    Scenario: Conflicting industry signals in description
      Given the PM Agent sends the following input:
        | field           | value                                                        |
        | userDescription | Healthcare patient portal with e-commerce prescription sales |
      When the Envisioning Agent processes the input
      Then results span both "Healthcare" and "Retail" industries
      And matchExplanation notes "Your description suggests multiple industries"
