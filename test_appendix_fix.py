#!/usr/bin/env python3
"""
Test script to validate document appendix template fixes.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def create_test_data():
    """Create test data structure matching the fixed template expectations."""
    
    # Sample document with citations
    test_document = {
        "filename": "Test_Contract_Agreement.pdf",
        "file_name": "Test_Contract_Agreement.pdf",
        "document_type": "Contract",
        "inferred_title": "Service Agreement Between Parties",
        "summary": "This document outlines the terms and conditions of a service agreement between two parties, including payment terms, deliverables, and termination clauses.",
        "key_information": "Contract value: $50,000; Duration: 12 months; Payment terms: Net 30; Termination notice: 60 days",
        "relevance_to_case": "This contract demonstrates the agreed-upon terms that were allegedly breached by the defendant, forming the basis of our breach of contract claim.",
        "legal_significance": "Contains specific performance obligations and damages provisions that support our client's position.",
        "citations": [
            {
                "page_number": 3,
                "text": "Payment shall be made within thirty (30) days of invoice receipt",
                "context": "Payment Terms Section",
                "significance": "Establishes clear payment obligation that was allegedly breached"
            },
            {
                "page_number": 7,
                "text": "Either party may terminate this agreement with sixty (60) days written notice",
                "context": "Termination Clause",
                "significance": "Shows proper termination procedures were not followed"
            }
        ]
    }
    
    # Sample video insight
    test_video = {
        "file_name": "security_camera_footage.mp4",
        "transcript": "Security camera footage showing the incident at 2:30 PM on March 15th.",
        "labels": ["person", "vehicle", "building"],
        "objects": ["sedan", "traffic_light", "pedestrian"],
        "text_annotations": ["STOP", "LICENSE PLATE: ABC123"],
        "insights": {
            "events": [
                {
                    "timestamp": "2:30:15",
                    "description": "Vehicle enters frame from left side",
                    "relevance": "Shows defendant vehicle approaching intersection"
                },
                {
                    "timestamp": "2:30:22",
                    "description": "Collision occurs at intersection",
                    "relevance": "Moment of impact captured on video"
                }
            ]
        },
        "duration": 45.2
    }
    
    # Sample case timeline
    test_timeline = [
        {
            "date": "2024-03-15",
            "event": "Initial incident occurred",
            "source": "Police_Report.pdf"
        },
        {
            "date": "2024-03-16",
            "event": "Client sought medical attention",
            "source": "Medical_Records.pdf"
        }
    ]
    
    # Mock analysis object
    class MockAnalysis:
        def __init__(self):
            self.analyzed_documents = [test_document]
            self.video_insights = [test_video]
    
    return {
        "results": {
            "case_timeline": test_timeline,
            "analysis": MockAnalysis(),
            "format_video_analysis": lambda video: f"<p>Video analysis: {video.get('file_name', 'Unknown')}</p>"
        }
    }

def test_template_rendering():
    """Test the document appendix template with our test data."""
    
    print("🧪 Testing Document Appendix Template...")
    
    # Locate template directory
    template_dir = Path("backend/assets/templates")
    if not template_dir.exists():
        print("❌ Template directory not found!")
        return False
    
    # Set up Jinja2 environment
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template("document_appendix.jinja2")
        print("✅ Template loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load template: {e}")
        return False
    
    # Get test data
    test_data = create_test_data()
    
    try:
        # Render template
        rendered_html = template.render(**test_data)
        print("✅ Template rendered successfully")
        
        # Basic validation checks
        validation_passed = True
        
        # Check 1: Ensure citations are rendered
        if "Document Citations" in rendered_html:
            print("✅ Citations section is present")
        else:
            print("❌ Citations section is missing")
            validation_passed = False
        
        # Check 2: Ensure no character-by-character iteration
        if "<li>T</li><li>h</li><li>e</li>" not in rendered_html:
            print("✅ No character iteration detected")
        else:
            print("❌ Character iteration bug still present")
            validation_passed = False
        
        # Check 3: Ensure proper list rendering
        if "Page 3" in rendered_html and "Page 7" in rendered_html:
            print("✅ Citation page numbers rendered correctly")
        else:
            print("❌ Citation page numbers not rendered properly")
            validation_passed = False
        
        # Check 4: Ensure video evidence section works
        if "Video Evidence Analysis" in rendered_html:
            print("✅ Video evidence section rendered")
        else:
            print("ℹ️  No video evidence section (this is okay if no video data)")
        
        # Save rendered output for inspection
        output_dir = Path("validation_output")
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / "test_appendix_output.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(rendered_html)
        
        print(f"✅ Test output saved to: {output_file}")
        
        if validation_passed:
            print("🎉 All validation checks passed!")
            return True
        print("⚠️  Some validation checks failed. Check the output for details.")
        return False
            
    except Exception as e:
        print(f"❌ Template rendering failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("=" * 60)
    print("🔧 Document Appendix Template Validation Test")
    print("=" * 60)
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")
    
    success = test_template_rendering()
    
    print("")
    print("=" * 60)
    if success:
        print("✅ TEMPLATE VALIDATION SUCCESSFUL")
        print("The document appendix template fixes are working correctly.")
    else:
        print("❌ TEMPLATE VALIDATION FAILED")
        print("Please review the output and fix any remaining issues.")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
