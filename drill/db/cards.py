from __future__ import annotations

import json
from typing import Any

from shared.sqlite.connection import row_to_dict


class DrillCardsRepository:
    def get_random_drill_card(self, drill_type: str | None = None) -> dict[str, Any] | None:
        params: list[Any] = []
        where = ["is_active = 1"]
        if drill_type:
            where.append("drill_type = ?")
            params.append(drill_type)
        sql = f"""
            SELECT *
            FROM drill_cards
            WHERE {" AND ".join(where)}
            ORDER BY RANDOM()
            LIMIT 1
        """
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return row_to_dict(row)

    def get_drill_card(self, drill_card_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM drill_cards
                WHERE id = ?
                """,
                (drill_card_id,),
            ).fetchone()
        return row_to_dict(row)

    def deactivate_cards_for_lexical_item(self, lexical_item_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            )

    def deactivate_cards_not_in(self, lexical_item_ids: set[int]) -> None:
        with self.transaction() as connection:
            if not lexical_item_ids:
                connection.execute("UPDATE drill_cards SET is_active = 0")
                return
            placeholders = ", ".join("?" for _ in lexical_item_ids)
            connection.execute(
                f"""
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id NOT IN ({placeholders})
                """,
                tuple(lexical_item_ids),
            )

    def upsert_drill_card(
        self,
        *,
        lexical_item_id: int,
        drill_type: str,
        target_kind: str,
        target_key: str,
        prompt_schema: str,
        answer_schema: str,
        skill_tags: list[str],
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO drill_cards (
                    lexical_item_id,
                    drill_type,
                    target_kind,
                    target_key,
                    prompt_schema,
                    answer_schema,
                    skill_tags,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT (
                    lexical_item_id,
                    drill_type,
                    target_kind,
                    target_key
                )
                DO UPDATE SET
                    prompt_schema = excluded.prompt_schema,
                    answer_schema = excluded.answer_schema,
                    skill_tags = excluded.skill_tags,
                    is_active = 1
                """,
                (
                    lexical_item_id,
                    drill_type,
                    target_kind,
                    target_key,
                    prompt_schema,
                    answer_schema,
                    json.dumps(skill_tags, ensure_ascii=False),
                ),
            )

    def sync_card_seeds_for_lexical_item(
        self,
        lexical_item_id: int,
        seeds: list[dict[str, Any]],
    ) -> int:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            )
            for seed in seeds:
                connection.execute(
                    """
                    INSERT INTO drill_cards (
                        lexical_item_id,
                        drill_type,
                        target_kind,
                        target_key,
                        prompt_schema,
                        answer_schema,
                        skill_tags,
                        is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (
                        lexical_item_id,
                        drill_type,
                        target_kind,
                        target_key
                    )
                    DO UPDATE SET
                        prompt_schema = excluded.prompt_schema,
                        answer_schema = excluded.answer_schema,
                        skill_tags = excluded.skill_tags,
                        is_active = 1
                    """,
                    (
                        lexical_item_id,
                        seed["drill_type"],
                        seed["target_kind"],
                        seed["target_key"],
                        seed["prompt_schema"],
                        seed["answer_schema"],
                        json.dumps(seed.get("skill_tags", []), ensure_ascii=False),
                    ),
                )
        return len(seeds)
