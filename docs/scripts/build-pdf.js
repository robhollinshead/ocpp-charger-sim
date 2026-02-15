/**
 * Build a single PDF from the technical documentation Markdown files.
 * Renders the Mermaid diagram to PNG first so it appears correctly in the PDF.
 * Requires: npm install (at repo root) for md-to-pdf and @mermaid-js/mermaid-cli.
 * Usage: from repo root, npm run docs:pdf
 * Output: docs/build/technical-documentation.pdf
 */

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const { mdToPdf } = require('md-to-pdf');

const REPO_ROOT = path.join(__dirname, '..', '..');
const DOCS_DIR = path.join(__dirname, '..');
const DIAGRAMS_DIR = path.join(DOCS_DIR, 'diagrams');
const BUILD_DIR = path.join(DOCS_DIR, 'build');
const OUTPUT_PDF = path.join(BUILD_DIR, 'technical-documentation.pdf');

const DOC_FILES = [
  'README.md',
  'architecture.md',
  'ocpp-support.md',
  'edge-cases.md',
  'ui-guide.md',
  'out-of-scope.md',
];

async function main() {
  fs.mkdirSync(BUILD_DIR, { recursive: true });
  fs.mkdirSync(DIAGRAMS_DIR, { recursive: true });

  const mmdPath = path.join(DIAGRAMS_DIR, 'architecture.mmd');
  const pngPath = path.join(DIAGRAMS_DIR, 'architecture.png');
  if (fs.existsSync(mmdPath)) {
    try {
      execSync(`npx --yes -p @mermaid-js/mermaid-cli mmdc -i "${mmdPath}" -o "${pngPath}" -b white`, {
        cwd: REPO_ROOT,
        stdio: 'inherit',
      });
    } catch (e) {
      console.warn('Mermaid diagram render failed (install @mermaid-js/mermaid-cli?). Using existing image if present.');
    }
  }

  const parts = [];
  for (const name of DOC_FILES) {
    const filePath = path.join(DOCS_DIR, name);
    if (fs.existsSync(filePath)) {
      parts.push(fs.readFileSync(filePath, 'utf8'));
      parts.push('\n\n---\n\n');
    }
  }
  if (parts.length === 0) {
    throw new Error('No doc files found in docs/');
  }
  const combined = parts.join('').replace(/\n\n---\n\n$/, '\n');

  const tempMd = path.join(DOCS_DIR, '_combined-for-pdf.md');
  fs.writeFileSync(tempMd, combined, 'utf8');

  try {
    await mdToPdf(
      { path: tempMd },
      {
        dest: OUTPUT_PDF,
        pdf_options: { format: 'A4', printBackground: true },
      }
    );
    console.log('Written:', OUTPUT_PDF);
  } finally {
    try {
      fs.unlinkSync(tempMd);
    } catch (_) {}
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
