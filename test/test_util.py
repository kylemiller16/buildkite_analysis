import os
import sys
from pathlib import Path

import pytest
import json

# Add project root to path for imports
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lib.util import get_all_job_ids  # type: ignore  # noqa: E402


def get_data_file(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "data", filename)


build_with_2_retries = 'wayve-dot-ai__federated-hil-gen2-dev__448.json'



class Test_get_all_job_ids:
    def test_get_all_job_ids(self):
        with open(get_data_file(build_with_2_retries), "r", encoding="utf-8") as f:
            build = json.load(f)
        job_ids = [job for job in get_all_job_ids(build) if "federated-hil-gen2-dev-validation-rcm-aem-evt-1" in job["job_name"]]
        assert len(job_ids) == 2
        assert job_ids[0]["retry"] == False
        assert job_ids[1]["retry"] == True



if __name__ == "__main__":
    pytest.main()
