# Master JSON Schema for Legal Findings Letter

This document defines the comprehensive JSON schema that will serve as the contract for our new AI-driven, structured data generation architecture. The AI will be instructed to return a single, valid JSON object conforming to this schema.

```json
{
  "title": "Legal Findings Letter",
  "description": "A comprehensive JSON schema for generating a structured legal findings letter.",
  "type": "object",
  "properties": {
    "case_name": {
      "type": "string",
      "description": "The name of the legal case."
    },
    "client_name": {
      "type": "string",
      "description": "The name of the client."
    },
    "greeting_line": {
      "type": "string",
      "description": "The opening salutation for the letter."
    },
    "attorney_signature": {
      "type": "string",
      "description": "The name of the attorney signing the letter."
    },
    "firm_name": {
      "type": "string",
      "description": "The name of the law firm."
    },
    "bridges": {
      "type": "object",
      "description": "Narrative bridges to introduce sections.",
      "properties": {
        "factual_summary": { "type": "string" },
        "legal_analysis": { "type": "string" },
        "next_steps": { "type": "string" }
      }
    },
    "generated_letter": {
      "type": "object",
      "properties": {
        "background_summary": { "type": "string" },
        "analysis_and_position": { "type": "string" },
        "strengths": { "type": "string" },
        "challenges": { "type": "string" }
      }
    },
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "elements": { "type": "array", "items": { "type": "string" } },
          "application": { "type": "string" },
          "remedies": { "type": "array", "items": { "type": "string" } },
          "client_risks": { "type": "string" }
        },
        "required": ["name", "elements", "application", "remedies", "client_risks"]
      }
    },
    "procedural_requirements": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "typical_timeline": { "type": "string" },
          "steps": { "type": "array", "items": { "type": "string" } },
          "consequence_if_ignored": { "type": "string" }
        },
        "required": ["name", "typical_timeline", "steps", "consequence_if_ignored"]
      }
    },
    "third_party_exposure": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "party": { "type": "string" },
          "basis": { "type": "string" },
          "risk": { "type": "string" },
          "mitigation_action": { "type": "string" }
        },
        "required": ["party", "basis", "risk", "mitigation_action"]
      }
    },
    "next_steps": {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "action": { "type": "string" },
              "owner": { "type": "string" },
              "deadline_days_from_trigger": { "type": "integer" },
              "trigger": { "type": "string" },
              "purpose": { "type": "string" },
              "success_criteria": { "type": "string" },
              "consequence_if_missed": { "type": "string" }
            },
            "required": ["action", "owner", "deadline_days_from_trigger", "trigger", "purpose", "success_criteria", "consequence_if_missed"]
          }
        }
      }
    },
    "call_to_action": {
      "type": "string",
      "description": "The final call-to-action for the client."
    }
  },
  "required": [
    "case_name",
    "client_name",
    "greeting_line",
    "attorney_signature",
    "firm_name",
    "bridges",
    "generated_letter",
    "claims",
    "procedural_requirements",
    "third_party_exposure",
    "next_steps",
    "call_to_action"
  ]
}
