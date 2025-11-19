"""CLIO context builder for enriching letter generation.

This module analyzes CLIO data to extract structured context including
communication timelines, party relationships, and patterns.
"""

from __future__ import annotations

from typing import Any, Dict, List

from legal_portal.core.data_models import (
    ClioCommunication,
    ClioContact,
    ClioMatter,
    ClioMatterContext,
)
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class ClioContextBuilder:
    """Service for building rich context from CLIO data."""

    def build_matter_context(  # noqa: D417
        self, matter: ClioMatter, communications: List[ClioCommunication], contacts: List[ClioContact]
    ) -> ClioMatterContext:
        """Build complete context from CLIO data.

        Parameters
        ----------
            matter: CLIO matter object
            communications: List of communications
            contacts: List of all contacts involved

        Returns
        -------
            ClioMatterContext with enriched data
        """
        logger.info(f"Building context for matter {matter.display_number}")

        timeline = self.build_communication_timeline(communications)
        party_relationships = self.identify_party_roles(contacts, communications)
        statistics = self.calculate_communication_statistics(communications, party_relationships)
        gaps = self.identify_communication_gaps(timeline)
        key_dates = self.extract_key_dates(timeline, matter)

        context = ClioMatterContext(
            matter_summary=matter.description or "No description provided",
            timeline=timeline,
            party_relationships=party_relationships,
            communication_statistics=statistics,
            key_dates=key_dates,
            communication_gaps=gaps,
        )

        logger.info(
            f"Built context: {len(timeline)} timeline events, "
            f"{len(party_relationships)} parties, "
            f"{len(gaps)} communication gaps"
        )

        return context

    def extract_qa_pairs_from_matter(self, matter: ClioMatter) -> List[Dict[str, str]]:  # noqa: D417
        """Auto-populate Q&A from matter data.

        Maps CLIO fields to intake questions to reduce manual data entry.

        Parameters
        ----------
            matter: CLIO matter object

        Returns
        -------
            List of {question, answer} dictionaries
        """
        qa_pairs = []

        if matter.client_name:
            qa_pairs.append({"question": "What is your name?", "answer": matter.client_name})

        if matter.description:
            qa_pairs.append({"question": "What is your legal issue?", "answer": matter.description})

        if matter.practice_area:
            qa_pairs.append(
                {"question": "What type of legal matter is this?", "answer": matter.practice_area}
            )

        # Map common custom fields
        custom_field_mapping = {
            "incident_date": "When did this incident occur?",
            "property_address": "What is the property address?",
            "opposing_counsel": "Who represents the other party?",
            "damages_sought": "What outcome are you seeking?",
            "court": "What court is this matter in?",
            "case_number": "What is the case number?",
        }

        for field_name, question in custom_field_mapping.items():
            if field_name in matter.custom_fields and matter.custom_fields[field_name]:
                qa_pairs.append({"question": question, "answer": str(matter.custom_fields[field_name])})

        logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from matter")
        return qa_pairs

    def build_communication_timeline(self, communications: List[ClioCommunication]) -> List[Dict[str, Any]]:  # noqa: D417
        """Create chronological timeline with annotations.

        Parameters
        ----------
            communications: List of communications

        Returns
        -------
            List of timeline events sorted chronologically
        """
        # Sort by date
        sorted_comms = sorted(communications, key=lambda c: c.date)

        timeline = []
        for comm in sorted_comms:
            timeline.append(
                {
                    "date": comm.date,
                    "type": "communication",
                    "subject": comm.subject,
                    "sender_name": comm.sender.name,
                    "recipient_names": [r.name for r in comm.recipients],
                    "communication_type": comm.communication_type,
                }
            )

        return timeline

    def identify_party_roles(  # noqa: D417
        self, contacts: List[ClioContact], communications: List[ClioCommunication]
    ) -> Dict[str, str]:
        """Infer party roles from communication patterns.

        Uses heuristics to classify contacts as:
        - Client: High bidirectional communication
        - Opposing Party: Receives demands, less responsive
        - Third Party: CC'd frequently, low activity

        Parameters
        ----------
            contacts: List of contacts
            communications: List of communications for analysis

        Returns
        -------
            Dict mapping contact name to inferred role
        """
        roles = {}

        # Count communication patterns
        send_counts = {}
        receive_counts = {}

        for comm in communications:
            sender_name = comm.sender.name
            send_counts[sender_name] = send_counts.get(sender_name, 0) + 1

            for recipient in comm.recipients:
                receive_counts[recipient.name] = receive_counts.get(recipient.name, 0) + 1

        # Simple heuristic classification
        for contact in contacts:
            name = contact.name
            sends = send_counts.get(name, 0)
            receives = receive_counts.get(name, 0)
            total_activity = sends + receives

            # Classification logic
            if total_activity == 0:
                roles[name] = "Third Party"
            elif sends > 10 and receives > 10:
                # High bidirectional activity suggests client
                roles[name] = "Client"
            elif sends == 0 and receives > 5:
                # Receives only suggests opposing party
                roles[name] = "Opposing Party"
            elif receives > sends * 2:
                # Receives much more than sends
                roles[name] = "Opposing Party"
            elif sends > receives * 2:
                # Sends much more than receives
                roles[name] = "Client"
            else:
                roles[name] = "Third Party"

        return roles

    def calculate_communication_statistics(  # noqa: D417
        self, communications: List[ClioCommunication], party_relationships: Dict[str, str]
    ) -> Dict[str, Any]:
        """Calculate patterns and statistics.

        Parameters
        ----------
            communications: List of communications
            party_relationships: Dict of contact names to roles

        Returns
        -------
            Dict with statistics and insights
        """
        attorney_initiated = 0
        client_initiated = 0
        opposing_initiated = 0

        # Count by sender role
        for comm in communications:
            sender_role = party_relationships.get(comm.sender.name, "Unknown")

            if "attorney" in sender_role.lower() or "lawyer" in sender_role.lower():
                attorney_initiated += 1
            elif "client" in sender_role.lower():
                client_initiated += 1
            elif "opposing" in sender_role.lower():
                opposing_initiated += 1

        # Calculate response rates (simplified)
        total_comms = len(communications)
        opposing_response_rate = opposing_initiated / max(total_comms, 1)

        # Generate insights
        insights = []
        if attorney_initiated > 0:
            insights.append(f"Attorney has initiated {attorney_initiated} communications")
        if client_initiated > 0:
            insights.append(f"Client has been proactive with {client_initiated} communications")
        if opposing_response_rate < 0.3 and total_comms > 5:
            insights.append("Opposing party shows limited responsiveness")
        elif opposing_response_rate > 0.5:
            insights.append("Opposing party has been actively communicating")

        return {
            "total_communications": total_comms,
            "attorney_initiated": attorney_initiated,
            "client_initiated": client_initiated,
            "opposing_initiated": opposing_initiated,
            "opposing_response_rate": opposing_response_rate,
            "avg_response_days": 0,  # Placeholder - would need paired analysis
            "insights": insights,
        }

    def identify_communication_gaps(self, timeline: List[Dict[str, Any]]) -> List[str]:  # noqa: D417
        """Identify notable gaps in communication (>30 days).

        Parameters
        ----------
            timeline: Chronological timeline of events

        Returns
        -------
            List of gap descriptions
        """
        gaps = []

        if len(timeline) < 2:
            return gaps

        for i in range(1, len(timeline)):
            prev_date = timeline[i - 1]["date"]
            curr_date = timeline[i]["date"]
            gap_days = (curr_date - prev_date).days

            if gap_days > 30:
                gaps.append(
                    f"{gap_days}-day gap between {prev_date.strftime('%b %d')} "
                    f"and {curr_date.strftime('%b %d, %Y')}"
                )

        return gaps

    def extract_key_dates(self, timeline: List[Dict[str, Any]], matter: ClioMatter) -> List[Dict[str, Any]]:  # noqa: D417
        """Extract key dates from timeline and matter.

        Parameters
        ----------
            timeline: Communication timeline
            matter: CLIO matter object

        Returns
        -------
            List of key date dictionaries
        """
        key_dates = []

        # Add matter open date
        key_dates.append({"date": matter.open_date, "event": "Matter Opened", "source": "CLIO Matter"})

        # Add first communication
        if timeline:
            first_comm = timeline[0]
            key_dates.append(
                {
                    "date": first_comm["date"],
                    "event": f"First Communication: {first_comm['subject']}",
                    "source": "CLIO Communications",
                }
            )

            # Add last communication
            last_comm = timeline[-1]
            key_dates.append(
                {
                    "date": last_comm["date"],
                    "event": f"Most Recent: {last_comm['subject']}",
                    "source": "CLIO Communications",
                }
            )

        # Add matter close date if exists
        if matter.close_date:
            key_dates.append({"date": matter.close_date, "event": "Matter Closed", "source": "CLIO Matter"})

        return sorted(key_dates, key=lambda x: x["date"])

    def format_clio_context_for_prompt(self, context: ClioMatterContext) -> str:  # noqa: D417
        """Format context as string for letter prompt.

        Parameters
        ----------
            context: ClioMatterContext object

        Returns
        -------
            Formatted string for inclusion in prompt
        """
        sections = []

        sections.append("CLIO MATTER CONTEXT:")
        sections.append(f"Matter Summary: {context.matter_summary}")
        sections.append("")

        # Communication timeline (show first 10)
        if context.timeline:
            sections.append("COMMUNICATION TIMELINE:")
            for event in context.timeline[:10]:
                sections.append(
                    f"- {event['date'].strftime('%b %d, %Y')}: {event['subject']} "
                    f"({event['sender_name']} → {', '.join(event['recipient_names'])})"
                )
            if len(context.timeline) > 10:
                sections.append(f"- ... and {len(context.timeline) - 10} more communications")
            sections.append("")

        # Communication gaps
        if context.communication_gaps:
            sections.append("COMMUNICATION GAPS:")
            for gap in context.communication_gaps:
                sections.append(f"- {gap}")
            sections.append("")

        # Party relationships
        if context.party_relationships:
            sections.append("PARTY RELATIONSHIPS:")
            for name, role in context.party_relationships.items():
                sections.append(f"- {name}: {role}")
            sections.append("")

        # Communication statistics
        if context.communication_statistics:
            sections.append("COMMUNICATION STATISTICS:")
            stats = context.communication_statistics
            sections.append(f"- Total communications: {stats.get('total_communications', 0)}")
            sections.append(f"- Attorney-initiated: {stats.get('attorney_initiated', 0)}")
            sections.append(f"- Client-initiated: {stats.get('client_initiated', 0)}")

            if stats.get("insights"):
                sections.append("\nKEY INSIGHTS:")
                for insight in stats["insights"]:
                    sections.append(f"- {insight}")

        return "\n".join(sections)
