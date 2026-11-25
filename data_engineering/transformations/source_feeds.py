"""Provenance mapping for the three fictional provider feeds."""
FEEDS = {
    "hospital": "Hospital billing",
    "clearinghouse": "Clearinghouse",
    "practice": "Practice management",
}

FEED_SQL = """
    CASE WHEN provider_id <= 34 THEN 'hospital'
         WHEN provider_id <= 67 THEN 'clearinghouse'
         ELSE 'practice' END
"""
