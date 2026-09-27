'use strict';

const configurations = [
  {attacker: [['swords', 'Sabre Infantry', 2640], ['crosshair', 'Crossbowmen', 1540], ['flag', 'Mounted Lancers', 923]], defender: [['shield', 'Shieldwall Infantry', 2510], ['bow-arrow', 'Longbowmen', 1620], ['flag', 'Light Cavalry', 691]]},
  {attacker: [['swords', 'Sabre Infantry', 2740], ['crosshair', 'Crossbowmen', 1640], ['flag', 'Mounted Lancers', 723]], defender: [['shield', 'Shieldwall Infantry', 2710], ['bow-arrow', 'Longbowmen', 1420], ['flag', 'Light Cavalry', 691]]},
  {attacker: [['swords', 'Sabre Infantry', 2840], ['crosshair', 'Crossbowmen', 1540], ['flag', 'Mounted Lancers', 723]], defender: [['shield', 'Shieldwall Infantry', 2610], ['bow-arrow', 'Longbowmen', 1520], ['flag', 'Light Cavalry', 691]]},
  {attacker: [['swords', 'Spear Infantry', 3040], ['crosshair', 'Crossbowmen', 1340], ['flag', 'Mounted Lancers', 723]], defender: [['shield', 'Huscarl Infantry', 2810], ['bow-arrow', 'Longbowmen', 1320], ['flag', 'Light Cavalry', 691]]},
  {attacker: [['swords', 'Sabre Infantry', 2640], ['crosshair', 'Crossbowmen', 1740], ['flag', 'Mounted Lancers', 723]], defender: [['shield', 'Shieldwall Infantry', 2410], ['bow-arrow', 'Longbowmen', 1620], ['flag', 'Light Cavalry', 791]]},
  {attacker: [['swords', 'Spear Infantry', 2940], ['crosshair', 'Crossbowmen', 1440], ['flag', 'Mounted Lancers', 723]], defender: [['shield', 'Huscarl Infantry', 2710], ['bow-arrow', 'Longbowmen', 1520], ['flag', 'Light Cavalry', 591]]}
];
const defaults = {show_mode: 'dramatic', army_scale_factor: 1, auto_battle_report: true, enable_tw3k_screenshots: false, domain_focus: 'wei', injectivity_strict: true};
let options = {...defaults};
try {
  const stored = JSON.parse(localStorage.getItem('cw2.frontend.options'));
  if (stored && ['dramatic', 'tactical', 'minimal'].includes(stored.show_mode)) options.show_mode = stored.show_mode;
  if (stored && Number.isFinite(stored.army_scale_factor) && stored.army_scale_factor > 0 && stored.army_scale_factor <= 10) options.army_scale_factor = stored.army_scale_factor;
  if (stored && ['wei', 'shu', 'wu', 'custom'].includes(stored.domain_focus)) options.domain_focus = stored.domain_focus;
  for (const key of ['auto_battle_report', 'enable_tw3k_screenshots', 'injectivity_strict']) if (typeof stored?.[key] === 'boolean') options[key] = stored[key];
} catch {}
let roll = 2;
let locked = false;
const format = value => Math.round(value).toLocaleString('en-GB');
const icon = name => `<i data-lucide="${name === 'bow-arrow' ? 'move-up-right' : name}" class="icon" aria-hidden="true"></i>`;
function renderIcons() {
  document.querySelectorAll('[data-icon]').forEach(element => {element.innerHTML = icon(element.dataset.icon);});
  if (window.lucide) window.lucide.createIcons();
}
function render() {
  document.body.dataset.mode = options.show_mode;
  for (const side of ['attacker', 'defender']) {
    const units = configurations[roll][side];
    document.getElementById(`${side}-roster`).innerHTML = units.map(([symbol, name, men]) => `<li><span class="unit-emblem">${icon(symbol)}</span><span>${name}</span><strong>${format(men * options.army_scale_factor)}</strong></li>`).join('');
    document.getElementById(`${side}-total`).textContent = format(units.reduce((sum, unit) => sum + Math.round(unit[2] * options.army_scale_factor), 0));
  }
  document.getElementById('roll-number').textContent = String(roll + 1).padStart(2, '0');
  document.getElementById('shuffle').disabled = locked;
  document.getElementById('lock').setAttribute('aria-pressed', String(locked));
  document.getElementById('lock-label').textContent = locked ? 'Unlock' : 'Lock';
  document.getElementById('roll-status').textContent = locked ? 'Roster locked' : 'Uncommitted roster';
  document.getElementById('footer-state').innerHTML = `${icon(locked ? 'shield-check' : 'shield')}${locked ? 'Armies ready for battle' : 'Awaiting your command'}`;
  const difference = configurations[roll].attacker.reduce((sum, unit) => sum + Math.round(unit[2] * options.army_scale_factor), 0) - configurations[roll].defender.reduce((sum, unit) => sum + Math.round(unit[2] * options.army_scale_factor), 0);
  document.getElementById('balance').innerHTML = `Norman advantage <strong>+${format(difference)}</strong>`;
  renderIcons();
}
const modal = document.getElementById('modal');
modal.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault();
    modal.close();
  }
});
function showDialog(content) {
  document.getElementById('modal-content').innerHTML = content;
  renderIcons();
  if (!modal.open) modal.showModal();
}
function selectSetting(key, label, choices) {
  return `<label class="setting">${label}<select name="${key}">${choices.map(value => `<option value="${value}" ${options[key] === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}</select></label>`;
}
const commands = {
  battle() {document.getElementById('battle-title').scrollIntoView({block: 'center', behavior: 'smooth'});},
  shuffle() {if (!locked) {roll = (roll + 1) % configurations.length; render();}},
  lock() {locked = !locked; render();},
  fight() {
    if (!locked) {
      showDialog('<h2 id="modal-title">Commit your armies</h2><p>Lock the current roster before taking the field.</p><button class="metal-button" data-command="commit">Lock roster</button>');
      return;
    }
    showDialog(`<span class="eyebrow">Frontend preview</span><h2 id="modal-title">Armies stand ready</h2><p>Battle of Hastings &middot; Roll ${String(roll + 1).padStart(2, '0')}</p><p>This standalone preview is not connected to the launcher. No battle pack has been installed and no game has been launched.</p><button class="metal-button" data-command="close">Return to the battlefield</button>`);
  },
  commit() {locked = true; render(); modal.close();},
  close() {modal.close();},
  back() {showDialog('<h2 id="modal-title">Leave this battle?</h2><p>Return to the original Hastings roster and unlock the armies?</p><button class="metal-button" data-command="reset">Reset battle</button><button class="metal-button" data-command="close">Stay</button>');},
  reset() {roll = 2; locked = false; modal.close(); render();},
  credits() {showDialog('<h2 id="modal-title">Crusader Wars II</h2><p>CK3 Battle Bridge. Frontend study inspired by the supplied Three Kingdoms menu concept.</p><p>Bodiam Castle photograph by Antony McCallum, <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC BY-SA 3.0</a>. Cropped and toned for display. Bayeux Tapestry and Hereford map: public domain, Wikimedia Commons.</p><p>Natural Paper by Mihaela Hinayon via Transparent Textures. Lucide icons (ISC); Cinzel and Crimson Text (SIL OFL). Full sources in the frontend README.</p><p>Hastings armies and rolls are demonstration data, not an extracted CK3 encounter.</p>');},
  options() {
    showDialog(`<h2 id="modal-title">Options</h2><form id="options-form">${selectSetting('show_mode', 'Presentation', ['dramatic', 'tactical', 'minimal'])}<label class="setting">Army scale<input name="army_scale_factor" type="number" min="0.1" max="10" step="0.1" value="${options.army_scale_factor}" required ${locked ? 'disabled' : ''}></label>${selectSetting('domain_focus', 'Domain', ['wei', 'shu', 'wu', 'custom'])}${[['auto_battle_report', 'Automatic battle report'], ['enable_tw3k_screenshots', 'Three Kingdoms screenshots'], ['injectivity_strict', 'Strict unit mapping']].map(([key, label]) => `<label class="setting">${label}<input type="checkbox" name="${key}" ${options[key] ? 'checked' : ''}></label>`).join('')}<button class="metal-button" type="submit">Save options</button><p id="options-status" role="status"></p></form>`);
  }
};
document.addEventListener('click', event => {
  const button = event.target.closest('[data-command]');
  if (button && !button.disabled) commands[button.dataset.command]?.();
});
document.addEventListener('submit', event => {
  if (event.target.id !== 'options-form') return;
  event.preventDefault();
  const data = new FormData(event.target);
  options.show_mode = data.get('show_mode');
  options.domain_focus = data.get('domain_focus');
  if (!locked) options.army_scale_factor = Number(data.get('army_scale_factor'));
  for (const key of ['auto_battle_report', 'enable_tw3k_screenshots', 'injectivity_strict']) options[key] = data.has(key);
  render();
  try {localStorage.setItem('cw2.frontend.options', JSON.stringify(options)); modal.close();}
  catch {document.getElementById('options-status').textContent = 'Applied for this session. Browser storage is unavailable.';}
});
window.addEventListener('load', renderIcons);
render();