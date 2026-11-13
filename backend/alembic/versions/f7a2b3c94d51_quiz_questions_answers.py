"""v2 quiz: per-session generated questions + per-player answers.

The 'Know Your Partner' quest generates questions about each partner's
profile interests at activation; answers ride the authenticated phone.

Revision ID: f7a2b3c94d51
Revises: d5e8f2a94c31
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a2b3c94d51"
down_revision = "d5e8f2a94c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("quest_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answerer_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_index", sa.SmallInteger(), nullable=False),
        sa.UniqueConstraint(
            "session_id", "answerer_user_id", "question_index",
            name="uq_quiz_question_per_answerer",
        ),
        sa.CheckConstraint("correct_index BETWEEN 0 AND 3", name="ck_quiz_correct_range"),
    )
    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("quest_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("choice", sa.SmallInteger(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "user_id", "question_index", name="uq_quiz_answer"),
        sa.CheckConstraint("choice BETWEEN 0 AND 3", name="ck_quiz_choice_range"),
    )


def downgrade() -> None:
    op.drop_table("quiz_answers")
    op.drop_table("quiz_questions")
