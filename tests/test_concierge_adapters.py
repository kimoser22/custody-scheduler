from sqlmodel import Session, select

from concierge.adapters import SqlSenderResolver
from database.schema import UserTable


def test_sql_sender_resolver_maps_phone(session_fixture: Session) -> None:
    session_fixture.add(
        UserTable(
            id=101,
            family_id=1,
            role="Parent",
            phone="+15550001",
            custody_label="Parent A",
        )
    )
    session_fixture.commit()

    resolver = SqlSenderResolver(session_fixture)
    sender = resolver.resolve("+15550001")
    assert sender is not None
    assert sender.user_id == 101
    assert sender.custody_label == "Parent A"
    assert resolver.resolve("+1999") is None
