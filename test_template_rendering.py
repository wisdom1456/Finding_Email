#!/usr/bin/env python3
"""
Test script to verify the Jinja2 template changes for findings_email and document_appendix
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Mock data structures to test template rendering
class MockAnalysis:
    def __init__(self):
        self.client_name = "John Doe"
        self.attorney_name = "Attorney Smith"


class MockDocument:
    def __init__(self):
        self.filename = "contract.pdf"
        self.document_type = "Contract"
        self.inferred_title = "Service Agreement Contract"
        self.summary = "This is a comprehensive service agreement between the parties."
        self.key_information = (
            "Payment terms, scope of work, and termination clauses are clearly defined."
        )
        self.relevance_to_case = "Critical document establishing the contractual relationship and obligations."
        self.legal_significance = (
            "Provides the foundation for breach of contract claims."
        )


class MockVideoInsight:
    def __init__(self):
        self.file_name = "evidence_video.mov"
        self.transcript = "This is a sample video transcript."
        self.labels = ["conversation", "office", "meeting"]
        self.objects = ["desk", "computer", "documents"]
        self.text_annotations = ["Contract #12345", "Page 1 of 5"]
        self.duration = 120.5
        self.confidence = 0.85
        self.is_criminal_case = False
        self.insights = {
            "summary": "Video shows a business meeting discussing contract terms.",
            "events": [
                {
                    "timestamp": "00:00:15",
                    "description": "Meeting participants introduce themselves",
                    "relevance": "Establishes the parties involved in contract negotiations",
                },
                {
                    "timestamp": "00:01:30",
                    "description": "Discussion of payment terms begins",
                    "relevance": "Critical evidence for payment dispute resolution",
                },
            ],
            "case_relevance": "Provides direct evidence of contract negotiations and agreed terms.",
        }


class MockCriminalVideoInsight:
    def __init__(self):
        self.file_name = "arrest_video.mov"
        self.transcript = "Officer: You have the right to remain silent..."
        self.labels = ["police", "arrest", "traffic stop"]
        self.objects = ["police car", "handcuffs", "badge"]
        self.text_annotations = ["POLICE", "Badge #1234"]
        self.duration = 300.0
        self.confidence = 0.92
        self.is_criminal_case = True
        self.criminal_analysis = {
            "timeline_summary": "Video captures a DUI arrest sequence from initial contact through booking.",
            "evidence_categories": [
                {
                    "category_number": 1,
                    "category": "Initial Contact",
                    "evidence_found": True,
                    "timestamp": "00:00:30",
                    "description": "Officer approaches vehicle and makes initial contact with suspect.",
                    "strength": "strong",
                    "legal_significance": "Establishes reasonable suspicion for the traffic stop.",
                    "constitutional_implications": "4th Amendment compliance - lawful initial contact",
                },
                {
                    "category_number": 2,
                    "category": "Miranda Rights",
                    "evidence_found": True,
                    "timestamp": "00:02:15",
                    "description": "Officer reads Miranda rights before custodial interrogation.",
                    "strength": "strong",
                    "legal_significance": "Critical for admissibility of subsequent statements.",
                    "constitutional_implications": "5th Amendment compliance - proper Miranda advisement",
                },
            ],
            "constitutional_issues": {
                "4th_amendment": "Traffic stop appears lawful with reasonable suspicion",
                "5th_amendment": "Miranda rights properly administered before questioning",
                "6th_amendment": "Right to counsel mentioned during Miranda advisement",
            },
            "missing_categories": ["Breath Test", "Field Sobriety Tests"],
        }
        self.insights = {
            "summary": "Arrest video showing DUI stop procedures.",
            "case_relevance": "Primary evidence for constitutional compliance assessment.",
        }


class MockAnalysisResult:
    def __init__(self):
        self.intake_analysis = MockAnalysis()
        self.analyzed_documents = [MockDocument()]
        self.video_insights = [MockVideoInsight(), MockCriminalVideoInsight()]


class MockGeneratedLetter:
    def __init__(self):
        self.background_summary = "<p>Based on our review of your case materials...</p>"
        self.analysis_and_position = (
            "<p>Our legal analysis reveals several key issues...</p>"
        )
        self.strengths = (
            "<ul><li>Strong documentary evidence</li><li>Clear contract terms</li></ul>"
        )
        self.challenges = "<ul><li>Potential statute of limitations issues</li></ul>"
        self.recommendations = "<ul><li>Proceed with formal demand letter</li><li>Gather additional evidence</li></ul>"
        self.next_steps = "<ul><li>Schedule follow-up meeting</li><li>Review settlement options</li></ul>"
        self.closing_paragraph = (
            "<p>We remain committed to achieving the best outcome for your case.</p>"
        )


class MockTimelineEvent:
    def __init__(self, date, source, event):
        self.date = date
        self.source = source
        self.event = event


def mock_format_video_analysis(video_insight):
    """Mock function to format video analysis for testing"""
    return f"<p>Mock video analysis for {video_insight.file_name}</p>"


def test_template_rendering():
    """Test both templates with mock data"""

    # Setup Jinja2 environment
    template_dir = os.path.join(os.getcwd(), "backend", "assets", "templates")
    if not os.path.exists(template_dir):
logger.info(f'❌ Template directory not found: {template_dir}')
        return False

    jinja_env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # Create mock data
    mock_analysis = MockAnalysisResult()
    mock_generated_letter = MockGeneratedLetter()
    mock_case_timeline = [
        MockTimelineEvent(
            "2023-01-15", "Contract Document", "Service agreement signed"
        ),
        MockTimelineEvent("2023-02-01", "Email Communication", "First payment made"),
        MockTimelineEvent(
            "2023-03-15", "Client Statement", "Service quality issues reported"
        ),
    ]

    template_context = {
        "analysis": mock_analysis,
        "generated_letter": mock_generated_letter,
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "case_timeline": mock_case_timeline,
        "format_video_analysis": mock_format_video_analysis,
    }

    try:
        # Test findings_email template
logger.info('🧪 Testing findings_email.jinja2...')
        main_template = jinja_env.get_template("findings_email.jinja2")
        main_html = main_template.render(
            results=template_context, current_date=template_context["current_date"]
        )

        # Basic validation checks
        if "Legal Analysis" in main_html:
logger.info('✅ Legal Analysis section found')
        else:
logger.info('❌ Legal Analysis section missing')

        if "Document Analysis" in main_html:
logger.info('✅ Document Analysis section found')
        else:
logger.info('❌ Document Analysis section missing')

        if "Video Evidence Analysis" in main_html:
logger.info('✅ Video Evidence Analysis section found')
        else:
logger.info('❌ Video Evidence Analysis section missing')

        if "Case Timeline" not in main_html:
logger.info('✅ Case Timeline correctly removed from main template')
        else:
logger.info('❌ Case Timeline still present in main template')

        # Check for timestamped events
        if "00:00:15" in main_html and "00:01:30" in main_html:
logger.info('✅ Timestamped events found in video analysis')
        else:
logger.info('❌ Timestamped events missing from video analysis')

        # Check for criminal analysis
        if "Miranda Rights" in main_html:
logger.info('✅ Criminal analysis found')
        else:
logger.info('❌ Criminal analysis missing')

        # Test document_appendix template
logger.info('\n🧪 Testing document_appendix.jinja2...')
        appendix_template = jinja_env.get_template("document_appendix.jinja2")
        appendix_html = appendix_template.render(
            results=template_context, current_date=template_context["current_date"]
        )

        # Basic validation checks for appendix
        if "Case Timeline" in appendix_html:
logger.info('✅ Case Timeline section found in appendix')
        else:
logger.info('❌ Case Timeline section missing from appendix')

        if "Service agreement signed" in appendix_html:
logger.info('✅ Timeline events found in appendix')
        else:
logger.info('❌ Timeline events missing from appendix')

        if (
            "Comprehensive Video Analysis" in appendix_html
            or "Criminal Law Evidence Analysis" in appendix_html
        ):
logger.info('✅ Enhanced video analysis found in appendix')
        else:
logger.info('❌ Enhanced video analysis missing from appendix')

        if "Constitutional Compliance" in appendix_html:
logger.info('✅ Constitutional analysis found in appendix')
        else:
logger.info('❌ Constitutional analysis missing from appendix')

        # Write test output files for manual inspection
        with open("test_main_letter.html", "w") as f:
            f.write(main_html)
logger.info('\n📄 Main letter test output written to: test_main_letter.html')

        with open("test_appendix.html", "w") as f:
            f.write(appendix_html)
logger.info('📄 Appendix test output written to: test_appendix.html')

logger.info('\n✅ Template rendering test completed successfully!')
        return True

    except Exception as e:
logger.error(f'❌ Template rendering failed: {e}')
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_template_rendering()
    sys.exit(0 if success else 1)
