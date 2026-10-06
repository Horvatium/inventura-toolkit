from sqlalchemy.orm import Session

from inventura.core.counting import DocumentStatus
from inventura.core.variance import VarianceRules
from inventura.demo import seed_demo
from inventura.io.column_mapping import ColumnMapping
from inventura.services.documents import list_documents


def test_demo_fills_an_empty_database_once(session: Session, mapping: ColumnMapping) -> None:
    result = seed_demo(session, mapping, VarianceRules(), materials=300, seed=3)

    assert result is not None
    assert result.documents == 12
    # Racks in every state, for the dashboard and the screenshots.
    assert set(result.statuses) == set(DocumentStatus)
    progress = list_documents(session, result.snapshot_id)
    assert progress[0].document.status is DocumentStatus.ZAKLJUCEN
    assert progress[-1].counted == 0

    assert seed_demo(session, mapping, VarianceRules(), materials=300, seed=3) is None
