#!/usr/bin/env python3

import json
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend_logic.email_generator import EmailGeneratorV2
from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
from backend_logic.config import get_openai_config, get_openai_api_key
from openai import OpenAI

def create_simple_test_case():
    """Create a simple test case for debugging."""
    intake_analysis = EnhancedIntakeAnalysis(
        client_name="Test Client",
        attorney_name="Test Attorney",
        case_summary="Test case summary",
        case_type="Contract Dispute",
        urgency_level="Standard",
        key_facts=["Fact 1", "Fact 2"],
        legal_claims=["Breach of contract"],
        financial_impact="$10,000"
    )
    
    analysis = CaseAnalysisResult(
        intake_analysis=intake_analysis,
        analyzed_documents=[],
        video_insights=[],
        transcripted_media=[],
        legal_assessment=None,
        demand_letter_evaluation=None
    )
    
    return analysis

def main():
    print("🔬 Debug Template Rendering")
    print("=" * 50)
    
    try:
        # Initialize email generator
        api_key = get_openai_api_key()
        client = OpenAI(api_key=api_key)
        generator = EmailGeneratorV2(client)
        
        # Create test case
        analysis = create_simple_test_case()
        
        print("📋 Generating email with JSON data...")
        
        # Generate structured JSON data
        json_data = generator._generate_structured_json(analysis)
        validated_json = generator._validate_json_response(json_data)
        
        print(f"✅ JSON generated with keys: {list(validated_json.keys())}")
        
        # Check if generated_letter section has content
        generated_letter = validated_json.get('generated_letter', {})
        print(f"📄 Generated letter sections: {list(generated_letter.keys())}")
        
        for section_name, content in generated_letter.items():
            print(f"  - {section_name}: {len(content)} chars")
            if content:
                print(f"    Preview: {content[:100]}...")
            
        # Test template rendering
        print("\n🎨 Testing template rendering...")
        docs = generator.generate_email_and_analysis_docs(analysis)
        
        print(f"📊 Generated documents: {list(docs.keys())}")
        main_content = docs.get('main_letter', '')
        
        print(f"📝 Main letter length: {len(main_content)} chars")
        
        # Save debug output
        with open('debug_template_output.html', 'w') as f:
            f.write(main_content)
        print("💾 Debug output saved to: debug_template_output.html")
        
        # Extract sections using validation harness logic
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(main_content, 'html.parser')
        headers = soup.find_all(['h2', 'h3'])
        
        print(f"\n🔍 Found {len(headers)} headers in rendered template:")
        for i, header in enumerate(headers):
            print(f"  {i+1}. <{header.name}>{header.get_text().strip()}</{header.name}>")
            
        if len(headers) == 0:
            print("❌ No headers found - template may be using legacy format")
            print("🔍 Checking for div.section-title elements:")
            div_sections = soup.find_all('div', class_='section-title')
            for i, div in enumerate(div_sections):
                print(f"  {i+1}. <div class='section-title'>{div.get_text().strip()}</div>")
        else:
            print("✅ Headers found - enhanced template is working")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()