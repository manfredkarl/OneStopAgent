Feature: Company intelligence search
  Company search should return rich profiles with proper confidence scoring.

  Scenario: Fallback profile for unknown company
    Given an unknown company name "XYZ Fake Corp 12345"
    When the fallback profile is requested for size "mid-market"
    Then the profile should have employee count between 500 and 5000
    And the confidence should be "low"
    And the profile name should contain the company name

  Scenario: Company profile confidence scoring
    Given a profile with employees, revenue, and headquarters
    When confidence is assessed
    Then confidence should be "high"

  Scenario: Partial data confidence scoring
    Given a profile with only employee count
    When confidence is assessed
    Then confidence should not be "high"

  Scenario: IT spend estimation
    Given a company with annual revenue 51200000000
    When IT spend is estimated
    Then estimated IT spend should be between 1 billion and 3 billion

  Scenario: Employee scoping
    Given a company with 79400 total employees
    When affected employees are scoped at 15 percent
    Then the result should be approximately 11910
