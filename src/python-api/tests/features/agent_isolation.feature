Feature: Agent data isolation
  Agents must not leak data from other agents into their outputs.

  Scenario: Architect context excludes BV data
    Given a state with completed business value data
    When the architect builds its context string
    Then the context should contain the user input
    And the context should contain shared assumptions
    And the context should not contain "Value drivers"
    And the context should not contain "annual_impact_range"

  Scenario: Architect context includes relevant data only
    Given a state with brainstorming data for Manufacturing industry
    When the architect builds its context string
    Then the context should contain "Manufacturing"
    And the context should contain shared assumptions

  Scenario: State to_context_string includes BV for other agents
    Given a state with completed business value data
    When to_context_string is called on the full state
    Then the result should contain "Value drivers"
