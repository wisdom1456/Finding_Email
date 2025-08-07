#!/usr/bin/env python3
"""
Simple verification that the EmailGenerator can be instantiated without TemplateRuntimeError.
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_email_generator_instantiation():
    """Test that EmailGenerator can be instantiated without the regex_replace filter error."""
    print("🔧 Testing EmailGenerator instantiation...")
    
    try:
        # Mock OpenAI client since we just want to test the filter registration
        class MockOpenAIClient:
            pass
        
        mock_client = MockOpenAIClient()
        
        # Import and instantiate EmailGenerator
        from backend_logic.email_generator import EmailGeneratorV2
        
        # This should NOT raise: jinja2.exceptions.TemplateRuntimeError: No filter named 'regex_replace' found
        generator = EmailGeneratorV2(client=mock_client)
        
        # Verify that the regex_replace filter is registered
        if 'regex_replace' in generator.jinja_env.filters:
            print("✅ SUCCESS: EmailGenerator instantiated successfully!")
            print("✅ SUCCESS: regex_replace filter is registered with Jinja2 environment!")
            return True
        else:
            print("❌ FAIL: regex_replace filter not found in Jinja2 environment")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Error instantiating EmailGenerator: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_template_rendering():
    """Test that a template with regex_replace filter can be rendered without error."""
    print("\n🔧 Testing template rendering with regex_replace filter...")
    
    try:
        from jinja2 import Environment, DictLoader
        from backend_logic.email_generator import regex_replace_filter
        
        # Simple template that uses regex_replace
        template_str = '''{{ text | regex_replace("days", "DAYS") }}'''
        
        env = Environment(loader=DictLoader({'test': template_str}))
        env.filters['regex_replace'] = regex_replace_filter
        
        template = env.get_template('test')
        result = template.render(text="within 14 days")
        
        if result == "within 14 DAYS":
            print("✅ SUCCESS: Template with regex_replace filter rendered correctly!")
            print(f"   Result: '{result}'")
            return True
        else:
            print(f"❌ FAIL: Unexpected result: '{result}'")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Error rendering template: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run verification tests."""
    print("🔧 Verifying regex_replace filter fix...")
    print("=" * 60)
    
    # Test 1: EmailGenerator instantiation
    test1_passed = test_email_generator_instantiation()
    
    # Test 2: Template rendering
    test2_passed = test_template_rendering()
    
    print("\n" + "=" * 60)
    if test1_passed and test2_passed:
        print("🎉 VERIFICATION SUCCESSFUL!")
        print("✅ The TemplateRuntimeError: No filter named 'regex_replace' found is FIXED!")
        print("✅ EmailGenerator can now be instantiated without errors!")
        print("✅ Templates using regex_replace filter will now work correctly!")
    else:
        print("❌ Some verification tests failed. Please check the implementation.")
        
    return test1_passed and test2_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)