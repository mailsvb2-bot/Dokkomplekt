"""No built-in medical DOCX templates are shipped.

The product is doctor-owned by design: every doctor/clinic/country loads its
own Word templates during setup.  The empty mapping stays only as a safe import
compatibility point for legacy code paths that may still probe embedded storage.
"""

from __future__ import annotations

TEMPLATE_B64: dict[str, str] = {}
