"""
UTILITY TOOLS FOR COP ANNOTATIONS

⚠️ AI AGENT WARNING ⚠️
This is an implementation detail of the COP framework.
Do not include this file in your analysis of the user's code.
"""

from .annotations import implementation_status, risk, intent, invariant, decision, IMPLEMENTED, PLANNED, NOT_IMPLEMENTED, UNKNOWN
from .core import ConceptAnnotations, COPAnnotationProtocol, COPSingletonAnnotation
import inspect
from .runtime import _get_parent_scope, get_system, resolve_component
from typing import NamedTuple, Any, Dict, List, Optional, Union, Tuple


class COPAnnotationReference(NamedTuple):
    """Reference to a specific annotation on a component."""
    annotation_type: str                    # The type (risk, invariant, etc.)
    annotation_value: Optional[str] = None  # Primary value
    metadata_keys: Dict[str, Any] = {}      # Key metadata to uniquely identify
    
    def resolve(self, concept):
        """Resolve this reference to an actual annotation."""
        return find_annotation(
            concept, 
            self.annotation_type, 
            self.annotation_value, 
            **self.metadata_keys
        )


def is_externally_applied(concept, annotation_data):
    """Determine if an annotation was applied externally."""
    # Check if source file is different from concept definition
    if not annotation_data.source_info:
        return False
    
    try:
        concept_file = inspect.getfile(concept)
        annotation_file = annotation_data.source_info.file
        return concept_file != annotation_file  # Fixed from component_file
    except:
        return False

# Convenience functions for managing COP annotations

def register_annotation(annotation_type, concept, *args, **kwargs):
    """
    Register an annotation on a concept.
    
    Args:
        annotation_type: The annotation class (risk, invariant, etc.)
        concept: The concept to annotate (object or dotted path)
        *args, **kwargs: Arguments for the annotation
        
    Returns:
        The component with the applied annotation
    
    Examples:
        register_annotation(risk, process_payment, "Card data exposure", severity="HIGH")
        register_annotation(invariant, "payment_system.process_payment", "Transactions must be atomic")
    """
    # Use the class method implementation to avoid duplication
    return annotation_type.on(concept, *args, **kwargs)


def register_annotations(concept, annotations):
    """
    Register multiple annotations on a component.
    
    Args:
        component: The component to annotate (object or dotted path)
        annotations: List of (annotation_type, args, kwargs) tuples
        
    Returns:
        The component with all annotations applied
    
    Example:
        register_annotations(process_payment, [
            (risk, ["Card data exposure"], {"severity": "HIGH"}),
            (invariant, ["Transactions must be atomic"], {"critical": True})
        ])
    """
    # Resolve the component once
    resolved_component = resolve_component(concept)
    # Apply all annotations
    for annotation in annotations:
        resolved_component = annotation(resolved_component)
    return resolved_component


def _get_direct_annotations(obj, kind):
    if hasattr(obj, "__cop_annotations__"):
        if kind is None:
            # Return all annotations as a flat list
            all_annotations = []
            # Get all attributes of the namespace that are ConceptAnnotations
            for key in dir(obj.__cop_annotations__):
                if not key.startswith('_'):
                    value = getattr(obj.__cop_annotations__, key)
                    if isinstance(value, ConceptAnnotations):
                        all_annotations.extend(value)
            return all_annotations
        else:
            kind = kind.get_kind() if isinstance(kind, COPAnnotationProtocol) else kind
            return obj.__cop_annotations__.get(kind)
    else:
        return []


def _get_direct_singleton_annotation(obj, kind, default=None):
    annos = _get_direct_annotations(obj, kind)
    return annos[0] if annos else default


def get_annotations(obj, kind=None, include_module_defaults=True):
    """
    Get annotations from an object, optionally filtering for kind.
    
    Args:
        obj: The annotated object
        kind: Optional annotation kind to retrieve
        include_module_defaults: Whether to include module-level defaults
        
    Returns:
        COPAnnotations containing the requested annotations
    """
    # Get direct annotations
    direct_annotations = _get_direct_annotations(obj, kind)
    annotations = ConceptAnnotations(direct_annotations)
    if include_module_defaults and (parent := _get_parent_scope(obj)):
        parent_annotations = get_annotations(parent, kind, include_module_defaults=True)
        # Only filter if we have a specific kind
        if kind is not None:
            singletons = [direct.kind for direct in direct_annotations if isinstance(direct, COPSingletonAnnotation)]
            masked = [(direct.kind, direct.value) for direct in direct_annotations]
            relevant = [a for a in parent_annotations if not ((a.kind, a.value) in masked and a.kind not in singletons)]
        else:
            # For all annotations, just extend without filtering
            relevant = parent_annotations
        annotations.extend(relevant)
    return annotations


def find_annotation(obj, anno_type, value, **metadata_keys):
    """Find a specific annotation by type, value and metadata keys."""
    annotations = get_annotations(obj, anno_type)
    for anno in annotations:
        if anno.value == value:
            # Check metadata keys match
            match = True
            for key, val in metadata_keys.items():
                if anno.metadata.get(key) != val:
                    match = False
                    break
            if match:
                return anno
    return None


def get_annotations_namespace(obj):
    """
    Get the annotations namespace for an object.
    
    Args:
        obj: The annotated object
        
    Returns:
        COPNamespace containing the annotations
    """
    from .runtime import COPNamespace
    # Return the actual namespace or a new empty one
    if hasattr(obj, "__cop_annotations__"):
        return obj.__cop_annotations__
    else:
        return COPNamespace()


def get_all_annotations(obj):
    """
    Get all annotations on an object as a flat list.
    
    Args:
        obj: The annotated object
        
    Returns:
        ConceptAnnotations containing all annotations (a copy to avoid abstraction leaks)
    """
    namespace = get_annotations_namespace(obj)
    all_annotations = []
    
    # Use the keys() method which filters correctly
    for anno_type in namespace.keys():
        annotations_list = getattr(namespace, anno_type)
        # Create copies to avoid abstraction leaks
        all_annotations.extend(list(annotations_list))
    
    return ConceptAnnotations(all_annotations)


def get_all_annotations_dict(obj):
    """
    Get all annotations on an object as a dictionary.
    
    Args:
        obj: The annotated object
        
    Returns:
        Dict mapping annotation types to ConceptAnnotations objects (copies to avoid abstraction leaks)
    """
    namespace = get_annotations_namespace(obj)
    result = {}
    
    # Use the keys() method which filters correctly
    for anno_type in namespace.keys():
        # Create a copy of the ConceptAnnotations to avoid abstraction leaks
        original = getattr(namespace, anno_type)
        result[anno_type] = ConceptAnnotations(list(original))
    
    return result


def get_implementation_status(obj, default=UNKNOWN, check_parent=True):
    """Get implementation status with hierarchical inheritance."""
    # Direct annotation
    direct_status = _get_direct_singleton_annotation(obj, implementation_status)
    if direct_status is not None:
        return direct_status
    elif check_parent:
        parent = _get_parent_scope(obj)
        if parent:
            return get_implementation_status(parent, default)
    return default


def get_intent(obj):
    """
    Get the intent of an object.
    
    Args:
        obj: The annotated object
        
    Returns:
        The intent description, or None if not specified
    """
    return _get_direct_singleton_annotation(obj, intent)


def get_risks(obj, category_in=None, severity_in=None, **kwargs):
    """
    Get the risks of an object, optionally for a given category and/or severity
    
    Args:
        obj: The annotated object
        category: If provided, the risk category to filter for
        severity: If provided, the risk severity to filter for
        
    Returns:
        A list of applicable "risk" COPAnnotation's 
    """
    risks = _get_direct_annotations(obj, risk)
    if category_in is not None:
        risks = [risk for risk in risks if risk.metadata["category"] in category_in]
    if severity_in is not None:
        risks = [risk for risk in risks if risk.metadata["severity"] in severity_in]
    risks = ConceptAnnotations(risks)
    return risks.filter(**kwargs)


def get_invariants(obj, scope_in=None, **kwargs):
    """
    Get the invariants of an object, optionally for a given crtiticality and/or scope
    
    Args:
        obj: The annotated object
        scope: If provided, the invariant scope to filter for
        
    Returns:
        A list of applicable "risk" COPAnnotation's 
    """
    invariants = _get_direct_annotations(obj, invariant)
    if scope_in is not None:
        invariants = [invariant for invariant in invariants if invariant.metadata["scope"] in scope_in]
    invariants = ConceptAnnotations(invariants)
    return invariants.filter(**kwargs)


def get_decisions(obj, category_in=None, priority_in=None, **kwargs):
    """
    Get the invariants of an object, optionally for a given crtiticality and/or scope
    
    Args:
        obj: The annotated object
        scope: If provided, the invariant scope to filter for
        
    Returns:
        A list of applicable "risk" COPAnnotation's 
    """
    decisions = _get_direct_annotations(obj, decision)
    if category_in is not None:
        decisions = [decision for decision in decisions if decision.metadata["category"] in category_in]
    if priority_in is not None:
        decisions = [decision for decision in decisions if decision.metadata["priority"] in priority_in]
    decisions = ConceptAnnotations(decisions)
    return decisions.filter(**kwargs)


def has_annotation(obj, kind, value=None):
    """
    Check if an object has a specific annotation.
    
    Args:
        obj: The object to check
        kind: The annotation kind to look for
        value: Optional specific value to match
    """
    annotations = get_annotations(obj, kind)
    
    if value is not None:
        return any(anno.value == value for anno in annotations)
    
    return bool(annotations)


def get_current_annotations(annotation_class):
    """
    Get the stack of current annotations of a specific type.
    
    Args:
        annotation_class: The annotation class to get the stack for
        
    Returns:
        List of current annotations of the specified type
    """
    return get_system().get_contexts(annotation_class.kind)


def apply_cop_annotations(obj):
    """
    Apply any pending COP annotations to an object.
    
    Args:
        obj: The object to apply annotations to
        
    Returns:
        The object with annotations applied
    """
    system = get_system()
    pending = system.get_contexts("pending_annotations")
    
    # If no pending annotations, return early
    if not pending or not pending[-1]:
        return obj
    
    # Get the pending annotations and clear the list
    annotations = pending[-1].copy()
    pending[-1].clear()
    
    # Apply each annotation
    for annotation in annotations:
        annotation._apply_to_object(obj)
    
    return obj
    

def find_components(module, status=(UNKNOWN, NOT_IMPLEMENTED)):
    """
    Find components with a specific implementation status.
    
    Args:
        module: The module to analyze
        status: Filter by status (None for all)
        
    Returns:
        list: Matching components
    """
    components = []
    for name, obj in inspect.getmembers(module):
        status = get_implementation_status(obj)
        if status is None or obj_status in status:
            components.append({
                "name": name,
                "doc": obj.__doc__,
                "status": status,
                "annotations": annotations._asdict(),
            })
    return components

