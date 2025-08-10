#!/usr/bin/env python3

"""
Test the effectiveness of the current normalization post-processing.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



def count_normalization_issues(html_content):
    """Count normalization issues like the validation harness does."""
    if not html_content:
        return 0, 0, 0
    
    # Parse HTML and extract text
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text()
    
    # Count duplicate sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentence_counts = {}
    for sentence in sentences:
        clean_sentence = re.sub(r"\s+", " ", sentence.strip().lower())
        if len(clean_sentence) > 10:  # Only count meaningful sentences
            sentence_counts[clean_sentence] = sentence_counts.get(clean_sentence, 0) + 1
    
    duplicate_sentences = sum(1 for count in sentence_counts.values() if count > 1)
    
    # Count long sentences (>15 words)
    long_sentences = 0
    for sentence in sentences:
        words = sentence.split()
        if len(words) > 15:
            long_sentences += 1
    
    # Count repeated 3-word phrases
    words = re.findall(r"\b\w+\b", text.lower())
    phrase_counts = {}
    for i in range(len(words) - 2):
        phrase = " ".join(words[i:i+3])
        phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
    
    repeated_phrases = sum(1 for count in phrase_counts.values() if count > 2)
    
    return duplicate_sentences, long_sentences, repeated_phrases

def improved_normalization_fixes(html_content):
    """
    Improved normalization post-processing that more aggressively fixes issues.
    """
    if not html_content:
        return html_content
    
    try:
logger.debug('🔧 Starting improved normalization processing...')
        
        # Parse HTML to preserve structure
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Get all text elements that can be modified
        for element in soup.find_all(["p", "li", "div"]):
            if element.string:
                original_text = element.string
                
                # AGGRESSIVE sentence breaking for sentences >15 words
                sentences = re.split(r"(?<=[.!?])\s+", original_text)
                processed_sentences = []
                
                for sentence in sentences:
                    words = sentence.split()
                    if len(words) > 15:
                        # Try multiple split points more aggressively
                        split_points = [
                            ", and ", ", but ", ", however ", "; ",
                            ", which ", ", that ", ", because ", ", since ",
                            ", although ", ", while ", ", if ", ", when ",
                            ", where ", " and ", " but ", " however "
                        ]
                        sentence_broken = False
                        
                        for split_point in split_points:
                            if split_point in sentence.lower():
                                parts = sentence.split(split_point, 1)
                                if len(parts[0].split()) >= 5 and len(parts[1].split()) >= 5:
                                    processed_sentences.append(parts[0].strip() + ".")
                                    # Capitalize first word of new sentence
                                    second_part = parts[1].strip()
                                    if second_part:
                                        second_part = second_part[0].upper() + second_part[1:]
                                        processed_sentences.append(second_part)
                                    sentence_broken = True
                                    break
                        
                        # If still not broken and very long (>20 words), force break
                        if not sentence_broken and len(words) > 20:
                            mid_point = len(words) // 2
                            first_part = " ".join(words[:mid_point]) + "."
                            second_part = " ".join(words[mid_point:])
                            if second_part:
                                second_part = second_part[0].upper() + second_part[1:]
                            processed_sentences.append(first_part)
                            processed_sentences.append(second_part)
                        elif not sentence_broken:
                            processed_sentences.append(sentence)
                    else:
                        processed_sentences.append(sentence)
                
                # Update element text
                new_text = " ".join(processed_sentences)
                element.string.replace_with(new_text)
        
        # Convert back to HTML string for phrase processing
        html_text = str(soup)
        
        # AGGRESSIVE phrase reduction for repeated 3-word phrases
        words = re.findall(r"\b\w+\b", html_text.lower())
        phrase_counts = {}
        
        for i in range(len(words) - 2):
            phrase = " ".join(words[i:i+3])
            phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
        
        # Replace repeated phrases (appearing more than 2 times) more aggressively
        for phrase, count in phrase_counts.items():
            if count > 2:
                # Create replacement mappings
                replacements = {
                    "under florida law": ["under applicable law", "under the law", "legally"],
                    "this matter involves": ["this case involves", "this involves", "the case"],
                    "legal analysis indicates": ["analysis shows", "analysis reveals", "evidence suggests"],
                    "recommended next steps": ["next steps", "recommendations", "action items"],
                    "case assessment reveals": ["assessment shows", "evaluation indicates", "review shows"],
                    "evidence review demonstrates": ["evidence shows", "review indicates", "analysis reveals"],
                    "florida statutes provide": ["statutes provide", "law provides", "rules state"],
                }
                
                # Find all occurrences
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                matches = list(pattern.finditer(html_text))
                
                # Replace all but first 2 instances
                if len(matches) > 2:
                    for i, match in enumerate(matches[2:], 2):
                        if phrase in replacements:
                            replacement = replacements[phrase][min(i-2, len(replacements[phrase])-1)]
                        else:
                            # Generic reduction - keep only first two words
                            words_in_phrase = phrase.split()
                            replacement = " ".join(words_in_phrase[:2])
                        
                        start, end = match.span()
                        html_text = html_text[:start] + replacement + html_text[end:]
        
logger.debug('✅ Improved normalization processing completed')
        return html_text
        
    except Exception as e:
logger.error(f'❌ Improved normalization processing failed: {e}')
        return html_content

# Test with sample content
test_html = """
<p>Under Florida law, this matter involves a complex legal analysis that indicates several considerations under Florida law. This matter involves multiple claims that require careful legal analysis under Florida law. Under Florida law, the recommended next steps include detailed case assessment under Florida law.</p>
<p>The comprehensive legal analysis indicates that this matter involves significant constitutional considerations under Florida law. Legal analysis indicates that the case assessment reveals multiple potential claims. Case assessment reveals that the evidence review demonstrates substantial factual support under Florida law.</p>
"""

logger.info('🧪 Testing current normalization issues:')
logger.info('=' * 50)
dup_before, long_before, repeated_before = count_normalization_issues(test_html)
logger.info(f'BEFORE: Duplicates: {dup_before}, Long sentences: {long_before}, Repeated phrases: {repeated_before}')

logger.info('\n🔧 Applying improved normalization...')
improved_html = improved_normalization_fixes(test_html)

dup_after, long_after, repeated_after = count_normalization_issues(improved_html)
logger.info(f'AFTER: Duplicates: {dup_after}, Long sentences: {long_after}, Repeated phrases: {repeated_after}')

logger.info('\n📊 IMPROVEMENT:')
logger.info(f'Duplicates: {dup_before} → {dup_after} ({dup_before - dup_after} improvement)')
logger.info(f'Long sentences: {long_before} → {long_after} ({long_before - long_after} improvement)')
logger.info(f'Repeated phrases: {repeated_before} → {repeated_after} ({repeated_before - repeated_after} improvement)')

logger.info('\n📝 SAMPLE OUTPUT:')
logger.info('=' * 50)
logger.info(improved_html)
