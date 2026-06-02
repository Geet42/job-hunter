/**
 * Generates a properly formatted A4 resume DOCX from structured JSON.
 * Input: path to JSON file as first argument
 * Output: DOCX written to path in JSON.output_path
 */

const {
  Document, Packer, Paragraph, TextRun,
  AlignmentType, BorderStyle, TabStopType, TabStopPosition,
} = require("docx");
const fs   = require("fs");
const path = require("path");

// ── Read input ───────────────────────────────────────────────
let data;
if (process.argv[2]) {
  data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
} else {
  data = JSON.parse(fs.readFileSync("/dev/stdin", "utf8"));
}

const { name, contact, summary, skills, experience, projects, education, certifications, output_path } = data;

// ── Design tokens ────────────────────────────────────────────
const FONT       = "Calibri";
const COLOR_HEAD = "1F3864";   // dark navy  — section headers
const COLOR_RULE = "2E75B6";   // blue       — rule lines
const COLOR_SUB  = "444444";   // dark gray  — company / tech line
const COLOR_META = "666666";   // medium     — dates / location
const BODY_PT    = 19;         // 9.5 pt  (half-points)
const HEAD_PT    = 20;         // 10 pt
const NAME_PT    = 32;         // 16 pt

// ── Helpers ──────────────────────────────────────────────────

/** Horizontal rule rendered as a bottom border on an empty paragraph */
function rule() {
  return new Paragraph({
    children: [],
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR_RULE, space: 1 } },
    spacing: { before: 80, after: 40 },
  });
}

/** Uppercase section header with underline rule */
function sectionHeader(text) {
  return new Paragraph({
    children: [
      new TextRun({ text: text.toUpperCase(), bold: true, size: HEAD_PT + 2, font: FONT, color: COLOR_HEAD }),
    ],
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: COLOR_RULE, space: 1 } },
    spacing: { before: 140, after: 30 },
  });
}

/**
 * Bullet point — uses "•" (U+2022) in Calibri font directly as a TextRun.
 * No Word numbering XML = no square-box rendering bug across viewers.
 * bold_ranges: list of strings to bold within the text.
 */
function bullet(text, bold_ranges = []) {
  const runs = [];

  // Inline bullet character in Calibri — renders correctly in Word, LibreOffice, PDF
  runs.push(new TextRun({ text: "•  ", font: FONT, size: BODY_PT }));

  if (!bold_ranges || bold_ranges.length === 0) {
    runs.push(new TextRun({ text, font: FONT, size: BODY_PT }));
  } else {
    // Find all bold ranges and split text around them
    const positions = [];
    for (const term of bold_ranges) {
      if (!term) continue;
      let idx = text.indexOf(term);
      while (idx !== -1) {
        positions.push({ start: idx, end: idx + term.length, term });
        idx = text.indexOf(term, idx + 1);
      }
    }
    positions.sort((a, b) => a.start - b.start);

    // Remove overlapping ranges
    const merged = [];
    for (const p of positions) {
      if (merged.length === 0 || p.start >= merged[merged.length - 1].end) {
        merged.push(p);
      }
    }

    let pos = 0;
    for (const p of merged) {
      if (p.start > pos) {
        runs.push(new TextRun({ text: text.slice(pos, p.start), font: FONT, size: BODY_PT }));
      }
      runs.push(new TextRun({ text: p.term, bold: true, font: FONT, size: BODY_PT }));
      pos = p.end;
    }
    if (pos < text.length) {
      runs.push(new TextRun({ text: text.slice(pos), font: FONT, size: BODY_PT }));
    }
  }

  return new Paragraph({
    children: runs,
    indent: { left: 240, hanging: 240 },
    spacing: { before: 20, after: 20 },
  });
}

/** Left-bold + right-gray tab-stop line (job title | company ... date | location) */
function entryHeader(left, right) {
  return new Paragraph({
    children: [
      new TextRun({ text: left, bold: true, font: FONT, size: HEAD_PT }),
      new TextRun({ text: "\t" + right, font: FONT, size: BODY_PT, color: COLOR_META }),
    ],
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
    spacing: { before: 100, after: 10 },
  });
}

/** Italic secondary line (tech stack / sub-company line) */
function subLine(text) {
  return new Paragraph({
    children: [new TextRun({ text, italics: true, font: FONT, size: BODY_PT - 1, color: COLOR_SUB })],
    spacing: { before: 0, after: 8 },
  });
}

/**
 * Skills rendered as plain "Label: value1, value2" lines — NO table.
 * Fixes the table-cell rendering that looked off in some PDF exports.
 */
function skillsLines(skills) {
  return Object.entries(skills).map(([label, value]) => {
    const valueStr = Array.isArray(value) ? value.join(", ") : (value || "");
    return new Paragraph({
      children: [
        new TextRun({ text: label + ": ", bold: true, font: FONT, size: BODY_PT }),
        new TextRun({ text: valueStr, font: FONT, size: BODY_PT }),
      ],
      spacing: { before: 16, after: 16 },
    });
  });
}

// ── Build document sections ──────────────────────────────────
const children = [];

// Name
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: name, bold: true, size: NAME_PT, font: FONT, color: COLOR_HEAD })],
  spacing: { before: 0, after: 40 },
}));

// Contact
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: contact, font: FONT, size: BODY_PT - 1, color: COLOR_SUB })],
  spacing: { before: 0, after: 80 },
}));

// Summary
children.push(sectionHeader("Summary"));
children.push(new Paragraph({
  children: [new TextRun({ text: summary, font: FONT, size: BODY_PT })],
  spacing: { before: 30, after: 20 },
}));

// Skills — plain lines, no table
children.push(sectionHeader("Skills"));
children.push(...skillsLines(skills));

// Experience
children.push(sectionHeader("Experience"));
for (const exp of (experience || [])) {
  const rightText = [exp.dates, exp.location].filter(Boolean).join(" | ");
  children.push(entryHeader(`${exp.title} | ${exp.company}`, rightText));
  for (const b of (exp.bullets || [])) {
    children.push(bullet(b, exp.bold_terms || []));
  }
}

// Projects
children.push(sectionHeader("Projects"));
for (const proj of (projects || [])) {
  children.push(entryHeader(proj.name, proj.context || ""));
  const techStr = Array.isArray(proj.tech) ? proj.tech.join(", ") : (proj.tech || "");
  if (techStr) children.push(subLine(techStr));
  for (const b of (proj.bullets || [])) {
    children.push(bullet(b, proj.bold_terms || []));
  }
}

// Education
children.push(sectionHeader("Education"));
for (const ed of (education || [])) {
  children.push(entryHeader(ed.degree, ed.dates || ""));
  if (ed.institution) children.push(subLine(ed.institution));
}

// Certifications
if (certifications && certifications.length > 0) {
  children.push(sectionHeader("Certifications"));
  children.push(new Paragraph({
    children: [new TextRun({ text: certifications.join("  |  "), font: FONT, size: BODY_PT })],
    spacing: { before: 30, after: 0 },
  }));
}

// ── Assemble and write ───────────────────────────────────────
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: BODY_PT, color: "222222" } },
    },
  },
  sections: [{
    properties: {
      page: {
        size:   { width: 11906, height: 16838 },          // A4
        margin: { top: 720, right: 800, bottom: 720, left: 800 }, // ~0.55 in
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const outPath = output_path || path.join(__dirname, "resume_output.docx");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, buf);
  console.log("OK:" + outPath);
}).catch((err) => {
  console.error("ERROR:" + err.message);
  process.exit(1);
});
