import asyncio
import importlib
import os
import tempfile
from pathlib import Path

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture(scope="session")
def seeded_db():
    tmp = Path(tempfile.mkdtemp()) / "vciso_test.db"
    os.environ["VCISO_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}"
    import vciso.db

    importlib.reload(vciso.db)
    import vciso.seed

    importlib.reload(vciso.seed)
    asyncio.run(vciso.seed.seed())
    yield tmp
    tmp.unlink(missing_ok=True)
