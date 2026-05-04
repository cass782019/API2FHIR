"""initial

Revision ID: 0001
Revises:
Create Date: 2026-04-30
"""
from __future__ import annotations

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Banco 'forge' criado pelo postgres-init.sh.
    # Tabelas de aplicação serão adicionadas em migrações futuras.
    pass


def downgrade() -> None:
    pass
