# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities to [security email]

You can expect:
- Acknowledgment within 48 hours
- Regular updates on progress
- Credit for responsible disclosure

## Security Measures

This project implements:
- File upload validation with path traversal prevention
- PII sanitization (40+ patterns)
- Content type validation
- Size limits enforcement
- Comprehensive security testing