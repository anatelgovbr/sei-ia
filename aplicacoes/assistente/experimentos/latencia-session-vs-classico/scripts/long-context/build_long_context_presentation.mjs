#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { escapeHtml, renderMarkdown } from "../shared/presentation_markdown.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const experimentRoot = path.resolve(here, "..", "..");
const artifactPath = path.join(experimentRoot, "artifacts", "long-context-presentation-data.json");
const outputPath = path.join(
  experimentRoot,
  "apresentacoes",
  "apresentacao-long-context.html",
);
const startMarker = "<!-- LONG CONTEXT CASES GENERATED START -->";
const endMarker = "<!-- LONG CONTEXT CASES GENERATED END -->";
const expectedIds = [
  "case-0960k-q1-factual",
  "case-0960k-q2-synthesis",
  "case-0960k-q3-insufficient-evidence",
  "case-5120k-q1-factual",
  "case-5120k-q2-synthesis",
  "case-5120k-q3-insufficient-evidence",
  "case-6260k-q1-factual",
  "case-6260k-q2-synthesis",
  "case-6260k-q3-insufficient-evidence",
];
const typeLabels = {
  factual: "factual",
  synthesis: "síntese",
  "insufficient-evidence": "evidência insuficiente",
};
const sizeLabels = {
  "case-0960k": "960k",
  "case-5120k": "5,12M",
  "case-6260k": "6,26M",
};

function formatNumber(value, digits = 2) {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function preview(value, limit = 360) {
  const compact = String(value).replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  const candidate = compact.slice(0, limit - 1);
  return `${candidate.slice(0, candidate.lastIndexOf(" "))}…`;
}

function classification(item) {
  const parts = ["qualidade válida", "gate passou"];
  if (item.classification.negativa_correta === true) parts.push("negativa correta");
  return parts.join(" · ");
}

function renderCriteria(rows) {
  return rows
    .map((row) => {
      const status = row.satisfied ? "✓" : "✕";
      const statusClass = row.satisfied ? "criterion-pass" : "criterion-fail";
      const statusLabel = row.satisfied ? "satisfeito" : "não satisfeito";
      return `<li><span class="${statusClass}" aria-label="${statusLabel}">${status}</span><div class="criterion-copy markdown-body">${renderMarkdown(row.criterion)}</div></li>`;
    })
    .join("\n");
}

function renderClaims(claims) {
  const verdictLabels = {
    supported: "sustentada",
    unsupported: "não sustentada",
    contradicted: "contradita",
  };
  return claims
    .map((claim) => {
      const refs = claim.evidence_references.join(", ") || "N/D";
      return `<tr><td class="claim-text markdown-body">${renderMarkdown(claim.text)}</td><td>${escapeHtml(verdictLabels[claim.verdict] ?? claim.verdict)}</td><td>${claim.citation_present ? "sim" : "não"}</td><td>${refs}</td><td>${claim.invented ? "sim" : "não"}</td></tr>`;
    })
    .join("\n");
}

function renderOccurrences(item) {
  if (item.occurrences.length === 0) {
    return '<p class="subtle">Nenhuma ocorrência ou falha relevante registrada para este item.</p>';
  }
  return `<ul>${item.occurrences.map((text) => `<li class="markdown-body">${renderMarkdown(text)}</li>`).join("")}</ul>`;
}

function renderSources(item) {
  const sourceLabels = {
    question: "Pergunta",
    gold: "Gold answer",
    rubric: "Rubrica",
    result: "Resultado/scoring protegido",
    official_aggregate: "Agregado oficial",
  };
  return Object.entries(sourceLabels)
    .map(([key, label]) => {
      const digest = item.sources[`${key}_sha256`];
      const digestHtml = digest
        ? `<br><span class="mono">SHA-256 ${escapeHtml(digest)}</span>`
        : "";
      return `<li><strong>${label}:</strong> <span class="mono">${escapeHtml(item.sources[key])}</span>${digestHtml}</li>`;
    })
    .join("\n");
}

function renderCase(item) {
  const metrics = item.scores;
  const judge = item.judge;
  const groundedness = judge.groundedness;
  const counts = groundedness.verdict_counts;
  const completeness = judge.completeness;
  const citation = judge.citation_quality;
  const hallucination = judge.hallucination;
  const corpus = item.corpus;
  const attempts = judge.attempts.join(" → ");
  const negativeLabel = item.classification.negativa_correta === true ? "sim" : "N/D";

  return `
<details class="audit-case" id="${escapeHtml(item.item_id)}">
  <summary>
    <span class="case-identity"><strong>${sizeLabels[item.case_id]} · ${typeLabels[item.question_type]}</strong><small class="mono">${escapeHtml(item.item_id)}</small></span>
    <span class="case-overall"><small>overall</small>${formatNumber(metrics.overall)}</span>
    <span class="status-badge">gate passou</span>
  </summary>
  <div class="audit-body">
    <div class="case-meta">
      <span>${corpus.document_count} documentos</span>
      <span>${new Intl.NumberFormat("pt-BR").format(corpus.token_count)} tokens de corpus</span>
      <span>${formatNumber(item.latency.stream_terminal_s)} s até terminal</span>
      <span>${item.tool_calls} tools</span>
      <a class="trace-link" href="${escapeHtml(item.trace_url)}" target="_blank" rel="noreferrer">Abrir trace Langfuse ↗</a>
    </div>

    <section class="audit-section" aria-labelledby="${escapeHtml(item.item_id)}-question">
      <h4 id="${escapeHtml(item.item_id)}-question">Pergunta integral</h4>
      <div class="copy-block markdown-body">${renderMarkdown(item.question)}</div>
    </section>

    <section class="audit-section" aria-labelledby="${escapeHtml(item.item_id)}-expected">
      <h4 id="${escapeHtml(item.item_id)}-expected">Gold answer e critérios esperados</h4>
      <div class="gold-block markdown-body">${renderMarkdown(item.gold_answer)}</div>
      <ol class="criteria-list">${renderCriteria(item.expected_criteria)}</ol>
    </section>

    <section class="audit-section" aria-labelledby="${escapeHtml(item.item_id)}-answer">
      <h4 id="${escapeHtml(item.item_id)}-answer">Resposta efetivamente produzida</h4>
      <div class="response-preview markdown-body">${renderMarkdown(preview(item.answer))}</div>
      <details class="content-expander">
        <summary>Ler resposta integral · ${new Intl.NumberFormat("pt-BR").format(item.answer.length)} caracteres</summary>
        <div class="response-body markdown-body">${renderMarkdown(item.answer)}</div>
      </details>
      <p class="hash-line">SHA-256 da resposta: <span class="mono">${escapeHtml(item.answer_sha256)}</span></p>
    </section>

    <section class="audit-section" aria-labelledby="${escapeHtml(item.item_id)}-judge">
      <div class="section-title-row">
        <div><h4 id="${escapeHtml(item.item_id)}-judge">Avaliação do judge</h4><p class="subtle">${classification(item)} · negativa correta: ${negativeLabel} · tentativas: ${escapeHtml(attempts)}</p></div>
        <span class="judge-decision">${formatNumber(metrics.overall)} overall</span>
      </div>
      <blockquote class="judge-rationale markdown-body">${renderMarkdown(judge.rationale)}</blockquote>
      <div class="judge-grid">
        <article class="judge-card">
          <span class="metric-label">COMPLETUDE</span><strong>${formatNumber(metrics.completeness)}</strong>
          <p>${completeness.satisfied}/${completeness.total} critérios obrigatórios satisfeitos. A justificativa item a item está na lista de critérios acima.</p>
        </article>
        <article class="judge-card">
          <span class="metric-label">GROUNDEDNESS</span><strong>${formatNumber(metrics.groundedness, 4)}</strong>
          <p>${counts.supported} de ${groundedness.claims.length} claims sustentadas; ${counts.unsupported} não sustentadas e ${counts.contradicted} contraditas. O detalhamento claim a claim está abaixo.</p>
        </article>
        <article class="judge-card">
          <span class="metric-label">ALUCINAÇÃO</span><strong>${hallucination.value ? "sim" : "não"}</strong>
          <p>${hallucination.count} alucinações e ${hallucination.invented_claims} claims marcadas como inventadas. Justificativa textual específica: N/D — o schema do judge registra o booleano e o atributo por claim, sem narrativa separada.</p>
        </article>
        <article class="judge-card">
          <span class="metric-label">QUALIDADE DE CITAÇÃO</span><strong>${formatNumber(metrics.citation_quality)}</strong>
          <p>${citation.cited_claims}/${citation.total_claims} claims verificadas têm citação. Referências e presença de citação estão discriminadas na auditoria de claims.</p>
        </article>
      </div>
      <details class="content-expander claims-expander">
        <summary>Auditar ${groundedness.claims.length} claims avaliadas pelo judge</summary>
        <div class="table-wrap compact-table"><table><thead><tr><th>Claim</th><th>Veredito</th><th>Citação</th><th>Refs.</th><th>Inventada</th></tr></thead><tbody>${renderClaims(groundedness.claims)}</tbody></table></div>
      </details>
    </section>

    <section class="audit-section occurrence-section" aria-labelledby="${escapeHtml(item.item_id)}-occurrences">
      <h4 id="${escapeHtml(item.item_id)}-occurrences">Ocorrências e falhas relevantes</h4>
      ${renderOccurrences(item)}
    </section>

    <details class="source-expander">
      <summary>Proveniência e reconciliação</summary>
      <ul class="source-list">${renderSources(item)}</ul>
      <p><strong>Execution:</strong> <span class="mono">${escapeHtml(item.execution_id)}</span><br><strong>Trace:</strong> <span class="mono">${escapeHtml(item.trace_id)}</span></p>
    </details>
  </div>
</details>`.trim();
}

function validate(data) {
  if (data.schema_version !== "long-context-presentation-audit-v1") {
    throw new Error(`Schema não suportado: ${data.schema_version}`);
  }
  const ids = data.items.map((item) => item.item_id);
  if (JSON.stringify(ids) !== JSON.stringify(expectedIds)) {
    throw new Error(`IDs ausentes ou fora de ordem: ${ids.join(", ")}`);
  }
  for (const item of data.items) {
    if (!item.question || !item.answer || !item.judge?.rationale) {
      throw new Error(`Pergunta, resposta e judge são obrigatórios em ${item.item_id}`);
    }
    if (!item.trace_url || item.classification?.gate !== "passed") {
      throw new Error(`Trace e gate aprovado são obrigatórios em ${item.item_id}`);
    }
  }
}

function replaceGeneratedSection(document, content) {
  const startIndex = document.indexOf(startMarker);
  const endIndex = document.indexOf(endMarker);
  if (startIndex === -1 || endIndex === -1 || endIndex < startIndex) {
    throw new Error("Marcadores dos casos Long Context não encontrados.");
  }
  return `${document.slice(0, startIndex + startMarker.length)}\n${content}\n          ${document.slice(endIndex)}`;
}

const checkOnly = process.argv.includes("--check");
const data = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
validate(data);
const original = fs.readFileSync(outputPath, "utf8");
const casesHtml = data.items.map(renderCase).join("\n\n");
const rendered = replaceGeneratedSection(original, casesHtml).replace(/[\t ]+$/gm, "");

if (checkOnly) {
  if (rendered !== original) {
    throw new Error("Apresentação desatualizada; execute build_long_context_presentation.mjs.");
  }
  console.log("Apresentação Long Context consistente com o artefato de 9 casos.");
} else {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, rendered);
  console.log(`Apresentação Long Context atualizada com ${data.items.length} casos: ${outputPath}`);
}
