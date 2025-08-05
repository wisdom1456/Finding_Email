#!/usr/bin/env python3
"""
Test to verify the Jinja2 template fix for format_video_analysis function access
"""

from jinja2 import Environment, FileSystemLoader
import os

# Mock format_video_analysis function
def mock_format_video_analysis(video_data):
    return f'<p>✅ Video analysis for {video_data.get("file_name", "unknown")} rendered successfully!</p>'

# Mock data structure matching the real application
mock_video_insight = {
    "file_name": "test_criminal_video.mp4",
    "insights": {"summary": "Mock criminal video analysis"},
    "transcript": "Mock transcript",
    "labels": ["evidence", "arrest"],
    "objects": ["officer", "suspect", "vehicle"],
    "text_annotations": ["POLICE", "LICENSE"],
    "duration": 120.5,
    "confidence": 0.95
}

mock_analysis = {
    "video_insights": [mock_video_insight]
}

# Template context exactly as passed in email_generator.py
template_context = {
    'analysis': mock_analysis,
    'generated_letter': {},
    'current_date': '2025-08-05',
    'format_video_analysis': mock_format_video_analysis
}

def test_template_fix():
    """Test that the fixed template renders correctly without errors"""
    
    # Get the template directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(current_dir, 'backend', 'assets', 'templates')
    
    print(f"Template directory: {template_dir}")
    print(f"Template directory exists: {os.path.exists(template_dir)}")
    
    if not os.path.exists(template_dir):
        print("❌ Template directory not found!")
        return False
    
    # Create Jinja2 environment
    try:
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template('document_appendix.jinja2')
        print("✅ Template loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load template: {e}")
        return False
    
    # Test template rendering with the fix
    try:
        result = template.render(results=template_context, current_date=template_context['current_date'])
        print("✅ Template rendered successfully without errors!")
        
        # Check if our mock function output is in the result
        if "Video analysis for test_criminal_video.mp4 rendered successfully!" in result:
            print("✅ Video analysis function was called and executed correctly!")
            return True
        else:
            print("⚠️  Template rendered but video analysis function may not have been called")
            return False
            
    except Exception as e:
        print(f"❌ Template rendering failed: {e}")
        return False

if __name__ == "__main__":
    print("=== TESTING TEMPLATE FIX VERIFICATION ===")
    
    success = test_template_fix()
    
    if success:
        print("\n🎉 SUCCESS: The Jinja2 template error has been resolved!")
        print("   - Template loads without errors")
        print("   - format_video_analysis function is accessible via results.format_video_analysis")
        print("   - Video analysis formatting works correctly")
    else:
        print("\n❌ FAILED: The fix may not have resolved the issue completely")
    
    print("\n=== TEST COMPLETE ===")