from __future__ import annotations

from drill.controllers.card_generator import build_drill_card_seeds
from drill.database import DrillDatabase
from word_bank.database import DatabaseError, WordBankDatabase


def sync_drill_cards_for_lexical_item(
    word_bank: WordBankDatabase,
    drill_db: DrillDatabase,
    lexical_item_id: int,
) -> int:
    try:
        item = word_bank.load_lexical_item(lexical_item_id)
    except DatabaseError:
        drill_db.deactivate_cards_for_lexical_item(lexical_item_id)
        return 0

    seeds = build_drill_card_seeds(item)
    return drill_db.sync_card_seeds_for_lexical_item(lexical_item_id, seeds)


def sync_all_drill_cards(word_bank: WordBankDatabase, drill_db: DrillDatabase) -> int:
    lexical_item_ids = word_bank.list_lexical_item_ids()
    total = 0
    for lexical_item_id in lexical_item_ids:
        total += sync_drill_cards_for_lexical_item(word_bank, drill_db, lexical_item_id)
    drill_db.deactivate_cards_not_in(set(lexical_item_ids))
    drill_db.ensure_all_drill_schedules()
    return total
