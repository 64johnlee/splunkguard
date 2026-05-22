"""Data models for SplunkGuard incident reports."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IncidentCategory(str, Enum):
    ERROR_SPIKE = "error_spike"
    LATENCY_DEGRADATION = "latency_degradation"
    SERVICE_DOWN = "service_down"
    SECURITY_THREAT = "security_threat"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DATA_PIPELINE_FAILURE = "data_pipeline_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    NETWORK_ANOMALY = "network_anomaly"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RemediationStep:
    action: str
    description: str
    spl_query: str = ""
    confidence: Confidence = Confidence.MEDIUM
    priority: int = 1


@dataclass
class AffectedComponent:
    name: str
    component_type: str        # host, service, index, sourcetype
    error_count: int = 0
    first_seen: str = ""
    last_seen: str = ""


@dataclass
class IncidentReport:
    title: str
    severity: Severity
    category: IncidentCategory = IncidentCategory.UNKNOWN
    summary: str = ""
    root_cause: str = ""
    affected_components: list[AffectedComponent] = field(default_factory=list)
    remediation_steps: list[RemediationStep] = field(default_factory=list)
    key_spl_queries: list[str] = field(default_factory=list)
    full_analysis: str = ""
    time_range: str = ""
    splunk_instance: str = ""
    is_ongoing: bool = True
