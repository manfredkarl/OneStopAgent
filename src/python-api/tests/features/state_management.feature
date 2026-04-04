Feature: Agent state management
  The AgentState tracks pipeline progress correctly.

  Scenario: Step lifecycle tracking
    Given a fresh agent state with plan steps
    When business_value is marked as running
    Then current_step should be "business_value"
    When business_value is marked as completed
    Then "business_value" should be in completed_steps
    And current_step should be empty

  Scenario: Shared assumptions parsing
    Given shared assumptions with affected_employees 500 and hourly_labor_rate 85
    When the typed accessor is used
    Then affected_employees should be 500
    And hourly_labor_rate should be 85

  Scenario: Context string includes completed agent data
    Given a state with completed BV showing 3 value drivers
    When to_context_string is called
    Then the result should contain "Value drivers: 3 identified"

  Scenario: Workflow pauses in guided mode
    Given the execution mode is "guided"
    When checking if business_value should pause
    Then the result should be true
    When checking if cost should pause
    Then the result should be true

  Scenario: Fast-run mode skips non-gate steps
    Given the execution mode is "fast-run"
    When checking if cost should pause
    Then the result should be false
    When checking if architect should pause
    Then the result should be true
