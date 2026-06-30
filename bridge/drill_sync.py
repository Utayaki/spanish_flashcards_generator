from __future__ import annotations

import logging

from drill.controllers.card_generator import build_drill_card_seeds
from drill.db import DrillDatabase
from shared.errors import DatabaseError
from word_bank.db import WordBankDatabase

logger = logging.getLogger(__name__)


class DrillSyncService:
    """Keeps drill.db cards in sync with word_bank.db lexical items."""

    def __init__(self, word_bank: WordBankDatabase, drill_db: DrillDatabase) -> None:
        self._word_bank = word_bank
        self._drill_db = drill_db

    def sync_lexical_item(self, lexical_item_id: int) -> int:
        try:
            item = self._word_bank.load_lexical_item(lexical_item_id)
        except DatabaseError:
            self._drill_db.deactivate_cards_for_lexical_item(lexical_item_id)
            return 0

        seeds = build_drill_card_seeds(item)
        return self._drill_db.sync_card_seeds_for_lexical_item(lexical_item_id, seeds)

    def sync_all(self) -> int:
        lexical_item_ids = self._word_bank.list_lexical_item_ids()
        total = 0
        for lexical_item_id in lexical_item_ids:
            total += self.sync_lexical_item(lexical_item_id)
        self._drill_db.deactivate_cards_not_in(set(lexical_item_ids))
        self._drill_db.ensure_all_drill_schedules()
        return total

    def sync_lexical_item_safe(self, lexical_item_id: int) -> str | None:
        """Sync one item; return error message on failure without raising."""
        try:
            self.sync_lexical_item(lexical_item_id)
            return None
        except Exception as exc:
            logger.exception("drill sync failed for lexical_item_id=%s", lexical_item_id)
            return str(exc)
