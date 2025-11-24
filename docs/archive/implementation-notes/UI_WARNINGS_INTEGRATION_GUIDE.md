# UI Integration Guide - Corpus Coverage Warnings

## Quick Integration

Add this code snippet to `src/legal_portal/ui/main.py` where the processing results are displayed:

### Location 1: After Processing Completes (Results Page)

```python
# After processing completes and result is available
if hasattr(st.session_state, 'result') and st.session_state.result:
    result = st.session_state.result
    
    # Display corpus coverage warnings (if any)
    if result.warnings:
        st.warning("⚠️ **Practice Area Notice**")
        for warning in result.warnings:
            st.markdown(warning)
        st.markdown("---")
```

### Location 2: Before Letter Generation (Optional Confirmation)

```python
# Before starting processing
if st.button("Generate Findings Letter"):
    # Quick coverage check
    from legal_portal.services.corpus_coverage_service import CorpusCoverageService
    from legal_portal.config.default import get_settings
    
    settings = get_settings()
    
    if settings.corpus_coverage_warnings:
        coverage_service = CorpusCoverageService()
        coverage_result = coverage_service.analyze_coverage(
            case_type=st.session_state.get('case_type'),
            case_facts=st.session_state.get('intake_content', '')[:2000],
            legal_issues=st.session_state.get('legal_issues', [])
        )
        
        if coverage_result["warnings"]:
            with st.expander("⚠️ **Review Practice Area Coverage**", expanded=True):
                for warning in coverage_result["warnings"]:
                    st.warning(warning)
                st.info(
                    "You can still proceed with letter generation. "
                    "However, statute citations may not be validated for unsupported practice areas."
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Proceed Anyway"):
                        st.session_state.coverage_acknowledged = True
                        st.rerun()
                with col2:
                    if st.button("Cancel"):
                        st.stop()
                        
                if not st.session_state.get('coverage_acknowledged'):
                    st.stop()  # Don't proceed until user acknowledges
    
    # Continue with normal processing...
    st.session_state.ui_step = "processing"
    st.rerun()
```

### Location 3: Sidebar Information Panel (Always Visible)

```python
# In the sidebar
with st.sidebar:
    st.markdown("### 📚 Florida Legal Corpus")
    
    from legal_portal.services.corpus_coverage_service import CorpusCoverageService
    coverage_service = CorpusCoverageService()
    
    with st.expander("Supported Practice Areas"):
        st.markdown(coverage_service.get_coverage_summary())
    
    st.markdown("---")
```

---

## Full Example: Results Page Integration

```python
def display_results():
    """Display processing results with corpus coverage warnings."""
    st.header("📄 Findings Letter Generated")
    
    result = st.session_state.result
    
    # CORPUS COVERAGE WARNINGS
    if result.warnings:
        st.warning("⚠️ **Practice Area Coverage Notice**")
        for warning in result.warnings:
            st.markdown(f"- {warning}")
        
        with st.expander("ℹ️ What does this mean?"):
            st.markdown("""
            The Florida Legal Corpus provides verified statute information for specific practice areas.
            If your case falls outside these areas, the application can still generate a findings letter,
            but statute citations may not be validated against the corpus.
            
            **What you can do:**
            - Review the generated letter carefully
            - Verify any statute citations independently
            - Consult with the attorney about jurisdictional concerns
            
            **Supported Florida Practice Areas:**
            - Consumer Protection & Business Misconduct
            - Landlord-Tenant Disputes
            - Foreclosure Defense
            - Construction Defects & Mechanic's Liens
            - Property Insurance Claims
            - Civil Litigation & Attorney Fees
            """)
        
        st.markdown("---")
    
    # STATUTE VALIDATION METRICS (if available)
    if hasattr(result, 'statute_validation') and result.statute_validation:
        validation = result.statute_validation
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "✅ Verified Citations",
                validation.get('verified_citations', 0)
            )
        with col2:
            st.metric(
                "❓ Unverified Citations",
                validation.get('unverified_citations', 0)
            )
        with col3:
            st.metric(
                "⚠️ Suspicious Citations",
                validation.get('suspicious_citations', 0)
            )
        
        if validation.get('suspicious_citations', 0) > 0:
            st.error(
                "⚠️ **Suspicious citations detected!** "
                "These statutes may not exist or may be incorrectly cited. "
                "Please review the findings letter carefully."
            )
        
        st.markdown("---")
    
    # DISPLAY THE LETTER
    st.markdown("### Generated Findings Letter")
    st.markdown(result.main_letter, unsafe_allow_html=True)
    
    # DOWNLOAD BUTTONS
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Letter (HTML)",
            data=result.main_letter,
            file_name="findings_letter.html",
            mime="text/html"
        )
    with col2:
        if result.main_letter_with_citations:
            st.download_button(
                label="📥 Download with Citations",
                data=result.main_letter_with_citations,
                file_name="findings_letter_cited.html",
                mime="text/html"
            )
```

---

## Configuration

Users can disable warnings via `.env`:

```bash
# Disable corpus coverage warnings
CORPUS_COVERAGE_WARNINGS=false

# Disable statute recommendations
SUGGEST_STATUTES=false

# Disable citation validation
VALIDATE_CITATIONS=false
```

---

## Styling Options

### Warning Box with Icon

```python
if result.warnings:
    st.markdown("""
    <div style="
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    ">
        <strong style="color: #856404;">⚠️ Practice Area Notice</strong><br/>
        <ul style="color: #856404; margin-top: 10px;">
    """, unsafe_allow_html=True)
    
    for warning in result.warnings:
        clean_warning = warning.replace("⚠️", "").strip()
        st.markdown(f"<li>{clean_warning}</li>", unsafe_allow_html=True)
    
    st.markdown("</ul></div>", unsafe_allow_html=True)
```

### Collapsible Info Panel

```python
if result.warnings:
    with st.expander("⚠️ Practice Area Coverage Notice - Click to Review", expanded=False):
        for warning in result.warnings:
            st.info(warning)
        
        st.markdown("**Need Help?**")
        st.markdown("""
        - Review the [Supported Practice Areas](#) documentation
        - Contact the attorney for guidance on unsupported case types
        - The application will still generate a letter, but citations may not be validated
        """)
```

---

## Testing

### Test Case 1: No Warnings (Florida Civil Case)

```python
# Should display no warnings
result = ProcessingResult(
    main_letter="<html>...</html>",
    warnings=[],  # Empty
    status="completed"
)
```

### Test Case 2: Federal Case Warning

```python
# Should display federal jurisdiction warning
result = ProcessingResult(
    main_letter="<html>...</html>",
    warnings=[
        "⚠️ This case appears to involve unsupported areas: Federal Claims (Not Supported). "
        "The Florida Legal Corpus does not cover these topics. Citations may not be validated."
    ],
    status="completed"
)
```

### Test Case 3: Unknown Practice Area

```python
# Should display coverage uncertainty warning
result = ProcessingResult(
    main_letter="<html>...</html>",
    warnings=[
        "⚠️ Could not determine specific practice area from case information. "
        "The Florida Legal Corpus covers: Consumer Protection, Landlord-Tenant, "
        "Foreclosure, Construction, Insurance, and Civil Litigation matters under Florida law only."
    ],
    status="completed"
)
```

---

## Next Steps

1. ✅ Choose integration location (results page recommended)
2. ✅ Copy appropriate code snippet
3. ✅ Test with various case types
4. ✅ Adjust styling to match application theme
5. ✅ Deploy and monitor user feedback

**Warnings are now available in `processing_result.warnings` - ready to display!**

