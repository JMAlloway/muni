"""Baseline revision (empty).

Run `alembic revision --autogenerate -m "baseline"` to replace with a real schema snapshot.
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Placeholder: generate a real baseline with `alembic revision --autogenerate`
    pass


def downgrade() -> None:
    # Nothing to rollback for the placeholder baseline.
    pass
