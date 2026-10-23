import hashlib
import os
import subprocess
import sys
from io import BytesIO
from zipfile import ZipFile

import pytest
from app.models import CV, Profile, Basics, Experience
from app.services.cv import render


@pytest.mark.parametrize('fmt', ['pdf', 'docx'])
def test_render_is_stable_between_processes(fmt):
    code = f'from app.services.cv import render; from app.models import CV, Profile; import hashlib; print(hashlib.sha256(render(CV(profile=Profile()), {fmt!r}).data).hexdigest())'
    hashes = [subprocess.check_output([sys.executable, '-c', code], env={**os.environ, 'PYTHONHASHSEED': str(i)}) for i in (1, 2)]
    assert hashes[0] == hashes[1]


def test_export_content_and_exclusions():
    cv = CV(profile=Profile(basics=Basics(full_name='Jane Example'), experience=[
        Experience(title='Engineer', company='Visible'), Experience(title='Hidden', include=False)]))
    result = render(cv, 'docx')
    with ZipFile(BytesIO(result.data)) as z:
        xml = z.read('word/document.xml').decode()
        assert 'Visible' in xml and 'Hidden' not in xml
        assert '<w:tbl>' not in xml
    assert render(cv, 'pdf').data.startswith(b'%PDF-')
    assert result.filename == 'CV-Jane-Example.docx'
