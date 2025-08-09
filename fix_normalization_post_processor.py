#!/usr/bin/env python3
"""
Post-processor to fix normalization issues in generated HTML content
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def break_long_sentences(text, max_words=15):
    """Break sentences longer than max_words into shorter ones."""
    sentences = re.split(r"([.!?]+)", text)
    result = []
    
    for i in range(0, len(sentences), 2):
        if i >= len(sentences):
            break
            
        sentence = sentences[i].strip()
        if not sentence:
            continue
            
        punctuation = sentences[i+1] if i+1 < len(sentences) else "."
        
        # Count words
        words = sentence.split()
        if len(words) <= max_words:
            result.append(sentence + punctuation)
        else:
            # Break into chunks
            chunks = []
            current_chunk = []
            
            for word in words:
                current_chunk.append(word)
                if len(current_chunk) >= max_words and word.endswith(","):
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                elif len(current_chunk) >= max_words:
                    # Find a good break point
                    break_point = max_words
                    for j in range(max_words-1, max(0, max_words-5), -1):
                        if j < len(current_chunk) and current_chunk[j] in ["and", "or", "but", "with", "under", "based", "that", "which"]:
                            break_point = j + 1
                            break
                    
                    chunks.append(" ".join(current_chunk[:break_point]))
                    current_chunk = current_chunk[break_point:]
            
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            
            # Add punctuation
            for j, chunk in enumerate(chunks):
                if j == len(chunks) - 1:
                    result.append(chunk + punctuation)
                else:
                    result.append(chunk + ".")
    
    return " ".join(result)

def reduce_repetition(text):
    """Reduce repeated phrases and vary language."""
    # Replace common repeated phrases with variations
    replacements = {
        "recommended next steps": ["next actions", "required steps", "action items"],
        "civil rights violation": ["rights violation", "constitutional violation", "legal violation"],
        "legal analysis": ["legal review", "legal assessment", "case analysis"],
        "based on the": ["given the", "considering the", "with the"],
        "review and recommended": ["review and suggested", "analysis and proposed", "assessment and required"],
        "Legal Review and Recommended Next Steps": "Legal Assessment and Action Plan",
        "legal claims analysis": "claims assessment",
        "evidence support": "supporting evidence",
        "strength assessment": "case strength",
        "potential damages": "available remedies",
    }
    
    # Track usage to avoid overuse
    used_replacements = {}
    
    for original, alternatives in replacements.items():
        count = text.lower().count(original.lower())
        if count > 1:
            # Replace subsequent occurrences with alternatives
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            matches = list(pattern.finditer(text))
            
            # Replace from the end to avoid position shifts
            for i, match in enumerate(reversed(matches)):
                if i > 0:  # Keep first occurrence, replace others
                    alt_index = (i - 1) % len(alternatives)
                    replacement = alternatives[alt_index]
                    start, end = match.span()
                    text = text[:start] + replacement + text[end:]
    
    return text

def normalize_html_content(html_content):
    """Apply normalization fixes to HTML content."""
    print("🔧 Applying normalization fixes...")
    
    # Parse HTML
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Process text content in paragraphs and list items
    for element in soup.find_all(["p", "li", "div"]):
        if element.string:
            original_text = element.get_text()
            
            # Break long sentences
            improved_text = break_long_sentences(original_text)
            
            # Reduce repetition
            improved_text = reduce_repetition(improved_text)
            
            # Replace content if changed
            if improved_text != original_text:
                element.string.replace_with(improved_text)
    
    # Process title and headers
    for element in soup.find_all(["title", "h1", "h2", "h3"]):
        if element.string:
            original_text = element.get_text()
            improved_text = reduce_repetition(original_text)
            if improved_text != original_text:
                element.string.replace_with(improved_text)
    
    return str(soup)

def main():
    """Test the normalization processor."""
    # Read the debug content
    try:
        with open("debug_normalization_content.html", encoding="utf-8") as f:
            html_content = f.read()
        
        print("📄 Processing normalization content...")
        
        # Apply normalization
        normalized_content = normalize_html_content(html_content)
        
        # Save normalized version
        with open("debug_normalization_content_fixed.html", "w", encoding="utf-8") as f:
            f.write(normalized_content)
        
        print("✅ Normalized content saved to: debug_normalization_content_fixed.html")
        
        # Quick analysis
        def count_long_sentences(text):
            plain_text = re.sub(r"<[^>]+>", "", text)
            sentences = re.split(r"[.!?]+", plain_text)
            sentences = [s.strip() for s in sentences if s.strip()]
            return len([s for s in sentences if len(s.split()) > 15])
        
        original_long = count_long_sentences(html_content)
        normalized_long = count_long_sentences(normalized_content)
        
        print(f"📊 Long sentences (>15 words): {original_long} → {normalized_long}")
        
        if normalized_long < original_long:
            print("✅ Improvement achieved!")
        else:
            print("⚠️  May need additional processing")
        
    except FileNotFoundError:
        print("❌ debug_normalization_content.html not found")
        print("   Run debug_normalization_issues.py first")

if __name__ == "__main__":
    main()
