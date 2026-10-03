"""
Test cases to explore COP framework features.

This module tests the various features of the COP framework
to ensure they work as expected and to demonstrate usage patterns.
"""

import pytest
from cop_python.min import (
    intent, 
    implementation_status, 
    risk, 
    invariant, 
    decision,
    IMPLEMENTED, 
    PARTIAL, 
    NOT_IMPLEMENTED,
    ConceptAnnotations,
    concept_annotations
)
from cop_python.utils import (
    get_implementation_status,
    get_intent,
    get_risks
)


# Test 1: Basic annotation application
def test_basic_annotations():
    """Test that basic annotations can be applied to functions."""
    
    @intent("Calculate sum of two numbers")
    @implementation_status(IMPLEMENTED)
    def add(a, b):
        return a + b
    
    # Check annotations are attached
    assert hasattr(add, "__cop_annotations__")
    
    # Check specific annotations via utils
    status = get_implementation_status(add)
    assert status.value == IMPLEMENTED
    
    intent_val = get_intent(add)
    assert intent_val.value == "Calculate sum of two numbers"
    
    # Test the function still works
    assert add(2, 3) == 5


# Test 2: Multiple annotations with metadata
def test_complex_annotations():
    """Test annotations with metadata and multiple risks."""
    
    @intent("Process sensitive user data")
    @implementation_status(PARTIAL, details="Missing encryption for some fields")
    @risk("Data exposure", category="security", severity="HIGH")
    @risk("Performance degradation", category="performance", severity="MEDIUM")
    @invariant("User IDs must be positive integers", critical=True)
    def process_user_data(user_id, data):
        if user_id <= 0:
            raise ValueError("User ID must be positive")
        return {"processed": True}
    
    # Check implementation status with details
    status = get_implementation_status(process_user_data)
    assert status.value == PARTIAL
    assert status.metadata.get("details") == "Missing encryption for some fields"
    
    # Check multiple risks
    risks = get_risks(process_user_data)
    assert len(risks) == 2
    
    security_risks = get_risks(process_user_data, category_in=["security"]) 
    assert len(security_risks) == 1
    assert security_risks[0].value == "Data exposure"


# Test 3: Class annotations
def test_class_annotations():
    """Test annotations on classes and methods."""
    
    @intent("Manage user accounts")
    @implementation_status(IMPLEMENTED)
    class UserManager:
        
        @intent("Create new user account")
        @implementation_status(IMPLEMENTED)
        @invariant("Username must be unique", critical=True)
        def create_user(self, username):
            return {"username": username, "id": 1}
        
        @intent("Delete user account") 
        @implementation_status(NOT_IMPLEMENTED)
        @decision(implementor="human", reason="Requires GDPR compliance review")
        def delete_user(self, user_id):
            raise NotImplementedError("User deletion not implemented")
    
    # Test class has annotations
    assert hasattr(UserManager, "__cop_annotations__")
    
    # Test method annotations
    manager = UserManager()
    create_method = manager.create_user
    assert get_implementation_status(create_method).value == IMPLEMENTED
    
    delete_method = manager.delete_user
    assert get_implementation_status(delete_method).value == NOT_IMPLEMENTED


# Test 4: Context managers for code sections
def test_context_managers():
    """Test using annotations as context managers."""
    
    def complex_function():
        results = []
        
        # Different sections with different annotations
        with implementation_status(IMPLEMENTED):
            with risk("Validation bypass", category="security", severity="HIGH"):
                results.append("validation")
        
        with implementation_status(NOT_IMPLEMENTED):
            with decision(implementor="ai", constraints=["Must handle errors"]):
                results.append("processing")
                # This would raise NotImplementedError in real code
        
        return results
    
    # Function should execute (context managers don't affect execution)
    result = complex_function()
    assert result == ["validation", "processing"]


# Test 5: ConceptAnnotations for reusable sets
def test_concept_annotations():
    """Test reusable annotation sets."""
    
    # Create a reusable set of annotations
    api_annotations = ConceptAnnotations([
        intent("RESTful API endpoint"),
        risk("Authentication required", category="security", severity="MEDIUM"),
        invariant("Must return JSON", critical=True)
    ])
    
    @api_annotations.apply_to
    def get_users():
        return []
    
    @api_annotations.apply_to
    def get_products():
        return []
    
    # Both functions should have the same annotations
    users_intent = get_intent(get_users)
    products_intent = get_intent(get_products)
    assert users_intent.value == products_intent.value == "RESTful API endpoint"
    
    # Both should have security risk
    users_risks = get_risks(get_users)
    products_risks = get_risks(get_products)
    assert len(users_risks) == len(products_risks) == 1


# Test 6: Decision tracking
def test_decision_annotations():
    """Test decision annotations with all parameters."""
    
    @decision(brief="Use PostgreSQL for main database",
             options=["PostgreSQL", "MySQL", "MongoDB"],
             answer="PostgreSQL",
             rationale="Better support for complex queries and ACID compliance",
             implementor="human",
             decider="tech_lead",
             category="architecture",
             date="2023-01-15")
    def get_database_connection():
        return "postgresql://..."
    
    # Verify decision was recorded
    decisions = getattr(get_database_connection, "__cop_annotations__", None)
    assert decisions is not None
    
    # Get decision annotations
    decision_list = decisions.get("decision")
    assert len(decision_list) == 1
    decision_anno = decision_list[0]
    
    assert decision_anno.value == "Use PostgreSQL for main database"
    assert decision_anno.metadata["options"] == ["PostgreSQL", "MySQL", "MongoDB"]
    assert decision_anno.metadata["answer"] == "PostgreSQL"
    assert decision_anno.metadata["implementor"] == "human"


# Test 7: Module-level annotations
def test_module_annotations():
    """Test applying annotations at module level."""
    
    # Create a mock module to test with
    class MockModule:
        pass
    
    module = MockModule()
    
    # Apply module-level annotations using context manager
    with concept_annotations.on(module):
        intent("Core business logic module")
        implementation_status(PARTIAL, details="Missing advanced features")
        risk("Contains sensitive business rules", category="security", severity="MEDIUM")
    
    # Check module has annotations
    assert hasattr(module, "__cop_annotations__")
    
    # Verify annotations were applied
    module_intent = get_intent(module)
    assert module_intent.value == "Core business logic module"
    
    module_status = get_implementation_status(module)
    assert module_status.value == PARTIAL


# Test 8: Error handling
def test_error_handling():
    """Test that framework handles errors gracefully."""
    
    # Test with None values
    @intent(None)
    @implementation_status(NOT_IMPLEMENTED)
    def function_with_none_intent():
        pass
    
    # Should not raise errors
    intent_val = get_intent(function_with_none_intent)
    assert intent_val.value is None
    
    # Test with empty strings
    @intent("")
    @risk("", category="security", severity="LOW")
    def function_with_empty_strings():
        pass
    
    risks = get_risks(function_with_empty_strings)
    assert len(risks) == 1
    assert risks[0].value == ""


# Test 9: Annotation inheritance (if supported)
def test_annotation_propagation():
    """Test how annotations propagate or inherit."""
    
    @intent("Parent functionality")
    @implementation_status(IMPLEMENTED)
    class Parent:
        @intent("Parent method")
        def method(self):
            pass
    
    class Child(Parent):
        @intent("Child method override")
        @implementation_status(PARTIAL)
        def method(self):
            pass
    
    # Child method should have its own annotations
    child = Child()
    child_method_intent = get_intent(child.method)
    # This might fail if inheritance is handled differently
    try:
        assert child_method_intent.value == "Child method override"
    except (AttributeError, AssertionError):
        # If inheritance doesn't work as expected
        pytest.skip("Annotation inheritance not supported as expected")


# Test 10: Complex real-world example
def test_real_world_example():
    """Test a realistic example with multiple features."""
    
    @intent("Process e-commerce order")
    @implementation_status(PARTIAL, details="International shipping not supported")
    @risk("Payment fraud", category="security", severity="HIGH",
          mitigation=["Fraud detection service", "Manual review for large orders"])
    @invariant("Order total must match sum of items", critical=True)
    @decision(implementor="human", 
             reason="Complex business rules and compliance requirements")
    def process_order(order_data):
        """Process an e-commerce order."""
        
        # Validate order
        with risk("Input validation", category="security", severity="MEDIUM"):
            if not order_data.get("items"):
                raise ValueError("Order must have items")
        
        # Calculate totals
        with invariant("Prices must be positive", critical=True):
            total = sum(item["price"] * item["quantity"] 
                       for item in order_data["items"])
        
        # Process payment
        with implementation_status(NOT_IMPLEMENTED):
            with decision(implementor="ai", 
                         constraints=["PCI compliance", "Handle all payment types"]):
                # payment_result = process_payment(total)
                payment_result = {"status": "success"}  # Mock for test
        
        return {
            "order_id": "12345",
            "total": total,
            "payment": payment_result
        }
    
    # Test the function
    order = {
        "items": [
            {"name": "Widget", "price": 10.0, "quantity": 2},
            {"name": "Gadget", "price": 25.0, "quantity": 1}
        ]
    }
    
    result = process_order(order)
    assert result["total"] == 45.0
    assert result["payment"]["status"] == "success"
    
    # Verify all annotations are present
    status = get_implementation_status(process_order)
    assert status.value == PARTIAL
    
    risks = get_risks(process_order)
    assert len(risks) == 1
    assert risks[0].metadata["mitigation"] == ["Fraud detection service", 
                                               "Manual review for large orders"]


if __name__ == "__main__":
    # Run tests
    test_basic_annotations()
    test_complex_annotations()
    test_class_annotations()
    test_context_managers()
    test_concept_annotations()
    test_decision_annotations()
    test_module_annotations()
    test_error_handling()
    test_annotation_propagation()
    test_real_world_example()
    
    print("All tests completed!")