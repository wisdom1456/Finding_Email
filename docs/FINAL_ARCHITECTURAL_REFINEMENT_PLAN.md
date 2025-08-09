# Final Architectural Refinement Plan

## 1. Introduction

The current legal analysis generation process has shown critical failures in both legal element accuracy and narrative depth. The model's tendency to hallucinate incorrect legal elements and its failure to produce sufficiently detailed narrative bridges makes the output unreliable and unsuitable for client-facing documents.

This document outlines a new architecture that shifts from an inference-based model to a deterministic, configuration-driven approach. By hard-coding legal elements into the system's configuration, we can eliminate the risk of hallucination and enforce a consistent, accurate structure.

## 2. Redesign of the `claims` Schema

### 2.1. Problem Identification

The root of the issue lies in the `universal_sections_schema.claims` key in [`backend/config/templates/universal_legal_config.yaml`](backend/config/templates/universal_legal_config.yaml:0). The current schema relies on the model to infer and apply the correct legal elements, which has proven to be unreliable.

### 2.2. Proposed New Schema

To resolve this, we will introduce a new `claim_definitions` section in the YAML configuration. This will serve as the single source of truth for legal elements for various case types. The `claims` section will then reference these definitions.

```yaml
claim_definitions:
  florida_construction_breach_of_contract:
    - "The existence of a valid contract."
    - "A material breach of the contract (e.g., defective work, non-payment)."
    - "Resulting damages (e.g., cost to repair, diminished value)."
  florida_landlord_tenant_eviction:
    - "The existence of a valid lease agreement."
    - "A material breach of the lease by the tenant (e.g., non-payment of rent, violation of terms)."
    - "Proper notice of eviction provided to the tenant as required by Florida law."
    - "Resulting damages, such as unpaid rent or costs of eviction."

claims:
  - claim_type: florida_construction_breach_of_contract # This key would be used to pull the predefined elements
    application_narrative: # Model generates this
    remedies: [] # Model generates this
    client_risks: # Model generates this
```

### 2.3. Rationale

This new architecture offers several key advantages:

*   **Deterministic and Verifiable:** By defining legal elements in a configuration file, we move from an unreliable inference-based system to one that is deterministic and easily verifiable.
*   **Eliminates Hallucination:** The risk of the model inventing incorrect legal elements is completely eliminated.
*   **Scalability and Maintenance:** Adding new claim types or updating existing ones becomes a simple matter of editing the YAML file, without needing to retrain or extensively re-prompt the model.

## 3. Revision of the `legal_analysis` Prompt

### 3.1. Problem Identification

The current prompt for `sections.legal_analysis.content` does not adequately constrain the model to focus on applying the facts to the correct legal elements.

### 3.2. Proposed Prompt Revision

The prompt will be rewritten to explicitly instruct the model to use the predefined legal elements provided from the new `claim_definitions` section. The model's primary task will be to generate the `application_narrative`, which connects the case-specific facts to these predefined elements.

**Revised Prompt Example:**

```
Given the following predefined legal elements for the claim of '{{ claim_type }}':
{% for element in claim_definitions[claim_type] %}
- {{ element }}
{% endfor %}

Your task is to generate a detailed 'application_narrative' that connects the facts of the case to each of these legal elements. For each element, explain how the facts support or fail to support it. The narrative should be clear, concise, and written for a client's understanding.
```

## 4. Forcing Narrative Depth with Chain-of-Thought

### 4.1. Problem Identification

The model consistently fails to generate the required 4-6 sentence narrative bridges between sections, resulting in abrupt transitions and a lack of depth.

### 4.2. Proposed `Chain-of-Thought` Prompting Strategy

To address this, we will implement a `Chain-of-Thought` strategy in the prompts for all HTML-producing sections. This will force the model to think through the structure and purpose of the narrative bridge before generating it.

**Prompt Addon Example:**

```
**NARRATIVE BRIDGE REQUIREMENT:**
1.  **Think Step-by-Step:**
    *   Identify the concluding point of the previous section.
    *   Identify the main purpose of this section.
    *   Draft a 4-6 sentence paragraph that smoothly transitions from the first point to the second, providing context and explaining the purpose of the analysis to the client.
2.  **Write the bridge:** Output the paragraph you drafted.
```

### 4.3. Rationale

By forcing the model to first "think" about the narrative bridge in a structured manner, we make it more likely that it will adhere to the specified length and depth requirements. This explicit instruction reduces the cognitive load on the model and guides it toward the desired output.