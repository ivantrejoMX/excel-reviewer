'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  jobId: null,
  filename: null,
  pollInterval: null,
  decisions: {},        // fix_id → 'approved' | 'rejected'
  optionChoices: {},    // fix_id → 'a_direct_ref' | 'b_named_range' | 'c_structured_ref'
  namedRangeNames: {},  // fix_id → string (user-supplied range name)
  validationQueue: [],
  autoFixes: [],
};

// ── Views ─────────────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(`view-${name}`).classList.add('active');
}

// ── Upload ────────────────────────────────────────────────────────────────────
const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const browseBtn  = document.getElementById('browse-btn');
const uploadErr  = document.getElementById('upload-error');

browseBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});
dropZone.addEventListener('click', e => {
  if (e.target !== browseBtn) fileInput.click();
});

function showUploadError(msg) {
  uploadErr.textContent = msg;
  uploadErr.style.display = 'block';
}

async function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['xlsx', 'xlsm'].includes(ext)) {
    showUploadError('Unsupported file type. Please upload an .xlsx or .xlsm file.');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showUploadError('File exceeds the 10 MB limit.');
    return;
  }

  const apiKey = document.getElementById('api-key-input').value.trim();
  if (apiKey && !apiKey.startsWith('sk-ant-')) {
    showUploadError('That doesn\'t look like an Anthropic key (should start with sk-ant-). Please check and try again.');
    return;
  }

  uploadErr.style.display = 'none';

  state.filename = file.name;
  document.getElementById('analyzing-filename').textContent = file.name;
  showView('analyzing');
  document.getElementById('progress-msg').textContent = 'Uploading…';

  const formData = new FormData();
  formData.append('file', file);
  if (apiKey) formData.append('anthropic_api_key', apiKey);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      showView('upload');
      showUploadError(err.detail || 'Upload failed.');
      return;
    }
    const data = await res.json();
    state.jobId = data.job_id;
    startPolling();
  } catch (e) {
    showView('upload');
    showUploadError('Could not reach the server. Is it running?');
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  state.pollInterval = setInterval(pollStatus, 1500);
}
function stopPolling() {
  clearInterval(state.pollInterval);
  state.pollInterval = null;
}

async function pollStatus() {
  try {
    const res = await fetch(`/api/jobs/${state.jobId}/status`);
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('progress-msg').textContent = data.progress_message || '…';

    if (data.status === 'READY') {
      stopPolling();
      renderResults(data);
    } else if (data.status === 'DONE') {
      stopPolling();
      triggerDownload();
    } else if (data.status === 'ERROR') {
      stopPolling();
      showView('upload');
      showUploadError(`Analysis failed: ${data.error || 'unknown error'}`);
    }
  } catch (_) {}
}

// ── Results ───────────────────────────────────────────────────────────────────
function severityBadgeClass(sev) {
  return sev === 'error' ? 'badge-error' : sev === 'warning' ? 'badge-warning' : 'badge-info';
}

function issueTypeLabel(type) {
  const labels = {
    circular_reference: 'Circular Ref',
    formula_error: 'Formula Error',
    hardcoded_value: 'Hardcoded Value',
    broken_lookup: 'Broken Lookup',
    simplification_opportunity: 'Simplification',
    volatile_function: 'Volatile Fn',
    duplicate_formula: 'Duplicate Formula',
    redundant_link: 'Redundant Link',
  };
  return labels[type] || type;
}

function renderResults(data) {
  state.autoFixes = data.auto_fixes || [];
  state.validationQueue = data.validation_queue || [];
  state.decisions = {};
  state.optionChoices = {};
  state.namedRangeNames = {};

  // Summary
  document.getElementById('summary-box').textContent = data.summary || '';

  // Stat pills
  const pills = document.getElementById('stat-pills');
  pills.innerHTML = '';
  const autoCount = state.autoFixes.length;
  const valCount  = state.validationQueue.length;
  if (autoCount) pills.innerHTML += `<span class="pill pill-success">✓ ${autoCount} auto-fixed</span>`;
  if (valCount)  pills.innerHTML += `<span class="pill pill-warning">⚠ ${valCount} need review</span>`;
  if (!autoCount && !valCount) pills.innerHTML = `<span class="pill pill-info">No issues found</span>`;

  document.getElementById('results-title').textContent =
    `Review — ${state.filename}`;

  // Partial analysis notice
  document.getElementById('partial-notice').style.display = data.partial_analysis ? 'block' : 'none';

  // Auto-fixes
  const autofixSection = document.getElementById('autofix-section');
  const autofixList    = document.getElementById('autofix-list');
  if (state.autoFixes.length) {
    autofixList.innerHTML = state.autoFixes.map(issue => `
      <div class="autofix-item">
        <span class="check-icon">✓</span>
        <div>
          <strong>${escHtml(issueTypeLabel(issue.issue_type))} — ${escHtml(issue.sheet_name)}!${escHtml(issue.cell_range)}</strong>
          <span>${escHtml(issue.description)}</span>
        </div>
      </div>`).join('');
    autofixSection.style.display = 'block';
  } else {
    autofixSection.style.display = 'none';
  }

  // Validation queue
  const valSection = document.getElementById('validation-section');
  const valList    = document.getElementById('validation-list');
  if (state.validationQueue.length) {
    valList.innerHTML = state.validationQueue.map(issue => buildValidationCard(issue)).join('');
    valSection.style.display = 'block';
    // Attach listeners after rendering
    state.validationQueue.forEach(issue => attachCardListeners(issue));
  } else {
    valSection.style.display = 'none';
  }

  updateApplyBar();
  showView('results');
}

function buildValidationCard(issue) {
  const badgeClass = severityBadgeClass(issue.severity);
  const isRedundant = issue.issue_type === 'redundant_link';

  let formulaRows = '';
  if (issue.original_formula) {
    formulaRows += `
      <div class="formula-block">
        <div class="formula-label">Current formula</div>
        <div class="formula-code">${escHtml(issue.original_formula)}</div>
      </div>`;
  }
  if (issue.suggested_fix && !isRedundant) {
    formulaRows += `
      <div class="formula-block">
        <div class="formula-label">Suggested fix</div>
        <div class="formula-code">${escHtml(issue.suggested_fix)}</div>
      </div>`;
  }

  let redundantOptions = '';
  if (isRedundant && issue.simplification_options) {
    const opts = issue.simplification_options;
    redundantOptions = `
      <div class="option-tabs">
        <button class="opt-tab active" data-fix="${issue.issue_id}" data-opt="a_direct_ref">a) Direct ref</button>
        <button class="opt-tab" data-fix="${issue.issue_id}" data-opt="b_named_range">b) Named range</button>
        ${opts.c_structured_ref && opts.c_structured_ref !== 'Not applicable' ? `<button class="opt-tab" data-fix="${issue.issue_id}" data-opt="c_structured_ref">c) Table ref</button>` : ''}
      </div>
      <div class="option-detail" id="opt-detail-${issue.issue_id}">
        ${escHtml(opts.a_direct_ref || '—')}
      </div>`;
    // initialise default choice
    state.optionChoices[issue.issue_id] = 'a_direct_ref';
  }

  return `
    <div class="validation-card" id="card-${issue.issue_id}">
      <div class="card-header">
        <span class="badge ${badgeClass}">${escHtml(issue.severity)}</span>
        <div>
          <div class="card-desc">${escHtml(issueTypeLabel(issue.issue_type))}</div>
          <div class="card-loc"><strong>${escHtml(issue.sheet_name)}</strong> · ${escHtml(issue.cell_range)}</div>
        </div>
        <div class="card-actions">
          <button class="btn-approve" id="approve-${issue.issue_id}" data-fix="${issue.issue_id}">Approve</button>
          <button class="btn-reject"  id="reject-${issue.issue_id}"  data-fix="${issue.issue_id}">Reject</button>
        </div>
      </div>
      <div class="card-body">
        <p style="font-size:.875rem;margin-bottom:10px;">${escHtml(issue.description)}</p>
        ${formulaRows ? `<div class="formula-row">${formulaRows}</div>` : ''}
        ${redundantOptions}
      </div>
    </div>`;
}

function attachCardListeners(issue) {
  document.getElementById(`approve-${issue.issue_id}`)?.addEventListener('click', () => setDecision(issue.issue_id, 'approved'));
  document.getElementById(`reject-${issue.issue_id}`)?.addEventListener('click',  () => setDecision(issue.issue_id, 'rejected'));

  // Option tab listeners for redundant links
  document.querySelectorAll(`.opt-tab[data-fix="${issue.issue_id}"]`).forEach(btn => {
    btn.addEventListener('click', () => {
      const opt = btn.dataset.opt;
      state.optionChoices[issue.issue_id] = opt;

      // Update active tab
      document.querySelectorAll(`.opt-tab[data-fix="${issue.issue_id}"]`).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // Update detail text
      const detail = document.getElementById(`opt-detail-${issue.issue_id}`);
      const opts = issue.simplification_options;
      let text = opts[opt] || '—';
      detail.innerHTML = escHtml(text);

      // Show named range input if b_named_range
      if (opt === 'b_named_range') {
        detail.innerHTML += `
          <div class="named-range-input">
            <label>Range name:</label>
            <input type="text" id="rangename-${issue.issue_id}" placeholder="e.g. Total_Revenue"
              value="${escHtml(state.namedRangeNames[issue.issue_id] || '')}" />
          </div>`;
        document.getElementById(`rangename-${issue.issue_id}`)?.addEventListener('input', e => {
          state.namedRangeNames[issue.issue_id] = e.target.value;
        });
      }
    });
  });
}

function setDecision(fixId, decision) {
  state.decisions[fixId] = decision;
  const card = document.getElementById(`card-${fixId}`);
  card.classList.remove('approved', 'rejected');
  card.classList.add(decision);

  document.getElementById(`approve-${fixId}`)?.classList.toggle('active', decision === 'approved');
  document.getElementById(`reject-${fixId}`)?.classList.toggle('active', decision === 'rejected');

  updateApplyBar();
}

function updateApplyBar() {
  const total = state.validationQueue.length;
  const made  = Object.keys(state.decisions).length;
  document.getElementById('decisions-count').textContent = `${made} / ${total}`;

  const allDone = total === 0 || made === total;
  document.getElementById('apply-btn').disabled = !allDone;
}

// ── Approve all ───────────────────────────────────────────────────────────────
document.getElementById('approve-all-btn').addEventListener('click', () => {
  state.validationQueue.forEach(issue => setDecision(issue.issue_id, 'approved'));
});

// ── Apply & Download ──────────────────────────────────────────────────────────
document.getElementById('apply-btn').addEventListener('click', async () => {
  const approvedIds = Object.entries(state.decisions)
    .filter(([, v]) => v === 'approved').map(([k]) => k);
  const rejectedIds = Object.entries(state.decisions)
    .filter(([, v]) => v === 'rejected').map(([k]) => k);

  // Build named_range_choices
  const namedRangeChoices = {};
  approvedIds.forEach(id => {
    if (state.optionChoices[id]) {
      namedRangeChoices[id] = state.optionChoices[id];
    }
    if (state.namedRangeNames[id]) {
      namedRangeChoices[`${id}_name`] = state.namedRangeNames[id];
    }
  });

  document.getElementById('apply-btn').disabled = true;
  document.getElementById('apply-btn').textContent = 'Applying…';
  showView('analyzing');
  document.getElementById('progress-msg').textContent = 'Applying approved fixes…';
  document.getElementById('analyzing-filename').textContent = state.filename;

  try {
    const res = await fetch(`/api/jobs/${state.jobId}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved_fix_ids: approvedIds, rejected_fix_ids: rejectedIds, named_range_choices: namedRangeChoices }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Apply failed');
    startPolling();
  } catch (e) {
    showView('upload');
    showUploadError(`Failed to apply fixes: ${e.message}`);
  }
});

function triggerDownload() {
  window.location.href = `/api/jobs/${state.jobId}/download`;
  // Reset UI after a moment
  setTimeout(() => {
    showView('upload');
    document.getElementById('apply-btn').textContent = 'Apply & Download';
    fileInput.value = '';
  }, 1500);
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
