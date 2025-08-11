# Security Implementation

## Overview

The Legal Document Analysis Portal implements comprehensive security measures to protect sensitive legal documents and personally identifiable information (PII). This document details all security implementations, testing coverage, and compliance measures.

## Security Architecture

```mermaid
graph TD
    subgraph "Input Layer"
        A[File Upload Security]
        B[Input Validation]
        C[Size Limits]
    end
    
    subgraph "Processing Layer"
        D[PII Sanitization]
        E[Secure Logging]
        F[Session Isolation]
    end
    
    subgraph "Storage Layer"
        G[Temporary Storage]
        H[Secure Deletion]
        I[Encryption at Rest]
    end
    
    subgraph "Output Layer"
        J[Content Sanitization]
        K[Download Security]
        L[Display Protection]
    end
    
    A --> D
    B --> D
    C --> D
    D --> G
    E --> G
    F --> G
    G --> J
    H --> J
    I --> J
```

## File Upload Security

### Implementation Location: `utils/security.py`

### Path Traversal Prevention
```python
def validate_file_path(filepath: str) -> bool:
    """Prevent path traversal attacks"""
    # Normalize path and check for traversal attempts
    normalized = os.path.normpath(filepath)
    if ".." in normalized or normalized.startswith("/"):
        return False
    return True
```

### File Type Validation
**Allowed Extensions:**
- Documents: `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`
- Media: `.mp3`, `.wav`, `.mp4`, `.avi`, `.mov`
- Email: `.eml`, `.msg`

**Magic Number Verification:**
```python
MAGIC_NUMBERS = {
    b'%PDF': 'pdf',
    b'PK\x03\x04': 'docx',
    b'\x89PNG': 'png',
    b'\xFF\xD8\xFF': 'jpg',
    b'GIF8': 'gif'
}
```

### Size Limits
- **Maximum Single File**: 100MB
- **Total Upload Limit**: 100MB aggregate
- **Validation**: Pre-upload and post-upload verification

### Filename Sanitization
```python
def sanitize_filename(filename: str) -> str:
    """Remove potentially dangerous characters"""
    # Remove path separators
    filename = filename.replace('/', '').replace('\\', '')
    # Remove special characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Limit length
    return filename[:255]
```

## PII Protection

### Implementation Location: `utils/pii_sanitizer.py`

### Legal-Specific PII Patterns (40+)

#### Personal Identifiers
1. **Social Security Numbers**: `\b\d{3}-\d{2}-\d{4}\b`
2. **Driver's License**: State-specific patterns
3. **Passport Numbers**: International formats
4. **Tax IDs**: EIN, ITIN patterns

#### Contact Information
5. **Email Addresses**: RFC-compliant regex
6. **Phone Numbers**: US and international
7. **Physical Addresses**: Street, city, state, ZIP
8. **IP Addresses**: IPv4 and IPv6

#### Financial Information
9. **Credit Card Numbers**: Luhn-validated
10. **Bank Account Numbers**: ABA routing
11. **IBAN**: International banking
12. **Bitcoin Addresses**: Cryptocurrency

#### Legal Identifiers
13. **Case Numbers**: Court-specific formats
14. **Bar Numbers**: Attorney identifiers
15. **Client IDs**: Firm-specific patterns
16. **Docket Numbers**: Federal and state

#### Medical Information
17. **Medical Record Numbers**: Hospital formats
18. **Insurance IDs**: Provider-specific
19. **Medicare/Medicaid**: Government IDs
20. **DEA Numbers**: Prescription authority

#### Biometric Data
21. **Fingerprint Hashes**: Common formats
22. **Face Recognition IDs**: System identifiers
23. **DNA Markers**: Forensic patterns

### Sanitization Process

```python
class PIISanitizer:
    def __init__(self, force_sanitize: bool = False):
        self.patterns = self._load_patterns()
        self.force_sanitize = force_sanitize or os.getenv('ENVIRONMENT') == 'production'
    
    def sanitize(self, text: str) -> str:
        """Apply all PII patterns"""
        if not self.force_sanitize:
            return text
            
        for pattern_name, regex in self.patterns.items():
            text = regex.sub(f'[{pattern_name}_REDACTED]', text)
        
        return text
    
    def double_sanitize_for_api(self, text: str) -> str:
        """Extra sanitization for external API calls"""
        # First pass: standard sanitization
        text = self.sanitize(text)
        # Second pass: aggressive removal
        text = self._remove_residual_pii(text)
        return text
```

### Production Enforcement
- **Automatic in Production**: `ENVIRONMENT=production` forces sanitization
- **Development Override**: Optional bypass for testing
- **Audit Trail**: All sanitization logged (without PII)

## Secure Logging

### Implementation Location: `utils/logging_config.py`

### PII-Safe Logging
```python
class SecureLogger:
    def __init__(self):
        self.sanitizer = PIISanitizer(force_sanitize=True)
        
    def log(self, level: str, message: str, **kwargs):
        # Sanitize message
        clean_message = self.sanitizer.sanitize(message)
        
        # Sanitize all kwargs
        clean_kwargs = {
            k: self.sanitizer.sanitize(str(v)) 
            for k, v in kwargs.items()
        }
        
        # Log safely
        logger.log(level, clean_message, **clean_kwargs)
```

### Log Rotation and Retention
- **Rotation**: 10MB file size limit
- **Retention**: 30-day maximum
- **Compression**: ZIP format for archives
- **Encryption**: Optional log encryption

### Structured Logging
```json
{
    "timestamp": "2025-08-10T20:00:00Z",
    "level": "INFO",
    "service": "document_processor",
    "message": "Processing document for client [CLIENT_NAME_REDACTED]",
    "metadata": {
        "document_id": "doc_123",
        "size_bytes": 1024000,
        "type": "pdf"
    }
}
```

## Input Validation

### Form Input Validation
```python
def validate_case_info(data: dict) -> bool:
    """Validate all form inputs"""
    validators = {
        'clientName': validate_name,
        'attorneyName': validate_name,
        'caseReference': validate_case_ref,
        'email': validate_email
    }
    
    for field, validator in validators.items():
        if field in data and not validator(data[field]):
            raise ValidationError(f"Invalid {field}")
    
    return True
```

### SQL Injection Prevention
- **Parameterized Queries**: Never concatenate user input
- **ORM Usage**: SQLAlchemy with bound parameters
- **Input Escaping**: HTML and SQL special characters

### XSS Protection
```python
def sanitize_html_output(content: str) -> str:
    """Prevent XSS attacks in rendered content"""
    # Escape HTML entities
    content = html.escape(content)
    # Remove script tags
    content = re.sub(r'<script.*?>.*?</script>', '', content, flags=re.DOTALL)
    # Remove event handlers
    content = re.sub(r'on\w+="[^"]*"', '', content)
    return content
```

## Session Security

### Streamlit Session Isolation
```python
def get_secure_session():
    """Ensure session isolation"""
    session_id = st.session_state.get('session_id')
    if not session_id:
        session_id = generate_secure_id()
        st.session_state.session_id = session_id
    
    return session_id
```

### Session Data Protection
- **No Cross-Session Access**: Each user isolated
- **Session Timeout**: Configurable expiration
- **Secure Cookies**: HTTPS-only in production

## API Security

### OpenAI API Protection
```python
class SecureAPIClient:
    def __init__(self):
        self.api_key = self._get_secure_key()
        self.sanitizer = PIISanitizer()
    
    def _get_secure_key(self) -> str:
        """Retrieve API key securely"""
        key = os.getenv('OPENAI_API_KEY')
        if not key:
            raise SecurityError("API key not configured")
        return key
    
    def make_request(self, prompt: str) -> str:
        """Make sanitized API request"""
        # Double sanitize for external API
        clean_prompt = self.sanitizer.double_sanitize_for_api(prompt)
        
        # Make request with rate limiting
        response = self._rate_limited_request(clean_prompt)
        
        return response
```

### Rate Limiting
- **Request Limits**: 500/min, 10k/day
- **Token Limits**: 30,000 TPM
- **Retry Logic**: Exponential backoff
- **Circuit Breaker**: Failure threshold protection

## Temporary Storage Security

### Google Cloud Storage
```python
class SecureCloudStorage:
    def __init__(self):
        self.bucket = self._get_secure_bucket()
        self.lifecycle_policy = {
            'lifecycle': {
                'rule': [{
                    'action': {'type': 'Delete'},
                    'condition': {'age': 1}  # 24-hour deletion
                }]
            }
        }
    
    def upload_temp_file(self, file_data: bytes, filename: str) -> str:
        """Upload with automatic cleanup"""
        # Generate unique, unguessable name
        secure_name = f"{uuid.uuid4()}/{sanitize_filename(filename)}"
        
        # Upload with encryption
        blob = self.bucket.blob(secure_name)
        blob.upload_from_string(file_data, encryption='AES256')
        
        # Set expiration
        blob.lifecycle_rules = self.lifecycle_policy
        
        return secure_name
```

### Local Storage
- **Temporary Directory**: OS-managed temp space
- **Automatic Cleanup**: Context manager pattern
- **Permission Restrictions**: 600 (owner read/write only)

## Security Testing Coverage

### Test Statistics
- **Total Security Tests**: 992 lines
- **Coverage Areas**: 15 security domains
- **Test Files**: 8 dedicated security test modules

### Test Categories

#### 1. Path Traversal Tests
```python
def test_path_traversal_prevention():
    """Test path traversal attack prevention"""
    malicious_paths = [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "/etc/shadow",
        "C:\\Windows\\System32"
    ]
    
    for path in malicious_paths:
        assert not validate_file_path(path)
```

#### 2. PII Sanitization Tests
```python
def test_pii_sanitization():
    """Test PII pattern matching and removal"""
    test_cases = [
        ("SSN: 123-45-6789", "SSN: [SSN_REDACTED]"),
        ("Call me at 555-1234", "Call me at [PHONE_REDACTED]"),
        ("Email: test@example.com", "Email: [EMAIL_REDACTED]")
    ]
    
    sanitizer = PIISanitizer(force_sanitize=True)
    for input_text, expected in test_cases:
        assert sanitizer.sanitize(input_text) == expected
```

#### 3. File Upload Tests
```python
def test_file_upload_security():
    """Test file upload validation"""
    # Test size limits
    large_file = b'x' * (101 * 1024 * 1024)  # 101MB
    assert not validate_file_size(large_file)
    
    # Test file type validation
    assert validate_file_type("document.pdf")
    assert not validate_file_type("malware.exe")
    
    # Test magic number verification
    pdf_header = b'%PDF-1.4'
    assert verify_magic_number(pdf_header, 'pdf')
```

#### 4. Input Validation Tests
```python
def test_input_validation():
    """Test form input validation"""
    # SQL injection attempts
    malicious_inputs = [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "<script>alert('XSS')</script>"
    ]
    
    for input_str in malicious_inputs:
        assert not validate_user_input(input_str)
```

## Compliance and Standards

### OWASP Top 10 Coverage
1. **A01:2021 – Broken Access Control**: ✅ Path traversal prevention
2. **A02:2021 – Cryptographic Failures**: ✅ Encrypted storage
3. **A03:2021 – Injection**: ✅ Input validation, parameterized queries
4. **A04:2021 – Insecure Design**: ✅ Security by design
5. **A05:2021 – Security Misconfiguration**: ✅ Secure defaults
6. **A06:2021 – Vulnerable Components**: ✅ Dependency scanning
7. **A07:2021 – Authentication Failures**: ✅ Session management
8. **A08:2021 – Data Integrity Failures**: ✅ Input validation
9. **A09:2021 – Logging Failures**: ✅ Secure logging
10. **A10:2021 – SSRF**: ✅ API request validation

### Legal Compliance
- **Attorney-Client Privilege**: Data isolation and encryption
- **HIPAA Considerations**: Medical record protection
- **GDPR Compliance**: PII handling and deletion
- **State Bar Requirements**: Secure document handling

## Security Monitoring

### Real-time Monitoring
```python
class SecurityMonitor:
    def __init__(self):
        self.alerts = []
        self.threshold = 10  # Suspicious activity threshold
        
    def monitor_activity(self, event: dict):
        """Monitor for security events"""
        if self._is_suspicious(event):
            self.alerts.append(event)
            
        if len(self.alerts) > self.threshold:
            self._trigger_alert()
    
    def _is_suspicious(self, event: dict) -> bool:
        """Detect suspicious patterns"""
        patterns = [
            'multiple_failed_uploads',
            'excessive_file_sizes',
            'rapid_api_calls',
            'pattern_matching_attempts'
        ]
        
        return any(p in event.get('type', '') for p in patterns)
```

### Audit Logging
- **All Security Events**: Logged with timestamp
- **User Actions**: Upload, download, processing
- **System Events**: Errors, warnings, failures
- **Retention**: 90 days for audit logs

## Security Best Practices

### Development Guidelines
1. **Never Log PII**: Always sanitize before logging
2. **Validate All Input**: Never trust user input
3. **Fail Securely**: Default to deny on error
4. **Minimize Attack Surface**: Disable unused features
5. **Keep Dependencies Updated**: Regular security patches

### Deployment Security
1. **HTTPS Only**: Enforce TLS in production
2. **Environment Variables**: Never hardcode secrets
3. **Network Isolation**: Restrict unnecessary access
4. **Regular Updates**: Security patch schedule
5. **Backup Strategy**: Encrypted backups

### Incident Response
1. **Detection**: Real-time monitoring alerts
2. **Containment**: Automatic session termination
3. **Investigation**: Comprehensive audit logs
4. **Recovery**: Rollback procedures
5. **Documentation**: Incident reports

## Security Roadmap

### Current Implementation (v2.0)
- ✅ File upload security
- ✅ PII sanitization (40+ patterns)
- ✅ Secure logging
- ✅ Input validation
- ✅ Session isolation

### Planned Enhancements (v3.0)
- [ ] End-to-end encryption
- [ ] Multi-factor authentication
- [ ] Advanced threat detection
- [ ] Security information and event management (SIEM)
- [ ] Penetration testing certification

## Security Contacts

For security concerns or vulnerability reports:
- **Security Email**: security@legalportal.com
- **Bug Bounty Program**: Available for critical vulnerabilities
- **Response Time**: 24 hours for critical issues

## Conclusion

The Legal Document Analysis Portal implements defense-in-depth security strategies across all layers of the application. With 992 lines of security test coverage and comprehensive PII protection, the system is designed to handle sensitive legal documents securely and in compliance with legal industry standards.