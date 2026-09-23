(function () {
  'use strict';

  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const panels = [...document.querySelectorAll('[role="tabpanel"]')];
  const formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
  const precise = new Intl.NumberFormat('en-US', { maximumFractionDigits: 5 });
  const MAX_FILE_BYTES = 1024 * 1024;
  let selectedG1 = false;
  let selectedG2 = false;

  function showView(view, focus = false) {
    tabs.forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    panels.forEach((panel) => { panel.hidden = panel.id !== view; });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => showView(tab.dataset.view));
    tab.addEventListener('keydown', (event) => {
      const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!offset && event.key !== 'Home' && event.key !== 'End') return;
      event.preventDefault();
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + offset + tabs.length) % tabs.length;
      showView(tabs[target].dataset.view, true);
    });
  });

  function setText(id, text) { document.getElementById(id).textContent = text; }
  function setMessage(id, text, error = false) {
    const element = document.getElementById(id);
    element.textContent = text;
    element.classList.toggle('error', error);
  }
  function updateSession() {
    const selected = [];
    if (selectedG1) selected.push('3K log');
    if (selectedG2) selected.push('CK3 plan');
    setText('session-readout', selected.length ? `${selected.join(' + ')} selected locally` : 'No local evidence selected');
  }
  function fillTable(id, rows, emptyText) {
    const body = document.getElementById(id);
    body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = id === 'g1-units' ? 6 : 5;
      cell.className = 'empty-cell';
      cell.textContent = emptyText;
      row.append(cell);
      body.append(row);
      return;
    }
    for (const values of rows) {
      const row = document.createElement('tr');
      for (const value of values) {
        const cell = document.createElement('td');
        cell.textContent = String(value);
        row.append(cell);
      }
      body.append(row);
    }
  }
  function setBar(side, total) {
    document.getElementById(`g1-${side}-bar`).style.width = total.survivors === null ? '0%' : `${Math.max(0, Math.min(100, total.survivors / total.initial * 100))}%`;
    setText(`g1-${side}-total`, total.survivors === null ? `${formatter.format(total.initial)} start` : `${formatter.format(total.survivors)} / ${formatter.format(total.initial)}`);
  }
  function resetG1() {
    selectedG1 = false;
    document.getElementById('g1-file').value = '';
    for (const id of ['g1-run', 'g1-phase', 'g1-outcome', 'g1-attacker-total', 'g1-defender-total']) setText(id, '-');
    for (const side of ['attacker', 'defender']) document.getElementById(`g1-${side}-bar`).style.width = '0%';
    fillTable('g1-units', [], 'No runtime log selected.');
    setMessage('g1-message', 'No local run selected.');
    updateSession();
  }
  function resetG2() {
    selectedG2 = false;
    document.getElementById('g2-file').value = '';
    for (const id of ['g2-combat', 'g2-winner', 'g2-fingerprint', 'g2-result']) setText(id, '-');
    setText('g2-status', 'Not verified');
    fillTable('g2-rows', [], 'No prepared plan selected.');
    setMessage('g2-message', 'No local plan selected.');
    updateSession();
  }
  function renderG1(report, filename) {
    selectedG1 = true;
    setText('g1-run', report.runId);
    setText('g1-phase', report.phase);
    setText('g1-outcome', report.resultCallbackPresent ? report.outcome : 'Unavailable');
    for (const side of ['attacker', 'defender']) setBar(side, report.totals[side]);
    fillTable('g1-units', report.units.map((unit) => [unit.alliance === 1 ? 'Attacker' : 'Defender', unit.script_name, unit.unit_type, formatter.format(unit.initial), formatter.format(unit.survivors), unit.routing ? 'Routing' : 'Holding']), 'No final snapshot in this run.');
    setMessage('g1-message', `${filename} / ${report.resultCallbackPresent ? 'Result callback captured' : 'No result callback; winner unavailable'}`);
    updateSession();
  }
  function renderG2(report, filename) {
    selectedG2 = true;
    setText('g2-combat', report.battleId);
    setText('g2-winner', `${report.outcome} (synthetic)`);
    setText('g2-status', 'Unverified in CK3');
    setText('g2-fingerprint', report.fingerprint);
    setText('g2-result', report.resultId);
    fillTable('g2-rows', ['attacker', 'defender'].map((side) => {
      const data = report.sides[side];
      return [side, data.armyIds.join(', '), formatter.format(data.initial), precise.format(data.fighting), formatter.format(data.loss)];
    }), 'No prepared plan selected.');
    setMessage('g2-message', `${filename} / prepared plan only; no CK3 reload verified`);
    updateSession();
  }
  async function readFile(file, parse, render, reset, messageId) {
    if (!file) return;
    try {
      if (file.size > MAX_FILE_BYTES) throw new Error('File exceeds 1 MB. Select a JSONL log or JSON plan, not a CK3 save.');
      render(parse(await file.text()), file.name);
    } catch (error) {
      reset();
      setMessage(messageId, error.message, true);
    }
  }

  document.getElementById('g1-file').addEventListener('change', (event) => readFile(event.target.files[0], window.CW2Evidence.parse3KLog, renderG1, resetG1, 'g1-message'));
  document.getElementById('g2-file').addEventListener('change', (event) => readFile(event.target.files[0], window.CW2Evidence.parseG2Plan, renderG2, resetG2, 'g2-message'));
  document.getElementById('g1-clear').addEventListener('click', resetG1);
  document.getElementById('g2-clear').addEventListener('click', resetG2);
})();