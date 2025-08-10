# Security Audit Report

Generated: 2025-01-07
Tool: pip-audit
Status: **13 Known Vulnerabilities Found**

## Critical Vulnerabilities (Immediate Action Required)

### 1. **requests 2.32.3** → 2.32.4
- **Issue**: URL parsing vulnerability may leak .netrc credentials to third parties
- **Impact**: HIGH - Credential exposure
- **CVE**: GHSA-9hjg-9r4m-mvj7

### 2. **aiohttp 3.11.16** → 3.12.14
- **Issue**: Request smuggling vulnerability in Python parser
- **Impact**: HIGH - Bypass firewall/proxy protections
- **CVE**: GHSA-9548-qrrj-x5pj

### 3. **h11 0.14.0** → 0.16.0
- **Issue**: Request smuggling via chunked-encoding parsing
- **Impact**: HIGH - Request smuggling attacks
- **CVE**: GHSA-vqfr-h8mv-ghfj

## Medium Priority Vulnerabilities

### 4. **pillow 11.2.1** → 11.3.0
- **Issue**: Heap buffer overflow in DDS format writing
- **Impact**: MEDIUM - Affects large image processing
- **CVE**: PYSEC-2025-61

### 5. **transformers 4.52.3** → 4.53.0
- **Issue**: ReDoS in TensorFlow weight name conversion
- **Impact**: MEDIUM - Service disruption
- **CVE**: GHSA-9356-575x-2w9m

### 6. **starlette 0.45.3** → 0.47.2
- **Issue**: Blocks main thread when parsing large forms
- **Impact**: MEDIUM - Performance degradation
- **CVE**: GHSA-2c2j-9gv5-cj73

### 7. **mcp 1.9.1** → 1.10.0
- **Issue 1**: Validation error causes unhandled exception (GHSA-3qhf-m339-9g5v)
- **Issue 2**: Exception after streamable HTTP session crashes server (GHSA-j975-95f5-7wqh)
- **Impact**: MEDIUM - Service availability

## Lower Priority Vulnerabilities

### 8. **urllib3 2.3.0** → 2.5.0
- **Issue 1**: Ignores redirect controls in Pyodide runtime (GHSA-48p4-8xcf-vxj5)
- **Issue 2**: Ignores retries parameter for redirect control (GHSA-pq67-6m6q-mj2v)
- **Impact**: LOW - Redirect bypass (specific environments)

### 9. **torch 2.7.0** → 2.7.1rc1
- **Issue 1**: DoS in torch.nn.functional.ctc_loss (GHSA-887c-mr87-cxwp)
- **Issue 2**: DoS in torch.mkldnn_max_pool2d (GHSA-3749-ghw9-m3mg)
- **Impact**: LOW - Local DoS attacks

### 10. **ecdsa 0.19.1** (No Fix Available)
- **Issue**: Minerva timing attack on P-256 curve
- **Impact**: LOW - Side channel attack (out of scope for project)
- **CVE**: GHSA-wj6h-64fc-37mp

## Recommended Actions

### Immediate (High Priority)
```bash
pip install --upgrade requests==2.32.4
pip install --upgrade aiohttp==3.12.14
pip install --upgrade h11==0.16.0
```

### Near Term (Medium Priority)
```bash
pip install --upgrade pillow==11.3.0
pip install --upgrade transformers==4.53.0
pip install --upgrade starlette==0.47.2
pip install --upgrade mcp==1.10.0
```

### When Convenient (Low Priority)
```bash
pip install --upgrade urllib3==2.5.0
pip install --upgrade torch==2.7.1rc1
```

## Integration with CI/CD

- Added pip-audit to security scanning pipeline
- Pre-commit hooks include bandit for SAST
- Regular dependency updates should be scheduled
- Security alerts should trigger immediate review

## Notes

- ecdsa vulnerability is considered out of scope by maintainers
- Most vulnerabilities require specific attack vectors
- Production deployment should prioritize high/medium fixes
- Monitor security advisories for new vulnerabilities
