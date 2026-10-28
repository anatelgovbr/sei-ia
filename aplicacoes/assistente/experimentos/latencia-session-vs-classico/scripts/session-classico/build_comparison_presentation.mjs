#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { escapeHtml, renderMarkdown } from "../shared/presentation_markdown.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const experimentRoot = path.resolve(here, "..", "..");
const artifacts = path.join(experimentRoot, "artifacts");
const outputPath = path.join(
  experimentRoot,
  "apresentacoes",
  "apresentacao-comparativo.html",
);
const dataPath = path.join(artifacts, "presentation-data.json");
const presentationData = JSON.parse(fs.readFileSync(dataPath, "utf8"));

function recordsByQid(records) {
  return new Map(records.map((record) => [record.qid, record]));
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) return "N/D";
  const factor = 10 ** digits;
  const rounded = Math.round((value + 1e-12) * factor) / factor;
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(rounded);
}

function formatCost(value) {
  if (value === null || value === undefined) return "N/D";
  return `US$ ${formatNumber(value, 3)}`;
}

function responseCard(label, className, record) {
  if (!record) {
    throw new Error(`Registro ausente para ${label}.`);
  }
  const latency = record?.latency ?? {};
  const judge = record?.judge ?? {};
  const score = judge.numeric?.overall;
  const cost = record?.cost?.usd;
  const hallucination = judge.bool?.hallucination;
  const error = latency.error;
  const response =
    record?.response || (error ? `Erro: ${error}` : "Resposta não persistida.");
  const responseHtml = record?.response_html || renderMarkdown(response);
  const rationale = judge.rationale || "Avaliação não disponível.";

  return `
    <article class="response-card ${className}">
      <div class="response-head">
        <strong>${escapeHtml(label)}</strong>
        <div class="response-meta">
          overall ${formatNumber(score, 2)} · total ${formatNumber(latency.total_s, 2)} s ·
          ${formatCost(cost)} · alucinação ${hallucination === null || hallucination === undefined ? "N/D" : hallucination ? "sim" : "não"}
        </div>
      </div>
      <div class="response-body markdown-body">${responseHtml}</div>
      <details class="judge-note">
        <summary>Avaliação do judge</summary>
        <p>${escapeHtml(rationale)}</p>
      </details>
    </article>`;
}

if (![1, 2].includes(presentationData.schema_version)) {
  throw new Error(`Schema de apresentação não suportado: ${presentationData.schema_version}`);
}

const standardRecords = presentationData.methods.standard;
const miniRecords = presentationData.methods.mini;
const lunaRecords = presentationData.methods.luna;
const classicRecords = presentationData.methods.classic;
const standard = recordsByQid(standardRecords);
const mini = recordsByQid(miniRecords);
const luna = recordsByQid(lunaRecords);
const classic = recordsByQid(classicRecords);

const expectedQids = standardRecords.map((record) => record.qid);
const expectedQidSet = new Set(expectedQids);
const qidIssues = Object.entries({
  standard: standardRecords,
  mini: miniRecords,
  luna: lunaRecords,
  classic: classicRecords,
}).flatMap(([method, records]) => {
  const qids = records.map((record) => record.qid);
  const qidSet = new Set(qids);
  const missing = expectedQids.filter((qid) => !qidSet.has(qid));
  const extra = qids.filter((qid) => !expectedQidSet.has(qid));
  const duplicates = qids.filter((qid, index) => qids.indexOf(qid) !== index);
  return missing.length || extra.length || duplicates.length
    ? [`${method}: ausentes=${missing.join(",") || "nenhum"}; extras=${extra.join(",") || "nenhum"}; duplicados=${[...new Set(duplicates)].join(",") || "nenhum"}`]
    : [];
});

if (
  standardRecords.length !== 10 ||
  miniRecords.length !== 10 ||
  lunaRecords.length !== 10 ||
  classicRecords.length !== 10 ||
  qidIssues.length > 0
) {
  throw new Error(
    `Comparação incompleta: standard=${standardRecords.length}, mini=${miniRecords.length}, luna=${lunaRecords.length}, clássico=${classicRecords.length}; ${qidIssues.join(" | ") || "QIDs alinhados"}.`,
  );
}

function summarizeRecords(records) {
  const valid = records.filter(
    (record) =>
      record.judge.numeric.overall !== null && record.latency.total_s !== null,
  );
  const sum = (values) => values.reduce((total, value) => total + value, 0);
  return {
    records: records.length,
    valid_records: valid.length,
    overall_mean:
      sum(valid.map((record) => record.judge.numeric.overall)) / valid.length,
    total_mean_s:
      sum(valid.map((record) => record.latency.total_s)) / valid.length,
    cost_usd_total: sum(records.map((record) => record.cost.usd ?? 0)),
  };
}

for (const [method, records] of Object.entries(presentationData.methods)) {
  const calculated = summarizeRecords(records);
  const declared = presentationData.summary[method];
  for (const key of Object.keys(calculated)) {
    if (Math.abs(calculated[key] - declared[key]) > 1e-9) {
      throw new Error(
        `Resumo inconsistente em ${method}.${key}: calculado=${calculated[key]} declarado=${declared[key]}`,
      );
    }
  }
}

const orderedQids = expectedQids;

const casesHtml = orderedQids
  .map((qid) => {
    const referenceRecord = standard.get(qid) ?? luna.get(qid);
    const question = referenceRecord.question;
    const shortQuestion = question.replace(/\s+/g, " ").slice(0, 150);
    return `
      <details class="qa-case">
        <summary><strong>${escapeHtml(qid)}</strong> · ${escapeHtml(shortQuestion)}${shortQuestion.length < question.replace(/\s+/g, " ").length ? "…" : ""}</summary>
        <div class="qa-question"><strong>Pergunta</strong>\n${escapeHtml(question)}</div>
        <div class="response-grid">
          ${responseCard("Session standard", "standard", standard.get(qid))}
          ${responseCard("Session mini", "mini", mini.get(qid))}
          ${responseCard("Session Luna", "luna", luna.get(qid))}
          ${responseCard("Clássico atualizado", "classic", classic.get(qid))}
        </div>
      </details>`;
  })
  .join("\n");

const comparisonMethods = [
  { key: "standard", records: standard },
  { key: "mini", records: mini },
  { key: "luna", records: luna },
  { key: "classic", records: classic },
];
const tieThreshold = 0.05;

function scoreClasses(qid) {
  const scores = comparisonMethods.map(
    ({ records }) => records.get(qid)?.judge?.numeric?.overall ?? null,
  );
  const validScores = scores.filter((score) => score !== null);
  const bestScore = Math.max(...validScores);
  const contenders = scores.filter(
    (score) => score !== null && bestScore - score <= tieThreshold + 1e-9,
  );

  return scores.map((score) => {
    if (score === null) return "";
    if (contenders.length > 1 && bestScore - score <= tieThreshold + 1e-9) {
      return "tie";
    }
    return score === bestScore ? "best" : "";
  });
}

function caseCell(record, className) {
  if (!record) throw new Error("Registro ausente na tabela caso a caso.");
  return `<td${className ? ` class="${className}"` : ""}>${formatNumber(
    record.judge.numeric.overall,
    2,
  )} / ${formatNumber(record.latency.total_s, 1)} s / ${formatNumber(
    record.cost.usd,
    3,
  )}</td>`;
}

const caseRowsHtml = orderedQids
  .map((qid) => {
    const classes = scoreClasses(qid);
    return `              <tr><td>${escapeHtml(qid)}</td>${caseCell(
      standard.get(qid),
      classes[0],
    )}${caseCell(mini.get(qid), classes[1])}${caseCell(
      luna.get(qid),
      classes[2],
    )}${caseCell(
      classic.get(qid),
      classes[3],
    )}</tr>`;
  })
  .join("\n");

const startMarker = "<!-- Q&A GENERATED START -->";
const endMarker = "<!-- Q&A GENERATED END -->";
const tableStartMarker = "<!-- CASE TABLE GENERATED START -->";
const tableEndMarker = "<!-- CASE TABLE GENERATED END -->";

function replaceGeneratedSection(html, start, end, content) {
  const startIndex = html.indexOf(start);
  const endIndex = html.indexOf(end);
  if (startIndex === -1 || endIndex === -1 || endIndex < startIndex) {
    throw new Error(`Marcadores não encontrados: ${start} / ${end}.`);
  }
  return (
    html.slice(0, startIndex + start.length) +
    "\n" +
    content +
    "\n          " +
    html.slice(endIndex)
  );
}

const html = fs.readFileSync(outputPath, "utf8");
const expectedSummaryValues = [
  formatNumber(presentationData.summary.standard.overall_mean, 3),
  formatNumber(presentationData.summary.mini.overall_mean, 3),
  formatNumber(presentationData.summary.luna.overall_mean, 3),
  formatNumber(presentationData.summary.classic.overall_mean, 3),
  `${formatNumber(presentationData.summary.standard.total_mean_s, 2)} s`,
  `${formatNumber(presentationData.summary.mini.total_mean_s, 2)} s`,
  `${formatNumber(presentationData.summary.luna.total_mean_s, 2)} s`,
  `${formatNumber(presentationData.summary.classic.total_mean_s, 2)} s`,
  formatCost(presentationData.summary.standard.cost_usd_total),
  formatCost(presentationData.summary.mini.cost_usd_total),
  formatCost(presentationData.summary.luna.cost_usd_total),
  formatCost(presentationData.summary.classic.cost_usd_total),
];
const missingSummaryValues = expectedSummaryValues.filter(
  (value) => !html.includes(value),
);
if (missingSummaryValues.length > 0) {
  throw new Error(
    `Resumo da apresentação diverge de presentation-data.json: ${missingSummaryValues.join(", ")}`,
  );
}
const withCaseTable = replaceGeneratedSection(
  html,
  tableStartMarker,
  tableEndMarker,
  caseRowsHtml,
);
const updated = replaceGeneratedSection(
  withCaseTable,
  startMarker,
  endMarker,
  casesHtml,
);

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, updated.replace(/^[\t ]+$/gm, ""));
console.log(
  `Apresentação validada e atualizada com quatro métodos e ${orderedQids.length} QIDs alinhados: ${outputPath}`,
);
