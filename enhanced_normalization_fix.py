#!/usr/bin/env python3

"""
Enhanced normalization fix that properly preserves HTML structure.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString


def enhanced_normalization_fixes(html_content):
    """
    Enhanced normalization that preserves HTML structure while aggressively fixing issues.
    """
    if not html_content:
        return html_content
    
    try:
        print("🔧 Starting enhanced normalization processing...")
        
        # Parse HTML carefully
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Phase 1: Fix long sentences by working on text nodes only
        for element in soup.find_all(["p", "li", "div"]):
            for text_node in element.find_all(text=True):
                if isinstance(text_node, NavigableString) and text_node.parent.name not in ["script", "style"]:
                    original_text = str(text_node).strip()
                    if len(original_text) > 10:  # Only process meaningful text
                        new_text = break_long_sentences(original_text)
                        if new_text != original_text:
                            text_node.replace_with(new_text)
        
        # Phase 2: Handle repeated phrases at the document level
        # Get all text content and track phrases
        all_text = soup.get_text()
        phrase_replacements = build_phrase_replacement_map(all_text)
        
        # Apply phrase replacements to individual text nodes
        for element in soup.find_all(["p", "li", "div"]):
            for text_node in element.find_all(text=True):
                if isinstance(text_node, NavigableString) and text_node.parent.name not in ["script", "style"]:
                    original_text = str(text_node)
                    new_text = apply_phrase_replacements(original_text, phrase_replacements)
                    if new_text != original_text:
                        text_node.replace_with(new_text)
        
        print("✅ Enhanced normalization processing completed")
        return str(soup)
        
    except Exception as e:
        print(f"❌ Enhanced normalization processing failed: {e}")
        return html_content

def break_long_sentences(text):
    """Break long sentences more aggressively while preserving meaning."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    processed_sentences = []
    
    for sentence in sentences:
        words = sentence.split()
        if len(words) > 15:
            # Try to break at natural points
            broken = break_sentence_at_natural_points(sentence)
            processed_sentences.extend(broken)
        else:
            processed_sentences.append(sentence)
    
    return " ".join(processed_sentences)

def break_sentence_at_natural_points(sentence):
    """Break a sentence at natural linguistic points."""
    words = sentence.split()
    
    # Define break points in order of preference
    break_patterns = [
        (r",\s+(and|but|however|moreover|furthermore|additionally|therefore|thus|consequently)\s+", 2),
        (r";\s+", 1),
        (r",\s+(which|that|where|when|because|since|although|while|if)\s+", 2),
        (r",\s+", 1),
        (r"\s+(and|but|however)\s+", 1),
    ]
    
    for pattern, min_words_before in break_patterns:
        match = re.search(pattern, sentence, re.IGNORECASE)
        if match:
            start, end = match.span()
            before = sentence[:start].strip()
            after = sentence[end:].strip()
            
            # Only break if both parts have enough words
            if len(before.split()) >= min_words_before and len(after.split()) >= min_words_before:
                # Ensure proper punctuation
                if not before.endswith((".", "!", "?")):
                    before += "."
                # Capitalize first word of second part
                if after and after[0].islower():
                    after = after[0].upper() + after[1:]
                
                return [before, after]
    
    # If no natural break point found and sentence is very long, force break at middle
    if len(words) > 20:
        mid_point = len(words) // 2
        # Try to find a good break point near the middle
        for i in range(max(0, mid_point - 3), min(len(words), mid_point + 4)):
            if words[i].endswith(","):
                first_part = " ".join(words[:i+1])[:-1] + "."  # Remove comma, add period
                second_part = " ".join(words[i+1:])
                if second_part and second_part[0].islower():
                    second_part = second_part[0].upper() + second_part[1:]
                return [first_part, second_part]
        
        # Last resort: break at middle
        first_part = " ".join(words[:mid_point]) + "."
        second_part = " ".join(words[mid_point:])
        if second_part and second_part[0].islower():
            second_part = second_part[0].upper() + second_part[1:]
        return [first_part, second_part]
    
    return [sentence]

def build_phrase_replacement_map(text):
    """Build a map of phrases that should be replaced to reduce repetition."""
    words = re.findall(r"\b\w+\b", text.lower())
    phrase_counts = {}
    
    # Count 3-word phrases
    for i in range(len(words) - 2):
        phrase = " ".join(words[i:i+3])
        phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
    
    # Create replacement map for phrases that appear more than 2 times
    replacement_map = {}
    
    # Define specific replacement strategies
    replacement_strategies = {
        "under florida law": ["under applicable law", "under the law", "legally", "by statute"],
        "this matter involves": ["this case involves", "this involves", "the case concerns", "the matter"],
        "legal analysis indicates": ["analysis shows", "analysis reveals", "evidence suggests", "review shows"],
        "recommended next steps": ["next steps", "recommendations", "action items", "proposed actions"],
        "case assessment reveals": ["assessment shows", "evaluation indicates", "review shows", "analysis demonstrates"],
        "evidence review demonstrates": ["evidence shows", "review indicates", "analysis reveals", "documentation shows"],
        "florida statutes provide": ["statutes provide", "law provides", "rules state", "regulations specify"],
        "substantial factual support": ["strong evidence", "solid support", "clear backing", "factual basis"],
        "multiple potential claims": ["several claims", "various claims", "different claims", "additional claims"],
        "comprehensive legal analysis": ["thorough analysis", "detailed review", "complete evaluation", "full assessment"],
    }
    
    for phrase, count in phrase_counts.items():
        if count > 2:
            if phrase in replacement_strategies:
                replacement_map[phrase] = replacement_strategies[phrase]
            else:
                # Generic strategy: create shorter alternatives
                words_in_phrase = phrase.split()
                if len(words_in_phrase) >= 3:
                    # Create alternatives by shortening
                    alternatives = [
                        " ".join(words_in_phrase[:2]),  # First two words
                        words_in_phrase[-1],  # Last word only
                        " ".join(words_in_phrase[1:]),  # Skip first word
                    ]
                    replacement_map[phrase] = alternatives
    
    return replacement_map

def apply_phrase_replacements(text, replacement_map):
    """Apply phrase replacements to text while tracking usage."""
    if not replacement_map:
        return text
    
    # Track how many times we've used each replacement
    if not hasattr(apply_phrase_replacements, "usage_count"):
        apply_phrase_replacements.usage_count = {}
    
    modified_text = text
    
    for phrase, alternatives in replacement_map.items():
        # Count occurrences in this text
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        matches = list(pattern.finditer(modified_text))
        
        # Replace all but the first 2 occurrences
        for i, match in enumerate(matches):
            if i >= 2:  # Keep first 2, replace the rest
                # Choose replacement based on usage count
                usage_key = f"{phrase}_{i}"
                current_usage = apply_phrase_replacements.usage_count.get(phrase, 0)
                replacement = alternatives[current_usage % len(alternatives)]
                apply_phrase_replacements.usage_count[phrase] = current_usage + 1
                
                # Apply replacement
                start, end = match.span()
                modified_text = modified_text[:start] + replacement + modified_text[end:]
                # Update remaining matches
                matches = list(pattern.finditer(modified_text))
    
    return modified_text

# Test the enhanced approach
if __name__ == "__main__":
    test_html = """
    <p>Under Florida law, this matter involves a complex legal analysis that indicates several considerations under Florida law. This matter involves multiple claims that require careful legal analysis under Florida law. Under Florida law, the recommended next steps include detailed case assessment under Florida law.</p>
    <p>The comprehensive legal analysis indicates that this matter involves significant constitutional considerations under Florida law. Legal analysis indicates that the case assessment reveals multiple potential claims. Case assessment reveals that the evidence review demonstrates substantial factual support under Florida law.</p>
    """
    
    print("🧪 Testing enhanced normalization:")
    print("=" * 50)
    
    # Count issues before
    from test_normalization_effectiveness import count_normalization_issues
    dup_before, long_before, repeated_before = count_normalization_issues(test_html)
    print(f"BEFORE: Duplicates: {dup_before}, Long sentences: {long_before}, Repeated phrases: {repeated_before}")
    
    # Apply enhanced normalization
    enhanced_html = enhanced_normalization_fixes(test_html)
    
    # Count issues after
    dup_after, long_after, repeated_after = count_normalization_issues(enhanced_html)
    print(f"AFTER: Duplicates: {dup_after}, Long sentences: {long_after}, Repeated phrases: {repeated_after}")
    
    print("\n📊 IMPROVEMENT:")
    print(f"Duplicates: {dup_before} → {dup_after} ({dup_before - dup_after} improvement)")
    print(f"Long sentences: {long_before} → {long_after} ({long_before - long_after} improvement)")
    print(f"Repeated phrases: {repeated_before} → {repeated_after} ({repeated_before - repeated_after} improvement)")
    
    print("\n📝 ENHANCED OUTPUT:")
    print("=" * 50)
    print(enhanced_html)
