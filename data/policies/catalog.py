"""Versioned fictional payer policy sections."""

def policy_sections():
    sections = []

    def add(**section):
        sections.append(section)

    for version, start, end, clause in [
        ("v1", "2025-01-01", "2025-07-01", "Authorization may be obtained up to two business days after service."),
        ("v2", "2025-07-01", "2026-01-01", "Authorization must be on file before the service. If it is missing, verify the payer portal before requesting reconsideration."),
        ("2026-v1", "2026-01-01", "2026-04-01", "Authorization may be obtained up to two business days after service."),
        ("2026-v2", "2026-04-01", "2026-07-01", "Authorization must be on file before the service. If it is missing, verify the payer portal before requesting reconsideration."),
    ]:
        add(id=f"NS-IMG-{version}", payer="Northstar Health", procedure="IMG-01",
            starts=start, ends=end, section=f"Imaging § 4.2 · {version}", excerpt=clause)
    add(id="NS-VIS-v1", payer="Northstar Health", procedure="VIS-03",
        starts="2025-01-01", ends="2026-01-01", section="Professional services § 2.1",
        excerpt="Coverage must be active on the service date. Review prior submissions for the same service before resubmitting.")

    return sections
