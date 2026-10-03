# Dashboard operations refresh

Owner request: replace stale download/status views, show source freshness and all
seven jobs, and simplify Home. Closes #156.

LOCAL-BECAUSE: live-checkout/jobs/raw-data: this review needs the Studio's local
acquisition journals and browser preview. Implementation is isolated. No purchase,
scoring, registration, live checkout edit or launchd change is authorized here.

Validation focuses on missing/corrupt/stale sources, overlapping attempt IDs,
loaded versus successful jobs, and read-only/secret boundaries. The dashboard is
an observation tool, never acquisition authority. Independent review and hub
coordination precede deployment.
