@presentation
Feature: Presentation Generation
  As an Azure seller
  I want the Presentation Agent to compile all agent outputs into a professional PowerPoint deck
  So that I can download and present the Azure solution proposal directly to my customer

  Background:
    Given I am authenticated as an Azure seller
    And I have an active project with at least one agent output completed

  # ──────────────────────────────────────────────────
  # Rule: PPTX Generation & Slide Structure
  # ──────────────────────────────────────────────────
  Rule: The Presentation Agent generates a structured PPTX deck from agent outputs

    @happy-path @api
    # FRD-PRESENTATION §3.1
    Scenario: Generate a full deck with all agent outputs available
      Given all agents have completed with outputs:
        | agent        | output               |
        | architect    | ArchitectureOutput    |
        | azure        | ServiceSelection[]    |
        | cost         | CostEstimate          |
        | value        | ValueAssessment       |
      When I send a GET request to "/api/projects/{projectId}/export/pptx"
      Then I receive a 200 response with Content-Type "application/vnd.openxmlformats-officedocument.presentationml.presentation"
      And the Content-Disposition header contains the filename with customer name and date
      And the X-Slide-Count header is present and ≤ 20

    @happy-path @api
    # FRD-PRESENTATION §3.1
    Scenario: Deck includes all required slides in correct order
      Given all agent outputs are available
      When the deck is generated
      Then the slides appear in order: Title, Executive Summary, Use Case, Architecture Diagram, Architecture Components, Azure Services, Cost Breakdown, Business Value, Next Steps

    @happy-path @api
    # FRD-PRESENTATION §3.2
    Scenario: Title slide contains project description and customer name
      Given the project description is "E-commerce platform migration to Azure"
      And the customerName is "Contoso Ltd"
      When the deck is generated
      Then the title slide shows the description truncated to 80 characters
      And the subtitle is "Azure Solution Proposal"
      And the customer name "Contoso Ltd" is displayed
      And the footer says "Confidential — Microsoft Internal Use"

    @happy-path @api
    # FRD-PRESENTATION §3.3
    Scenario: Executive summary slide uses ValueAssessment when available
      Given the ValueAssessment has an executiveSummary
      When the deck is generated
      Then the Executive Summary slide uses the executiveSummary text verbatim
      And it is truncated to 500 characters if longer
      And up to 4 key highlights are included as bullet points

    @happy-path @api
    # FRD-PRESENTATION §3.9
    Scenario: Next Steps slide includes standard recommended actions
      When the deck is generated
      Then the Next Steps slide contains:
        | action                                                               |
        | Review and refine the proposed architecture                          |
        | Validate cost estimates with customer workload data                  |
        | Schedule a deep-dive workshop with the Microsoft account team        |
        | Begin proof-of-concept in Azure                                      |

  # ──────────────────────────────────────────────────
  # Rule: Missing Section Handling
  # ──────────────────────────────────────────────────
  Rule: The deck adapts when agent outputs are missing

    @edge-case @api
    # FRD-PRESENTATION §5.4
    Scenario Outline: Omit slides when agent was skipped
      Given the "<agent>" agent was skipped
      When the deck is generated
      Then the "<section>" slides are omitted
      And the Executive Summary slide includes a note: "<note>"
      And the sectionsOmitted array includes "<section_id>"

      Examples:
        | agent     | section                | note                                       | section_id     |
        | architect | Architecture Diagram   | Architecture diagram not generated.        | architecture   |
        | azure     | Azure Services         | Azure service details not generated.       | services       |
        | cost      | Cost Breakdown         | Cost estimate not generated.               | cost           |
        | value     | Business Value         | Business value assessment not generated.   | business-value |

    @edge-case @api
    # FRD-PRESENTATION §5.4, §10.2
    Scenario: Minimal deck when only PM gathered requirements
      Given only the PM Agent has gathered requirements and no specialist agents ran
      When the deck is generated
      Then the deck contains exactly 4 slides: Title, Executive Summary, Use Case, Next Steps
      And the Executive Summary is auto-generated from requirements

    @edge-case @api
    # FRD-PRESENTATION §5.4
    Scenario: Envisioning skipped does not affect slide count
      Given the Envisioning Agent was skipped but all other agents completed
      When the deck is generated
      Then the Use Case slide is generated from requirements without envisioning data
      And no slides are omitted due to envisioning being skipped

  # ──────────────────────────────────────────────────
  # Rule: Architecture Diagram Slide
  # ──────────────────────────────────────────────────
  Rule: The architecture diagram is rendered and embedded in the deck

    @happy-path @api
    # FRD-PRESENTATION §5.1
    Scenario: Architecture diagram rendered as PNG in slide
      Given the ArchitectureOutput contains valid mermaidCode
      When the Mermaid CLI renders the diagram at 1920x1080
      Then the PNG image is embedded centered in the Architecture Diagram slide
      And scaled to fit within 11 by 5 inches

    @error @api
    # FRD-PRESENTATION §5.1
    Scenario: Diagram conversion failure inserts placeholder slide
      Given the ArchitectureOutput contains mermaidCode that fails to render
      When all fallback attempts fail (retry with neutral theme, SVG fallback)
      Then a placeholder slide is inserted with a grey dashed border box
      And the text says "Architecture diagram could not be rendered as an image."
      And the ArchitectureOutput.narrative is displayed below truncated to 400 characters
      And warnings array includes "Diagram conversion failed — placeholder used"

  # ──────────────────────────────────────────────────
  # Rule: Export API
  # ──────────────────────────────────────────────────
  Rule: The PPTX export API handles auth, errors, and caching

    @error @api
    # FRD-PRESENTATION §7.1
    Scenario: Reject export for unauthorized user
      Given the project belongs to a different user
      When I send a GET request to "/api/projects/{projectId}/export/pptx"
      Then I receive a 403 response with error "Forbidden"

    @error @api
    # FRD-PRESENTATION §7.1
    Scenario: Reject export when no agent outputs exist
      Given no agents besides PM have produced output
      When I send a GET request to "/api/projects/{projectId}/export/pptx"
      Then I receive a 422 response with error "No agent outputs available to generate a deck"

    @error @api
    # FRD-PRESENTATION §7.1
    Scenario: Reject concurrent generation for same project
      Given PPTX generation is already in progress for this project
      When I send another GET request to "/api/projects/{projectId}/export/pptx"
      Then I receive a 409 response with error "Generation in progress"
      And the response includes retryAfter of 5 seconds

    @error @api
    # FRD-PRESENTATION §9
    Scenario: Unrecoverable generation failure returns 500
      Given PptxGenJS throws an unexpected error during generation
      When the deck generation fails
      Then I receive a 500 response with error "Presentation generation failed"
      And the full stack trace is logged server-side

  # ──────────────────────────────────────────────────
  # Rule: Regeneration Logic
  # ──────────────────────────────────────────────────
  Rule: The deck is regenerated when source data changes

    @happy-path @api
    # FRD-PRESENTATION §7.2
    Scenario: Serve cached deck when source data unchanged
      Given a PPTX was previously generated
      And no agent outputs have changed since generation
      When I send a GET request to "/api/projects/{projectId}/export/pptx"
      Then the cached PPTX buffer is served without regeneration
      And the sourceHash matches

    @happy-path @api
    # FRD-PRESENTATION §7.2
    Scenario: Regenerate deck when agent outputs have changed
      Given a PPTX was previously generated
      And the seller has modified the architecture after the last generation
      When I send a GET request to "/api/projects/{projectId}/export/pptx"
      Then a new deck is generated reflecting the updated architecture
      And the new sourceHash differs from the previous one

    @happy-path @api
    # FRD-PRESENTATION §7.2
    Scenario: Force regeneration with query parameter
      Given a cached deck exists with matching sourceHash
      When I send a GET request to "/api/projects/{projectId}/export/pptx?force=true"
      Then the deck is regenerated regardless of sourceHash match

  # ──────────────────────────────────────────────────
  # Rule: Slide Count Limits & Truncation
  # ──────────────────────────────────────────────────
  Rule: The deck enforces a maximum of 20 slides

    @edge-case @api
    # FRD-PRESENTATION §6.3
    Scenario: Deck exceeding 20 slides is truncated
      Given the project has many services and value drivers producing 24 slides
      When the deck is generated
      Then the total slide count is at most 20
      And cost detail slides are collapsed to show top-10 items with "Other" row
      And service slides are collapsed to a single slide with top-8 services
      And warnings array records the truncation actions taken

    @edge-case @api
    # FRD-PRESENTATION §6.4
    Scenario: Long content is truncated per content type rules
      When the deck is generated
      Then slide titles are truncated at 60 characters with ellipsis
      And body text blocks are truncated at 500 characters at the last sentence boundary
      And table cells are truncated at 100 characters

  # ──────────────────────────────────────────────────
  # Rule: Frontend Behavior
  # ──────────────────────────────────────────────────
  Rule: The UI provides download, progress, and regeneration prompts

    @happy-path @ui
    # FRD-PRESENTATION §8.1
    Scenario: Download button enabled when agent outputs exist
      Given at least one agent besides PM has completed output
      Then the "Download PowerPoint" button is enabled in the chat interface

    @edge-case @ui
    # FRD-PRESENTATION §8.1
    Scenario: Download button disabled when no agent outputs exist
      Given no specialist agents have completed output
      Then the "Download PowerPoint" button is disabled
      And the tooltip says "No agent outputs to export yet"

    @happy-path @ui
    # FRD-PRESENTATION §8.2
    Scenario: Download shows generation progress
      When I click "Download PowerPoint"
      Then the button text changes to "Generating…" with a spinner
      And if it takes longer than 10 seconds, an inline message says "Building your deck — this may take a moment…"
      And on completion, a toast notification says "PowerPoint downloaded successfully" with slide count

    @happy-path @ui
    # FRD-PRESENTATION §8.3
    Scenario: Regeneration prompt after agent output changes
      Given a PPTX was previously generated
      And the seller has modified the architecture since then
      Then the Download button shows a badge indicator "Updates available"
      And clicking it triggers regeneration with a toast "Deck regenerated with latest changes"

  # ──────────────────────────────────────────────────
  # Rule: Edge Cases
  # ──────────────────────────────────────────────────
  Rule: The Presentation Agent handles edge cases gracefully

    @edge-case @api
    # FRD-PRESENTATION §10.5
    Scenario: Cost line items exceed 50 items
      Given the CostEstimate has 55 line items
      When the deck is generated
      Then the top 20 by cost are shown on slides
      And remaining items are collapsed into an "Other services" row with summed cost

    @edge-case @api
    # FRD-PRESENTATION §10.7
    Scenario: Customer name with special characters sanitized for filename
      Given the customerName is "Contoso (UK) Ltd."
      When the deck is exported
      Then the filename replaces non-alphanumeric characters with dashes
      And the slide text renders the customer name as-is

    @edge-case @api
    # FRD-PRESENTATION §10.15
    Scenario: Approximate pricing flagged on cost slides
      Given the CostEstimate pricingSource is "approximate"
      When the deck is generated
      Then the cost slides display an amber badge "⚠ Approximate pricing — API was unavailable"

    @edge-case @api
    # FRD-PRESENTATION §9
    Scenario: PPTX generation fails and PDF fallback is attempted
      Given PPTX generation has failed after 2 retries
      When the server attempts a PDF fallback export
      Then the response Content-Type is "application/pdf"
      And the X-Export-Fallback header is set to "pdf"
      And the frontend notifies the user about the PDF format
