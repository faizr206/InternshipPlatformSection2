# IPP walking skeleton demo

A dependency-free course prototype of the **Internship Practicum Platform (IPP)**.

Live demo: <https://ray-suton.github.io/ipp-walking-skeleton-demo/>

The Overview, journey tracker and activity feed show the handoffs: Employer HR submits a listing, the University Administrator publishes it, a Student applies, and Employer HR and Faculty Reviewer read the linked application. Application and placement status are separate; placement remains **Not placed**.

## Shared synthetic data

The app fetches [data/ipp_sample_data.json](data/ipp_sample_data.json) on startup. Its field names and supplied records are preserved for P04/P05 and P06/P07.

- Five profile records represent four students. Select a synthetic student in the Student view; the app uses the highest submitted profile version and ignores drafts. Layla starts at version 2.
- Initially only **OP-028, OP-031 and OP-034** are shown to students. Listings must be both published and open to be browsed or applied to; closed OP-036 and unpublished OP-039 are excluded.
- Student results, applications and dialogs omit supervisor_name and supervisor_contact. The downloadable JSON retains these synthetic fields for the P07 handoff.
- Corrections append a profile version; earlier versions and the shared file remain unchanged. Noor's missing interests and availability are shown explicitly.
- The synthetic-data banner stays visible. Role switching and HR authorization are simulated; there is no login or shared backend.

Records are browser-local under ipp-demo-v2. Old ipp-demo-v1 records are left untouched and are not loaded. **Reset demo data** restores the shared fixture.

## Run locally

~~~bash
npm start     # http://127.0.0.1:4173/ (next available port if busy)
npm test      # Node built-in runner; no dependencies to install
npm run stamp # refresh asset hashes after changing styles or src/*.js
~~~

No build step. Use the server: startup fetches JSON, so opening index.html through file:// is unsupported. Network access is needed to load the static assets and seed; offline operation is not guaranteed.

See [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md) for architecture and the demo script, [feature-list.json](feature-list.json) for the feature inventory, and [PROGRESS.md](PROGRESS.md) for verification and remaining work.
