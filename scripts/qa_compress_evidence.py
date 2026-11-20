"""Remove only generated uncompressed traces after byte-for-byte hash validation."""
import gzip
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'reports/live_recheck_20261120/deep_run'
records=[]
for p in root.glob('http_*.jsonl'):
    archive=p.with_suffix(p.suffix+'.gz')
    if not archive.exists():
        continue
    with p.open('rb') as f:
        original=hashlib.file_digest(f,'sha256').hexdigest()
    with gzip.open(archive,'rb') as f:
        unpacked=hashlib.file_digest(f,'sha256').hexdigest()
    if original!=unpacked:
        raise RuntimeError('Archive hash mismatch: '+p.name)
    records.append({'original':p.name,'archive':archive.name,'uncompressed_sha256':original,'verified_identical':True})
    p.unlink()
verification=root/'trace_compression_verification.json'
if records:
    verification.write_text(json.dumps(records,indent=2),encoding='utf-8')
archives=[]
for archive in sorted(root.glob('http_*.jsonl.gz')):
    with archive.open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    archives.append({'file':archive.name,'size_bytes':archive.stat().st_size,'sha256':digest,
                     'repository_status':'Excluded from Git because raw HTTP evidence archives exceed practical repository limits; retained locally.'})
(root/'raw_trace_manifest.json').write_text(json.dumps(archives,indent=2),encoding='utf-8')
print(json.dumps(records,indent=2))
