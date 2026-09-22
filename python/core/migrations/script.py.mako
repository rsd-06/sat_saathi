"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2  # noqa: F401 - used by rendered types
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry  # noqa: F401 - rendered bare by geoalchemy2
from sqlalchemy.dialects import postgresql  # noqa: F401 - used by rendered types

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
