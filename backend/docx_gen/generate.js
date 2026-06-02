/**
 * Generates a properly formatted A4 resume DOCX from structured JSON.
 * Input: JSON via stdin or first arg (path to JSON file)
 * Output: DOCX file written to path specified in JSON.output_path
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, TabStopType,
  TabStopPosition, LevelFormat, HeadingLevel,
} = require("docx");
const fs = require("fs");
const path = require("path");

// ── Read input ──────────────────────────────────────────────
let data;
if (process.argv[2]) {
  data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
} else {
  data = JSON.parse(fs.readFileSync("/dev/stdin", "utf8"));
}

const {
  name, contact, summary, skills, experience, projects, education,
  certifications, output_path,
} = data;

// ── Helpers ──────────────────────────────────────────────────
const FONT = "Calibri";
const COLOR_ACCENT = "1F3864"; // dark navy
const COLOR_RULE = "2E75B6";   // blue section rule
const BODY_SIZE = 19;          // 9.5pt
const HEAD_SIZE = 21;          // 10.5pt

function rule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR_RULE, space: 1 } },
    spacing: { before: 60, after: 60 },
    children: [],
  });
}

function sectionHeader(text) {
  return new Paragraph({
    children: [
      new TextRun({ text: text.toUpperCase(), bold: true, size: HEAD_SIZE + 1, font: FONT, color: COLOR_ACCENT }),
    ],
    spacing: { before: 120, after: 20 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: COLOR_RULE, space: 1 } },
  });
}

function bullet(text, bold_ranges = []) {
  // bold_ranges: array of strings to bold within the text
  let remaining = text;
  const runs = [];

  if (bold_ranges.length === 0) {
    runs.push(new TextRun({ text, font: FONT, size: BODY_SIZE }));
  } else {
    // Split text around bold markers
    let cursor = 0;
    const positions = [];
    for (const term of bold_ranges) {
      let idx = text.indexOf(term, cursor);
      while (idx !== -1) {
        positions.push({ start: idx, end: idx + term.length, term });
        idx = text.indexOf(term, idx + 1);
      }
    }
    positions.sort((a, b) => a.start - b.start);

    let pos = 0;
    for (const p of positions) {
      if (p.start > pos) {
        runs.push(new TextRun({ text: text.slice(pos, p.start), font: FONT, size: BODY_SIZE }));
      }
      runs.push(new TextRun({ text: p.term, bold: true, font: FONT, size: BODY_SIZE }));
      pos = p.end;
    }
    if (pos < text.length) {
      runs.push(new TextRun({ text: text.slice(pos), font: FONT, size: BODY_SIZE }));
    }
  }

  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: runs,
    spacing: { before: 20, after: 20 },
  });
}

function entryHeader(left, right) {
  return new Paragraph({
    children: [
      new TextRun({ text: left, bold: true, font: FONT, size: HEAD_SIZE }),
      new TextRun({ text: "\t" + right, font: FONT, size: BODY_SIZE, color: "555555" }),
    ],
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
    spacing: { before: 80, after: 10 },
  });
}

function subHeader(left, right) {
  return new Paragraph({
    children: [
      new TextRun({ text: left, italics: true, font: FONT, size: BODY_SIZE, color: "444444" }),
      new TextRun({ text: "\t" + (right || ""), font: FONT, size: BODY_SIZE, color: "777777" }),
    ],
    tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
    spacing: { before: 0, after: 10 },
  });
}

// ── Skills table ─────────────────────────────────────────────
function skillsBlock(skills) {
  const rows = Object.entries(skills).map(([label, value]) => {
    const valueStr = Array.isArray(value) ? value.join(", ") : value;
    return new TableRow({
      children: [
        new TableCell({
          width: { size: 1800, type: WidthType.DXA },
          borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } },
          children: [new Paragraph({ children: [new TextRun({ text: label + ":", bold: true, font: FONT, size: BODY_SIZE })] })],
        }),
        new TableCell({
          width: { size: 7200, type: WidthType.DXA },
          borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } },
          children: [new Paragraph({ children: [new TextRun({ text: valueStr, font: FONT, size: BODY_SIZE })] })],
        }),
      ],
    });
  });

  return new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [1800, 7200],
    borders: {
      top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideH: { style: BorderStyle.NONE }, insideV: { style: BorderStyle.NONE },
    },
    rows,
  });
}

// ── Build document ───────────────────────────────────────────
const children = [];

// Name
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: name, bold: true, size: 32, font: FONT, color: COLOR_ACCENT })],
  spacing: { before: 0, after: 40 },
}));

// Contact line
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: contact, font: FONT, size: BODY_SIZE - 1, color: "555555" })],
  spacing: { before: 0, after: 60 },
}));

// Summary
children.push(sectionHeader("Summary"));
children.push(new Paragraph({
  children: [new TextRun({ text: summary, font: FONT, size: BODY_SIZE, italics: false })],
  spacing: { before: 40, after: 40 },
}));

// Skills
children.push(sectionHeader("Skills"));
children.push(skillsBlock(skills));

// Experience
children.push(sectionHeader("Experience"));
for (const exp of experience) {
  children.push(entryHeader(
    `${exp.title} | ${exp.company}`,
    `${exp.dates} | ${exp.location || ""}`,
  ));
  for (const b of exp.bullets) {
    children.push(bullet(b, exp.bold_terms || []));
  }
}

// Projects
children.push(sectionHeader("Projects"));
for (const proj of projects) {
  children.push(entryHeader(proj.name, proj.context || ""));
  children.push(subHeader(Array.isArray(proj.tech) ? proj.tech.join(", ") : proj.tech, ""));
  for (const b of proj.bullets) {
    children.push(bullet(b, proj.bold_terms || []));
  }
}

// Education
children.push(sectionHeader("Education"));
for (const ed of education) {
  children.push(entryHeader(ed.degree, ed.dates));
  children.push(new Paragraph({
    children: [new TextRun({ text: ed.institution, font: FONT, size: BODY_SIZE, italics: true, color: "555555" })],
    spacing: { before: 0, after: 20 },
  }));
}

// Certifications
if (certifications && certifications.length > 0) {
  children.push(sectionHeader("Certifications"));
  children.push(new Paragraph({
    children: [new TextRun({ text: certifications.join(" | "), font: FONT, size: BODY_SIZE })],
    spacing: { before: 40, after: 0 },
  }));
}

// ── Create document ───────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: {
          paragraph: { indent: { left: 360, hanging: 180 } },
          run: { font: "Symbol", size: BODY_SIZE },
        },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: BODY_SIZE, color: "222222" } },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 720, right: 720, bottom: 720, left: 720 }, // 0.5in margins
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
