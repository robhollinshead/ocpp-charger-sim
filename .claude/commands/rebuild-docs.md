# Rebuild Documentation PDF

Check for new documentation files, update the build script if needed, update screenshots, then build the PDF.

## Step 1 — Find undocumented Markdown files

Read `docs/scripts/build-pdf.js` and extract the `DOC_FILES` array. Then list all `.md` files directly in `docs/` (not subdirectories). Report any files present in `docs/` that are not in `DOC_FILES` and are not temporary files (i.e. not `_combined-for-pdf.md`).

## Step 2 — Update build-pdf.js for any new files

For each new `.md` file found in Step 1, insert it into `DOC_FILES` in a logical position:
- Feature guides (e.g. `offline-charging.md`, `scenarios.md`) go after `ui-guide.md` and before `out-of-scope.md`
- Reference docs (e.g. a new `api-reference.md`) go after `ocpp-support.md`
- When in doubt, add before `out-of-scope.md`

Only edit the file if there are actually new files to add.

## Step 3 — Check screenshots

Read each new `.md` file added in Step 2. Look for any references to `screenshots/` images (e.g. `![...](screenshots/foo.png)`). For each referenced screenshot:
- Check if the file exists in `docs/screenshots/`
- If it does not exist, note it for the user with a clear warning: "Screenshot `screenshots/foo.png` referenced in `foo.md` does not exist — add it before the PDF will render correctly."

Do NOT attempt to generate or create screenshot image files yourself.

## Step 4 — Build the PDF

Run the following command from the repo root:

```bash
npm run docs:pdf
```

Report the output. If it succeeds, confirm the output path (`docs/build/technical-documentation.pdf`). If it fails, show the error and stop — do not retry.
