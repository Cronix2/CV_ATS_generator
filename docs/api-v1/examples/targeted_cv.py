"""Run from the repository root after installing httpx; no production credentials included."""
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    output = Path('passefiltre-demo-output')
    output.mkdir(mode=0o700, exist_ok=True)
    cv = json.loads(Path(__file__).with_name('cv.json').read_text())['cv']
    with httpx.Client(
        base_url=os.environ.get('PF_URL', 'http://localhost:8000/api/v1') + '/',
        headers={'Authorization': 'Bearer ' + os.environ['PF_KEY'],
                 'X-PasseFiltre-User-Id': os.environ['PF_USER']}, timeout=30,
    ) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            # Do not dump response bodies, request headers or CVs into application logs.
            if response.is_error:
                raise RuntimeError(f'API HTTP {response.status_code}; request_id={response.headers.get("x-request-id", "")}')
            return response

        def post(path, body):
            # Persist this key in your own job record before retrying an uncertain request.
            return call('POST', path, json=body, headers={'Idempotency-Key': str(uuid4())}).json()

        def wait(ident):
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                job = call('GET', 'jobs/' + ident).json()
                if job['status'] == 'succeeded':
                    return job['result']
                if job['status'] in ('failed', 'cancelled', 'needs_code', 'needs_captcha'):
                    raise RuntimeError('Job requires attention: ' + job['status'])
                time.sleep(2)
            raise TimeoutError('Poll deadline reached; keep the job ID to resume polling')

        task = post('workflows', {'schema_version': '1', 'cv': cv,
                    'offer': {'title': 'Développement Python', 'company': 'Exemple', 'text': 'Maintenance API Python'},
                    'use_ai': False})
        ident = wait(task['id'])['resource_id']
        workflow = call('GET', 'workflows/' + ident).json()
        review_file = output / 'workflow-to-review.json'
        review_file.write_text(json.dumps(workflow, ensure_ascii=False, indent=2))
        print('Lire le CV source, le brouillon et les changements dans', review_file)
        if input('Après vérification humaine, saisir APPROUVER : ') != 'APPROUVER':
            print('Brouillon conservé sans approbation ni export.')
            return
        approved = post('workflows/' + ident + '/approve', {
            'version': workflow['version'], 'digest': workflow['data']['digest'], 'confirmed': True})
        for job in approved['jobs']:
            export_id = wait(job['id'])['resource_id']
            meta = call('GET', 'exports/' + export_id).json()['data']
            data = call('GET', 'exports/' + export_id + '/download').content
            # Do not use a remote filename as a filesystem path.
            suffix = '.pdf' if meta['mime'] == 'application/pdf' else '.docx'
            (output / ('cv' + suffix)).write_bytes(data)
        print('PDF et DOCX enregistrés dans', output)


if __name__ == '__main__':
    main()
