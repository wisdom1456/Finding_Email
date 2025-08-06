from __future__ import annotations

import json

from backend.tests.utils.rtf_processor import (
    extract_structured_content,
    normalize_text,
    rtf_to_text,
)
from backend.tests.utils.semantic_analyzer import SemanticAnalyzer


class EmailComparator:
    def __init__(self, reference_email_path, generated_email_content):
        self.reference_email_path = reference_email_path
        self.generated_email_content = generated_email_content
        self.semantic_analyzer = SemanticAnalyzer()
        self.comparison_results = {}

    def _load_and_process_reference_email(self):
        with open(self.reference_email_path, "rb") as f:
            rtf_content = f.read()
        return self._process_email(rtf_content, is_rtf=True)

    def _process_generated_email(self):
        return self._process_email(self.generated_email_content, is_rtf=False)

    def _process_email(self, content, is_rtf=False):
        text = rtf_to_text(content) if is_rtf else content

        normalized_text = normalize_text(text)
        structured_content = extract_structured_content(normalized_text)

        return {
            "raw_text": text,
            "normalized_text": normalized_text,
            "structured_content": structured_content,
        }

    def compare(self):
        ref_email = self._load_and_process_reference_email()
        gen_email = self._process_generated_email()

        self.compare_structure(
            ref_email["structured_content"], gen_email["structured_content"]
        )
        self.compare_substance(
            ref_email["normalized_text"], gen_email["normalized_text"]
        )
        self.compare_style(ref_email["raw_text"], gen_email["raw_text"])
        self.compare_tone(ref_email["normalized_text"], gen_email["normalized_text"])

        return self.comparison_results, gen_email["raw_text"]

    def compare_structure(self, ref_struct, gen_struct):
        ref_keys = set(ref_struct.keys())
        gen_keys = set(gen_struct.keys())

        missing_sections = list(ref_keys - gen_keys)
        extra_sections = list(gen_keys - ref_keys)

        score = 1 - (len(missing_sections) + len(extra_sections)) / len(ref_keys)

        self.comparison_results["structure"] = {
            "score": max(0, score),
            "missing_sections": missing_sections,
            "extra_sections": extra_sections,
        }

    def compare_substance(self, ref_text, gen_text):
        similarity = self.semantic_analyzer.get_semantic_similarity(ref_text, gen_text)
        self.comparison_results["substance"] = {
            "score": similarity,
            "details": "Semantic similarity of the entire email body.",
        }

    def compare_style(self, ref_text, gen_text):
        # Placeholder for style comparison
        # This can be expanded to check formatting, sentence length, etc.
        self.comparison_results["style"] = {
            "score": -1,  # Not implemented
            "details": "Style comparison is not yet implemented.",
        }

    def compare_tone(self, ref_text, gen_text):
        # Placeholder for tone analysis
        ref_tone = self.semantic_analyzer.analyze_tone(ref_text)
        gen_tone = self.semantic_analyzer.analyze_tone(gen_text)

        # A simple comparison logic for tones
        if ref_tone and gen_tone and ref_tone["label"] == gen_tone["label"]:
            score = ref_tone["score"]
        else:
            score = 0

        self.comparison_results["tone"] = {
            "score": score,
            "reference_tone": ref_tone,
            "generated_tone": gen_tone,
        }

    def get_results_as_json(self):
        return json.dumps(self.comparison_results, indent=4)
