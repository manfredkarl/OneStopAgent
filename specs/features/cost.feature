@cost
Feature: Cost Estimation
  As an Azure seller
  I want the Cost Specialist Agent to estimate Azure costs using the Retail Prices API
  So that I can present monthly and annual cost projections to my customer

  Background:
    Given I am authenticated as an Azure seller
    And I have an active project with architecture and service selections

  # ──────────────────────────────────────────────────
  # Rule: API Pricing & Calculation
  # ──────────────────────────────────────────────────
  Rule: The Cost Agent queries Azure Retail Prices API and calculates costs

    @happy-path @api
    # FRD-COST §2.2, §3.2
    Scenario: Generate cost estimate with live pricing
      Given the Azure Specialist has selected the following services:
        | serviceName          | sku     | region  |
        | Azure App Service    | B1      | eastus  |
        | Azure SQL Database   | S1      | eastus  |
        | Azure Blob Storage   | Hot LRS | eastus  |
      When the Cost Specialist Agent is invoked
      Then the response contains a CostEstimate with currency "USD"
      And each service has a calculated monthlyCost
      And totalMonthly equals the sum of all line item costs
      And totalAnnual equals totalMonthly multiplied by 12
      And pricingSource is "live"
      And generatedAt is a valid ISO 8601 timestamp

    @happy-path @api
    # FRD-COST §2.4, §4.1
    Scenario: Calculate App Service B1 monthly cost correctly
      Given the Azure Retail Prices API returns retailPrice 0.075 for App Service B1 in eastus
      And hoursPerMonth is 730
      When the Cost Agent calculates the monthly cost
      Then the monthlyCost for Azure App Service is 54.75
      And the assumption "730 hours/month (24/7 operation)" is included

    @happy-path @api
    # FRD-COST §4.5
    Scenario: Include explicit assumptions in every estimate
      When the Cost Specialist generates an estimate
      Then the assumptions array includes:
        | assumption                                         |
        | Pay-as-you-go pricing (no EA/CSP discounts)       |
        | All prices in USD                                  |
      And assumptions include the scale parameters used
      And assumptions include the region

    @edge-case @api
    # FRD-COST §4.1
    Scenario: Free-tier services display zero cost with assumption note
      Given Azure Application Insights is selected with usage within the free 5 GB tier
      When the Cost Agent calculates the estimate
      Then the monthlyCost for Application Insights is 0.00
      And an assumption says "First 5 GB Application Insights data included free"
      And the service is still included in the cost table

  # ──────────────────────────────────────────────────
  # Rule: Parameter Adjustment
  # ──────────────────────────────────────────────────
  Rule: Sellers can adjust scale parameters and trigger recalculation

    @happy-path @api
    # FRD-COST §5.1, §5.2
    Scenario: Adjust concurrent users triggers recalculation
      Given the current estimate assumes 1000 concurrent users
      When I change concurrentUsers to 5000
      Then compute instance count is recalculated based on the new user count
      And a new CostEstimate is returned with updated costs
      And generatedAt timestamp is updated

    @happy-path @api
    # FRD-COST §5.2
    Scenario: Change region triggers new API queries
      Given the current estimate is for region "eastus"
      When I change the region to "westeurope"
      Then new Azure Retail Prices API queries are issued for "westeurope"
      And all service prices are updated for the new region

    @happy-path @api
    # FRD-COST §5.3
    Scenario: Diff display shows before and after costs
      Given the previous monthly total was $84.75
      When I double the concurrent users and recalculate
      Then the diff table shows previous and new monthly cost per service
      And the delta column shows absolute and percentage changes
      And increases are highlighted in red/warning

    @edge-case @api
    # FRD-COST §5.2
    Scenario: Non-region parameter changes reuse cached retail prices
      Given the current estimate has cached retailPrice values
      When I change only the hoursPerMonth from 730 to 365
      Then the cached retail prices are reused
      And no new API queries are issued
      And totals are recalculated with the new hours value

  # ──────────────────────────────────────────────────
  # Rule: Caching & Fallback
  # ──────────────────────────────────────────────────
  Rule: The agent caches prices and falls back gracefully when API is unavailable

    @happy-path @api
    # FRD-COST §6.1
    Scenario: Use cached prices within 24-hour TTL
      Given a cached price exists for "Azure App Service:B1:eastus" from 6 hours ago
      When the Cost Agent needs pricing for that service
      Then the cached price is used
      And pricingSource is set to "cached"
      And no API call is made

    @edge-case @api
    # FRD-COST §6.1
    Scenario: Expired cache triggers fresh API query
      Given a cached price exists for "Azure SQL Database:S1:eastus" from 25 hours ago
      When the Cost Agent needs pricing for that service
      Then the expired cache is discarded
      And a fresh API call is made

    @error @api
    # FRD-COST §6.2
    Scenario: API failure with retries falls back to expired cache
      Given the Azure Retail Prices API is returning 500 errors
      And an expired cache entry exists for the requested service
      When the Cost Agent retries 3 times with exponential backoff
      Then the expired cached price is used
      And pricingSource is set to "approximate"
      And a warning is displayed about approximate pricing

    @error @api
    # FRD-COST §6.2, §8
    Scenario: API failure with no cache returns error
      Given the Azure Retail Prices API is unavailable
      And no cached prices exist for any service
      When the Cost Agent attempts to generate an estimate
      Then an error is returned suggesting to try again later
      And no estimate is generated

    @edge-case @api
    # FRD-COST §6.3
    Scenario Outline: Pricing source indicator reflects data freshness
      Given the pricing data source is "<source>"
      Then the UI displays a "<badge>" badge
      And the badge color is "<color>"

      Examples:
        | source      | badge                 | color  |
        | live        | ✅ Live pricing        | green  |
        | cached      | 🕐 Cached pricing      | yellow |
        | approximate | ⚠️ Approximate pricing | orange |

  # ──────────────────────────────────────────────────
  # Rule: Disclaimer & Formatting
  # ──────────────────────────────────────────────────
  Rule: All cost outputs include mandatory disclaimers and proper formatting

    @happy-path @ui
    # FRD-COST §7.4
    Scenario: Disclaimer always displayed below cost table
      When the cost estimate is rendered
      Then a disclaimer is shown stating estimates use Azure Retail pay-as-you-go pricing
      And the disclaimer states EA, CSP, and negotiated discounts are excluded
      And the disclaimer includes "All prices in USD" and the generation timestamp

    @happy-path @ui
    # FRD-COST §9.5
    Scenario: Currency formatting follows USD conventions
      Given the cost estimate includes a service costing 1234.56 per month
      Then the monthlyCost is displayed as "$1,234.56"
      And the dollar sign prefix, two decimal places, and comma separator are used

  # ──────────────────────────────────────────────────
  # Rule: Edge Cases
  # ──────────────────────────────────────────────────
  Rule: The Cost Agent handles edge cases in pricing data

    @edge-case @api
    # FRD-COST §9.1
    Scenario: API returns zero results for a service SKU
      Given the Retail Prices API returns 0 items for "Azure Custom Vision" in "eastus"
      When the Cost Agent processes the response
      Then the service is included with monthlyCost 0.00
      And an assumption says "Pricing unavailable for Azure Custom Vision in eastus — excluded from total"

    @edge-case @api
    # FRD-COST §9.2
    Scenario: Unknown SKU triggers broader query
      Given the Azure Specialist selected SKU "B1 v2" which is not in the pricing catalog
      When the Cost Agent queries the API
      Then a broader query without armSkuName filter is attempted
      And if a close match "B1" exists, it is used with an assumption note

    @edge-case @api
    # FRD-COST §9.3
    Scenario: Service not available in selected region
      Given the seller selected region "southafricanorth"
      And "Azure AI Document Intelligence" is not offered there
      When the Cost Agent encounters this
      Then the message says the service is not available in that region
      And the nearest available region is suggested
      And auto-switch does not occur without seller confirmation

    @edge-case @api
    # FRD-COST §9.4
    Scenario: Very large estimate exceeding $100K per month
      Given the scale parameters produce an estimate of $150,000 per month
      When the estimate is rendered
      Then a visual warning says "This estimate exceeds $100,000/month"
      And the message suggests considering reserved instances or EA pricing

    @edge-case @api
    # FRD-COST §9.7
    Scenario: Multiple meters per service produce separate line items
      Given Azure Cosmos DB returns separate meters for RU/s and storage
      When the Cost Agent processes the response
      Then two line items are created: "Azure Cosmos DB (RU/s)" and "Azure Cosmos DB (Storage)"
      And each has its own monthlyCost

    @edge-case @api
    # FRD-COST §9.8
    Scenario: API pagination follows NextPageLink up to 10 pages
      Given the API response includes a NextPageLink
      When the Cost Agent retrieves prices
      Then it follows NextPageLink until null or 10 pages
      And all collected items are used for price calculation
