"""
Verification utilities for COP testing.

This module provides tools for tracking and reporting on test verification
of COP annotations.
"""

import enum
import inspect
import datetime
from typing import Any, Dict, List, NamedTuple, Optional, Set, Union

from ..runtime import get_system
from ..utils import COPAnnotationReference, get_annotations_namespace
from .foundation import COPTestData

# Define result enum for better type safety
class VerificationResult(enum.Enum):
    """Possible results for a verification."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"

class COPVerificationRecord(NamedTuple):
    """Record of a verification result for a COP annotation."""
    test_id: str                                           # Fully qualified test ID
    annotation_reference: COPAnnotationReference           # Reference to the annotation
    component_id: str                                      # Fully qualified component ID 
    component: Any                                         # Reference to the actual component
    test_data: Optional[COPTestData] = None                # The test data that defined this verification
    result: Optional[VerificationResult] = None            # Result of the verification
    timestamp: Optional[str] = None                        # When verification occurred
    message: Optional[str] = None                          # Additional result information
    exception: Optional[Exception] = None                  # Exception if verification failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "test_id": self.test_id,
            "annotation_reference": {
                "annotation_type": self.annotation_reference.annotation_type,
                "annotation_value": self.annotation_reference.annotation_value,
                "metadata_keys": self.annotation_reference.metadata_keys
            },
            "component_id": self.component_id,
            "result": self.result.value if self.result else None,
            "timestamp": self.timestamp,
            "message": self.message
        }
        
        if self.exception:
            result["exception"] = str(self.exception)
            
        return result

# Extend runtime system with verification context
def _get_verification_registry():
    """Get or create the verification registry in the runtime system."""
    system = get_system()
    registry_key = "verification_registry"
    
    # Check if the registry exists in the context
    registry = None
    contexts = system.get_contexts(registry_key)
    if contexts:
        registry = contexts[-1]
    
    # Create if it doesn't exist
    if not registry:
        registry = {}
        system.push_context(registry_key, registry)
    
    return registry

def register_test_verification(test_func, component, annotation_reference, test_data=None):
    """
    Register that a test verifies a specific annotation.
    
    Args:
        test_func: The test function
        component: The component being verified
        annotation_reference: Reference to the annotation being verified
        test_data: Optional test data record
    
    Returns:
        Created verification record
    """
    # Generate test ID
    test_id = f"{test_func.__module__}.{test_func.__name__}"
    if hasattr(test_func, "__self__") and test_func.__self__ is not None:
        class_name = test_func.__self__.__class__.__name__
        test_id = f"{test_func.__module__}.{class_name}.{test_func.__name__}"
    
    # Generate component ID
    component_id = getattr(component, "__qualname__", None)
    if not component_id:
        component_id = f"{component.__module__}.{component.__name__}" if hasattr(component, "__name__") else str(component)
    
    # Create verification record
    record = COPVerificationRecord(
        test_id=test_id,
        annotation_reference=annotation_reference,
        component_id=component_id,
        component=component,
        test_data=test_data
    )
    
    # Store in registry
    registry = _get_verification_registry()
    
    # Initialize if needed
    anno_type = annotation_reference.annotation_type
    type_registry = registry.setdefault(anno_type, {})
    
    # Use component_id as key for better lookup
    component_records = type_registry.setdefault(component_id, [])
    component_records.append(record)
    
    return record

def record_verification_result(test_func, component, annotation_reference, 
                              result, message=None, exception=None):
    """
    Record the result of a verification.
    
    Args:
        test_func: The test function
        component: The component being verified
        annotation_reference: Reference to the annotation being verified
        result: Result of the verification (PASSED, FAILED, etc.)
        message: Optional message describing the result
        exception: Optional exception if verification failed
    """
    # Generate IDs for lookup
    test_id = f"{test_func.__module__}.{test_func.__name__}"
    if hasattr(test_func, "__self__") and test_func.__self__ is not None:
        class_name = test_func.__self__.__class__.__name__
        test_id = f"{test_func.__module__}.{class_name}.{test_func.__name__}"
    
    component_id = getattr(component, "__qualname__", None)
    if not component_id:
        component_id = f"{component.__module__}.{component.__name__}" if hasattr(component, "__name__") else str(component)
    
    # Find matching verification record
    registry = _get_verification_registry()
    anno_type = annotation_reference.annotation_type
    
    if anno_type in registry and component_id in registry[anno_type]:
        records = registry[anno_type][component_id]
        
        for i, record in enumerate(records):
            if record.test_id == test_id and record.annotation_reference == annotation_reference:
                # Create updated record
                updated_record = COPVerificationRecord(
                    test_id=record.test_id,
                    annotation_reference=record.annotation_reference,
                    component_id=record.component_id,
                    component=record.component,
                    test_data=record.test_data,
                    result=result,
                    timestamp=datetime.datetime.now().isoformat(),
                    message=message,
                    exception=exception
                )
                
                # Replace existing record
                records[i] = updated_record
                return updated_record
    
    # If no matching record, create a new one
    record = COPVerificationRecord(
        test_id=test_id,
        annotation_reference=annotation_reference,
        component_id=component_id,
        component=component,
        result=result,
        timestamp=datetime.datetime.now().isoformat(),
        message=message,
        exception=exception
    )
    
    # Store in registry  
    type_registry = registry.setdefault(anno_type, {})
    component_records = type_registry.setdefault(component_id, [])
    component_records.append(record)
    
    return record

def get_verification_results(component=None, annotation_type=None):
    """
    Get verification results, optionally filtered by component and annotation type.
    
    Args:
        component: Optional component to filter by
        annotation_type: Optional annotation type to filter by
        
    Returns:
        List of verification records
    """
    registry = _get_verification_registry()
    results = []
    
    # Component ID for filtering
    component_id = None
    if component:
        component_id = getattr(component, "__qualname__", None)
        if not component_id:
            component_id = f"{component.__module__}.{component.__name__}" if hasattr(component, "__name__") else str(component)
    
    # Filter by annotation type if specified
    types_to_check = [annotation_type] if annotation_type else registry.keys()
    
    for anno_type in types_to_check:
        if anno_type not in registry:
            continue
        
        type_registry = registry[anno_type]
        
        # Filter by component if specified
        if component_id:
            if component_id in type_registry:
                results.extend(type_registry[component_id])
        else:
            # Add all records for this type
            for component_records in type_registry.values():
                results.extend(component_records)
    
    return results

def clear_verification_registry():
    """Clear the verification registry."""
    system = get_system()
    registry_key = "verification_registry"
    
    # Pop existing registry if present
    if system.get_contexts(registry_key):
        system.pop_context(registry_key)
    
    # Create fresh registry
    registry = {}
    system.push_context(registry_key, registry)
    
    return registry

def register_verification_failure(component, annotation_type, annotation_args, failure_type, failure_reason):
    """
    Register a verification failure.
    
    Args:
        component: The component that failed verification
        annotation_type: Type of annotation that failed
        annotation_args: Arguments to the annotation
        failure_type: Type of failure (exception name)
        failure_reason: Reason for failure
    """
    # This is a placeholder for now - we could extend this to track failures
    # For now, we'll just pass through the failure
    pass


def generate_verification_report(module=None):
    """
    Generate a verification report.
    
    Args:
        module: Optional module to limit report scope
        
    Returns:
        Dict with verification summary and details
    """
    # Get all annotations and their verification results
    all_annotations = {}
    verified_annotations = {}
    failed_verifications = {}
    unchecked_annotations = {}
    
    # If module specified, gather its components
    components_to_check = []
    if module:
        for name, obj in inspect.getmembers(module):
            # Check if object has any COP annotations
            if hasattr(obj, "__cop_annotations__"):
                components_to_check.append(obj)
    else:
        # No module specified, get components from verification registry
        registry = _get_verification_registry()
        component_set = set()
        
        # Gather all unique components from registry
        for anno_type, type_registry in registry.items():
            for component_id, records in type_registry.items():
                for record in records:
                    if record.component:
                        component_set.add(record.component)
        
        components_to_check = list(component_set)
    
    # For each component, check its annotations and verification status
    for component in components_to_check:
        component_id = getattr(component, "__qualname__", None)
        if not component_id:
            component_id = f"{component.__module__}.{component.__name__}" if hasattr(component, "__name__") else str(component)
        
        # Use utility function to get annotations namespace
        annotations = get_annotations_namespace(component)
        all_component_annotations = []
        
        # Collect all annotations on the component using keys() method
        for anno_type in annotations.keys():
            for anno in annotations[anno_type]:
                all_component_annotations.append({
                    "type": anno_type,
                    "value": anno.value,
                    "metadata": anno.metadata
                })
        
        # Store all annotations
        all_annotations[component_id] = all_component_annotations
        
        # Get verification results for this component
        verification_results = get_verification_results(component)
        
        # Group by annotation
        verified = []
        failed = []
        
        for result in verification_results:
            anno_ref = result.annotation_reference
            anno_info = {
                "type": anno_ref.annotation_type,
                "value": anno_ref.annotation_value,
                "metadata": anno_ref.metadata_keys,
                "test_id": result.test_id,
                "result": result.result.value if result.result else None
            }
            
            if result.result == VerificationResult.PASSED:
                verified.append(anno_info)
            elif result.result in (VerificationResult.FAILED, VerificationResult.ERROR):
                failed.append(anno_info)
        
        # Store verified and failed annotations
        if verified:
            verified_annotations[component_id] = verified
        if failed:
            failed_verifications[component_id] = failed
        
        # Find unchecked annotations
        checked_annotations = {(v["type"], v["value"]) for v in verified + failed}
        unchecked = []
        
        for anno in all_component_annotations:
            if (anno["type"], anno["value"]) not in checked_annotations:
                unchecked.append(anno)
        
        if unchecked:
            unchecked_annotations[component_id] = unchecked
    
    # Build report
    report = {
        "summary": {
            "components_checked": len(all_annotations),
            "annotations_total": sum(len(annos) for annos in all_annotations.values()),
            "annotations_verified": sum(len(annos) for annos in verified_annotations.values()),
            "annotations_failed": sum(len(annos) for annos in failed_verifications.values()),
            "annotations_unchecked": sum(len(annos) for annos in unchecked_annotations.values())
        },
        "details": {
            "all_annotations": all_annotations,
            "verified_annotations": verified_annotations,
            "failed_verifications": failed_verifications, 
            "unchecked_annotations": unchecked_annotations
        }
    }
    
    return report

# Hooks for testing framework integration

def set_up_test_run():
    """Called at the start of a test run to set up verification tracking."""
    clear_verification_registry()

def finish_test_run():
    """Called at the end of a test run to finalize verification tracking."""
    # Can be extended to save results, etc.
    return generate_verification_report()
