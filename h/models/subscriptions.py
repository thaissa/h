from enum import Enum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from h.db import Base


class Subscriptions(Base):
    """Permission from the user to send different types of communication."""

    class Type(str, Enum):
        """
        All the different types of subscriptions we support.

        Not integrated with the type field, but it would be nice if it was.
        """

        REPLY = "reply"
        MENTION = "mention"
        MODERATION = "moderation"

    __tablename__ = "subscriptions"

    id = sa.Column(sa.Integer, autoincrement=True, primary_key=True)

    uri = sa.Column(sa.UnicodeText(), nullable=False)
    """Identifier of the entity that is subscribing.

    Currently this is always a fully qualified user id.
    """

    type = sa.Column(sa.VARCHAR(64), nullable=False)
    """The type of subscription the entity has.

    Currently this can only be "reply".
    """

    active: Mapped[bool] = mapped_column(default=True)
    """Whether the subscription is active or not."""

    __table_args__ = (sa.Index("subs_uri_lower_idx_subscriptions", sa.func.lower(uri)),)

    def __repr__(self):
        return f"<Subscription uri={self.uri} type={self.type} active={self.active}>"
