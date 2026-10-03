"""Bounded GET-only authority transport retries; no stale/revoked fallback."""
import json
import subprocess
import time
import prior_authority

TRANSIENT=('dial tcp','i/o timeout','connection reset','tls handshake timeout','temporary failure','context deadline exceeded','http 502','http 503','http 504')

def fetch_live_comment(cid,*,query=None,sleep=time.sleep):
 if not str(cid).isdigit():raise ValueError('invalid approval comment ID')
 def native():return subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True,stderr=subprocess.PIPE,timeout=10)
 query=query or native
 for i in range(3):
  try:raw=query()
  except subprocess.TimeoutExpired:
   if i==2:raise ValueError('live authority transport exhausted') from None
  except subprocess.CalledProcessError as e:
   detail=e.stderr or '';detail=detail.decode(errors='replace') if isinstance(detail,bytes) else detail
   if not any(marker in detail.lower() for marker in TRANSIENT) or i==2:raise ValueError('live authority transport failed') from None
  else:
   # Parse/body/login/state mismatch is not a transport failure and never retries.
   return json.loads(raw)
  sleep(i+1)
 raise ValueError('live authority unavailable')


def check(base,auth,manifest,root,commit,context,*,fetch=None):
 return prior_authority.check(base,auth,manifest,root,commit,context,fetch=fetch or fetch_live_comment)
