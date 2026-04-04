Feature: ROI Dashboard data integrity
  The ROI dashboard must produce valid data that React can render.

  Scenario: Confidence level is always a string
    Given BV confidence is a scored dict with label "moderate"
    When the ROI agent builds the dashboard
    Then dashboard confidenceLevel should be the string "moderate"
    And dashboard confidenceLevel should not be a dict

  Scenario: Confidence level from legacy string format
    Given BV confidence is the string "high"
    When the ROI agent builds the dashboard
    Then dashboard confidenceLevel should be the string "high"

  Scenario: ROI calculation with valid inputs
    Given annual cost is 102000
    And annual impact range is 800000 to 1500000
    When the ROI agent runs
    Then roi_percent should be a positive number
    And payback_months should be a positive number
    And dashboard should contain drivers array
    And dashboard should contain projection data

  Scenario: ROI handles missing cost data
    Given no cost estimate is available
    When the ROI agent runs
    Then it should return needs_info
    And needs_info should contain a question about cost

  Scenario: ROI handles missing BV impact range
    Given cost estimate is 102000 annually
    But no annual impact range is available
    When the ROI agent runs
    Then it should return needs_info with qualitative benefits

  Scenario: Dashboard values are JSON-serializable
    Given a fully populated ROI state
    When the dashboard is serialized to JSON
    Then no TypeError should be raised
    And all values should be primitive types or arrays
