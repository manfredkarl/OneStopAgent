@architecture
Feature: Architecture & Azure Services
  As an Azure seller
  I want the System Architect and Azure Specialist agents to generate architecture diagrams and select Azure services
  So that I can propose a concrete Azure solution to my customer

  Background:
    Given I am authenticated as an Azure seller
    And I have an active project with gathered requirements

  # ──────────────────────────────────────────────────
  # Rule: Mermaid Diagram Generation
  # ──────────────────────────────────────────────────
  Rule: The System Architect generates valid Mermaid diagrams with complexity limits

    @happy-path @api
    # FRD-ARCHITECTURE §2.2, §2.3
    Scenario: Generate a valid architecture diagram for a web application
      Given the project requirements include:
        | key      | value                     |
        | workload | web app                   |
        | scale    | 1000 concurrent users     |
        | data     | relational, <50 GB        |
        | auth     | Entra ID SSO              |
      When the System Architect Agent is invoked
      Then the response contains valid Mermaid flowchart TD syntax
      And metadata.diagramType is "flowchart"
      And metadata.nodeCount is less than or equal to 30
      And metadata.edgeCount is less than or equal to 60
      And the components array has an entry for every diagram node

    @happy-path @api
    # FRD-ARCHITECTURE §2.3.3
    Scenario: Nodes use correct shapes by category
      Given the System Architect generates a diagram with varied component categories
      Then user/external nodes use trapezoid shape
      And compute nodes use rectangle shape
      And data store nodes use cylinder shape
      And networking nodes use rounded shape
      And security nodes use hexagon shape
      And AI/ML nodes use stadium shape

    @happy-path @api
    # FRD-ARCHITECTURE §2.5
    Scenario: Architecture narrative is seller-appropriate
      When the System Architect Agent generates output
      Then the narrative field contains 2 to 4 paragraphs of Markdown text
      And it is 150 to 400 words
      And it describes data flow, scaling strategy, and security posture
      And it uses bold for Azure service names
      And it contains no code snippets, pricing, or SKU details

    @edge-case @api
    # FRD-ARCHITECTURE §2.3.2
    Scenario: Diagram exceeding 30 nodes triggers consolidation
      Given the project requirements result in 35 potential components
      When the System Architect Agent generates a diagram
      Then it consolidates related nodes into logical groups
      And the final diagram has 30 or fewer nodes

    @error @api
    # FRD-ARCHITECTURE §2.3.5
    Scenario: Invalid Mermaid syntax triggers auto-retry
      Given the System Architect Agent generates Mermaid code with a syntax error
      When the validation pipeline parses the diagram
      Then the agent is re-prompted with the parse error details
      And a retry is attempted up to 2 times
      And metadata.retryCount reflects the number of retries

    @error @api
    # FRD-ARCHITECTURE §2.3.5
    Scenario: Mermaid validation fails after all retries
      Given the System Architect has failed Mermaid validation twice
      When the third attempt also fails
      Then the response includes the raw mermaidCode
      And an error field with the parse error
      And metadata.retryCount is 2

    @happy-path @api
    # FRD-ARCHITECTURE §2.4
    Scenario: Components match diagram nodes exactly
      When the System Architect generates output
      Then components.length equals metadata.nodeCount
      And each component has name, azureService, description, and category
      And components are ordered topologically

  # ──────────────────────────────────────────────────
  # Rule: Input Validation
  # ──────────────────────────────────────────────────
  Rule: The System Architect validates its input contract

    @error @api
    # FRD-ARCHITECTURE §2.1
    Scenario: Reject input with empty requirements
      When the System Architect Agent is invoked with empty requirements
      Then the response is 400 EMPTY_REQUIREMENTS

    @error @api
    # FRD-ARCHITECTURE §2.1
    Scenario: Reject input with invalid project ID
      When the System Architect Agent is invoked with an invalid projectId
      Then the response is 400 INVALID_PROJECT_ID

    @error @api
    # FRD-ARCHITECTURE §2.1
    Scenario: Reject modification request exceeding 500 characters
      When the System Architect receives a modificationRequest of 501 characters
      Then the response is 400 INVALID_MODIFICATION

  # ──────────────────────────────────────────────────
  # Rule: Azure Specialist Agent — Service Selection
  # ──────────────────────────────────────────────────
  Rule: The Azure Specialist maps architecture components to Azure services with SKUs

    @happy-path @api
    # FRD-ARCHITECTURE §3.2
    Scenario: Select Azure services for architecture components
      Given the System Architect has produced an architecture with components:
        | name                   | category   |
        | Azure App Service      | compute    |
        | Azure SQL Database     | data       |
        | Azure Blob Storage     | storage    |
      When the Azure Specialist Agent is invoked
      Then each component receives a ServiceSelection with serviceName, sku, region, and capabilities
      And each selection includes mcpSourced flag and learnUrl
      And alternatives are provided where viable options exist

    @happy-path @api
    # FRD-ARCHITECTURE §3.3.1
    Scenario Outline: SKU selection scales with concurrent users
      Given the scale requirements specify <users> concurrent users
      When the Azure Specialist selects an App Service SKU
      Then the recommended SKU is "<expected_sku>"

      Examples:
        | users | expected_sku |
        | 50    | B1           |
        | 500   | S1           |
        | 10000 | P2v3         |

    @happy-path @api
    # FRD-ARCHITECTURE §3.3.3
    Scenario: Region defaults to eastus when no preference specified
      Given no regionPreference is provided in the input
      When the Azure Specialist selects service regions
      Then all services default to "eastus"

    @edge-case @api
    # FRD-ARCHITECTURE §3.3.3
    Scenario: Service unavailable in preferred region falls back to nearest
      Given the regionPreference is "brazilsouth"
      And "Azure AI Document Intelligence" is not available in "brazilsouth"
      When the Azure Specialist selects the region for that service
      Then the nearest available region is selected
      And the deviation is noted in the output

    @happy-path @api
    # FRD-ARCHITECTURE §3.4
    Scenario: Trade-offs are presented in structured format
      Given a component has viable alternatives
      When the Azure Specialist returns service selections
      Then alternatives include serviceName and tradeOff fields
      And at most 3 alternatives are listed per component
      And the tradeOff text follows the pattern "{Alternative} offers {advantage} but {disadvantage}"

  # ──────────────────────────────────────────────────
  # Rule: MCP Integration
  # ──────────────────────────────────────────────────
  Rule: Both agents use Microsoft Learn MCP Server for grounding

    @happy-path @api
    # FRD-ARCHITECTURE §4.1, §4.4
    Scenario: Architecture grounded with MCP data
      Given the Microsoft Learn MCP Server is available
      When the System Architect Agent generates output
      Then metadata.mcpSourced is true
      And the narrative includes inline citations to Microsoft Learn URLs
      And each ServiceSelection has mcpSourced true and a valid learnUrl

    @error @api
    # FRD-ARCHITECTURE §4.3
    Scenario: MCP Server unavailable triggers fallback to built-in knowledge
      Given the Microsoft Learn MCP Server is unavailable
      When the System Architect Agent generates output
      Then metadata.mcpSourced is false
      And a visible banner is displayed with "Unverified — MCP source unavailable"
      And recommendations are based on built-in knowledge
      And learnUrl fields are populated as best-effort but marked as unverified

    @edge-case @api
    # FRD-ARCHITECTURE §4.3
    Scenario: MCP Server times out after 10 seconds
      Given the MCP Server does not respond within 10 seconds
      When the agent is waiting for MCP data
      Then the agent proceeds with built-in knowledge
      And mcpSourced is set to false on all outputs

  # ──────────────────────────────────────────────────
  # Rule: Architecture Modification Flow
  # ──────────────────────────────────────────────────
  Rule: Sellers can modify the architecture incrementally

    @happy-path @api
    # FRD-ARCHITECTURE §5.1, §5.2
    Scenario: Add a component via modification request
      Given an architecture has been generated with 5 components
      When I send a modification request "Add Azure Cache for Redis between the API and the database"
      Then the System Architect applies a delta update
      And the updated diagram includes a new Redis node
      And unchanged components remain identical
      And the Azure Specialist re-evaluates only the new component

    @happy-path @api
    # FRD-ARCHITECTURE §5.2
    Scenario: Replace a service via modification request
      Given an architecture includes "Azure Cosmos DB" as a data store
      When I send a modification request "Replace Cosmos DB with Azure SQL"
      Then the mermaidCode is updated with the replacement
      And the components array reflects the swap
      And the narrative is updated

    @happy-path @api
    # FRD-ARCHITECTURE §5.2
    Scenario: Remove a component via modification request
      Given an architecture includes "Azure CDN" for content delivery
      When I send a modification request "Remove the CDN, we don't need it"
      Then the CDN node and its edges are removed from the diagram
      And the components array no longer includes the CDN entry
      And the narrative is updated to reflect the removal

    @error @api
    # FRD-ARCHITECTURE §5.3
    Scenario: Modification rejected when it would exceed 30-node limit
      Given an architecture already has 29 nodes
      When I send a modification request to add 3 new components
      Then the modification is rejected with a warning about exceeding the 30-node limit
      And the previous architecture is preserved unchanged

  # ──────────────────────────────────────────────────
  # Rule: Diagram Export
  # ──────────────────────────────────────────────────
  Rule: Architecture diagrams can be exported as PNG or SVG

    @happy-path @api
    # FRD-ARCHITECTURE §6.1
    Scenario: Export architecture diagram as PNG
      Given an architecture diagram has been generated
      When I send a GET request to "/api/projects/{projectId}/export/architecture?format=png"
      Then I receive a 200 response with Content-Type "image/png"
      And the Content-Disposition header contains the filename with project ID

    @happy-path @api
    # FRD-ARCHITECTURE §6.1
    Scenario: Export architecture diagram as SVG
      Given an architecture diagram has been generated
      When I send a GET request to "/api/projects/{projectId}/export/architecture?format=svg"
      Then I receive a 200 response with Content-Type "image/svg+xml"

    @error @api
    # FRD-ARCHITECTURE §6.1
    Scenario: Export fails when no architecture has been generated
      Given no architecture has been generated for the project
      When I send a GET request to "/api/projects/{projectId}/export/architecture"
      Then I receive a 404 response with error "NO_ARCHITECTURE"
      And details say "No architecture has been generated for this project"

    @error @api
    # FRD-ARCHITECTURE §6.1
    Scenario: Export with unsupported format returns error
      When I send a GET request to "/api/projects/{projectId}/export/architecture?format=pdf"
      Then I receive a 400 response with error "INVALID_FORMAT"
      And details say "Supported formats: png, svg"
