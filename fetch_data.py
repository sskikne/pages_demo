#!/usr/bin/env python3
"""Fetch standards coverage data from the Learning Commons Knowledge Graph API
and save it as a static JSON file for the GitHub Pages site."""

import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

# Load config from .env.local
def load_env():
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env

env = load_env()
API_KEY = env['KG_API_KEY']
BASE_URL = env['KG_API_URL'] + '/v0'

GRADE_LEVELS = ['PK', 'K'] + [str(i) for i in range(1, 13)]

def api_get(path, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url += '?' + urlencode(params, doseq=True)
    req = Request(url, headers={'x-api-key': API_KEY})
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        return None

def fetch_all_standards(framework_uuid):
    """Fetch all standards for a framework, handling pagination."""
    all_standards = []
    cursor = None
    while True:
        params = {
            'standardsFrameworkCaseIdentifierUUID': framework_uuid,
            'normalizedStatementType': 'Standard',
            'limit': 1000,
        }
        if cursor:
            params['cursor'] = cursor
        result = api_get('/academic-standards', params)
        if not result:
            break
        all_standards.extend(result.get('data', []))
        pagination = result.get('pagination', {})
        if pagination.get('hasMore') and pagination.get('nextCursor'):
            cursor = pagination['nextCursor']
        else:
            break
    return all_standards

def main():
    print("Fetching standards frameworks...")
    frameworks_resp = api_get('/standards-frameworks')
    if not frameworks_resp:
        print("Failed to fetch frameworks", file=sys.stderr)
        sys.exit(1)

    frameworks = frameworks_resp['data']
    print(f"Found {len(frameworks)} frameworks")

    # Build coverage data: subject -> jurisdiction -> grade -> count
    coverage = {}
    framework_info = {}

    for i, fw in enumerate(frameworks):
        subject = fw['academicSubject']
        jurisdiction = fw['jurisdiction']
        fw_uuid = fw['caseIdentifierUUID']
        fw_name = fw['name']

        print(f"[{i+1}/{len(frameworks)}] {fw_name}...")

        standards = fetch_all_standards(fw_uuid)
        print(f"  -> {len(standards)} standards")

        # Count standards per grade level
        grade_counts = {}
        for std in standards:
            grades = std.get('gradeLevel') or []
            for g in grades:
                if g in GRADE_LEVELS:
                    grade_counts[g] = grade_counts.get(g, 0) + 1

        if subject not in coverage:
            coverage[subject] = {}
        if jurisdiction not in coverage[subject]:
            coverage[subject][jurisdiction] = {}

        coverage[subject][jurisdiction] = {
            'frameworkName': fw_name,
            'frameworkId': fw['identifier'],
            'totalStandards': len(standards),
            'grades': grade_counts,
        }

        # Small delay to be respectful to the API
        time.sleep(0.1)

    # Save output
    output = {
        'generatedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'subjects': sorted(coverage.keys()),
        'gradeLevels': GRADE_LEVELS,
        'coverage': coverage,
    }

    os.makedirs('docs', exist_ok=True)
    output_path = os.path.join(os.path.dirname(__file__), 'docs', 'data.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nData saved to {output_path}")
    print(f"Subjects: {output['subjects']}")
    total_entries = sum(
        len(jurisdictions) for jurisdictions in coverage.values()
    )
    print(f"Total state/subject entries: {total_entries}")

if __name__ == '__main__':
    main()
