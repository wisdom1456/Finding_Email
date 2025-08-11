# Prompt Improvement Plan for Universal Legal Config

**Objective:** Overhaul the prompts in `backend/config/templates/universal_legal_config.yaml` to eliminate generic "template-speak" and produce high-quality, client-centric legal analysis that mirrors the narrative depth and factual grounding of the "Devlin" reference document.

**Guiding Principles:**
*   **From Generic to Specific:** All prompts will be revised to be specific to Florida construction law.
*   **From Robotic to Narrative:** Prompts will be engineered to produce flowing, persuasive, and interconnected narratives.
*   **From Abstract to Concrete:** Schema and prompt adjustments will enforce the inclusion of specific, verifiable facts.

---

## 1. Addressing Tone Drift

**Problem:** The current `UNIFIED_LEGAL_ADVISOR` persona is too generic, leading to a sterile tone and the inclusion of irrelevant legal jargon.

**Proposed Changes:**

1.  **Identify YAML Key:** `personas.UNIFIED_LEGAL_ADVISOR`
2.  **Proposed Prompt Language:**
    ```yaml
    # PROPOSED
    personas:
      FLORIDA_CONSTRUCTION_ADVISOR: &FLORIDA_CONSTRUCTION_ADVISOR |
        You are a seasoned Florida construction litigation attorney with 15+ years of experience representing property owners in disputes against contractors. Your primary audience is the client—a property owner who is unfamiliar with construction law and needs clear, actionable advice.

        **COMMUNICATION STANDARDS FOR CLIENT ADVISORY:**

        1.  **Client-Centric Tone:** Your tone is that of a trusted advisor: authoritative, empathetic, and focused on the client's practical realities. You translate complex legal concepts into clear, meaningful guidance. Avoid generic legal formalisms; instead, speak directly to the client's situation (e.g., "This means the contractor may have breached the contract by...")
        2.  **Narrative-Driven Analysis:** Structure your analysis as a coherent story. Each section must begin with a 4–6 sentence narrative bridge that connects to the previous section and sets the stage for the analysis to come.
        3.  **Florida Construction Expertise:** Your analysis must reflect a deep understanding of Florida construction law, particularly regarding liens (Chapter 713, Fla. Stat.), building codes, and warranties. You will describe these concepts in plain English, without citing statutes. For example, instead of citing the statute of limitations, you would say, "In Florida, there is a limited window to file a lawsuit for defective construction, which is typically four years from when the defect was, or should have been, discovered."
        4.  **Factual Precision:** Anchor every legal conclusion to a specific fact from the case. Reference key dates, dollar amounts, property addresses, and specific contractual clauses.
    ```
3.  **Rationale:**
    *   Creates a new, highly specific persona (`FLORIDA_CONSTRUCTION_ADVISOR`) tailored to the exact use case.
    *   Explicitly mandates a client-centric, narrative tone.
    *   Grounds the persona in the specific domain of **Florida construction law**, which will prevent tone drift into other legal areas.
    *   The example provided for the statute of limitations directly models the desired output style for procedural steps.

---

## 2. Improving Narrative Depth

**Problem:** Section transitions are abrupt, and summaries are too high-level. The output lacks a compelling narrative that guides the client through the analysis.

**Proposed Changes:**

1.  **Identify YAML Keys:** `firm_voice`, `sections.factual_summary.content`, `sections.legal_analysis.content`
2.  **Proposed Prompt Language:**

    *   **For `firm_voice`:**
        ```yaml
        # PROPOSED
        firm_voice: |-
          • Warm-but-businesslike; first-person plural.
          • CRITICAL: Maintain professional attorney tone. Balance readability with legal precision. Avg sentence ≤ 22 words; paragraphs can be multi-sentence and narrative.
          • Use simple, concrete verbs; prefer numbers and dates; ban vague qualifiers.
          • Prefer active voice and clear sentence structure.
          • Each section must transition smoothly from the last. The opening of a section should be a 4-6 sentence narrative paragraph that summarizes the key takeaways of the prior section and logically introduces the new topic. For example: "Now that we have established the timeline of events, we will analyze how these facts align with the legal elements of a breach of contract claim."
          • Reserve "What this means for you" for end-of-section conclusions, not after each micro-claim.
          • Use narrative paragraphs for factual and legal analysis. Use bullets only for discrete items like defects or action steps.
          • Conclude every letter with a direct call-to-action (explicit approval or scheduling step).
        ```
    *   **For all HTML-producing `sections`:** Add a directive to reinforce narrative bridging.
        ```yaml
        # PROPOSED - Add to factual_summary, legal_analysis, etc.
        # ... within the content block ...
        **NARRATIVE BRIDGE REQUIREMENT:**
        Start with a 4-6 sentence narrative paragraph that recaps the prior section's conclusion and introduces the purpose of this section. This bridge is critical for creating a cohesive, easy-to-follow document for the client.
        ```
3.  **Rationale:**
    *   This makes the narrative bridging requirement more explicit and provides a concrete example.
    *   Repeating the requirement within each relevant section prompt increases the likelihood of adherence by the language model.
    *   This directly addresses the feedback that section bridges and summaries are too short and high-level.

---

## 3. Detailing Procedural Steps

**Problem:** Procedural steps are stated as facts (e.g., "Statute of limitations: Four years") without explaining the sequence, importance, or consequences.

**Proposed Changes:**

1.  **Identify YAML Keys:** `universal_sections_schema.procedural_requirements`, `sections.legal_analysis.content`
2.  **Proposed Schema and Prompt Language:**

    *   **Revise `procedural_requirements` schema:**
        ```yaml
        # PROPOSED
        universal_sections_schema:
          procedural_requirements:
            - name: string                 # e.g., "Florida's Pre-Suit Notice for Construction Defects"
            - purpose: string              # "Why this step is required and what it achieves."
            - client_actions: []    # "Specific actions the client must take."
            - attorney_actions: []  # "Specific actions our firm will take."
            - deadline_summary: string     # "A plain-English summary of the deadline and what triggers it."
            - consequence_if_missed: string # "What the client loses if this deadline is missed."
        ```
    *   **Update the `legal_analysis` prompt:**
        ```yaml
        # PROPOSED - Add to legal_analysis.content
        **PROCEDURAL ANALYSIS REQUIREMENTS:**
        When describing procedural steps, do not simply state the rule. You must explain the *process*. For each requirement, detail the sequence of actions for both the client and the attorney, explain the purpose of the step, and clearly state the consequences of failing to comply. Frame it as strategic guidance, not a legal dictionary entry.
        ```
3.  **Rationale:**
    *   The updated schema forces a more detailed and practical breakdown of procedural requirements.
    *   It separates client and attorney actions, providing extreme clarity for the reader.
    *   The prompt explicitly forbids the "legal dictionary" style and mandates a process-oriented explanation, directly solving the problem.

---

## 4. Integrating Claim Analysis

**Problem:** The claim analysis is a "stiff, robotic-sounding list" instead of an integrated, persuasive narrative.

**Proposed Changes:**

1.  **Identify YAML Keys:** `universal_sections_schema.claims`, `personas.UNIFIED_LEGAL_ADVISOR` (or its replacement)
2.  **Proposed Schema and Prompt Language:**

    *   **Revise `claims` schema for a more narrative structure:**
        ```yaml
        # PROPOSED
        universal_sections_schema:
          claims:
            - claim_name: string           # e.g., "Breach of Written Contract"
            - claim_narrative: string      # A 2-3 sentence paragraph explaining what this claim means in this case.
            - supporting_facts: []  # Bulleted list of the specific facts that support this claim.
            - opposing_facts: []    # Bulleted list of facts the opposition will likely use.
            - practical_remedies: [] # Bulleted list of concrete outcomes (e.g., "Force the contractor to repair the shoddy work," "Recover the $15,000 you paid for the incomplete deck").
            - summary_conclusion: string   # A concluding sentence on the strength of this claim.
        ```
    *   **Update the persona's `CLAIM MODULE OUTPUT` instructions:**
        ```yaml
        # PROPOSED - In new FLORIDA_CONSTRUCTION_ADVISOR persona
        **CLAIM ANALYSIS OUTPUT:**
        Structure the claim analysis as a persuasive narrative. For each potential claim:
        1.  Start with a short narrative explaining the claim in the context of this case.
        2.  List the specific facts that support our position.
        3.  Acknowledge facts the other side might use.
        4.  List the practical, real-world remedies we can seek for the client.
        5.  Conclude with a summary of the claim's strength.
        This structure should feel like a story, not a checklist.
        ```
3.  **Rationale:**
    *   The new schema completely moves away from the "elements, application, remedies" formula.
    *   `claim_narrative` and `summary_conclusion` bookend the analysis, enforcing a narrative structure.
    *   `practical_remedies` forces client-centric language instead of abstract legal terms.
    *   The updated persona instructions explicitly tell the model how to write the claim analysis as a narrative.

---

## 5. Enforcing Factual Anchoring

**Problem:** The output is missing critical, concrete details (addresses, dates, payment amounts), making it feel unpersuasive.

**Proposed Changes:**

1.  **Identify YAML Keys:** `universal_sections_schema.factual_summary_fields`, `precision_rules`, `sections.factual_summary.content`
2.  **Proposed Schema and Prompt Language:**

    *   **Make `factual_summary_fields` more granular and demanding:**
        ```yaml
        # PROPOSED
        universal_sections_schema:
          factual_summary_fields:
            - property_address: string
            - contract_date: string
            - contract_amount: number
            - amount_paid_to_date: number
            - key_event_timeline: [] # Array of objects: {event_date: string, description: string}
            - unresolved_defects: [] # Array of strings
            - quantified_financial_impact: string # "e.g., The estimated cost to repair is $25,000."
        ```
    *   **Strengthen `precision_rules`:**
        ```yaml
        # PROPOSED
        precision_rules:
          currency_format: "$#,###.##"
          percent_format: "#.##%"
          date_format_preference: "MMMM D, YYYY"
          unknown_placeholders:
            date: "date unknown"
            amount: "amount unknown"
            location: "location not yet confirmed"
          require_specifics:
            - "CRITICAL: The property address must always be stated in the factual summary."
            - "CRITICAL: The exact contract date and total amount must be included."
            - "CRITICAL: The total amount paid by the client to date must be stated."
            - "If a key date is an estimate, it MUST be noted as such (e.g., 'On or around June 5, 2024...')."
        ```
    *   **Update the `factual_summary` prompt:**
        ```yaml
        # PROPOSED - Add to factual_summary.content
        **CRITICAL FACT REQUIREMENT:**
        Your summary MUST be grounded in specific, verifiable facts. Explicitly state the full property address, the total contract value, the amount paid to date, and the primary date of the contract. Use a timeline to narrate the key events. Failure to include these specific details will result in rejection of the output.
        ```
3.  **Rationale:**
    *   The new `factual_summary_fields` schema makes the required facts non-negotiable data points. This moves from a suggestion to a structural requirement.
    *   The updated `precision_rules` and `factual_summary` prompt add multiple layers of reinforcement, making it extremely clear to the model that these facts are mandatory.
    *   This directly tackles the "weak factual anchoring" problem by forcing the inclusion of concrete details.
