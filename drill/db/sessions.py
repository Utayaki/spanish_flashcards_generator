from __future__ import annotations

import json
from typing import Any


class DrillSessionsRepository:
    def record_drill_attempt(
        self,
        *,
        drill_card_id: int,
        session_id: int | None,
        submitted_answer: dict[str, Any],
        expected_answer: dict[str, Any],
        result: dict[str, Any],
        is_correct: bool,
        response_ms: int | None = None,
    ) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drill_attempts (
                    drill_card_id,
                    session_id,
                    submitted_answer_json,
                    expected_answer_json,
                    result_json,
                    is_correct,
                    response_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_card_id,
                    session_id,
                    json.dumps(submitted_answer, ensure_ascii=False),
                    json.dumps(expected_answer, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    1 if is_correct else 0,
                    response_ms,
                ),
            )
            if session_id is not None:
                connection.execute(
                    """
                    UPDATE drill_sessions
                    SET
                        total_attempts = total_attempts + 1,
                        correct_attempts = correct_attempts + ?
                    WHERE id = ?
                    """,
                    (1 if is_correct else 0, session_id),
                )
            return int(cursor.lastrowid)

    def create_drill_session(self, *, mode: str = "random", drill_type: str | None = None) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drill_sessions (mode, drill_type)
                VALUES (?, ?)
                """,
                (mode, drill_type),
            )
            return int(cursor.lastrowid)

    def finish_drill_session(self, session_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_sessions
                SET finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (session_id,),
            )

    def get_drill_stats_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            overall = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_attempts,
                    SUM(is_correct) AS correct_attempts
                FROM drill_attempts
                """
            ).fetchone()
            by_type = connection.execute(
                """
                SELECT
                    dc.drill_type,
                    COUNT(*) AS total_attempts,
                    SUM(da.is_correct) AS correct_attempts
                FROM drill_attempts da
                JOIN drill_cards dc ON dc.id = da.drill_card_id
                GROUP BY dc.drill_type
                ORDER BY dc.drill_type
                """
            ).fetchall()

        total = int(overall["total_attempts"] or 0)
        correct = int(overall["correct_attempts"] or 0)
        by_type_rows = []
        for row in by_type:
            row_total = int(row["total_attempts"] or 0)
            row_correct = int(row["correct_attempts"] or 0)
            by_type_rows.append(
                {
                    "drill_type": row["drill_type"],
                    "total_attempts": row_total,
                    "correct_attempts": row_correct,
                    "accuracy": row_correct / row_total if row_total else None,
                }
            )
        return {
            "overall": {
                "total_attempts": total,
                "correct_attempts": correct,
                "accuracy": correct / total if total else None,
            },
            "by_type": by_type_rows,
        }
