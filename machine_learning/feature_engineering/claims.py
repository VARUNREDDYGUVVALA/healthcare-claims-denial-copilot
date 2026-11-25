"""Point-in-time claim evidence and feature construction."""
from data_engineering.ingestion.duckdb_extract import rows


def claim_lines(db):
    return rows(db, """
        WITH coverage AS (
            SELECT l.id, list(struct_pack(id := e.id, starts := e.starts, ends := e.ends, recorded := e.recorded) ORDER BY e.id) AS records FROM lines l
            JOIN claims c ON c.id=l.claim_id JOIN eligibility e
            ON e.member=c.member AND e.payer=c.payer AND l.service >= e.starts
            AND l.service < e.ends AND e.recorded < c.submitted GROUP BY l.id
        ), auth AS (
            SELECT l.id, list(struct_pack(id := a.id, starts := a.starts, ends := a.ends, recorded := a.recorded) ORDER BY a.id) AS records FROM lines l
            JOIN claims c ON c.id=l.claim_id JOIN authorizations a
            ON a.member=c.member AND a.payer=c.payer AND a.procedure=l.procedure
            AND l.service >= a.starts AND l.service < a.ends AND a.recorded < c.submitted GROUP BY l.id
        ), responses_by_claim AS (
            SELECT l.claim_id, count(*) FILTER (WHERE r.status='denied') AS denied,
                count(*) FILTER (WHERE r.status='approved') AS approved,
                count(*) FILTER (WHERE r.status='pending' OR r.status IS NULL) AS pending
            FROM lines l LEFT JOIN responses r ON r.line_id=l.id GROUP BY l.claim_id
        )
        SELECT l.*, c.member, c.payer, c.submitted,
            coalesce(e.records, []) AS eligibility, coalesce(a.records, []) AS authorizations,
            (SELECT list(p.id ORDER BY p.id) FROM lines p JOIN claims pc ON pc.id=p.claim_id
             WHERE pc.member=c.member AND pc.payer=c.payer AND p.service=l.service
             AND p.procedure=l.procedure AND (pc.submitted<c.submitted OR
             (p.claim_id=l.claim_id AND p.id<l.id))) AS duplicates,
            r.status, r.reason, r.received,
            CASE WHEN rc.denied>0 AND rc.approved>0 THEN 'partially denied'
                 WHEN rc.pending>0 THEN 'pending'
                 WHEN rc.denied>0 THEN 'denied' ELSE 'approved' END AS claim_status
        FROM lines l JOIN claims c ON c.id=l.claim_id
        LEFT JOIN coverage e ON e.id=l.id LEFT JOIN auth a ON a.id=l.id
        LEFT JOIN responses r ON r.line_id=l.id JOIN responses_by_claim rc ON rc.claim_id=l.claim_id
        ORDER BY c.submitted, l.id
    """)

def features(line):
    return {
        "payer": line["payer"], "procedure": line["procedure"],
        "missing_eligibility": int(not line["eligibility"]),
        "missing_imaging_authorization": int(line["procedure"] == "IMG-01" and not line["authorizations"]),
        "possible_duplicate": int(bool(line["duplicates"])),
    }

def baseline(line):
    f = features(line)
    return .55 * f["missing_eligibility"] + .38 * f["missing_imaging_authorization"] + .48 * f["possible_duplicate"]
