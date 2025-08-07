"""
Timeline analysis and chronological processing for legal case data.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import dateutil.parser as date_parser


class TimelineAnalyzer:
    """Handles timeline creation and chronological analysis of case events."""

    def __init__(self):
        """Initialize TimelineAnalyzer."""
        self.date_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # MM/DD/YYYY or MM-DD-YYYY
            r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',    # YYYY/MM/DD or YYYY-MM-DD
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',  # Month DD, YYYY
            r'\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b',     # DD Month YYYY
        ]
        
        self.time_indicators = [
            r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b',  # Time patterns
            r'\b(?:morning|afternoon|evening|night)\b',
            r'\b(?:early|late|mid)\s+(?:morning|afternoon|evening)\b',
        ]

    def extract_timeline_from_content(self, content: str, source: str = "unknown") -> List[Dict[str, Any]]:
        """Extract timeline events from text content."""
        print(f"TIMELINE ANALYZER: 📅 Extracting timeline from {source}")
        
        if not content or not content.strip():
            print(f"TIMELINE ANALYZER: ⚠️  No content provided for {source}")
            return []
        
        events = []
        sentences = self._split_into_sentences(content)
        
        for i, sentence in enumerate(sentences):
            # Look for dates in each sentence
            dates = self._extract_dates_from_text(sentence)
            
            if dates:
                for date_info in dates:
                    event = {
                        "date": date_info["date"],
                        "date_string": date_info["original"],
                        "description": sentence.strip(),
                        "source": source,
                        "confidence": date_info["confidence"],
                        "sentence_index": i,
                        "context": self._get_sentence_context(sentences, i)
                    }
                    events.append(event)
        
        # Sort events by date
        events.sort(key=lambda x: x["date"] if x["date"] else datetime.min)
        
        print(f"TIMELINE ANALYZER: 📅 Extracted {len(events)} timeline events from {source}")
        return events

    def create_comprehensive_timeline(self, analysis_data: Any) -> Dict[str, Any]:
        """Create comprehensive timeline from all available data sources."""
        print("TIMELINE ANALYZER: 🗓️  Creating comprehensive timeline")
        
        all_events = []
        sources_processed = []
        
        # Extract from intake form
        if hasattr(analysis_data, 'intake_summary') and analysis_data.intake_summary:
            intake_events = self.extract_timeline_from_content(
                str(analysis_data.intake_summary), 
                "intake_form"
            )
            all_events.extend(intake_events)
            sources_processed.append("intake_form")
        
        # Extract from case documents
        if hasattr(analysis_data, 'case_documents') and analysis_data.case_documents:
            for i, doc in enumerate(analysis_data.case_documents):
                doc_content = doc.content if hasattr(doc, 'content') else str(doc)
                doc_name = getattr(doc, 'file_name', f"document_{i}")
                
                doc_events = self.extract_timeline_from_content(
                    doc_content, 
                    f"document_{doc_name}"
                )
                all_events.extend(doc_events)
                sources_processed.append(f"document_{doc_name}")
        
        # Extract from video transcripts
        if hasattr(analysis_data, 'video_insights') and analysis_data.video_insights:
            for video in analysis_data.video_insights:
                if video.transcript:
                    video_events = self.extract_timeline_from_content(
                        video.transcript, 
                        f"video_{video.file_name}"
                    )
                    all_events.extend(video_events)
                    sources_processed.append(f"video_{video.file_name}")
        
        # Remove duplicates and merge similar events
        unique_events = self._deduplicate_events(all_events)
        
        # Identify gaps and inconsistencies
        analysis = self._analyze_timeline_patterns(unique_events)
        
        print(f"TIMELINE ANALYZER: 🗓️  Timeline created with {len(unique_events)} events")
        print(f"TIMELINE ANALYZER: 🗓️  Sources: {', '.join(sources_processed)}")
        
        return {
            "events": unique_events,
            "sources_processed": sources_processed,
            "total_events": len(unique_events),
            "date_range": self._get_date_range(unique_events),
            "analysis": analysis,
            "created_at": datetime.now().isoformat()
        }

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for timeline extraction."""
        # Simple sentence splitting - can be enhanced with more sophisticated methods
        sentences = re.split(r'[.!?]+\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_dates_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract dates from text using multiple patterns."""
        dates_found = []
        
        # Try each date pattern
        for pattern in self.date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                date_string = match.group()
                parsed_date = self._parse_date_string(date_string)
                
                if parsed_date:
                    dates_found.append({
                        "date": parsed_date,
                        "original": date_string,
                        "confidence": self._calculate_date_confidence(date_string, text),
                        "position": match.span()
                    })
        
        # Remove duplicates
        unique_dates = []
        seen_dates = set()
        
        for date_info in dates_found:
            date_key = date_info["date"].strftime("%Y-%m-%d")
            if date_key not in seen_dates:
                unique_dates.append(date_info)
                seen_dates.add(date_key)
        
        return unique_dates

    def _parse_date_string(self, date_string: str) -> Optional[datetime]:
        """Parse date string into datetime object."""
        try:
            # Clean up the date string
            cleaned = re.sub(r'[^\w\s/:-]', '', date_string).strip()
            
            # Try dateutil parser first (very flexible)
            parsed = date_parser.parse(cleaned, fuzzy=True)
            
            # Validate the parsed date is reasonable
            if self._is_reasonable_date(parsed):
                return parsed
            
        except (ValueError, TypeError) as e:
            print(f"TIMELINE ANALYZER: ⚠️  Date parsing failed for '{date_string}': {e}")
        
        return None

    def _is_reasonable_date(self, date: datetime) -> bool:
        """Check if parsed date is reasonable for legal cases."""
        current_year = datetime.now().year
        
        # Date should be between 1900 and 5 years in the future
        if date.year < 1900 or date.year > current_year + 5:
            return False
        
        # Date shouldn't be in the far future for most legal cases
        if date > datetime.now() + timedelta(days=365 * 2):
            return False
        
        return True

    def _calculate_date_confidence(self, date_string: str, context: str) -> float:
        """Calculate confidence score for extracted date."""
        confidence = 0.5  # Base confidence
        
        # Higher confidence for explicit date formats
        if re.match(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', date_string):
            confidence += 0.3
        elif re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', date_string):
            confidence += 0.2
        
        # Higher confidence if surrounded by time indicators
        context_lower = context.lower()
        time_words = ['occurred', 'happened', 'on', 'date', 'dated', 'signed', 'filed', 'received']
        
        for word in time_words:
            if word in context_lower:
                confidence += 0.1
                break
        
        # Check for time indicators near the date
        for pattern in self.time_indicators:
            if re.search(pattern, context, re.IGNORECASE):
                confidence += 0.1
                break
        
        return min(confidence, 1.0)  # Cap at 1.0

    def _get_sentence_context(self, sentences: List[str], index: int, window: int = 1) -> str:
        """Get context around a sentence for better timeline understanding."""
        start = max(0, index - window)
        end = min(len(sentences), index + window + 1)
        
        context_sentences = sentences[start:end]
        return " ".join(context_sentences)

    def _deduplicate_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate events and merge similar ones."""
        if not events:
            return []
        
        unique_events = []
        seen_combinations = set()
        
        for event in events:
            # Create a key for deduplication
            date_str = event["date"].strftime("%Y-%m-%d") if event["date"] else "no_date"
            desc_key = event["description"][:50].lower().strip()  # First 50 chars
            key = f"{date_str}_{desc_key}"
            
            if key not in seen_combinations:
                unique_events.append(event)
                seen_combinations.add(key)
            else:
                # Find the existing event and potentially merge
                for existing_event in unique_events:
                    existing_date_str = existing_event["date"].strftime("%Y-%m-%d") if existing_event["date"] else "no_date"
                    existing_desc_key = existing_event["description"][:50].lower().strip()
                    existing_key = f"{existing_date_str}_{existing_desc_key}"
                    
                    if existing_key == key:
                        # Merge sources and update confidence
                        if event["source"] not in existing_event["source"]:
                            existing_event["source"] += f", {event['source']}"
                        existing_event["confidence"] = max(existing_event["confidence"], event["confidence"])
                        break
        
        return unique_events

    def _analyze_timeline_patterns(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze timeline for patterns, gaps, and inconsistencies."""
        if not events:
            return {"gaps": [], "patterns": [], "inconsistencies": []}
        
        analysis = {
            "gaps": [],
            "patterns": [],
            "inconsistencies": [],
            "date_clusters": [],
            "source_coverage": {}
        }
        
        # Analyze date gaps
        dated_events = [e for e in events if e["date"]]
        if len(dated_events) > 1:
            dated_events.sort(key=lambda x: x["date"])
            
            for i in range(len(dated_events) - 1):
                current_date = dated_events[i]["date"]
                next_date = dated_events[i + 1]["date"]
                gap_days = (next_date - current_date).days
                
                if gap_days > 30:  # Gap longer than 30 days
                    analysis["gaps"].append({
                        "start_date": current_date.strftime("%Y-%m-%d"),
                        "end_date": next_date.strftime("%Y-%m-%d"),
                        "gap_days": gap_days,
                        "significance": "high" if gap_days > 90 else "medium"
                    })
        
        # Analyze source coverage
        source_counts = {}
        for event in events:
            source = event["source"]
            source_counts[source] = source_counts.get(source, 0) + 1
        
        analysis["source_coverage"] = source_counts
        
        # Identify date clusters (events happening close together)
        if len(dated_events) > 2:
            clusters = self._find_date_clusters(dated_events)
            analysis["date_clusters"] = clusters
        
        return analysis

    def _find_date_clusters(self, dated_events: List[Dict[str, Any]], max_gap_days: int = 7) -> List[Dict[str, Any]]:
        """Find clusters of events that happened close together in time."""
        clusters = []
        current_cluster = []
        
        for i, event in enumerate(dated_events):
            if not current_cluster:
                current_cluster.append(event)
            else:
                last_date = current_cluster[-1]["date"]
                current_date = event["date"]
                gap_days = (current_date - last_date).days
                
                if gap_days <= max_gap_days:
                    current_cluster.append(event)
                else:
                    # End current cluster if it has multiple events
                    if len(current_cluster) > 1:
                        clusters.append({
                            "start_date": current_cluster[0]["date"].strftime("%Y-%m-%d"),
                            "end_date": current_cluster[-1]["date"].strftime("%Y-%m-%d"),
                            "event_count": len(current_cluster),
                            "events": current_cluster
                        })
                    
                    # Start new cluster
                    current_cluster = [event]
        
        # Don't forget the last cluster
        if len(current_cluster) > 1:
            clusters.append({
                "start_date": current_cluster[0]["date"].strftime("%Y-%m-%d"),
                "end_date": current_cluster[-1]["date"].strftime("%Y-%m-%d"),
                "event_count": len(current_cluster),
                "events": current_cluster
            })
        
        return clusters

    def _get_date_range(self, events: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        """Get the overall date range of events."""
        dated_events = [e for e in events if e["date"]]
        
        if not dated_events:
            return {"start": None, "end": None, "span_days": 0}
        
        dates = [e["date"] for e in dated_events]
        start_date = min(dates)
        end_date = max(dates)
        span_days = (end_date - start_date).days
        
        return {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "span_days": span_days
        }

    def format_timeline_for_prompt(self, timeline_data: Dict[str, Any], max_events: int = 20) -> str:
        """Format timeline data for inclusion in AI prompts."""
        if not timeline_data.get("events"):
            return "No timeline events found in the provided data."
        
        events = timeline_data["events"][:max_events]  # Limit for prompt size
        
        formatted_lines = ["TIMELINE OF EVENTS:"]
        
        for event in events:
            date_str = event["date"].strftime("%Y-%m-%d") if event["date"] else "Date unknown"
            source = event["source"]
            description = event["description"][:100] + "..." if len(event["description"]) > 100 else event["description"]
            confidence = event["confidence"]
            
            formatted_lines.append(f"- {date_str} ({source}, confidence: {confidence:.1f}): {description}")
        
        # Add summary information
        if timeline_data.get("date_range"):
            date_range = timeline_data["date_range"]
            if date_range["start"] and date_range["end"]:
                formatted_lines.append(f"\nTimeline spans from {date_range['start']} to {date_range['end']} ({date_range['span_days']} days)")
        
        # Add significant gaps
        if timeline_data.get("analysis", {}).get("gaps"):
            formatted_lines.append("\nSIGNIFICANT GAPS:")
            for gap in timeline_data["analysis"]["gaps"][:3]:  # Top 3 gaps
                formatted_lines.append(f"- {gap['gap_days']} day gap between {gap['start_date']} and {gap['end_date']}")
        
        return "\n".join(formatted_lines)