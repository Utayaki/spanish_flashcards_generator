from __future__ import annotations

from typing import Any

from drill.controllers.question_builder import build_question_from_card, check_answer_for_question
from drill.database import DrillDatabase
from shared.api.drill_answers import validate_answer_keys
from shared.errors import ValidationError
from word_bank.database import WordBankDatabase


class DrillService:
    def __init__(self, word_bank: WordBankDatabase, drill_db: DrillDatabase) -> None:
        self._word_bank = word_bank
        self._drill_db = drill_db

    def check_card_answer(
        self,
        drill_card_id: int,
        answers: dict[str, Any],
    ) -> dict[str, Any]:
        card = self._drill_db.get_drill_card(drill_card_id)
        if card is None:
            raise LookupError(f"drill card not found: {drill_card_id}")
        if not int(card["is_active"]):
            raise ValidationError(f"drill card is inactive: {drill_card_id}")

        question = build_question_from_card(self._word_bank, card)
        validate_answer_keys(question, answers)
        return check_answer_for_question(self._word_bank, question, answers)
