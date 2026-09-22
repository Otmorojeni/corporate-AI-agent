/**
 * Corporate AI Assistant - Frontend Application
 * Interacts with FastAPI backend via OpenAPI endpoints:
 *   - GET /health
 *   - POST /v1/assistant/query
 *   - POST /v1/abbreviations/extract
 *   - GET /ui/config (internal dynamic model info)
 */

// Determine API Base URL dynamically
const API_BASE = (window.location.protocol === 'file:' || !window.location.hostname)
  ? 'http://localhost:8000'
  : window.location.origin;

// DOM Elements
const healthStatusEl = document.getElementById('health-status');
const healthTextEl = document.getElementById('health-text');
const tabs = document.querySelectorAll('.tab-btn');
const panels = document.querySelectorAll('.tab-panel');

// Query Tab Elements
const queryInput = document.getElementById('query-input');
const querySubmitBtn = document.getElementById('query-submit-btn');
const queryClearBtn = document.getElementById('query-clear-btn');
const queryLoading = document.getElementById('query-loading');
const queryResult = document.getElementById('query-result');
const queryAlert = document.getElementById('query-alert');
const answerText = document.getElementById('answer-text');
const detectedTermsList = document.getElementById('detected-terms-list');
const sourcesList = document.getElementById('sources-list');
const sourcesSection = document.getElementById('sources-section');
const telemetryLatency = document.getElementById('telemetry-latency');
const telemetryReqId = document.getElementById('telemetry-req-id');
const copyAnswerBtn = document.getElementById('copy-answer-btn');
const footerModelName = document.getElementById('footer-model-name');

// Upload Tab Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const selectedFileInfo = document.getElementById('selected-file-info');
const selectedFileName = document.getElementById('selected-file-name');
const selectedFileSize = document.getElementById('selected-file-size');
const removeFileBtn = document.getElementById('remove-file-btn');
const uploadBtn = document.getElementById('upload-btn');
const uploadLoading = document.getElementById('upload-loading');
const uploadAlert = document.getElementById('upload-alert');
const uploadSuccess = document.getElementById('upload-success');
const uploadSuccessMsg = document.getElementById('upload-success-msg');
const extractedSection = document.getElementById('extracted-section');
const extractedTbody = document.getElementById('extracted-tbody');
const extractedCount = document.getElementById('extracted-count');
const tableFilterInput = document.getElementById('table-filter-input');
const askAboutDocBtn = document.getElementById('ask-about-doc-btn');

let currentSelectedFile = null;
let lastExtractedAbbreviations = [];
let currentRawAnswer = '';

// ==========================================
// 1. Service Health & Dynamic Model Config
// ==========================================
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    if (res.ok) {
      healthStatusEl.className = 'status-pill online';
      healthTextEl.textContent = 'Сервис готов к работе';
    } else {
      throw new Error(`Status ${res.status}`);
    }
  } catch (err) {
    healthStatusEl.className = 'status-pill offline';
    healthTextEl.textContent = 'Сервер недоступен (запустите uvicorn)';
  }
}

async function loadModelConfig() {
  try {
    const res = await fetch(`${API_BASE}/ui/config`);
    if (res.ok) {
      const data = await res.json();
      if (footerModelName && data.model_name) {
        footerModelName.textContent = data.model_name;
      }
    }
  } catch (_) {
    // If not reachable, keep whatever server injected or fallback
    if (footerModelName && footerModelName.textContent.includes('{{')) {
      footerModelName.textContent = 'LLM API (.env)';
    }
  }
}

// ==========================================
// 2. Tabs Navigation
// ==========================================
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    tabs.forEach(t => t.classList.toggle('active', t === tab));
    panels.forEach(p => p.classList.toggle('active', p.id === `tab-${target}`));
  });
});

function switchTab(tabName) {
  const targetTab = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
  if (targetTab) {
    targetTab.click();
  }
}

// ==========================================
// 3. Modern Textarea Auto-Resize
// ==========================================
function autoResizeInput() {
  queryInput.style.height = 'auto';
  const newHeight = Math.min(Math.max(queryInput.scrollHeight, 52), 240);
  queryInput.style.height = newHeight + 'px';
}

queryInput.addEventListener('input', autoResizeInput);

// ==========================================
// 4. Robust Markdown Parser (Zero-dependency & offline-safe)
// ==========================================
function renderMarkdown(md) {
  if (!md) return '';

  // 1. Protect code blocks before general escaping
  const codeBlocks = [];
  let text = md.replace(/```(?:[a-zA-Z0-9_-]*\r?\n)?([\s\S]*?)```/g, (match, code) => {
    const id = `XYZCODEBLOCK${codeBlocks.length}XYZ`;
    const escapedCode = escapeHtml(code.trim());
    codeBlocks.push(`<pre class="code-block"><code>${escapedCode}</code></pre>`);
    return `\n${id}\n`;
  });

  // 2. Escape HTML special characters
  text = escapeHtml(text);

  // 3. Inline code
  text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // 4. Bold & Italic
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  text = text.replace(/(?<!\w)_([^_]+)_(?!\w)/g, '<em>$1</em>');

  // 5. Line by line parsing for headers and lists
  const lines = text.split('\n');
  const output = [];
  let inOl = false;
  let inUl = false;

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    // Headers
    if (/^####\s+/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      output.push(`<h5 class="md-h5">${trimmed.replace(/^####\s+/, '')}</h5>`);
      continue;
    }
    if (/^###\s+/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      output.push(`<h4 class="md-h4">${trimmed.replace(/^###\s+/, '')}</h4>`);
      continue;
    }
    if (/^##\s+/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      output.push(`<h3 class="md-h3">${trimmed.replace(/^##\s+/, '')}</h3>`);
      continue;
    }
    if (/^#\s+/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      output.push(`<h2 class="md-h2">${trimmed.replace(/^#\s+/, '')}</h2>`);
      continue;
    }

    // Numbered lists: 1. Item
    const olMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (olMatch) {
      if (inUl) { output.push('</ul>'); inUl = false; }
      if (!inOl) { output.push('<ol class="md-ol">'); inOl = true; }
      output.push(`<li>${olMatch[2]}</li>`);
      continue;
    }

    // Bullet lists: - Item or * Item
    const ulMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (ulMatch) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (!inUl) { output.push('<ul class="md-ul">'); inUl = true; }
      output.push(`<li>${ulMatch[1]}</li>`);
      continue;
    }

    // Horizontal Rule: ---, ***, ___
    if (/^(\-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      output.push('<hr class="md-hr">');
      continue;
    }

    // Blockquotes: > text
    if (/^>\s+(.*)$/.test(trimmed)) {
      if (inOl) { output.push('</ol>'); inOl = false; }
      if (inUl) { output.push('</ul>'); inUl = false; }
      const quoteText = trimmed.replace(/^>\s+/, '');
      output.push(`<blockquote class="md-quote">${quoteText}</blockquote>`);
      continue;
    }

    // Empty line or normal text
    if (inOl) { output.push('</ol>'); inOl = false; }
    if (inUl) { output.push('</ul>'); inUl = false; }

    if (trimmed === '') {
      output.push('');
    } else {
      output.push(trimmed);
    }
  }

  if (inOl) output.push('</ol>');
  if (inUl) output.push('</ul>');

  // 6. Group continuous normal lines into paragraphs
  const htmlParts = [];
  let currentP = [];

  for (let j = 0; j < output.length; j++) {
    const item = output[j];
    if (item.startsWith('<h') || item.startsWith('<ol') || item.startsWith('</ol>') ||
        item.startsWith('<ul') || item.startsWith('</ul') || item.startsWith('<li>') ||
        item.startsWith('<hr') || item.startsWith('<blockquote') ||
        item.startsWith('XYZCODEBLOCK')) {
      if (currentP.length > 0) {
        htmlParts.push(`<p class="md-p">${currentP.join('<br>')}</p>`);
        currentP = [];
      }
      htmlParts.push(item);
    } else if (item === '') {
      if (currentP.length > 0) {
        htmlParts.push(`<p class="md-p">${currentP.join('<br>')}</p>`);
        currentP = [];
      }
    } else {
      currentP.push(item);
    }
  }

  if (currentP.length > 0) {
    htmlParts.push(`<p class="md-p">${currentP.join('<br>')}</p>`);
  }

  let finalHtml = htmlParts.join('\n');

  // 7. Restore code blocks
  codeBlocks.forEach((cb, idx) => {
    finalHtml = finalHtml.replace(`XYZCODEBLOCK${idx}XYZ`, cb);
  });

  return finalHtml;
}

// ==========================================
// 5. Query Assistant (Q&A)
// ==========================================
function showAlert(element, message, type = 'danger') {
  element.className = `alert alert-${type} active`;
  element.textContent = message;
}

function hideAlert(element) {
  element.className = 'alert';
  element.textContent = '';
}

async function handleQuerySubmit() {
  const query = queryInput.value.trim();
  if (!query) {
    showAlert(queryAlert, 'Пожалуйста, введите текст запроса.');
    queryInput.focus();
    return;
  }

  hideAlert(queryAlert);
  queryLoading.classList.add('active');
  queryResult.classList.remove('active');
  querySubmitBtn.disabled = true;

  const requestId = `req-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const startTime = performance.now();

  try {
    const response = await fetch(`${API_BASE}/v1/assistant/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        request_id: requestId,
        query: query
      })
    });

    const elapsedSec = ((performance.now() - startTime) / 1000).toFixed(2);

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const detail = errData.detail || `Ошибка сервера (${response.status})`;
      throw new Error(detail);
    }

    const data = await response.json();
    renderQueryResult(data, elapsedSec);
  } catch (error) {
    showAlert(queryAlert, `Не удалось получить ответ: ${error.message}`);
  } finally {
    queryLoading.classList.remove('active');
    querySubmitBtn.disabled = false;
  }
}

function renderQueryResult(data, elapsedSec) {
  // Store raw answer for copy button
  currentRawAnswer = data.answer || '';

  // Render formatted Markdown in answer card
  answerText.innerHTML = renderMarkdown(currentRawAnswer || 'Ответ не сгенерирован.');

  // Detected Terms
  detectedTermsList.innerHTML = '';
  const terms = data.detected_terms || [];
  if (terms.length === 0) {
    const emptyBadge = document.createElement('div');
    emptyBadge.style.fontSize = '0.85rem';
    emptyBadge.style.color = 'var(--text-muted)';
    emptyBadge.style.fontStyle = 'italic';
    emptyBadge.textContent = 'Специализированные аббревиатуры не обнаружены (общий контекст)';
    detectedTermsList.appendChild(emptyBadge);
  } else {
    terms.forEach(term => {
      const badge = document.createElement('div');
      badge.className = 'term-badge';
      badge.innerHTML = `
        <span class="term-canonical">${escapeHtml(term.canonical)}</span>
        <span class="term-divider">→</span>
        <span class="term-expansion">${escapeHtml(term.expansion)}</span>
      `;
      detectedTermsList.appendChild(badge);
    });
  }

  // Sources
  sourcesList.innerHTML = '';
  const sources = data.sources || [];
  if (sources.length === 0) {
    sourcesSection.style.display = 'none';
  } else {
    sourcesSection.style.display = 'block';
    sources.forEach(src => {
      const item = document.createElement('div');
      item.className = 'source-item';
      item.innerHTML = `
        <span class="source-name">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          ${escapeHtml(src.document_id)}
        </span>
        <span class="source-page">Стр. ${src.page}</span>
      `;
      sourcesList.appendChild(item);
    });
  }

  // Telemetry
  telemetryLatency.textContent = `⏱️ Время ответа: ${elapsedSec} с`;
  telemetryReqId.textContent = `ID: ${data.request_id || ''}`;

  queryResult.classList.add('active');
}

// Copy Answer
copyAnswerBtn.addEventListener('click', async () => {
  if (!currentRawAnswer) return;
  try {
    await navigator.clipboard.writeText(currentRawAnswer);
    const originalText = copyAnswerBtn.innerHTML;
    copyAnswerBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
      Скопировано!
    `;
    setTimeout(() => {
      copyAnswerBtn.innerHTML = originalText;
    }, 2000);
  } catch (err) {
    console.warn('Clipboard write failed:', err);
  }
});

// Clear query input and result
queryClearBtn.addEventListener('click', () => {
  queryInput.value = '';
  queryInput.style.height = 'auto';
  queryResult.classList.remove('active');
  document.querySelectorAll('.prompt-chip').forEach(c => c.classList.remove('active'));
  hideAlert(queryAlert);
  queryInput.focus();
});

// Clear prompt chip active state on manual editing
queryInput.addEventListener('input', () => {
  document.querySelectorAll('.prompt-chip').forEach(c => c.classList.remove('active'));
});

// Ctrl+Enter / Cmd+Enter hotkey
queryInput.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    handleQuerySubmit();
  }
});

querySubmitBtn.addEventListener('click', handleQuerySubmit);

// Quick Prompt Chips (evaluation__train.xlsx)
const promptChips = document.querySelectorAll('.prompt-chip');
promptChips.forEach(chip => {
  chip.addEventListener('click', () => {
    const query = chip.dataset.query;
    if (!query) return;

    // Toggle active state
    promptChips.forEach(c => c.classList.remove('active'));
    chip.classList.add('active');

    // Populate input field, resize and submit
    queryInput.value = query;
    autoResizeInput();
    handleQuerySubmit();
  });
});



// ==========================================
// 6. PDF Upload & Extraction
// ==========================================
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' байт';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ';
  return (bytes / (1024 * 1024)).toFixed(2) + ' МБ';
}

function handleFileSelection(file) {
  if (!file) return;

  hideAlert(uploadAlert);
  uploadSuccess.classList.remove('active');

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showAlert(uploadAlert, 'Пожалуйста, выберите файл в формате PDF.');
    return;
  }

  const MAX_BYTES = 50 * 1024 * 1024;
  if (file.size > MAX_BYTES) {
    showAlert(uploadAlert, 'Размер файла превышает 50 МиБ. Загрузите файл меньшего размера.');
    return;
  }

  currentSelectedFile = file;
  selectedFileName.textContent = file.name;
  selectedFileSize.textContent = `(${formatFileSize(file.size)})`;
  selectedFileInfo.classList.add('active');
  uploadBtn.disabled = false;
}

// Drag and drop events
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files[0]) {
    handleFileSelection(e.target.files[0]);
  }
});

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
    handleFileSelection(e.dataTransfer.files[0]);
  }
});

removeFileBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  currentSelectedFile = null;
  fileInput.value = '';
  selectedFileInfo.classList.remove('active');
  uploadBtn.disabled = true;
});

// Upload & Extract action
uploadBtn.addEventListener('click', async () => {
  if (!currentSelectedFile) return;

  hideAlert(uploadAlert);
  uploadSuccess.classList.remove('active');
  extractedSection.classList.remove('active');
  uploadLoading.classList.add('active');
  uploadBtn.disabled = true;

  const formData = new FormData();
  formData.append('file', currentSelectedFile, currentSelectedFile.name);

  try {
    const res = await fetch(`${API_BASE}/v1/abbreviations/extract`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      let detail = `Ошибка при обработке (${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) detail = errJson.detail;
      } catch (_) {}
      throw new Error(detail);
    }

    const data = await res.json();
    lastExtractedAbbreviations = data.abbreviations || [];

    // Show success message
    uploadSuccessMsg.textContent = `Файл "${currentSelectedFile.name}" успешно обработан и мгновенно проиндексирован в RAG-базе ассистента! Обнаружено терминов: ${lastExtractedAbbreviations.length}`;
    uploadSuccess.classList.add('active');

    renderExtractedTable(lastExtractedAbbreviations);
    extractedSection.classList.add('active');
  } catch (err) {
    showAlert(uploadAlert, `Ошибка: ${err.message}`);
  } finally {
    uploadLoading.classList.remove('active');
    uploadBtn.disabled = false;
  }
});

function renderExtractedTable(items) {
  extractedTbody.innerHTML = '';
  extractedCount.textContent = `Найдено: ${items.length}`;

  if (items.length === 0) {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
        В документе не обнаружено явных расшифровок аббревиатур. Текст документа проиндексирован для поиска.
      </td>
    `;
    extractedTbody.appendChild(row);
    return;
  }

  items.forEach(item => {
    const tr = document.createElement('tr');
    
    // Pages list
    const occurrences = item.occurrences || [];
    const pages = [...new Set(occurrences.map(o => o.page))].sort((a, b) => a - b);
    const pagesDisplay = pages.length ? pages.join(', ') : '—';

    // Quotes display
    const firstQuote = occurrences.length && occurrences[0].quote ? occurrences[0].quote : '—';

    tr.innerHTML = `
      <td><strong>${escapeHtml(item.canonical)}</strong></td>
      <td>${escapeHtml(item.expansion)}</td>
      <td><span class="source-page">Стр. ${escapeHtml(pagesDisplay)}</span></td>
      <td class="quote-cell">«${escapeHtml(firstQuote)}»</td>
    `;
    extractedTbody.appendChild(tr);
  });
}

// Filter extracted table
tableFilterInput.addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase().trim();
  if (!query) {
    renderExtractedTable(lastExtractedAbbreviations);
    return;
  }

  const filtered = lastExtractedAbbreviations.filter(item => {
    const matchCanonical = (item.canonical || '').toLowerCase().includes(query);
    const matchExpansion = (item.expansion || '').toLowerCase().includes(query);
    const matchQuotes = (item.occurrences || []).some(o => (o.quote || '').toLowerCase().includes(query));
    return matchCanonical || matchExpansion || matchQuotes;
  });

  renderExtractedTable(filtered);
});

// "Ask about this doc" shortcut
askAboutDocBtn.addEventListener('click', () => {
  if (currentSelectedFile) {
    const docName = currentSelectedFile.name;
    queryInput.value = `Что говорится в документе ${docName} о ... ?`;
    autoResizeInput();
  }
  switchTab('query');
  queryInput.focus();
});

// Utilities
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialization
checkHealth();
loadModelConfig();
setInterval(checkHealth, 15000);
