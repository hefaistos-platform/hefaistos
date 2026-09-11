"""
Pydantic schemas for CoreTide OpenTide YAML validation.
Enforces strict schema compliance before rule persistence.
"""
from pydantic import BaseModel, Field, field_validator, UUID4
from typing import Optional, Dict, Any, List
from enum import Enum
import re


class Severity(str, Enum):
    """CoreTide severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Status(str, Enum):
    """Rule maturity status."""
    EXPERIMENTAL = "experimental"
    TEST = "test"
    STABLE = "stable"


class OpenTideMetadata(BaseModel):
    """CoreTide universal metadata schema."""
    title: str = Field(..., min_length=1, max_length=200, description="Rule title")
    description: str = Field(..., min_length=10, description="Detailed rule description")
    author: str = Field(..., min_length=1, description="Author name or organization")
    severity: Severity
    mitre_technique: str = Field(..., description="MITRE ATT&CK technique ID (e.g., T1059.001)")
    uuid: UUID4 = Field(..., description="UUIDv4 identifier")
    status: Status = Status.EXPERIMENTAL
    tags: Optional[List[str]] = Field(default_factory=list, description="Searchable tags")
    created: Optional[str] = Field(None, description="ISO 8601 timestamp")
    modified: Optional[str] = Field(None, description="ISO 8601 timestamp")

    @field_validator('mitre_technique')
    @classmethod
    def validate_mitre_technique(cls, v: str) -> str:
        """Ensure MITRE technique ID matches T####.### format."""
        pattern = r'^T\d{4}(\.\d{3})?$'
        if not re.match(pattern, v):
            raise ValueError(
                f"Invalid MITRE technique ID: {v}. Must match pattern T####[.###] (e.g., T1059 or T1059.001)"
            )
        return v


class KQLPlatform(BaseModel):
    """Microsoft Defender / Sentinel KQL schema."""
    query: str = Field(..., min_length=1, description="Kusto Query Language query")
    data_source: Optional[str] = Field(None, description="Data source identifier")
    tables: Optional[List[str]] = Field(default_factory=list, description="Required tables")


class SPLPlatform(BaseModel):
    """Splunk SPL schema."""
    query: str = Field(..., min_length=1, description="Splunk Processing Language query")
    index: Optional[str] = Field(None, description="Splunk index name")
    sourcetype: Optional[str] = Field(None, description="Splunk sourcetype")


class ElasticPlatform(BaseModel):
    """Elastic EQL schema."""
    query: str = Field(..., min_length=1, description="Elastic Event Query Language query")


class WazuhPlatform(BaseModel):
    """Wazuh XML rule schema."""
    rule: str = Field(..., min_length=1, description="XML rule content")
    level: Optional[int] = Field(None, ge=0, le=16, description="Alert severity level")
    groups: Optional[List[str]] = Field(default_factory=list, description="Rule groups")


class QRadarPlatform(BaseModel):
    """IBM QRadar AQL schema."""
    query: str = Field(..., min_length=1, description="AQL WHERE clause")
    scope: Optional[str] = Field("local", pattern=r"^(local|global)$", description="Query scope")


class OpenTidePlatforms(BaseModel):
    """Platform-specific subschemas. At least one platform must be configured."""
    kql: Optional[KQLPlatform] = None
    elastic: Optional[ElasticPlatform] = None
    spl: Optional[SPLPlatform] = None
    wazuh: Optional[WazuhPlatform] = None
    qradar: Optional[QRadarPlatform] = None

    def model_post_init(self, _context: Any) -> None:
        """Validate that at least one platform is configured."""
        platforms = [self.kql, self.elastic, self.spl, self.wazuh, self.qradar]
        if not any(platforms):
            raise ValueError("At least one platform (kql, elastic, spl, wazuh, qradar) must be configured")


class OpenTideRule(BaseModel):
    """Complete CoreTide rule schema with strict validation."""
    metadata: OpenTideMetadata
    platforms: OpenTidePlatforms

    model_config = {"extra": "forbid"}

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Export to YAML-serializable dictionary."""
        return {
            'metadata': self.metadata.model_dump(exclude_none=True),
            'platforms': {
                k: v.model_dump(exclude_none=True)
                for k, v in self.platforms.model_dump(exclude_none=True).items()
                if v is not None
            }
        }
