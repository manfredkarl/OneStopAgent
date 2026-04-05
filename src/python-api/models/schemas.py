from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Any
from datetime import datetime, timezone
import uuid


class CompanyProfile(BaseModel):
    """Structured company intelligence profile extracted from public sources."""
    name: str
    legalName: Optional[str] = None
    ticker: Optional[str] = None
    website: Optional[str] = None
    logoUrl: Optional[str] = None

    # Firmographics
    industry: Optional[str] = None
    subIndustry: Optional[str] = None
    headquarters: Optional[str] = None
    foundedYear: Optional[int] = None
    employeeCount: Optional[int] = None
    employeeCountSource: Optional[str] = None

    # Financials
    annualRevenue: Optional[float] = None
    revenueCurrency: Optional[str] = None
    fiscalYear: Optional[str] = None
    revenueSource: Optional[str] = None
    itSpendEstimate: Optional[float] = None
    itSpendRatio: Optional[float] = None

    @field_validator("employeeCount")
    @classmethod
    def employee_count_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError(f"must be positive, got {v}")
        return v

    @field_validator("annualRevenue")
    @classmethod
    def annual_revenue_must_be_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("itSpendRatio")
    @classmethod
    def it_spend_ratio_must_be_in_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"must be between 0.0 and 1.0, got {v}")
        return v

    # Technology
    cloudProvider: Optional[str] = None
    knownAzureUsage: Optional[list[str]] = None
    erp: Optional[str] = None
    techStackNotes: Optional[str] = None

    # Derived / fallback fields
    hourlyLaborRate: Optional[float] = None
    sizeTier: Optional[str] = None  # "small" | "mid-market" | "enterprise" for fallbacks

    # Metadata
    confidence: Literal["high", "medium", "low"] = "low"
    sources: list[str] = Field(default_factory=list)
    enrichedAt: Optional[str] = None
    disambiguated: bool = False


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    description: str
    customer_name: Optional[str] = None
    company_profile: Optional[dict[str, Any]] = None
    active_agents: list[str] = Field(
        default_factory=lambda: [
            "architect",
            "cost",
            "business_value",
            "roi",
            "presentation",
        ]
    )
    status: Literal["in_progress", "completed", "error"] = "in_progress"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    role: Literal["user", "agent"]
    agent_id: Optional[str] = None
    content: str
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateProjectRequest(BaseModel):
    description: str = Field(min_length=10, max_length=5000)
    customer_name: Optional[str] = Field(default=None, max_length=200)
    active_agents: Optional[list[str]] = None
    company_profile: Optional[dict[str, Any]] = None


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class PlanStep(BaseModel):
    tool: str
    agent_name: str
    emoji: str
    reason: str
    status: Literal["pending", "running", "done", "skipped"] = "pending"
