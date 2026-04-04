Feature: Pipeline execution flow
  The agent pipeline must execute in correct order with approval gates.

  Scenario: BV completes before architect starts
    Given a project state ready for the pipeline
    And the business value agent has completed
    When the pipeline processes the BV result
    Then the BV result should be emitted before architect starts
    And an approval gate should be present after BV

  Scenario: Architect runs only after BV approval
    Given BV has completed with value drivers
    When the user approves the BV result
    Then the architect agent should start
    And the architect should not have started during BV execution

  Scenario: Full pipeline ordering
    Given all agents are active
    When the pipeline runs to completion
    Then the execution order should be BV then Architect then Cost then ROI then Presentation

  Scenario: Skipped agent does not block pipeline
    Given business_value is not in active agents
    When the pipeline runs
    Then business_value should be marked as skipped
    And architect should still execute

  Scenario: Pipeline continues after non-required agent failure
    Given the cost agent fails during execution
    When the pipeline processes the error
    Then the ROI agent should still be attempted
    And the cost step should be marked as failed
