"""Portable, versioned package format for cross-device configuration transfer."""

from .format import (
    DATA_TYPES,
    FORMAT_VERSION,
    PackageFormatError,
    compute_content_id,
    parse_manifest,
    validate_manifest,
)
from .policy import CollectionReport, PortableEntry, collect_portable_config
from .export import (
    PackageExportError,
    PackageExportResult,
    build_package_manifest,
    export_archive,
    export_directory,
)
from .check import CheckedPackage, PackageCheckError, check_package
from .mapping import (
    AgentCandidate,
    PackageMappingError,
    PackageMappingItem,
    PackageMappingPlan,
    plan_package_mappings,
)
from .conflicts import (
    AgentRuleSnapshot,
    ConflictRow,
    PackageConflictError,
    PackageConflictPlan,
    PackageTargetSnapshot,
    inspect_package_targets,
    plan_package_conflicts,
)
from .importer import PackageImportError, PackageImportPlan, PackageImportService

__all__ = [
    "DATA_TYPES",
    "FORMAT_VERSION",
    "PackageFormatError",
    "PackageExportError",
    "PackageExportResult",
    "PackageCheckError",
    "CheckedPackage",
    "CollectionReport",
    "PortableEntry",
    "collect_portable_config",
    "build_package_manifest",
    "export_archive",
    "export_directory",
    "check_package",
    "AgentCandidate",
    "PackageMappingError",
    "PackageMappingItem",
    "PackageMappingPlan",
    "plan_package_mappings",
    "AgentRuleSnapshot",
    "ConflictRow",
    "PackageConflictError",
    "PackageConflictPlan",
    "PackageTargetSnapshot",
    "inspect_package_targets",
    "plan_package_conflicts",
    "PackageImportError",
    "PackageImportPlan",
    "PackageImportService",
    "compute_content_id",
    "parse_manifest",
    "validate_manifest",
]
