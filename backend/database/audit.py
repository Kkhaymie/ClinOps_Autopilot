# backend/database/audit.py
"""
Append-only audit trail logging for the AE approval workflow and any other
compliance-relevant action. Nothing in this codebase should ever call
.update() or .delete() against the audit_trail table.
"""

import logging
from typing import Optional

from database.client import supabase

logger = logging.getLogger(__name__)


def log_audit(
    table_name: str,
    record_id: str,
    action: str,
    user_id: Optional[str] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    ai_model: Optional[str] = None,
    ai_confidence: Optional[int] = None,
) -> None:
    try:
        supabase.table("audit_trail").insert({
            "table_name": table_name,
            "record_id": record_id,
            "action": action,
            "user_id": user_id,
            "old_values": old_values,
            "new_values": new_values,
            "ai_model": ai_model,
            "ai_confidence": ai_confidence,
        }).execute()
    except Exception:
        logger.exception(
            "log_audit failed (table=%s, record=%s, action=%s)",
            table_name, record_id, action,
        )