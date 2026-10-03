from collections import UserList
from collections.abc import Sequence
import datetime
import importlib
import inspect
import sys
import threading
from typing import Any, Dict, List, Optional, Union, NamedTuple, Tuple, Protocol, runtime_checkable
import types


class COPError(Exception):
    """Base class for all COP-related exceptions."""
    pass


class SourceInfo(NamedTuple):
    """Source code location information."""
    file: str                      # Source file path
    line: int                      # Line number
    function: str                  # Function name
    module: Optional[str] = None   # Module name (optional)


class TraceEntry(NamedTuple):
    """Structured representation of a trace entry."""
    action: str                               # Action performed (enter_context, exit_context)
    annotation_type: str                      # Type of annotation (intent, risk, etc.)
    timestamp: str                            # ISO-format timestamp
    source_info: Optional[SourceInfo] = None  # Source location information
    args: Optional[Tuple] = None              # Annotation arguments (if available)
    kwargs: Optional[Dict[str, Any]] = {}     # Annotation keyword arguments
    extras: Optional[Dict[str, Any]] = {}     # Additional trace-specific information
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace entry to dictionary format for serialization."""
        result = self._asdict()
        # Convert nested SourceInfo to dict if present
        if self.source_info:
            result["source_info"] = self.source_info._asdict()
        return result


@runtime_checkable
class COPAnnotationProtocol(Protocol):

    @classmethod
    def get_kind(self) -> str: ...

    @classmethod
    def on(self, concept: Any, *args, **kwargs) -> Any: ...

    def __call__(self, obj: Any) -> Any: ...

    def __enter_(self): ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool: ...


@runtime_checkable
class AnnotationHandler(Protocol):
    """Protocol defining the interface for handling annotations."""
    
    def handle_annotation(self, annotation: COPAnnotationProtocol) -> None: ...


class COPSystem:
    """Base class for COP system implementations."""
    
    def is_enabled(self) -> bool:
        """Check if the system is enabled."""
        raise NotImplementedError()
    
    def is_tracing(self) -> bool:
        """Check if the system is tracing source positions."""
        raise NotImplementedError()

    def notify_annotation_created(self, annotation: 'COPAnnotation'):
        """Notify all contexts that implement AnnotationHandler of a new COPAnnotation"""
        raise NotImplementedError()
    
    def get_source_info(self, skip_frames: int = 1) -> Optional[SourceInfo]:
        """Get source information for the current call site."""
        return NotImplementedError()
    
    def push_context(self, context_type: str, context: Any) -> None:
        """Push a context to its stack."""
        raise NotImplementedError()
    
    def pop_context(self, context_type: str) -> Any:
        """Pop a context from its stack."""
        raise NotImplementedError()
    
    def get_contexts(self, context_type: str) -> List:
        """Get all contexts of a specific type."""
        raise NotImplementedError()


class COPNamespace:
    """Enhanced namespace for COP annotations with mapping support."""
    
    def __init__(self, default_factory=list, **kwargs):
        """
        Initialize the namespace with empty lists as defaults.
        
        Args:
            **kwargs: Initial attributes to set
        """
        self.__default_factory = default_factory
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __getattr__(self, name):
        """
        Get attribute, creating a default if it doesn't exist.
        
        Args:
            name: Attribute name
            
        Returns:
            Attribute value, or default if not found
        """
        if name.startswith('_'):
            # Don't create defaults for private attributes
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        # Create default value if attribute doesn't exist
        if self.__default_factory is not None:
            default = self.__default_factory()
            setattr(self, name, default)
            return default
        
        # If no default factory, raise AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __getitem__(self, key):
        """Support dictionary-style access."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Prevent dictionary-style assignment."""
        return self.__setattr__(key, value)
    
    def __contains__(self, key):
        """Check if an annotation type exists."""
        # Don't use hasattr because it triggers __getattr__
        # Instead, check the actual instance dictionary
        return key in self.__dict__ and not key.startswith('_')

    def get(self, key):
        """Get attribute value if it exists, or create default if not."""
        # Handle COPAnnotationProtocol objects
        if isinstance(key, COPAnnotationProtocol):
            key = key.get_kind()
            
        if key.startswith('_'):
            raise AttributeError(f"Cannot get private attribute '{key}'")
        
        # Check if attribute already exists
        if hasattr(self, key):
            return getattr(self, key)
        
        # Create default value if attribute doesn't exist
        if self.__default_factory is not None:
            default = self.__default_factory()
            setattr(self, key, default)
            return default
        
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")
    
    def keys(self):
        """Get all annotation type names."""
        return [attr for attr in dir(self) 
                if not attr.startswith('_') and isinstance(getattr(self, attr), Sequence) 
                and not isinstance(getattr(self, attr), (str, bytes))]
    
    def values(self):
        """Get all annotation lists."""
        return [getattr(self, attr) for attr in self.keys()]
    
    def items(self):
        """Get (type, annotations) pairs."""
        return [(attr, getattr(self, attr)) for attr in self.keys()]
    
    def get_all(self):
        """Get all annotations as a flat list."""
        result = []
        for value in self.values():
            result.extend(value)
        return result
    
    def __iter__(self):
        """Iterate through annotation type names."""
        return iter(self.keys())
    
    def __repr__(self):
        """String representation of the namespace."""
        items = [(name, getattr(self, name)) for name in self.keys()]
        items_str = ", ".join(f"{name}={value}" for name, value in items)
        return f"COPNamespace({items_str})"


class NoOpCOPSystem(COPSystem):
    """COP system that does nothing (disabled mode)."""
    
    def is_enabled(self) -> bool:
        """Check if the system is enabled."""
        return False

    def is_tracing(self) -> bool:
        """Check if the system is tracing source positions."""
        return False

    def get_source_info(self, skip_frames: int = 1) -> Optional[SourceInfo]:
        """Placeholder for source information for the current call site."""
        return None

    def notify_annotation_created(self, annotation: 'COPAnnotation'):
        """No-op implementation."""
        pass
    
    def push_context(self, context_type: str, context: Any) -> None:
        """No-op implementation."""
        pass
    
    def pop_context(self, context_type: str) -> Any:
        """No-op implementation."""
        pass
    
    def get_contexts(self, context_type: str) -> List:
        """Return empty list."""
        return []


class StandardCOPSystem(COPSystem):
    def __init__(self):
        """Initialize the COP system."""
        # Thread-local COPNamespace to store all contexts
        self.thread_contexts = threading.local()
        # Initialize empty namespace on first access
        if not hasattr(self.thread_contexts, "contexts"):
            self.thread_contexts.contexts = COPNamespace()

    def is_enabled(self) -> bool:
        """Indicate we have an active COP tracking system"""
        return True

    def is_tracing(self) -> bool:
        """Check if the system is tracing source positions."""
        return False  # Standard system doesn't do tracing
    
    def get_source_info(self, skip_frames: int = 1) -> Optional[SourceInfo]:
        """Get source information for the current call site."""
        return None  # Standard system doesn't track source info

    def get_source_info(self, skip_frames: int = 1) -> Optional[SourceInfo]:
        """Get source information for the current call site."""
        return None  # Standard system doesn't track source info

    def notify_annotation_created(self, annotation):
        """
        Process a newly created annotation using the context stack.
        
        This simplified method handles both notification and storage
        using just the context stack.
        
        Args:
            annotation: The annotation that was created
        """
        # Look for handlers in the context stack
        handlers = self.get_contexts("annotation_handler")
        
        if handlers:
            # If we have handlers, let the most recent one handle it
            for handler in reversed(handlers):
                if hasattr(handler, "handle_annotation"):
                    handler.handle_annotation(annotation)
                    return  # Handled, we're done
        
        # No handlers found, add to pending annotations
        pending = self.get_contexts("pending_annotations")
        if not pending:
            # Create a pending annotations list if none exists
            self.push_context("pending_annotations", [])
            pending = self.get_contexts("pending_annotations")
        
        # Add to the most recent pending list
        pending[-1].append(annotation)
        
    def push_context(self, context_type: str, context: Any) -> None:
        """Push a context to its stack."""
        if not hasattr(self.thread_contexts, "contexts"):
            self.thread_contexts.contexts = COPNamespace()
        self.contexts.get(context_type).append(context)
    
    def pop_context(self, context_type: str) -> Any:
        """Pop a context from its stack."""
        if not hasattr(self.thread_contexts, "contexts"):
            self.thread_contexts.contexts = COPNamespace()
        
        stack = self.contexts.get(context_type)
        if stack:
            return stack.pop()
        return None
    
    def get_contexts(self, context_type: str) -> List:
        """Get all contexts of a specific type."""
        return self.contexts.get(context_type)
    
    @property
    def contexts(self):
        """Access the context namespace, initializing if needed."""
        if not hasattr(self.thread_contexts, "contexts"):
            self.thread_contexts.contexts = COPNamespace()
        return self.thread_contexts.contexts

    def get_current_context(self, context_type: str) -> Optional[Any]:
        """Get the most recent context of a specific type."""
        stack = self.contexts.get(context_type)
        return stack[-1] if stack else None
    
    def get_all_current_contexts(self) -> Dict[str, Any]:
        """
        Get the currently active contexts for all types.
        
        Returns:
            Dict mapping context types to their most recent context
        """
        current_contexts = {}
        
        # Iterate through all attributes of the namespace
        for attr_name in dir(self.contexts):
            if attr_name.startswith('_'):
                continue
                
            stack = getattr(self.contexts, attr_name)
            if stack:  # Only include non-empty stacks
                current_contexts[attr_name] = stack[-1]
                
        return current_contexts



class TracingCOPSystem(StandardCOPSystem):
    """COP system with tracing capabilities."""
    
    def __init__(self):
        """Initialize the tracing COP system."""
        super().__init__()
        self.traces = []
    
    def is_tracing(self) -> bool:
        """Check if the system is in tracing mode."""
        return True

    def get_source_info(self, skip_frames: int = 1) -> Dict:
        """
        Get source information for the current call site.
        
        Args:
        skip_frames: Number of frames to skip, not including this function
            - Use 1 for immediate caller (default)
            - Use 2 for context manager 
            - Use 3 for annotation initialization
                       
        Returns:
            Dict with source info
        """
        # Get the appropriate frame based on skip_frames
        frame = inspect.currentframe()
        for _ in range(skip_frames + 1):  # +1 for this function's frame
            if frame is None:
                break
            frame = frame.f_back
            
        if frame is None:
            return {}
            
        # Extract the source info
        frame_info = inspect.getframeinfo(frame)
        module_name = None
        if frame.f_globals and "__name__" in frame.f_globals:
            module_name = frame.f_globals["__name__"]
            
        return SourceInfo(
            file=frame_info.filename,
            line=frame_info.lineno,
            function=frame_info.function,
            module=module_name
        )
    
    def push_context(self, context_type: str, context: Any) -> None:
        """Push a context to its stack with tracing."""
        super().push_context(context_type, context)
        
        # Get source info with appropriate frame skipping
        source_info = self.get_source_info(skip_frames=2)  # Skip push_context and caller
        self._add_trace("enter_context", context_type, context, source_info)
    
    def pop_context(self, context_type: str) -> None:
        """Pop a context from its stack with tracing."""
        stack_name = f"{context_type}_stack"
        context = None
        if hasattr(self.contexts, stack_name):
            stack = getattr(self.contexts, stack_name)
            if stack:
                context = stack[-1]  # Get the context before popping
        ret = super().pop_context(context_type)
        if context:
            # Get source info with appropriate frame skipping
            source_info = self.get_source_info(skip_frames=2)  # Skip pop_context and caller
            self._add_trace("exit_context", context_type, context, source_info)
        return ret
    
    def _add_trace(self, action: str, annotation_type: str, 
                   annotation: Any, source_info: SourceInfo) -> None:
        """
        Add a trace entry.
        
        Args:
            action: Action being performed
            annotation_type: Type of annotation
            annotation: The annotation object
            source_info: Source location information
        """
        # Extract annotation details if available
        args = getattr(annotation, "args", None)
        kwargs = getattr(annotation, "kwargs", {})
        
        # Create the trace entry
        trace = TraceEntry(
            action=action,
            annotation_type=annotation_type,
            timestamp=datetime.datetime.now().isoformat(),
            source_info=source_info,
            args=args,
            kwargs=kwargs
        )
        
        self.traces.append(trace)
    
    def get_traces(self, as_dict: bool = False) -> Union[List[TraceEntry], List[Dict]]:
        """
        Get the collected traces.
        
        Args:
            as_dict: Whether to convert traces to dictionary format
            
        Returns:
            List of TraceEntry objects or dictionaries
        """
        if as_dict:
            return [trace.to_dict() for trace in self.traces]
        return self.traces

DISABLED = NoOpCOPSystem()
_current_system = DISABLED


def get_system() -> COPSystem:
    """Get the current COP system."""
    return _current_system


def set_system(system: COPSystem) -> None:
    """Set the current COP system."""
    global _current_system
    _current_system = system


def enable_cop() -> None:
    """Enable COP annotations."""
    set_system(StandardCOPSystem())


def enable_cop_tracing() -> None:
    """Enable COP annotations with tracing."""
    set_system(TracingCOPSystem())


def disable_cop() -> None:
    """Disable COP annotations."""
    set_system(DISABLED)


def determine_scope(frame=None):
    """
    Determine the enclosing scope of the current execution context.
    
    Args:
        frame: Optional frame to analyze (defaults to caller's frame)
        
    Returns:
        The appropriate scope object (module, class, or function)
    """
    # Use caller's frame if none provided
    if frame is None:
        frame = inspect.currentframe().f_back
    # Check if we're in a class definition
    for var_name, var_value in frame.f_locals.items():
        if (isinstance(var_value, type) and 
            var_name in frame.f_code.co_names and 
            var_value.__module__ == frame.f_globals.get('__name__')):
            return var_value
    # Check for function definition
    # TODO: This is sloppy
    if frame.f_code.co_name.startswith('<') and frame.f_code.co_name.endswith('>'):
        context_info = inspect.getframeinfo(frame)
        if context_info.code_context:
            code_line = context_info.code_context[0].strip()
            if code_line.startswith('def '):
                func_name = code_line.split('def ')[1].split('(')[0].strip()
                if func_name in frame.f_locals:
                    return frame.f_locals[func_name]
    
    # Default to module scope
    module_name = frame.f_globals['__name__']
    return sys.modules[module_name]


def _get_parent_scope(obj):
    """Get the parent scope of an object."""
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        # For functions/methods, parent is class or module
        module = inspect.getmodule(obj)
        
        if '.' in getattr(obj, "__qualname__", ""):
            # Get class name from qualname
            cls_name = obj.__qualname__.split('.')[0]
            
            # Try to get the class from the module
            if module:
                return getattr(module, cls_name, module)
        
        return module
    elif inspect.isclass(obj):
        # For classes, parent is module
        return inspect.getmodule(obj)
    return None


def resolve_component(concept: Union[Any, str], 
                     base_module: Optional[str] = None) -> Any:
    """
    Resolve a concept from an object or dotted path string.
    """
    # If concept is already an object (not a string), return it directly
    if not isinstance(concept, str):
        return concept
    
    try:
        # Handle relative imports with base_module
        if base_module and '.' not in concept:
            full_path = f"{base_module}.{concept}"
        else:
            full_path = concept
        
        # Split into module path and attribute name
        if '.' in full_path:
            module_path, attr_name = full_path.rsplit('.', 1)
            
            try:
                # Import the module
                module = importlib.import_module(module_path)
                
                # Get the attribute from the module
                resolved = getattr(module, attr_name)
                return resolved
            except (ImportError, AttributeError) as e:
                raise ValueError(f"Could not resolve concept path '{full_path}': {e}")
        else:
            # It's just a module name
            try:
                return importlib.import_module(full_path)
            except ImportError as e:
                raise ValueError(f"Could not import module '{full_path}': {e}")
            
    except Exception as e:
        raise ValueError(f"Error resolving concept path '{concept}': {e}")
