# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.2.x   | :white_check_mark: |
| 2.1.x   | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please open a draft security advisory at:
https://github.com/nehcuh/vibesop-py/security/advisories

You should receive a response within 48 hours.

## Security Features

VibeSOP includes several security features:

1. **Path Traversal Protection**: All file writes go through `PathSafety` checks
2. **Security Scanning**: Input scanned for prompt injection and other threats
3. **Atomic File Writes**: Prevents corruption during configuration generation
4. **Input Validation**: Pydantic v2 runtime validation on all data models

## Known Limitations

- LLM API keys are stored in environment variables (best practice: use secret managers)
- Configuration files may contain sensitive data (ensure proper file permissions)
