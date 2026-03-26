@chat
Feature: Chat Interface & Project Management
  As an Azure seller using OneStopAgent
  I want to create projects, chat with agents, and manage agent selection
  So that I can scope Azure solutions for my customers efficiently

  Background:
    Given I am authenticated as an Azure seller with a valid Entra ID token

  # ──────────────────────────────────────────────────
  # Rule: Project Creation (POST /api/projects)
  # ──────────────────────────────────────────────────
  Rule: Sellers can create new projects with a description

    @happy-path @api
    # FRD-CHAT §2.1
    Scenario: Create a new project with a clear description
      When I send a POST request to "/api/projects" with body:
        | field       | value                                                                |
        | description | Modernise on-premises .NET monolith to Azure, serving 50K concurrent users across EMEA |
      Then I receive a 201 response with a project ID in UUID v4 format
      And a Project record is persisted with status "in_progress"
      And all agents are initialised as active
      And the PM Agent posts an acknowledgement message summarising the description

    @happy-path @api
    # FRD-CHAT §2.1
    Scenario: Create a new project with an optional customer name
      When I send a POST request to "/api/projects" with body:
        | field        | value                                                    |
        | description  | AI-powered customer support chatbot for retail banking   |
        | customerName | Contoso Ltd                                              |
      Then I receive a 201 response with a project ID
      And the project record has customerName "Contoso Ltd"

    @error @api
    # FRD-CHAT §3.1, §7.1
    Scenario: Reject project creation when description is missing
      When I send a POST request to "/api/projects" with body:
        | field        | value      |
        | customerName | Contoso    |
      Then I receive a 400 response with error "Field 'description' is required."

    @error @api
    # FRD-CHAT §3.1, §7.1
    Scenario: Reject project creation when description is empty whitespace
      When I send a POST request to "/api/projects" with body:
        | field       | value |
        | description |       |
      Then I receive a 400 response with error "Project description must not be empty."

    @edge-case @api
    # FRD-CHAT §3.1, §8 EC-3
    Scenario: Accept project description at exact maximum length
      When I send a POST request to "/api/projects" with a description of exactly 5000 characters
      Then I receive a 201 response with a project ID

    @error @api
    # FRD-CHAT §3.1, §7.1
    Scenario: Reject project description exceeding maximum length
      When I send a POST request to "/api/projects" with a description of 5001 characters
      Then I receive a 400 response with error "Project description must not exceed 5,000 characters."

    @error @api
    # FRD-CHAT §3.1, §7.1
    Scenario: Reject project with customer name exceeding 200 characters
      When I send a POST request to "/api/projects" with body:
        | field        | value                                          |
        | description  | E-commerce platform migration                  |
        | customerName | <a string of 201 characters>                   |
      Then I receive a 400 response with error "Customer name must not exceed 200 characters."

    @error @api
    # FRD-CHAT §3.1, §7.1
    Scenario: Reject project description containing script injection
      When I send a POST request to "/api/projects" with body:
        | field       | value                                         |
        | description | <script>alert('xss')</script> build a web app |
      Then I receive a 400 response with error "Description contains invalid content."

    @error @api
    # FRD-CHAT §7.1
    Scenario: Reject project creation when storage is unavailable
      Given the backend storage is unavailable
      When I send a POST request to "/api/projects" with body:
        | field       | value                     |
        | description | IoT monitoring dashboard  |
      Then I receive a 500 response with error "Project creation failed. Please try again."
      And no project record or chat messages are persisted

  # ──────────────────────────────────────────────────
  # Rule: Project Listing & Retrieval
  # ──────────────────────────────────────────────────
  Rule: Sellers can list and retrieve their projects

    @happy-path @api
    # FRD-CHAT §2.2
    Scenario: List all projects for the authenticated user
      Given I have 3 existing projects
      When I send a GET request to "/api/projects"
      Then I receive a 200 response with 3 projects ordered by updatedAt descending
      And each project description is truncated to 200 characters

    @edge-case @api
    # FRD-CHAT §2.2, §8 EC-1
    Scenario: List projects when user has no projects
      Given I have no existing projects
      When I send a GET request to "/api/projects"
      Then I receive a 200 response with an empty array

    @happy-path @api
    # FRD-CHAT §2.3
    Scenario: Retrieve full project state by ID
      Given I have a project with ID "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
      When I send a GET request to "/api/projects/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
      Then I receive a 200 response with the full Project object
      And the response includes activeAgents, context, status, and timestamps

    @error @api
    # FRD-CHAT §2.3, §7.1
    Scenario: Reject retrieval of another user's project
      Given a project exists owned by a different user
      When I send a GET request to "/api/projects/{otherUsersProjectId}"
      Then I receive a 403 response with error "You do not have access to this project."

    @error @api
    # FRD-CHAT §2.3, §7.1, §8 EC-17
    Scenario: Reject retrieval of a non-existent project
      When I send a GET request to "/api/projects/non-existent-uuid"
      Then I receive a 404 response with error "Project not found."

  # ──────────────────────────────────────────────────
  # Rule: Chat Messaging (POST /api/projects/:id/chat)
  # ──────────────────────────────────────────────────
  Rule: Sellers can send chat messages and receive agent responses

    @happy-path @api
    # FRD-CHAT §2.4
    Scenario: Send a chat message and receive PM Agent response
      Given I have an active project
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field   | value                                                          |
        | message | The customer needs HIPAA compliance and deployment in US East. |
      Then I receive a 200 response with an agent response
      And the response has role "agent" and agentId "pm"
      And the user message and agent response are persisted as ChatMessages

    @happy-path @api
    # FRD-CHAT §2.4
    Scenario: Send a message targeting a specific agent
      Given I have an active project with the cost agent activated
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field       | value                                       |
        | message     | Re-run cost estimation for US West region   |
        | targetAgent | cost                                        |
      Then I receive a 200 response from the cost agent

    @error @api
    # FRD-CHAT §3.2, §7.1
    Scenario: Reject chat message with empty content
      Given I have an active project
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field   | value |
        | message |       |
      Then I receive a 400 response with error "Message must not be empty."

    @edge-case @api
    # FRD-CHAT §3.2, §8 EC-5
    Scenario: Accept chat message at exact maximum length of 10000 characters
      Given I have an active project
      When I send a POST request to "/api/projects/{projectId}/chat" with a message of exactly 10000 characters
      Then I receive a 200 response with an agent response

    @error @api
    # FRD-CHAT §3.2, §7.1
    Scenario: Reject chat message exceeding maximum length
      Given I have an active project
      When I send a POST request to "/api/projects/{projectId}/chat" with a message of 10001 characters
      Then I receive a 400 response with error "Message must not exceed 10,000 characters."

    @error @api
    # FRD-CHAT §3.2, §7.1
    Scenario: Reject chat message targeting an unknown agent
      Given I have an active project
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field       | value                    |
        | message     | Run analysis             |
        | targetAgent | nonexistent-agent        |
      Then I receive a 422 response with error "Unknown agent 'nonexistent-agent'."

    @error @api
    # FRD-CHAT §3.2, §7.1
    Scenario: Reject chat message targeting an inactive agent
      Given I have an active project with the cost agent deactivated
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field       | value               |
        | message     | Estimate my costs   |
        | targetAgent | cost                |
      Then I receive a 422 response with error "Agent 'cost' is not active in this project."

    @error @api
    # FRD-CHAT §7.1
    Scenario: Reject chat when agent exceeds hard timeout
      Given I have an active project
      And the targeted agent takes longer than 120 seconds to respond
      When I send a POST request to "/api/projects/{projectId}/chat" with body:
        | field   | value                |
        | message | Generate architecture |
      Then I receive a 504 response with error "Agent response timed out. Please try again."

  # ──────────────────────────────────────────────────
  # Rule: Chat History (GET /api/projects/:id/chat)
  # ──────────────────────────────────────────────────
  Rule: Sellers can retrieve paginated chat history

    @happy-path @api
    # FRD-CHAT §2.5
    Scenario: Retrieve chat history with default pagination
      Given I have a project with 75 chat messages
      When I send a GET request to "/api/projects/{projectId}/chat"
      Then I receive a 200 response with 50 messages in reverse chronological order
      And hasMore is true
      And nextCursor is a valid message UUID

    @happy-path @api
    # FRD-CHAT §2.5
    Scenario: Retrieve next page of chat history using cursor
      Given I have a project with 75 chat messages
      And I have the nextCursor from the first page
      When I send a GET request to "/api/projects/{projectId}/chat?before={nextCursor}&limit=50"
      Then I receive a 200 response with 25 messages
      And hasMore is false
      And nextCursor is null

    @error @api
    # FRD-CHAT §3.4, §7.1
    Scenario: Reject chat history with invalid limit parameter
      Given I have an active project
      When I send a GET request to "/api/projects/{projectId}/chat?limit=0"
      Then I receive a 400 response with error "Parameter 'limit' must be an integer between 1 and 100."

  # ──────────────────────────────────────────────────
  # Rule: Agent Selection & Control
  # ──────────────────────────────────────────────────
  Rule: Sellers can activate and deactivate agents with constraints

    @happy-path @api
    # FRD-CHAT §2.6
    Scenario: List all agents and their statuses for a project
      Given I have an active project
      When I send a GET request to "/api/projects/{projectId}/agents"
      Then I receive a 200 response with agents listed in pipeline order
      And the System Architect has canDeactivate false
      And the PM Agent is not listed in the response

    @happy-path @api
    # FRD-CHAT §2.7, §4.3
    Scenario: Deactivate an idle optional agent
      Given I have an active project with the cost agent in "idle" status
      When I send a PATCH request to "/api/projects/{projectId}/agents/cost" with body:
        | field  | value |
        | active | false |
      Then I receive a 200 response with the cost agent status
      And the cost agent active field is false
      And the PM Agent posts a message about the removed agent

    @error @api
    # FRD-CHAT §2.7, §3.3, §7.1
    Scenario: Reject deactivation of the System Architect agent
      Given I have an active project
      When I send a PATCH request to "/api/projects/{projectId}/agents/architect" with body:
        | field  | value |
        | active | false |
      Then I receive a 409 response with error "System Architect cannot be deactivated. It is required for all downstream agents."

    @error @api
    # FRD-CHAT §2.7, §3.3, §7.1
    Scenario: Reject deactivation of a working agent without confirmation
      Given I have an active project with the azure-specialist agent currently "working"
      When I send a PATCH request to "/api/projects/{projectId}/agents/azure-specialist" with body:
        | field  | value |
        | active | false |
      Then I receive a 422 response with error "Agent 'azure-specialist' is currently working. Set 'confirm: true' to cancel its task and deactivate."

    @happy-path @api
    # FRD-CHAT §2.7, §4.3
    Scenario: Deactivate a working agent with explicit confirmation
      Given I have an active project with the azure-specialist agent currently "working"
      When I send a PATCH request to "/api/projects/{projectId}/agents/azure-specialist" with body:
        | field   | value |
        | active  | false |
        | confirm | true  |
      Then I receive a 200 response
      And the azure-specialist agent status is "idle" and active is false
      And a cancellation chat message is posted
      And any in-progress output is discarded

    @happy-path @api
    # FRD-CHAT §4.3
    Scenario: Re-activate a previously deactivated agent
      Given I have an active project with the business-value agent deactivated
      When I send a PATCH request to "/api/projects/{projectId}/agents/business-value" with body:
        | field  | value |
        | active | true  |
      Then I receive a 200 response with the business-value agent active as true

    @edge-case @api
    # FRD-CHAT §8 EC-8
    Scenario: Idempotent deactivation from concurrent tabs
      Given I have an active project with the cost agent already deactivated
      When I send a PATCH request to "/api/projects/{projectId}/agents/cost" with body:
        | field  | value |
        | active | false |
      Then I receive a 200 response with the current agent state
      And the agent remains inactive

  # ──────────────────────────────────────────────────
  # Rule: Guided Questioning Flow
  # ──────────────────────────────────────────────────
  Rule: The PM Agent conducts structured questioning to gather requirements

    @happy-path @ui
    # FRD-CHAT §4.2
    Scenario: PM Agent asks structured questions in sequence
      Given I have created a project with a clear description
      And the PM Agent has started guided questioning
      When the PM Agent posts a question about "Target users / audience"
      Then the question includes metadata with questionIndex and totalQuestions
      And the question suggests common options and allows "skip"

    @happy-path @ui
    # FRD-CHAT §4.2
    Scenario: Seller skips a question and PM assumes default
      Given the PM Agent has asked about geographic requirements
      When I respond with "skip"
      Then the PM Agent stores the default value "East US" for geography
      And the PM Agent posts an assumption message flagged with ⚠️
      And the next question is asked

    @happy-path @ui
    # FRD-CHAT §4.2
    Scenario: Seller ends questioning early by saying proceed
      Given the PM Agent has asked 4 of 10 questions
      And workload_type and user_scale have been answered
      When I respond with "proceed"
      Then the PM Agent flags all remaining unanswered topics as assumptions
      And the PM Agent posts a summary listing all requirements with assumptions marked
      And a "Start Agents" button appears

    @edge-case @ui
    # FRD-CHAT §4.2
    Scenario: PM Agent caps questions at maximum of 10
      Given the PM Agent has already asked 10 questions
      Then the PM Agent stops asking and posts a summary of gathered requirements
      And the flow advances to agent pipeline

    @edge-case @ui
    # FRD-CHAT §8 EC-22
    Scenario: PM Agent distinguishes intent from keyword matching
      Given the PM Agent is conducting guided questioning
      When I send the message "How should we proceed with compliance?"
      Then the PM Agent treats this as a question about compliance
      And does not trigger pipeline advance

  # ──────────────────────────────────────────────────
  # Rule: Authentication & Security
  # ──────────────────────────────────────────────────
  Rule: All endpoints require valid authentication

    @error @api
    # FRD-CHAT §5 SEC-1, §7.1
    Scenario: Reject request without authentication token
      When I send a POST request to "/api/projects" without a Bearer token
      Then I receive a 401 response with error "Authentication required."
      And the response includes a WWW-Authenticate header "Bearer realm=\"OneStopAgent\""

    @error @api
    # FRD-CHAT §5 SEC-1, §7.1
    Scenario: Reject request with expired authentication token
      Given my JWT token has expired
      When I send a GET request to "/api/projects"
      Then I receive a 401 response with error "Authentication token has expired. Please sign in again."

    @error @api
    # FRD-CHAT §5 SEC-4, §7.1
    Scenario: Enforce rate limiting at 60 requests per minute
      Given I have made 60 requests within the last minute
      When I send another request to any API endpoint
      Then I receive a 429 response with error "Rate limit exceeded. Try again in <N> seconds."
      And the response includes a Retry-After header

  # ──────────────────────────────────────────────────
  # Rule: Frontend Behaviour
  # ──────────────────────────────────────────────────
  Rule: The frontend renders chat, projects, and agent UI correctly

    @happy-path @ui
    # FRD-CHAT §6.1
    Scenario: Landing page renders create project form
      When I navigate to the landing page "/"
      Then I see a multi-line text area with placeholder "Describe your customer's scenario or need…"
      And I see a single-line customer name input with placeholder "Customer name (optional)"
      And the "Create Project" button is disabled
      And up to 5 recent projects are listed below the form

    @happy-path @ui
    # FRD-CHAT §6.3
    Scenario: Chat interface auto-scrolls on new agent message
      Given I am viewing the chat interface at the bottom of the thread
      When a new agent message arrives
      Then the chat thread auto-scrolls to show the new message

    @edge-case @ui
    # FRD-CHAT §6.3
    Scenario: Chat interface shows new message pill when scrolled up
      Given I have manually scrolled up 200 pixels or more from the bottom
      When a new agent message arrives
      Then a "↓ New messages" pill is displayed
      And clicking the pill scrolls to the newest message

    @edge-case @api
    # FRD-CHAT §8 EC-13
    Scenario: User message is queued while agent is working
      Given an agent is currently in "working" status
      When I send a chat message
      Then the message is accepted with a 200 response
      And it is displayed in the chat with a "queued" indicator
      And the PM Agent processes it after the current agent completes

    @edge-case @api
    # FRD-CHAT §8 EC-25
    Scenario: Agent produces an empty response
      Given I have an active project
      And the targeted agent returns no output
      Then the PM Agent posts "did not produce output" error message
      And the agent status transitions to "error"

    @edge-case @api
    # FRD-CHAT §8 EC-21
    Scenario: All optional agents deactivated leaves only PM and System Architect
      Given I have deactivated all optional agents
      Then the PM Agent warns "Only the System Architect is active"
      And the pipeline will produce only an architecture diagram
