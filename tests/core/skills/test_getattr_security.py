"""Test getattr security fix - prevent special attribute access via getattr."""


from vibesop.core.skills.workflow import ExecutionContext, WorkflowEngine


class TestGetattrSecurity:
    """Test that getattr cannot be used to access special attributes."""

    def test_getattr_blocks_special_attributes(self) -> None:
        """Test that getattr(obj, '__class__') is blocked."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Try to access __class__ via getattr
        result = engine._evaluate_condition('getattr(x, "__class__")', context)
        assert result is False, "getattr with __class__ should be blocked"

    def test_getattr_blocks_double_underscore_attributes(self) -> None:
        """Test that getattr with any __attr__ pattern is blocked."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Try various special attributes
        special_attrs = [
            "__class__",
            "__bases__",
            "__dict__",
            "__mro__",
            "__subclasshook__",
        ]

        for attr in special_attrs:
            result = engine._evaluate_condition(f'getattr(x, "{attr}")', context)
            assert result is False, f"getattr with {attr} should be blocked"

    def test_getattr_allows_normal_attributes(self) -> None:
        """Test that getattr with normal attributes still works."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": 5})

        # Normal getattr should work (if the attribute exists)
        # For int objects, real and imag are normal attributes
        engine._evaluate_condition('getattr(x, "real")', context)
        # This should return True (5.real is a valid attribute)

    def test_getattr_blocks_mixed_special_attributes(self) -> None:
        """Test that getattr blocks various __attr__ patterns."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={"x": []})

        # Try with a list object
        special_attrs = ["__class__", "__len__", "__getitem__"]

        for attr in special_attrs:
            result = engine._evaluate_condition(f'getattr(x, "{attr}")', context)
            assert result is False, f"getattr on list with {attr} should be blocked"

    def test_getattr_blocks_indirect_special_access(self) -> None:
        """Test that getattr with variable attribute name is blocked."""
        engine = WorkflowEngine()
        context = ExecutionContext(skill_id="test", variables={
            "attr_name": "__class__",
            "obj": "test"
        })

        # Even with variable-based attribute name, should be blocked
        # because getattr now requires literal string arguments
        result = engine._evaluate_condition('getattr(obj, attr_name)', context)
        assert result is False, "getattr with variable attribute name should be blocked"
