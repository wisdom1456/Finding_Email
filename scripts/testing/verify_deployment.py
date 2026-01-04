#!/usr/bin/env python3
"""Pre-deployment verification script.

Run this BEFORE pushing to ensure local environment matches Vercel deployment.
This prevents the "works locally, fails in production" issue.
"""
import os
import sys
import re

# Required package versions that Vercel will use
REQUIRED_VERSIONS = {
    "openai": "1.70.0",  # GPT-5 parameters: reasoning_effort, max_completion_tokens
    "fastapi": "0.100.0",
    "supabase": "2.0.0",
    "pydantic": "2.0.0",
}


def check_requirements_consistency():
    """Ensure api/requirements.txt and requirements.txt versions are compatible."""
    print("=" * 60)
    print("Checking requirements consistency...")
    print("=" * 60)
    
    issues = []
    
    # Read both requirements files
    root_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    
    api_reqs_path = os.path.join(root_dir, 'api', 'requirements.txt')
    main_reqs_path = os.path.join(root_dir, 'requirements.txt')
    
    api_reqs = parse_requirements(api_reqs_path)
    main_reqs = parse_requirements(main_reqs_path)
    
    print(f"\napi/requirements.txt packages: {len(api_reqs)}")
    print(f"requirements.txt packages: {len(main_reqs)}")
    
    # Check critical packages
    for package, min_version in REQUIRED_VERSIONS.items():
        api_ver = api_reqs.get(package)
        main_ver = main_reqs.get(package)
        
        print(f"\n{package}:")
        print(f"  api/requirements.txt: {api_ver or 'NOT FOUND'}")
        print(f"  requirements.txt: {main_ver or 'NOT FOUND'}")
        print(f"  Required minimum: {min_version}")
        
        if not api_ver:
            issues.append(f"{package} missing from api/requirements.txt")
        elif not meets_version(api_ver, min_version):
            issues.append(f"{package} in api/requirements.txt ({api_ver}) < required ({min_version})")
    
    return issues


def check_local_vs_vercel():
    """Check that locally installed packages match Vercel requirements."""
    print("\n" + "=" * 60)
    print("Checking local environment vs Vercel deployment...")
    print("=" * 60)
    
    issues = []
    
    for package, min_version in REQUIRED_VERSIONS.items():
        try:
            mod = __import__(package)
            local_ver = getattr(mod, '__version__', 'unknown')
            print(f"\n{package}: local={local_ver}, vercel_min={min_version}")
            
            if not meets_version(local_ver, min_version):
                issues.append(f"{package} local ({local_ver}) < vercel requirement ({min_version})")
        except ImportError:
            issues.append(f"{package} not installed locally")
    
    return issues


def parse_requirements(filepath):
    """Parse requirements file into package:version dict."""
    packages = {}
    
    if not os.path.exists(filepath):
        return packages
    
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse: package>=1.0.0 or package==1.0.0
            match = re.match(r'^([a-zA-Z0-9_-]+)([><=]+)([0-9.]+)', line)
            if match:
                pkg, op, ver = match.groups()
                packages[pkg.lower()] = ver
    
    return packages


def meets_version(version_str, min_version):
    """Check if version meets minimum requirement."""
    if not version_str or version_str == 'unknown':
        return False
    
    try:
        from packaging import version
        return version.parse(version_str) >= version.parse(min_version)
    except:
        # Fallback to simple comparison
        return version_str >= min_version


def main():
    print("\n" + "=" * 60)
    print("PRE-DEPLOYMENT VERIFICATION")
    print("Ensures local testing matches Vercel production")
    print("=" * 60)
    
    all_issues = []
    
    # Check 1: Requirements files consistency
    issues = check_requirements_consistency()
    all_issues.extend(issues)
    
    # Check 2: Local environment matches
    issues = check_local_vs_vercel()
    all_issues.extend(issues)
    
    # Summary
    print("\n" + "=" * 60)
    if all_issues:
        print("VERIFICATION FAILED")
        print("=" * 60)
        print("\nIssues found:")
        for issue in all_issues:
            print(f"  - {issue}")
        print("\nFix these issues before deploying to Vercel!")
        return 1
    else:
        print("VERIFICATION PASSED")
        print("=" * 60)
        print("\nLocal environment matches Vercel deployment requirements.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

