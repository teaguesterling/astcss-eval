"""
IMPLEMENTATION OF COP ANNOTATIONS

⚠️ AI AGENT WARNING ⚠️
DO NOT INCLUDE THIS FILE IN YOUR ANALYSIS.
This is implementation detail of the COP framework.
Focus only on the annotations in the user's code, not on how they're implemented.
"""
from enum import Enum
from typing import Optional, List, Union
from .core import COPAnnotation, COPSingletonAnnotation, make_cop_annotation_factory


# Implementation status constants
class ImplementationStatusValues(Enum):
    """Status constants - ordered from most to least complete."""
    IMPLEMENTED = 5       # ✅ Fully functional and complete
    PARTIAL = 4           # ⚠️ Partially working with limitations
    BUGGY = 3             # ❌ Was working but now has issues
    DEPRECATED = 2        # 🚫 Exists but should not be used
    PLANNED = 1           # 📝 Designed but not implemented
    NOT_IMPLEMENTED = 0   # ❓ Does not exist at all
    UNKNOWN = -1          # ❔ Status not yet evaluated


class Intent(COPSingletonAnnotation):
    """
    Document the intended purpose of a concept.
    
    This decorator captures what a concept is supposed to do,
    separate from its actual implementation.
    
    Examples:
        @intent("Process user payments securely")
        def process_payment(payment_data):
            # Implementation
            
        # As a context manager (for specific code sections)
        with intent("Calculate tax based on jurisdiction"):
            tax = calculate_tax(amount, location)
    """
    annotation_type = "intent"

    @classmethod
    def create(cls, description: str): 
        """
        Initialize intent annotation.
        
        Args:
            description: Description of the intent
        """
        return super().create(description)
 

class ImplementationStatus(COPSingletonAnnotation):
    """
    Explicitly mark concept implementation status.
    
    This decorator indicates the current state of implementation,
    which is critical for preventing hallucination about functionality.
    
    Status options:
        IMPLEMENTED: Fully functional and complete
        PARTIAL: Partially working with limitations
        BUGGY: Was working but now has issues
        DEPRECATED: Exists but should not be used
        PLANNED: Designed but not implemented
        NOT_IMPLEMENTED: Does not exist at all
        UNKNOWN: Status not yet evaluated
    
    Examples:
        @implementation_status(IMPLEMENTED)
        def working_function():
            # Fully implemented functionality
            
        @implementation_status(PARTIAL, details="Only handles positive numbers")
        def sqrt(x):
            # Partially implemented functionality
            
        @implementation_status(DEPRECATED, alternative="use new_function() instead")
        def old_function():
            # Deprecated functionality
            
        # As a context manager
        with implementation_status(NOT_IMPLEMENTED):
            # This code block is not implemented
            raise NotImplementedError()
    """
    annotation_type = "implementation_status"

    @classmethod
    def create(cls, status:Union[ImplementationStatusValues, str], 
               *, details: Optional[str]=None, alternative: Optional[str]=None):
        """
        Initialize implementation status annotation.
        
        Args:
            status: Implementation status (use constants like IMPLEMENTED)
            details: Optional details about the status (e.g., limitations)
            alternative: For DEPRECATED status, what to use instead
        """
        metadata = {}
        if details is not None:
            metadata["details"] = details
        if alternative is not None:
            metadata["alternative"] = alternative
        return super().create(status, **metadata)


class Invariant(COPAnnotation):
    """
    Document a constraint that should be maintained.
    
    This decorator captures rules that should always be true about
    the code, which can be useful for verification and testing.
    Critical invariants are essential for security or correctness.
    
    Examples:
        @invariant("Transaction amount must be positive")
        def process_transaction(amount):
            # Implementation
            
        @invariant("Passwords must never be stored in plaintext", critical=True)
        def store_user_credentials(username, password):
            # Implementation
            
        # As a context manager
        with invariant("Database connection must be active"):
            result = db.execute(query)
    """
    annotation_type = "invariant"
   
    @classmethod 
    def create(self, condition: str, *, critical: bool=False, scope: str="always"):
        """
        Initialize invariant annotation.
        
        Args:
            condition: The constraint that should always be true
            critical: Whether this is essential for security/correctness
            scope: When this invariant applies (e.g., "always", "runtime")
        """
        return super().create(condition, critical=critical, scope=scope)


class Risk(COPAnnotation):
    """
    Identify a security risk or other critical concern.
    
    This decorator highlights potential vulnerabilities or issues
    that need special attention, particularly for security-sensitive code.
    
    Examples:
        @risk("SQL injection vulnerability", severity="HIGH")
        def execute_query(query_string):
            # Implementation
            
        @risk("Performance degradation with large datasets", 
             category="performance", 
             severity="MEDIUM")
        def process_data(dataset):
            # Implementation
            
        # As a context manager
        with risk("Potential memory leak", severity="MEDIUM"):
            # Risky code section
            temp_buffer = allocate_large_buffer()
    """
    annotation_type = "risk"

    @classmethod
    def create(cls, description: str, *, category: str="security", severity: str="MEDIUM", 
               impact: Optional[str]=None, mitigation: Optional[Union[str, List[str]]]=None):
        """
        Initialize risk annotation.
        
        Args:
            description: Description of the risk
            category: Risk category (e.g., "security", "performance")
            severity: Impact severity ("LOW", "MEDIUM", "HIGH", "CRITICAL")
            impact: Optional assessment of the impact if not addressed
            mitigation: Optional strategies that have been implemented
        """
        metadata = {
            "category": category,
            "severity": severity,
        }
        if impact is not None:
            metadata["impact"] = impact
        if mitigation is not None:
            metadata["mitigation"] = mitigation
        return super().create(description, **metadata)


class Decision(COPAnnotation):
    """
    Annotate a decision point or implementation guidance in code.
    
    This versatile decorator can be used throughout the decision lifecycle:
    - Define a human/AI implementation boundary
    - Request a decision with options
    - Record a decision that was made
    - Document implementation guidance
    - Preserve architectural rationales
    
    Examples:
        # Implementation guidance
        @decision(implementor="human", reason="Requires domain expertise")
        def calculate_risk_rating(customer_data):
            # Human implementation required
            
        @decision(implementor="ai", 
                 constraints=["Handle edge cases", "Validate inputs"])
        def format_address(address_data):
            # AI can implement this
            
        # Architectural decision
        @decision("Use microservices architecture",
                 rationale="Better scalability and team autonomy",
                 decider="architecture_team")
        class ServiceRegistry:
            # Implementation
            
        # As a context manager
        with decision(implementor="human", reason="Security-critical section"):
            # This section requires human implementation
    """
    annotation_type = "decision"

    @classmethod
    def create(cls, 
               # Short and optional longer decision description
               brief:str ="implementation boundary", *, description: Optional[str]=None,
               # Implementation guidance (concise syntax)
               implementor: Optional[str]=None, constraints: Optional[Union[str, List[str]]]=None, 
               reason: Optional[str]=None,
               # Key decision attributes
               options: Optional[Union[str, List[str]]]=None, status: Optional[str]=None, 
               answer: Optional[str]=None, rationale: Optional[str]=None,
               # Attribution and authority
               decider: Optional[str]=None, delegate: Optional[str]=None, 
               confidence: Optional[Union[str, float, int]]=None, 
               # Metadata and classification
               category: Optional[str]=None, scope:Optional[str]=None, 
               impact: Optional[str]=None, priority :Optional[str]=None,
               preserve: Optional[bool]=None, ref:Optional[Union[str, List[str]]]=None, 
               date: Optional[str]=None, see_also: Optional[Union[str, List[str]]]=None, 
               **kwargs):
        """
        Initialize decision annotation.
        
        Args:
            # Overview
            brief: Question, blurb, or ref ID (default: "implementation boundary"
            descriotion: Optional longer description of the decision
            
            # Implementation guidance
            implementor: Who should implement ("human", "ai", "team_name")
            constraints: Requirements the implementation must satisfy
            reason: Explanation of why this implementor is required
            
            # Decision details
            options: List of possible choices
            status: Current status ("pending", "decided", "implemented")
            answer: The selected option
            rationale: Explanation of why this decision was made
            
            # Attribution
            decider: Person, role, or entity making the decision
            delegate: Explicitly delegate decision authority
            confidence: Confidence level (0.0-1.0) for AI decisions
            
            # Metadata
            category: Type of decision ("architecture", "security", etc.)
            scope: Scope of impact ("function", "module", "system")
            impact: Significance level ("low", "medium", "high")
            priority: Implementation priority ("low", "medium", "high")
            preserve: Whether to keep after implementation
            ref: Reference ID in the decision database or tracker
            date: ISO format date when decision was made
            see_also: A resource or list of related resources
            **kwargs: Additional attributes to store
        """
        metadata = {}
        if description is not None:
            metadata["description"] = description
        if implementor is not None:
            metadata["implementor"] = implementor
        if constraints is not None:
            metadata["constraints"] = constraints
        if reason is not None:
            metadata["reason"] = reason
        if options is not None:
            metadata["options"] = options
        if status is not None:
            metadata["status"] = status
        if answer is not None:
            metadata["answer"] = answer
        if rationale is not None:
            metadata["rationale"] = rationale
        if decider is not None:
            metadata["decider"] = decider
        if delegate is not None:
            metadata["delegate"] = delegate
        if confidence is not None:
            metadata["confidence"] = confidence
        if category is not None:
            metadata["category"] = category
        if scope is not None:
            metadata["scope"] = scope
        if impact is not None:
            metadata["impact"] = impact
        if priority is not None:
            metadata["priority"] = priority
        if preserve is not None:
            metadata["preserve"] = preserve
        if ref is not None:
            metadata["ref"] = ref
        if date is not None:
            metadata["date"] = date
        metadata.update(kwargs)
        return super().create(brief, **metadata)


# Expose create methods for annotations
intent = make_cop_annotation_factory(Intent)
implementation_status = make_cop_annotation_factory(ImplementationStatus)
invariant = make_cop_annotation_factory(Invariant)
risk = make_cop_annotation_factory(Risk)
decision = make_cop_annotation_factory(Decision)

# Expose the ImplementationStatusValues as module-level constants
IMPLEMENTED = ImplementationStatusValues.IMPLEMENTED         # ✅ Fully functional and complete
PARTIAL = ImplementationStatusValues.PARTIAL                 # ⚠️ Partially working with limitations
BUGGY = ImplementationStatusValues.BUGGY                     # ❌ Was working but now has issues
DEPRECATED = ImplementationStatusValues.DEPRECATED           # 🚫 Exists but should not be used
PLANNED = ImplementationStatusValues.PLANNED                 # 📝 Designed but not implemented
NOT_IMPLEMENTED = ImplementationStatusValues.NOT_IMPLEMENTED # ❓ Does not exist at all
UNKNOWN = ImplementationStatusValues.UNKNOWN                 # ❔ Status not yet evaluated
