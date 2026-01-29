"""Prompt building functionality for AI analysis components."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from legal_portal.core.data_models import EnhancedIntakeAnalysis, ProcessedDocument


class PromptBuilder:
    """Builds prompts for different AI analysis tasks."""

    def __init__(self, config_manager):
        """Initialize with config manager for prompt templates."""
        self.config_manager = config_manager

    def build_intake_prompt(self, content: str) -> str:
        """Builds the prompt for analyzing an intake form using configuration-driven prompts."""
        # Get prompt from configuration or use fallback
        base_prompt = self.config_manager.get_prompt(
            "intake_analysis",
            # Fallback prompt if configuration is missing
            "You are a seasoned Florida litigation attorney with 15+ years of experience analyzing case documents and extracting legally significant information. Your document analysis supports comprehensive legal findings emails.\n\n"
            "DOCUMENT ANALYSIS EXPERTISE:\n"
            "1. **Legal Relevance Assessment:** Identify information directly relevant to potential legal claims and defenses under Florida law\n"
            "2. **Strategic Document Review:** Extract facts that will be critical for case development, settlement negotiations, or litigation\n"
            "3. **Evidence Identification:** Recognize documentary evidence that supports or undermines legal positions\n"
            "4. **Professional Synthesis:** Organize findings to support detailed attorney analysis and client communication\n"
            "5. **Florida Practice Focus:** Consider how document contents relate to Florida legal standards and procedural requirements\n"
            "6. **Case Development Support:** Structure analysis to facilitate comprehensive legal strategy and client counseling",
        )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`EnhancedIntakeAnalysis` schema below.\n\n"
            "• Do **NOT** wrap the JSON in markdown fences.\n"
            "• Do **NOT** change key names, add keys, or emit commentary.\n"
            "• Write summaries and analysis in clear, accessible language (9th-grade reading level)\n"
            "• Use direct professional language ('you have' rather than 'we have analyzed')\n\n"
            "==========================\n"
            "SOURCE INTAKE FORM (read-only)\n"
            f"{content}\n"
            "==========================\n\n"
            "SCHEMA — EnhancedIntakeAnalysis\n"
            "{\n"
            '  "client_name": "Client Name",\n'
            '  "attorney_name": "Attorney Name",\n'
            '  "case_summary": "Case summary.",\n'
            '  "case_type": "Case Type",\n'
            '  "urgency_level": "Urgency",\n'
            '  "client_priorities": ["Priority 1"],\n'
            '  "desired_outcomes": ["Outcome 1"],\n'
            '  "key_facts": ["Fact 1"],\n'
            '  "parties_involved": [{"name": "Name", "role": "Role"}],\n'
            '  "financial_impact": "Financial impact summary.",\n'
            '  "legal_claims": ["Claim 1"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1. Capture every field—even if absent in the form.\n"
            '   • If data is missing, output an empty string `""` or empty list `[]`.\n'
            "2. `case_summary`: 120–200 words, neutral tone.\n"
            "3. `key_facts`: bullet-style strings ≤25 words each.\n"
            '4. `parties_involved`: each object **must** have `"name"` and `"role"` (e.g., Plaintiff, Contractor).\n'
            "5. Keep every other string ≤40 words.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n"
            "• Key order exactly as in schema.\n\n"
            "BEGIN."
        )

    def build_case_document_prompt(self, doc: ProcessedDocument, ctx: EnhancedIntakeAnalysis) -> str:
        """Builds a context-aware prompt for a case document using configuration-driven prompts."""
        client_priorities_str = (
            ", ".join(ctx.client_priorities) if ctx.client_priorities else "None specified"
        )
        desired_outcomes_str = ", ".join(ctx.desired_outcomes) if ctx.desired_outcomes else "None specified"

        # Get prompt from configuration or use fallback
        base_prompt = self.config_manager.get_prompt(
            "case_document_analysis",
            # Fallback prompt if configuration is missing
            "You are a seasoned Florida litigation attorney with 15+ years of experience analyzing legal documents and extracting case-critical information. Your analysis forms the foundation for professional legal findings emails.\n\n"
            "PROFESSIONAL ANALYSIS STANDARDS:\n"
            "1. **Attorney-Level Precision:** Extract and organize information with the thoroughness expected from an experienced litigator\n"
            "2. **Case-Building Focus:** Identify facts, parties, and circumstances that will be essential for legal strategy and client communication\n"
            "3. **Florida Law Context:** Consider how extracted information relates to Florida legal standards and procedural requirements\n"
            "4. **Professional Documentation:** Structure analysis to support detailed attorney findings emails and case development\n"
            "5. **Client-Ready Foundation:** Organize information for clear presentation to clients while maintaining legal precision\n"
            "6. **Strategic Awareness:** Recognize and prioritize information based on its litigation and settlement value",
        )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            "Return **one—and only one—valid JSON object** that matches the\n"
            "`AnalyzedDocument` schema below.\n\n"
            "• JSON only—no markdown, no extra text.\n"
            "• Preserve key order.\n"
            "• PRIORITIZE analysis elements that directly relate to client's stated priorities and desired outcomes.\n"
            "• Write all content in clear, accessible language (9th-grade reading level)\n"
            "• Use direct professional language addressing the client directly\n\n"
            "==========================\n"
            "DOCUMENT (read-only)\n"
            f"Filename: {doc.file_name}\n"
            f"Content: {doc.content}\n"
            "==========================\n"
            "CLIENT PRIORITIES FOR THIS ANALYSIS:\n"
            f"• Priorities: {client_priorities_str}\n"
            f"• Desired Outcomes: {desired_outcomes_str}\n"
            f"• Case Type: {ctx.case_type or 'Not specified'}\n"
            f"• Urgency Level: {ctx.urgency_level or 'Not specified'}\n"
            "==========================\n"
            "FULL INTAKE CONTEXT\n"
            f"{ctx.model_dump_json(indent=2)}\n"
            "==========================\n\n"
            "SCHEMA — AnalyzedDocument\n"
            "{\n"
            '  "file_name": "The original filename of the document.",\n'
            "  \"document_type\": \"The type of document (e.g., 'Contract', 'Email', 'Image').\",\n"
            '  "inferred_title": "A meaningful, non-repetitive title for the document (less than 15 words).",\n'
            '  "summary": "A concise, value-driven summary of the document\'s content (100-150 words).",\n'
            '  "key_information": "A single consolidated string containing the most critical information. Format as a paragraph, NOT a list. If multiple points exist, separate them with semicolons within the string.",\n'
            '  "relevance_to_case": "A clear explanation of how this document supports or undermines the client\'s position, referencing specific case priorities."\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1.  `file_name`: Must be the exact filename provided.\n"
            "2.  `inferred_title`: Create a meaningful and non-repetitive title. Do not just repeat the filename.\n"
            "3.  `summary`: Must be concise and value-driven, focusing on the most important aspects of the document.\n"
            "4.  `key_information`: Extract the most critical information as a bulleted list string.\n"
            "5.  `relevance_to_case`: Clearly articulate the document's relevance to the overall case strategy and client goals.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• All strings double-quoted.\n\n"
            "BEGIN."
        )

    def build_media_summary_prompt(self, content: dict | str, media_type: str, file_name: str) -> str:
        """Builds prompt for summarizing media content using configuration-driven prompts."""
        # Get prompt from configuration or use fallback
        base_prompt = self.config_manager.get_prompt(
            "media_summarization",
            # Fallback prompt if configuration is missing
            "You are a senior litigation attorney specializing in clear, professional legal communication. Create a concise summary (100-150 words) of the provided media content that will be easily understood by clients without legal training.\n\n"
            "AUTHENTIC_ATTORNEY_ADVISOR PRINCIPLES:\n"
            "• Use clear, accessible language (9th-grade reading level)\n"
            "• Focus on actionable details and key facts\n"
            "• Use direct professional perspective ('the analysis shows,' 'the evidence indicates')\n"
            "• Maintain professional authority while being accessible\n"
            "• Highlight evidence relevant to Florida legal matters",
        )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            f"Provided {media_type} content for {file_name}:\n"
            f"```\n{content if isinstance(content, str) else str(content)}\n```\n\n"
            "Create a clear, client-friendly summary that explains what the evidence shows.\n"
            "BEGIN SUMMARY."
        )

    def build_final_assessment_prompt(
        self,
        analysis_data: str,
        timeline_content: str,
        video_relevance_content: str = "",
    ) -> str:
        """Builds the prompt for the final legal assessment."""
        # Get prompt from configuration or use fallback
        base_prompt = self.config_manager.get_prompt(
            "final_assessment",
            # Fallback prompt if configuration is missing
            "You are a seasoned Florida litigation attorney with 15+ years of experience conducting comprehensive case assessments and providing strategic legal analysis. You are preparing the legal analysis foundation that will support a detailed findings email to your client.\n\n"
            "ATTORNEY ANALYSIS STANDARDS:\n"
            "1. **Professional Legal Authority:** Provide analysis with the depth and expertise expected from a senior litigation attorney\n"
            "2. **Florida Law Mastery:** Reference specific Florida statutes with proper citations (e.g., Florida Statutes § 83.51(1)) and demonstrate deep knowledge of Florida jurisprudence\n"
            "3. **Strategic Legal Assessment:** Evaluate claim viability, evidence strength, and litigation prospects with the judgment of an experienced practitioner\n"
            "4. **Client-Focused Analysis:** Structure findings to support clear, authoritative client communication while maintaining legal precision\n"
            "5. **Professional Objectivity:** Provide balanced assessment of strengths and challenges based on Florida law and litigation realities\n"
            "6. **Case Development Strategy:** Consider both immediate legal remedies and long-term strategic options under Florida law\n\n"
            "PROFESSIONAL ASSESSMENT PROTOCOL: When addressing complex or counterintuitive legal strategies:\n"
            '• **Professional Context:** "Based on my experience with Florida [relevant area] law..."\n'
            "• **Legal Foundation:** Cite specific Florida statutes, case law, or procedural requirements\n"
            "• **Strategic Rationale:** Explain the legal and practical reasoning behind the recommendation\n"
            "• **Risk Assessment:** Address potential outcomes and strategic considerations\n"
            '• **Professional Guidance:** "This analysis reflects Florida law standards and litigation experience"\n\n'
            "CRITICAL: Reference ONLY Florida statutes, case law, and legal precedents (e.g., Florida Statutes § 83.51(1), Florida case citations). Do NOT cite laws from other jurisdictions unless they have specific relevance to Florida legal standards.",
        )

        return (
            "SYSTEM\n"
            f"{base_prompt}\n\n"
            'Output a single JSON object with exactly two top-level keys: `"legal_assessment"` and `"demand_letter_evaluation"`—nothing else.\n\n'
            "• JSON only—no markdown, no commentary.\n"
            "• Do not alter key names.\n\n"
            "==========================\n"
            "AUTHENTIC_ATTORNEY_ADVISOR EXAMPLE LETTER STYLE:\n\n"
            "Dear Mr. Price:\n\n"
            "We hope you are doing well. We wanted to follow up with a summary of our findings after completing our comprehensive review of the timeline and materials you submitted regarding the property located at 2260 Terra Cotta Cove, Apt. 110, Land O Lakes, Florida 34639, including the lease agreement, correspondence, invoices, videos and maintenance-related documentation.\n\n"
            "As we discussed, your primary concern centers on the prolonged and recurring water intrusion, inadequate remediation efforts, and the resulting conditions that have potentially rendered the unit uninhabitable. The timeline you provided documents multiple reports of water damage and potential mold spanning several months, which we have carefully analyzed under Florida law.\n\n"
            "You advised that you moved into the unit on or about August 1, 2024, and within days began experiencing issues involving water intrusion in the bedroom after rainfall. Maintenance initially attributed the flooding to improper grading and dug a temporary trench, but subsequent rains continued to result in pooling, wall saturation, and elevated moisture levels.\n\n"
            "Over the following months, including September and October 2024, water continued to enter the unit. You explained that you submitted multiple maintenance requests and had professional services, such as ServPro, document unsafe moisture levels which could lead to mold development. You relayed that, despite ongoing communication and photographic evidence, the property management team delayed effective repairs, with contractors often failing to complete the necessary work or denying the severity of the problem.\n\n"
            "Here are the key points of our analysis under Florida law:\n\n"
            "• We believe the recurring water intrusion and subsequent mold exposure may rise to the level of a constructive eviction, which under Florida law arises when conditions are so intolerable that the tenant is forced to vacate.\n\n"
            "• Pursuant to Florida Statutes § 83.51(1), landlords are required to maintain rental premises in compliance with building, housing, and health codes, and where no codes apply, in good repair and fit for human habitation.\n\n"
            "• Our analysis of the evidence supports a potential breach of the implied warranty of habitability, as your timeline and third-party reports confirm the unit is likely unsafe and inadequately maintained under Florida standards.\n\n"
            "• Your documented efforts to notify management and allow a reasonable opportunity to cure strengthen your position that the landlord could be in violation of lease agreement under Florida landlord-tenant law.\n\n"
            "At this juncture, we believe the most appropriate course of action is to issue a formal demand letter requesting that the landlord take corrective measures to address the longstanding water intrusion and suspected mold conditions. Specifically, we recommend that you demand the landlord:\n\n"
            "• Regrade the foundational land surrounding the apartment to prevent further flooding and water intrusion into the unit;\n\n"
            "• Retain a licensed mold assessor to conduct a full indoor air quality and mold inspection of the premises, with a written assessment report issued to you promptly; and\n\n"
            "• If the mold assessment confirms the presence of mold, the landlord must retain a licensed mold remediation specialist to perform remediation of all affected areas identified in the assessment report, with all remediation work to be completed no later than fifteen (15) days following the issuance of the mold assessment.\n\n"
            "We believe this approach may lead to a joint resolution that includes mutual waivers and a clear release of future liability.\n\n"
            "Please let us know if you would like us to proceed with a draft of the demand letter, or whether you would prefer that we first set a phone call to discuss our review and recommendations for next steps. For your consideration, we have attached a letter outlining the demand letter process, including a detailed explanation of its purpose and what to anticipate upon issuance.\n\n"
            "We're committed to achieving the best possible outcome for your case.\n\n"
            "Thank you,\n"
            "Chevonne Christian, Esq.\n"
            "Civil Division Attorney\n"
            "==========================\n\n"
            "COMBINED ANALYSIS (read-only)\n"
            f"{analysis_data}\n"
            "==========================\n\n"
            "CASE TIMELINE\n"
            f"{timeline_content}\n"
            "==========================\n\n"
            "VIDEO RELEVANCE ANALYSIS\n"
            f"{video_relevance_content}\n"
            "==========================\n\n"
            "SCHEMAS\n"
            "LegalAssessment:\n"
            "{\n"
            '  "case_type": "Case Type",\n'
            '  "claim_viability": "Claim Viability",\n'
            '  "overall_evidence_strength": "Strength",\n'
            '  "potential_challenges": "A clear description of potential challenges, using bullet points or narrative as appropriate for clarity. Follow the style of the example letter above.",\n'
            '  "recommended_actions": "Recommended next steps, using bullet points or narrative as appropriate for clarity. Follow the style of the example letter above.",\n'
            '  "demand_letter_appropriate": true,\n'
            '  "urgency_assessment": "Urgency"\n'
            "}\n"
            "DemandLetterEvaluation:\n"
            "{\n"
            '  "is_appropriate": true,\n'
            '  "reasoning": "Reasoning in the style of the example letter above",\n'
            '  "potential_outcomes": ["Outcome 1"],\n'
            '  "relevant_statutes": ["Statute 1 - cite only local jurisdiction statutes"]\n'
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1.  **Follow the example letter style exactly.** Your tone should be clear, concise, and professional like a real attorney communicating with a client.\n"
            "2.  **Use simple language** that a non-lawyer can easily understand. Avoid overly academic or verbose language.\n"
            "3.  **Use bullet points** for key findings and recommendations to improve readability, as shown in the example.\n"
            "4.  **Pay attention to jurisdiction** - cite only relevant local statutes (e.g., Florida Statutes § 83.51(1)). Do NOT invent or misapply laws from other states.\n"
            '5.  `claim_viability`: pick "Strong", "Moderate", or "Weak".\n'
            "6.  `demand_letter_appropriate`: true if pre-suit demand adds leverage.\n"
            "7.  If `demand_letter_evaluation.is_appropriate` is **false**, set\n"
            '    `"reasoning": ""`, `"potential_outcomes": []`, `"relevant_statutes": []`.\n'
            "8.  **Timeline Integration**: Consider the chronological timeline of events when assessing case strength and recommended actions.\n"
            "9.  **Video Evidence Integration**: Factor in the video relevance analysis when evaluating evidence strength and case strategy.\n"
            "10. **Write directly and to the point** following the professional but accessible style demonstrated in the example letter.\n\n"
            "VALIDATION\n"
            "• Must parse as JSON.\n"
            "• Floats with two decimals.\n"
            "• Key order per schema.\n\n"
            "BEGIN."
        )
