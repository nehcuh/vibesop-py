# Testing Guide

## Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/cli/test_auto.py -v

# Run specific test
uv run pytest tests/test_models.py::test_skill_route -v

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run benchmarks
make benchmark
```

## Writing Tests

### Test Structure

```python
class TestComponentName:
    """Tests for ComponentName."""

    def test_specific_behavior(self) -> None:
        """Test a specific behavior."""
        # Arrange
        component = ComponentName()

        # Act
        result = component.method(input)

        # Assert
        assert result == expected
```

### Using Fixtures

Shared fixtures are in `tests/conftest.py`. Module-specific fixtures are in each subdirectory's `conftest.py`.

```python
def test_with_fixture(sample_skill, temp_dir):
    # sample_skill from tests/conftest.py
    # temp_dir from tests/conftest.py
    pass
```

### Mocking

Use `pytest-mock` for mocking:

```python
def test_with_mock(mocker):
    mock_router = mocker.patch('vibesop.routing.engine.SkillRouter')
    mock_router.route.return_value = expected_result
```

## Coverage Targets

- Overall: 80%+
- Core modules: 85%+
- CLI commands: 60%+
- Branch coverage: 50%+
