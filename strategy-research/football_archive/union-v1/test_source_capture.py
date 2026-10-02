import json
from pathlib import Path
import shutil
import sys
import pytest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import epoch
BUNDLE=HERE.parent/'acquisition/football-archive-v4'


@pytest.mark.parametrize('name',['executor.py','builder.py','price_eligibility.py','validator.py','archive_markets/cache.py'])
def test_changed_v4_source_never_executes_marker(tmp_path,name):
    bundle=tmp_path/'v4';shutil.copytree(BUNDLE,bundle)
    marker=tmp_path/'EXECUTED';(bundle/name).write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n")
    with pytest.raises(ValueError):epoch.source_executor(bundle)
    assert not marker.exists()


def test_captured_v4_never_reopens_executable_bytes_after_verification(tmp_path,monkeypatch):
    bundle=tmp_path/'v4';shutil.copytree(BUNDLE,bundle);original=epoch.verified_v4_bytes
    marker=tmp_path/'EXECUTED'
    def capture_then_swap(path):
        data=original(path)
        for name in ('executor.py','builder.py','price_eligibility.py','validator.py'):
            (path/name).write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n")
        return data
    monkeypatch.setattr(epoch,'verified_v4_bytes',capture_then_swap)
    # Compiled captured original code stays safe; validator's data reread detects
    # the changed freeze and refuses it before anything can load a key/transport.
    with pytest.raises(ValueError):epoch.source_executor(bundle)
    assert not marker.exists()
