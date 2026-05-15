let template = null;
let settings = null;
let styles = {};
let emotionOptions = [];
let promptTemplates = [];
let activeTemplateName = "Default";
let conceptAttachments = [];
let emotionImageState = [];
let isBusy = false;
let currentTask = "";
let currentVisionImagePath = "";
let lastQnaAnswers = "";
let currentBrowserDescription = "";
let selectedCharacterProjectPath = "";
let characterBrowserCards = [];
let browserSortMode = "date_desc";
let browserSearchTerm = "";
let browserIncludeTags = new Set();
let browserExcludeTags = new Set();
let browserFilterPanelOpen = false;
let browserTagSortMode = "alpha";
let browserTagMerges = {};
let aiTagCleanupSuggestions = [];
let browserSelectedProjects = new Set();
let browserVirtualFolders = [];
let browserCurrentFolderId = "__all__";
let browserFolderScope = "global";
let sdModelCatalog = [];
let sdCurrentServerModel = "";

const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const uid = () => Math.random().toString(36).slice(2, 10);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error('Could not read file.'));
    reader.readAsDataURL(file);
  });
}

function setStatus(msg, kind='') {
  const el = $('#status');
  el.textContent = msg || '';
  el.className = `status ${kind}`;
}

function getOutputText() { return ($('#outputText')?.value || '').trim(); }
function hasOutput() { return getOutputText().length > 0; }
function getStableDiffusionSectionText() {
  const text = getOutputText();
  const match = text.match(/(^|\n)\s*-{0,}\s*(?:stable diffusion prompt|stable diffusion)\s*:?\s*\n([\s\S]*)$/i);
  if (!match) return '';
  let section = (match[2] || '').trim();
  const stop = section.search(/\n\s*-{3,}\s*\n\s*(?:name|description|personality|scenario|first message|alternative first messages|example dialogues|lorebook entries|tags|state tracking)\s*:?\s*\n/i);
  if (stop > 0) section = section.slice(0, stop).trim();
  return section;
}

function hasStableDiffusionPrompt() {
  const section = getStableDiffusionSectionText();
  if (!section) return false;
  if (/positive\s+prompt\s*[:：]/i.test(section)) return true;
  const cleaned = section
    .split(/\n+/)
    .map(line => line.trim())
    .filter(line => line && !/^[-*]?\s*negative\s+(prompt)?\s*[:：]/i.test(line))
    .join(' ')
    .trim();
  // Some models output the positive prompt as raw comma-separated tags under
  // Stable Diffusion Prompt without an explicit "Positive Prompt:" label.
  return cleaned.length > 20 && cleaned.includes(',');
}
function setBusy(task) {
  isBusy = !!task;
  currentTask = task || '';
  const banner = $('#busyBanner');
  const busyText = $('#busyText');
  if (banner) {
    if (busyText) busyText.textContent = task || '';
    banner.classList.toggle('hidden', !task);
  }
  updateAvailability();
}
function describeBackupInfo(info, fallbackPhase) {
  if (!info || !info.used) return '';
  const phase = info.phase || fallbackPhase || 'generation';
  const phaseText = {
    qa_interview: 'Pre-generation Q&A interview',
    character_generation: 'Character generation',
    followup_revision: 'Follow-up revision',
    text_generation: 'Text generation',
  }[phase] || phase;
  const lite = info.lite ? ' using Lite Mode' : '';
  const from = info.primaryModel ? ` after ${info.primaryModel} refused` : ' after primary model refusal';
  const to = info.backupModel ? `: ${info.backupModel}` : '';
  return `${phaseText}: backup model triggered${from}${to}${lite}.`;
}

function showBackupTriggered(info, fallbackPhase) {
  const msg = describeBackupInfo(info, fallbackPhase);
  if (!msg) return false;
  setBusy('BACKUP TEXT MODEL TRIGGERED — ' + msg);
  setStatus(msg, 'ok');
  return true;
}

function getVisionImagePath() {
  return String(currentVisionImagePath || ($('#visionImagePath')?.value || '') || (settings?.visionImagePath || '')).trim();
}

function hasVisionImageSelected() {
  return getVisionImagePath().length > 0;
}

function setVisionImagePath(path) {
  const value = String(path || '').trim();
  currentVisionImagePath = value;
  const input = $('#visionImagePath');
  if (input) {
    input.value = value;
    input.dataset.selectedPath = value;
  }
  if (settings) settings.visionImagePath = value;
  const analyze = $('#analyzeVisionBtn');
  if (analyze) {
    analyze.dataset.visionPath = value;
    analyze.disabled = isBusy ? true : !value;
    analyze.title = value ? '' : 'Select a vision image first.';
  }
}

function preventDragDefaults(event) {
  event.preventDefault();
  event.stopPropagation();
}

function bindDropZone(id, options) {
  const zone = $('#' + id);
  if (!zone) return;
  const input = options.inputId ? $('#' + options.inputId) : null;
  const setActive = (active) => zone.classList.toggle('drag-over', !!active && !isBusy);
  ['dragenter', 'dragover'].forEach(evt => zone.addEventListener(evt, (e) => {
    preventDragDefaults(e);
    if (isBusy) return;
    setActive(true);
  }));
  ['dragleave', 'dragend'].forEach(evt => zone.addEventListener(evt, (e) => {
    preventDragDefaults(e);
    setActive(false);
  }));
  zone.addEventListener('drop', async (e) => {
    preventDragDefaults(e);
    setActive(false);
    if (isBusy) {
      setStatus('Please wait until the current task finishes before dropping files.', 'error');
      return;
    }
    const files = [...(e.dataTransfer?.files || [])];
    if (!files.length) return;
    await options.onFiles(files);
  });
  zone.addEventListener('click', () => {
    if (isBusy) return;
    if (input) input.click();
    else if (options.onClick) options.onClick();
  });
}

function updateAvailability() {
  const output = hasOutput();
  const sdReady = hasStableDiffusionPrompt();
  const visionReady = hasVisionImageSelected();
  $$('button, select, input, textarea').forEach(el => {
    if (el.id === 'status') return;
    el.disabled = isBusy;
  });
  const stopBtn = $('#stopTaskBtn');
  if (stopBtn) stopBtn.disabled = !isBusy;
  ['conceptAttachmentDropZone','visionDropZone','savedFileDropZone','cardImageDropZone','builderCardDropZoneMain','builderCardDropZoneMode','conceptCardDropZoneMain','conceptCardDropZoneMode'].forEach(id => { const z = $('#'+id); if (z) z.classList.toggle('disabled', isBusy); });
  if (!isBusy) {
    ['copyBtn','exportBtn','reviseBtn','generateEmotionImagesBtn','zipEmotionImagesBtn'].forEach(id => { const el = $('#'+id); if (el) el.disabled = !output; });
    const genImg = $('#generateImagesBtn');
    if (genImg) genImg.disabled = !sdReady;
    const analyze = $('#analyzeVisionBtn');
    if (analyze) {
      const path = getVisionImagePath();
      analyze.dataset.visionPath = path;
      analyze.disabled = !path;
      analyze.title = path ? '' : 'Select a vision image first.';
    }
    const follow = $('#followupText');
    if (follow) follow.disabled = !output;
  }
}

function bindTabs() {
  $$('.nav').forEach(btn => btn.addEventListener('click', () => {
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    $('#' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'browser') refreshCharacterBrowser(false);
    updateAvailability();
  }));
}

function bindSubTabs() {
  $$('.subtabs').forEach(group => {
    const groupName = group.dataset.subtabGroup;
    $$('.subtab', group).forEach(btn => btn.addEventListener('click', () => {
      $$('.subtab', group).forEach(b => b.classList.remove('active'));
      $$(`[data-subtab-panel="${groupName}"]`).forEach(panel => panel.classList.remove('active'));
      btn.classList.add('active');
      const panel = $('#' + btn.dataset.subtab);
      if (panel) panel.classList.add('active');
      if (btn.dataset.subtab === 'output-debug') refreshDebugLog(true);
      updateAvailability();
    }));
  });
}

async function init() {
  bindTabs();
  bindSubTabs();
  const state = await window.pywebview.api.get_state();
  template = state.template;
  settings = state.settings;
  styles = state.styles || {};
  emotionOptions = state.emotions || [];
  promptTemplates = state.templates || ["Default"];
  activeTemplateName = state.activeTemplateName || settings.activeTemplateName || "Default";
  hydrateSettings();
  updateCardModeHint();
  renderStyles();
  renderEmotionOptions();
  renderTemplateSelector();
  renderTemplate();
  renderQaQuestions();
  renderConceptAttachments();
  bindActions();
  updateAvailability();
  startDebugLogAutoRefresh();
}

function hydrateSettings() {
  $('#apiBaseUrl').value = settings.apiBaseUrl || '';
  $('#apiKey').value = settings.apiKey || '';
  $('#model').value = settings.model || '';
  const backupTextModel = $('#backupTextModel'); if (backupTextModel) backupTextModel.value = settings.backupTextModel || '';
  const backupTextMode = $('#backupTextMode'); if (backupTextMode) backupTextMode.value = settings.backupTextMode || 'same';
  const aiSuggestionModel = $('#aiSuggestionModel'); if (aiSuggestionModel) aiSuggestionModel.value = settings.aiSuggestionModel || '';
  $('#visionApiBaseUrl').value = settings.visionApiBaseUrl || '';
  $('#visionApiKey').value = settings.visionApiKey || '';
  $('#visionModel').value = settings.visionModel || '';
  setVisionImagePath(settings.visionImagePath || '');
  activeTemplateName = settings.activeTemplateName || activeTemplateName || 'Default';
  $('#temperature').value = settings.temperature ?? 0.75;
  $('#maxInputTokens').value = settings.maxInputTokens ?? 200000;
  $('#maxOutputTokens').value = settings.maxOutputTokens ?? 131000;
  const apiTimeoutSeconds = $('#apiTimeoutSeconds'); if (apiTimeoutSeconds) apiTimeoutSeconds.value = settings.apiTimeoutSeconds ?? 300;
  const apiRetryCount = $('#apiRetryCount'); if (apiRetryCount) apiRetryCount.value = settings.apiRetryCount ?? 2;
  const frontPorchDataFolder = $('#frontPorchDataFolder'); if (frontPorchDataFolder) frontPorchDataFolder.value = settings.frontPorchDataFolder || '';
  $('#sdBaseUrl').value = settings.sdBaseUrl || 'http://127.0.0.1:7860';
  renderSdModelSelect(sdModelCatalog, settings.sdModel || '', sdCurrentServerModel || '');
  $('#sdSteps').value = settings.sdSteps ?? 28;
  $('#sdCfgScale').value = settings.sdCfgScale ?? 7;
  $('#sdSampler').value = settings.sdSampler || 'Euler a';
  $('#modeSelect').value = settings.mode || 'full';
  $('#cardMode').value = settings.cardMode || 'single';
  $('#multiCharacterCount').value = settings.multiCharacterCount ?? 2;
  if ($('#sharedScenePolicy')) $('#sharedScenePolicy').value = settings.sharedScenePolicy || 'ai_reconcile';
  const exportFormat = ['chara_v2_png','chara_v2_json','markdown'].includes(settings.exportFormat) ? settings.exportFormat : 'chara_v2_png';
  $('#exportFormat').value = exportFormat;
  $('#cardImagePath').value = settings.cardImagePath || '';
  $('#altCount').value = settings.alternateFirstMessages ?? 2;
  browserTagMerges = cleanBrowserTagMerges(settings.browserTagMerges || {});
  browserVirtualFolders = Array.isArray(settings.browserVirtualFolders) ? settings.browserVirtualFolders : [];
}


function applyLoadedState(state) {
  if (state.settings) {
    settings = state.settings;
    if (!['chara_v2_png','chara_v2_json','markdown'].includes(settings.exportFormat)) settings.exportFormat = 'chara_v2_png';
    hydrateSettings();
    updateCardModeHint();
    renderStyles();
    renderEmotionOptions();
  }
  if (state.template) {
    template = state.template;
    activeTemplateName = (state.settings && state.settings.activeTemplateName) || activeTemplateName || 'Default';
    renderTemplateSelector();
    renderTemplate();
  }
  if (typeof state.concept === 'string') {
    $('#conceptText').value = state.concept;
  }
  if (typeof state.output === 'string') {
    $('#outputText').value = state.output;
  }
  currentBrowserDescription = state.browserDescription || state.libraryDescription || '';
  lastQnaAnswers = typeof state.qnaAnswers === 'string' ? state.qnaAnswers : '';
  const qaBox = $('#qaAnswersText');
  if (qaBox) qaBox.value = lastQnaAnswers;
  if (typeof state.imagePath === 'string') {
    $('#cardImagePath').value = state.imagePath;
    if (settings) settings.cardImagePath = state.imagePath;
  }
  if (typeof state.visionDescription === 'string' && $('#visionDescription')) {
    $('#visionDescription').value = state.visionDescription;
  }
  if (Array.isArray(state.conceptAttachments)) {
    conceptAttachments = state.conceptAttachments;
    renderConceptAttachments();
  }
  if (Array.isArray(state.emotionImages)) {
    emotionImageState = state.emotionImages;
    renderEmotionImageResults(emotionImageState);
  }
  if (state.builderState) {
    restoreBuilderWorkspaceState(state.builderState);
  }
}

function renderTemplateSelector() {
  const select = $('#templateSelect');
  if (!select) return;
  select.innerHTML = '';
  const names = promptTemplates.length ? promptTemplates : ['Default'];
  names.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });
  select.value = activeTemplateName || 'Default';
  const input = $('#templateNameInput');
  if (input) input.value = (activeTemplateName && activeTemplateName !== 'Default') ? activeTemplateName : '';
}

function renderEmotionOptions() {
  const holder = $('#emotionOptions');
  if (!holder) return;
  holder.innerHTML = '';
  const selected = new Set(settings.emotionImageEmotions || ['neutral']);
  emotionOptions.forEach(emotion => {
    const label = document.createElement('label');
    label.className = 'emotion-chip';
    label.innerHTML = `<input type="checkbox" value="${emotion}" ${selected.has(emotion) ? 'checked' : ''} /><span>${emotion}</span>`;
    holder.appendChild(label);
  });
}



function renderSdModelSelect(models = [], selectedValue = '', currentModel = '') {
  const select = $('#sdModel');
  if (!select) return;
  const previous = String(selectedValue || select.value || settings?.sdModel || '').trim();
  const current = String(currentModel || '').trim();
  sdCurrentServerModel = current;
  sdModelCatalog = Array.isArray(models) ? models.slice() : [];
  select.innerHTML = '';

  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.textContent = current ? `Use current/default server model (${current})` : 'Use current/default server model';
  select.appendChild(defaultOpt);

  const seen = new Set(['']);
  sdModelCatalog.forEach(item => {
    const value = String(item?.value || item?.title || item?.modelName || '').trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    const opt = document.createElement('option');
    opt.value = value;
    let label = String(item?.displayName || item?.title || item?.modelName || value).trim() || value;
    if (current && value === current) label += ' [current]';
    opt.textContent = label;
    select.appendChild(opt);
  });

  if (previous && !seen.has(previous)) {
    const opt = document.createElement('option');
    opt.value = previous;
    opt.textContent = `${previous} [saved/custom]`;
    select.appendChild(opt);
  }
  select.value = previous;
}

async function fetchStableDiffusionModels() {
  const localSettings = collectSettings();
  if (!String(localSettings.sdBaseUrl || '').trim()) {
    setStatus('Enter an SD Forge / Automatic1111 Base URL first.', 'error');
    return;
  }
  try {
    setBusy('FETCHING SD MODELS — querying SD Forge / Automatic1111…');
    setStatus('Fetching Stable Diffusion models…', '');
    const res = await window.pywebview.api.fetch_sd_models(localSettings);
    if (!res.ok) throw new Error(res.error || 'Could not fetch Stable Diffusion models.');
    renderSdModelSelect(res.models || [], res.selectedModel || localSettings.sdModel || '', res.currentModel || '');
    const count = Array.isArray(res.models) ? res.models.length : 0;
    setStatus(`Fetched ${count} Stable Diffusion model${count === 1 ? '' : 's'}.`, 'ok');
  } catch (e) {
    setStatus(String(e?.message || e), 'error');
  } finally {
    setBusy('');
  }
}

function cleanModelName(value) {
  value = String(value || '').trim();
  if (!value) return '';
  const markers = ['mlabonne/','openai/','anthropic/','google/','meta-llama/','mistralai/','deepseek/','qwen/','moonshotai/','huihui-ai/','sao10k/','nousresearch/','cognitivecomputations/'];
  const lower = value.toLowerCase();
  let cut = -1;
  for (const marker of markers) {
    let idx = lower.indexOf(marker);
    while (idx !== -1) {
      if (idx > 0 && !' \t\n,;|'.includes(value[idx - 1])) cut = Math.max(cut, idx);
      idx = lower.indexOf(marker, idx + 1);
    }
  }
  if (cut > 0) value = value.slice(cut).trim();
  const parts = value.split(/[\s,;|]+/).filter(Boolean);
  if (parts.length > 1) value = parts[parts.length - 1];
  return value;
}

function collectSettings() {
  return {
    apiBaseUrl: $('#apiBaseUrl').value.trim(),
    apiKey: $('#apiKey').value.trim(),
    model: cleanModelName($('#model').value),
    backupTextModel: ($('#backupTextModel') ? cleanModelName($('#backupTextModel').value) : ''),
    backupTextMode: ($('#backupTextMode') ? $('#backupTextMode').value : 'same'),
    aiSuggestionModel: ($('#aiSuggestionModel') ? cleanModelName($('#aiSuggestionModel').value) : ''),
    visionApiBaseUrl: $('#visionApiBaseUrl').value.trim(),
    visionApiKey: $('#visionApiKey').value.trim(),
    visionModel: cleanModelName($('#visionModel').value),
    visionImagePath: $('#visionImagePath').value.trim(),
    activeTemplateName: activeTemplateName || 'Default',
    temperature: Number($('#temperature').value || 0.75),
    maxInputTokens: Number($('#maxInputTokens').value || 200000),
    maxOutputTokens: Number($('#maxOutputTokens').value || 131000),
    apiTimeoutSeconds: Number(($('#apiTimeoutSeconds') ? $('#apiTimeoutSeconds').value : 300) || 300),
    apiRetryCount: Number(($('#apiRetryCount') ? $('#apiRetryCount').value : 2) || 2),
    frontPorchDataFolder: ($('#frontPorchDataFolder') ? $('#frontPorchDataFolder').value.trim() : ''),
    sdBaseUrl: $('#sdBaseUrl').value.trim() || 'http://127.0.0.1:7860',
    sdModel: ($('#sdModel') ? $('#sdModel').value.trim() : ''),
    sdSteps: Number($('#sdSteps').value || 28),
    sdCfgScale: Number($('#sdCfgScale').value || 7),
    sdSampler: $('#sdSampler').value.trim() || 'Euler a',
    mode: $('#modeSelect').value,
    cardMode: $('#cardMode').value,
    multiCharacterCount: Number($('#multiCharacterCount').value || 2),
    sharedScenePolicy: ($('#sharedScenePolicy') ? $('#sharedScenePolicy').value : 'ai_reconcile'),
    frontend: 'front_porch',
    exportFormat: $('#exportFormat').value || 'chara_v2_png',
    cardImagePath: $('#cardImagePath').value.trim(),
    firstMessageStyle: $('#firstStyle').value,
    alternateFirstMessages: Number($('#altCount').value || 0),
    alternateFirstMessageStyles: $$(`[data-alt-style-index]`).map(el => el.value),
    emotionImageEmotions: $$('#emotionOptions input:checked').map(el => el.value),
    browserTagMerges: browserTagMerges || {},
    browserVirtualFolders: browserVirtualFolders || [],
  };
}

function apiKeyRequiredForBase(base) {
  const value = String(base || '').toLowerCase();
  if (!value) return false;
  return !['localhost', '127.0.0.1', '0.0.0.0', '::1', 'host.docker.internal'].some(x => value.includes(x));
}

function validateTextApiSettings(settings) {
  const missing = [];
  if (!String(settings.apiBaseUrl || '').trim()) missing.push('API Base URL');
  if (!String(settings.model || '').trim()) missing.push('Text Model');
  if (apiKeyRequiredForBase(settings.apiBaseUrl) && !String(settings.apiKey || '').trim()) missing.push('API Key');
  if (missing.length) {
    return `AI settings are incomplete: ${missing.join(', ')}. Open AI Settings and re-enter your endpoint/model/key before generating or revising.`;
  }
  return '';
}

function validateVisionApiSettings(settings) {
  const base = String(settings.visionApiBaseUrl || settings.apiBaseUrl || '').trim();
  const key = String(settings.visionApiKey || settings.apiKey || '').trim();
  const missing = [];
  if (!base) missing.push('Vision API Base URL or Text API Base URL');
  if (!String(settings.visionModel || '').trim()) missing.push('Vision Model');
  if (apiKeyRequiredForBase(base) && !key) missing.push('Vision API Key or Text API Key');
  if (missing.length) {
    return `Vision settings are incomplete: ${missing.join(', ')}. Open AI Settings and re-enter your vision model/key before analyzing an image.`;
  }
  return '';
}

function switchToSettingsTab() {
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  const btn = $('[data-tab="settings"]');
  if (btn) btn.classList.add('active');
  const tab = $('#settings');
  if (tab) tab.classList.add('active');
}

function renderStyles() {
  const select = $('#firstStyle');
  select.innerHTML = '';
  for (const [key, label] of Object.entries(styles)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = key.replaceAll('_', ' ') + ' — ' + label.split(':')[0];
    select.appendChild(opt);
  }
  select.value = settings.firstMessageStyle || 'cinematic';
  renderAltStyleRows();
}

function renderAltStyleRows() {
  const holder = $('#altStyleRows');
  if (!holder) return;
  holder.innerHTML = '';
  const count = Number($('#altCount')?.value || settings.alternateFirstMessages || 0);
  const selected = settings.alternateFirstMessageStyles || [];
  for (let i = 0; i < count; i++) {
    const row = document.createElement('label');
    row.className = 'alt-style-row';
    const select = document.createElement('select');
    select.dataset.altStyleIndex = String(i);
    const same = document.createElement('option');
    same.value = '';
    same.textContent = `Alternative ${i + 1}: same as main`;
    select.appendChild(same);
    for (const [key, label] of Object.entries(styles)) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = key.replaceAll('_', ' ') + ' — ' + label.split(':')[0];
      select.appendChild(opt);
    }
    select.value = selected[i] || '';
    row.appendChild(document.createTextNode(`Alternative First Message ${i + 1}`));
    row.appendChild(select);
    holder.appendChild(row);
  }
}

function sectionCategory(section) {
  const category = String(section.category || '').toLowerCase();
  if (category === 'description' || category === 'personality') return category;
  const sid = section.id || '';
  if (sid === 'description') return 'description';
  if (['personality','sexual_traits','background'].includes(sid)) return 'personality';
  const fixed = new Set(['name','scenario','first_message','alternate_first_messages','example_dialogues','lorebook','tags','system_prompt','state_tracking','stable_diffusion']);
  if (fixed.has(sid)) return 'fixed';
  return 'personality';
}

function sectionTemplatePanel(section) {
  const sid = section.id || '';
  const cat = sectionCategory(section);
  if (cat === 'description') return 'sectionsDescription';
  if (cat === 'personality') return 'sectionsPersonality';
  if (sid === 'scenario') return 'sectionsScenario';
  if (sid === 'first_message' || sid === 'alternate_first_messages') return 'sectionsFirst';
  if (sid === 'example_dialogues' || sid === 'lorebook') return 'sectionsExamples';
  if (sid === 'tags' || sid === 'system_prompt') return 'sectionsTagsSystem';
  if (sid === 'state_tracking' || sid === 'stable_diffusion') return 'sectionsStateSd';
  return 'sectionsPersonality';
}

function isEditableTemplateSection(section) {
  return sectionCategory(section) === 'description' || sectionCategory(section) === 'personality';
}

function makeNewSection(category) {
  if (category === 'description') {
    return { id: uid(), title: 'Visual Details', category: 'description', enabled: true, description: 'Additional physical/visual details that should be included in the card Description field.', fields: [
      { id: uid(), label: 'Detail', enabled: true, hint: '' }
    ]};
  }
  return { id: uid(), title: 'Thoughts', category: 'personality', enabled: true, description: 'Additional behavioral, mental, relationship, or backstory details that should be included in the card Personality field.', fields: [
    { id: uid(), label: 'Topic', enabled: true, hint: '' }
  ]};
}

function renderTemplate() {
  renderRules();
  renderQaQuestions();
  ['sectionsDescription','sectionsPersonality','sectionsScenario','sectionsFirst','sectionsExamples','sectionsTagsSystem','sectionsStateSd'].forEach(id => {
    const el = $('#'+id); if (el) el.innerHTML = '';
  });
  template.sections.forEach((section, index) => {
    // Normalize old saved templates into the new tab grouping without forcing a reset.
    if (!section.category) {
      const cat = sectionCategory(section);
      if (cat !== 'fixed') section.category = cat;
    }
    const holder = $('#' + sectionTemplatePanel(section));
    if (holder) holder.appendChild(renderSection(section, index));
  });
}

function renderRules() {
  const holder = $('#globalRules');
  if (!holder) return;
  holder.innerHTML = '';
  template.globalRules.forEach((rule, index) => {
    const row = document.createElement('div');
    row.className = 'rule-row';
    row.innerHTML = `<input value="${escapeAttr(rule)}" /><button class="danger-ghost">Delete</button>`;
    $('input', row).addEventListener('input', e => template.globalRules[index] = e.target.value);
    $('button', row).addEventListener('click', () => { template.globalRules.splice(index, 1); renderRules(); saveTemplateDebounced(); });
    holder.appendChild(row);
  });
}

function ensureQaTemplate() {
  template.qa ||= { enabled: false, sections: [] };
  if (!Array.isArray(template.qa.sections)) {
    const legacy = Array.isArray(template.qa.questions) ? template.qa.questions : [];
    template.qa.sections = legacy.length ? [{
      id: 'qa_general',
      title: 'General',
      enabled: true,
      collapsed: false,
      questions: legacy.map(q => typeof q === 'object' ? { enabled: q.enabled !== false, text: q.text || q.question || '' } : { enabled: true, text: String(q || '') })
    }] : [];
  }

  // Important: normalize Q&A data in-place so textarea/button event handlers keep
  // pointing at the live objects. Replacing the section/question arrays while the
  // user is typing can resurrect old default values when they add another question.
  template.qa.sections.forEach((section, index) => {
    if (!section.id) section.id = `qa_section_${Date.now()}_${index}`;
    if (!section.title) section.title = `Q&A Section ${index + 1}`;
    section.enabled = section.enabled !== false;
    section.collapsed = section.collapsed === true;
    if (!Array.isArray(section.questions)) section.questions = [];
    section.questions.forEach((q, qIndex) => {
      if (typeof q !== 'object' || q === null) {
        section.questions[qIndex] = { enabled: true, text: String(q || '') };
        return;
      }
      q.enabled = q.enabled !== false;
      if (q.text == null) q.text = q.question || '';
      q.text = String(q.text || '');
    });
  });

  // Keep a flattened legacy list for older backend/template files, but the UI uses sections.
  template.qa.questions = template.qa.sections.flatMap(section => section.enabled === false ? [] : section.questions.filter(q => q.enabled !== false && String(q.text || '').trim()).map(q => q.text));
}

function makeQaSection(title = 'New Q&A Section') {
  return { id: `qa_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`, title, enabled: true, collapsed: false, questions: [] };
}

function renderQaQuestions() {
  if (!template) return;
  ensureQaTemplate();
  const enabled = $('#qaEnabled');
  const holder = $('#qaQuestionsList');
  if (enabled) {
    enabled.checked = !!template.qa.enabled;
    enabled.onchange = (e) => { template.qa.enabled = e.target.checked; saveTemplateDebounced(); };
  }
  if (!holder) return;
  holder.innerHTML = '';
  if (!template.qa.sections.length) {
    const empty = document.createElement('div');
    empty.className = 'attachment-list empty';
    empty.textContent = 'No Q&A sections yet.';
    holder.appendChild(empty);
    return;
  }
  template.qa.sections.forEach((section, sectionIndex) => {
    const node = document.createElement('div');
    node.className = 'qa-section-card';
    node.innerHTML = `
      <div class="qa-section-head">
        <button type="button" class="qa-collapse" title="Collapse / expand">${section.collapsed ? '▸' : '▾'}</button>
        <label class="toggle-inline"><input class="qa-section-enabled" type="checkbox" ${section.enabled !== false ? 'checked' : ''} /> Enabled</label>
        <input class="qa-section-title" value="${escapeAttr(section.title || '')}" placeholder="Section title" />
        <div class="qa-row-actions">
          <button type="button" class="qa-add-question">Add Question</button>
          <button type="button" class="danger-ghost qa-delete-section">Delete Section</button>
        </div>
      </div>
      <div class="qa-section-body"></div>
    `;
    $('.qa-collapse', node).addEventListener('click', () => { section.collapsed = !section.collapsed; renderQaQuestions(); saveTemplateDebounced(); });
    $('.qa-section-enabled', node).addEventListener('change', e => { section.enabled = e.target.checked; saveTemplateDebounced(); });
    $('.qa-section-title', node).addEventListener('input', e => { section.title = e.target.value; saveTemplateDebounced(); });
    $('.qa-add-question', node).addEventListener('click', () => { section.questions.push({ enabled: true, text: 'What hidden desire, fear, or contradiction should shape your behavior in the opening scenario?' }); section.collapsed = false; renderQaQuestions(); saveTemplateDebounced(); });
    $('.qa-delete-section', node).addEventListener('click', () => { if (!confirm(`Delete Q&A section "${section.title || 'Untitled'}"?`)) return; template.qa.sections.splice(sectionIndex, 1); ensureQaTemplate(); renderQaQuestions(); saveTemplateDebounced(); });
    const body = $('.qa-section-body', node);
    body.style.display = section.collapsed ? 'none' : '';
    if (!section.questions.length) {
      const empty = document.createElement('div');
      empty.className = 'attachment-list empty';
      empty.textContent = 'No questions in this section.';
      body.appendChild(empty);
    }
    section.questions.forEach((question, questionIndex) => {
      const row = document.createElement('div');
      row.className = 'qa-question-row';
      row.innerHTML = `<label class="toggle-inline"><input class="qa-question-enabled" type="checkbox" ${question.enabled !== false ? 'checked' : ''} /> Use</label><textarea rows="2" placeholder="Question ${questionIndex + 1}">${escapeText(question.text || '')}</textarea><div class="qa-row-actions"><button type="button" class="qa-up">↑</button><button type="button" class="qa-down">↓</button><button type="button" class="danger-ghost qa-delete">Delete</button></div>`;
      $('.qa-question-enabled', row).addEventListener('change', e => { question.enabled = e.target.checked; saveTemplateDebounced(); });
      $('textarea', row).addEventListener('input', e => { question.text = e.target.value; saveTemplateDebounced(); });
      $('.qa-delete', row).addEventListener('click', () => { section.questions.splice(questionIndex, 1); ensureQaTemplate(); renderQaQuestions(); saveTemplateDebounced(); });
      $('.qa-up', row).addEventListener('click', () => { if (questionIndex <= 0) return; [section.questions[questionIndex-1], section.questions[questionIndex]] = [section.questions[questionIndex], section.questions[questionIndex-1]]; renderQaQuestions(); saveTemplateDebounced(); });
      $('.qa-down', row).addEventListener('click', () => { if (questionIndex >= section.questions.length - 1) return; [section.questions[questionIndex+1], section.questions[questionIndex]] = [section.questions[questionIndex], section.questions[questionIndex+1]]; renderQaQuestions(); saveTemplateDebounced(); });
      body.appendChild(row);
    });
    holder.appendChild(node);
  });
}


function renderSection(section, index) {
  const node = $('#sectionTemplate').content.firstElementChild.cloneNode(true);
  const editable = isEditableTemplateSection(section);
  node.dataset.sectionId = section.id;
  node.classList.toggle('locked-section', !editable);
  $('.section-enabled', node).checked = section.enabled !== false;
  $('.section-title', node).value = section.title || '';
  $('.section-desc', node).value = section.description || '';
  $('.section-enabled', node).addEventListener('change', e => { section.enabled = e.target.checked; saveTemplateDebounced(); });
  // Any section's instructions can be edited, including fixed sections like
  // Name, Scenario and Example Dialogues. Only Description/Personality tab
  // sections can be renamed/deleted or have custom fields added.
  $('.section-desc', node).addEventListener('input', e => { section.description = e.target.value; saveTemplateDebounced(); });
  if (editable) {
    $('.section-title', node).addEventListener('input', e => { section.title = e.target.value; saveTemplateDebounced(); });
    $('.delete-section', node).addEventListener('click', () => { template.sections.splice(index, 1); renderTemplate(); saveTemplateDebounced(); });
    $('.add-field', node).addEventListener('click', () => { section.fields ||= []; section.fields.push({ id: uid(), label: 'New Field', enabled: true, hint: '' }); renderTemplate(); saveTemplateDebounced(); });
  } else {
    $('.section-title', node).readOnly = true;
    $('.delete-section', node).style.display = 'none';
    $('.add-field', node).style.display = 'none';
  }
  $('.move-up', node).addEventListener('click', () => moveSection(index, -1));
  $('.move-down', node).addEventListener('click', () => moveSection(index, 1));
  const top = $('.section-top', node);
  const badge = document.createElement('span');
  badge.className = 'section-badge';
  badge.textContent = editable ? (sectionCategory(section) === 'description' ? 'Description field' : 'Personality field') : 'Fixed section';
  top.appendChild(badge);
  const fields = $('.fields', node);
  (section.fields || []).forEach((field, fieldIndex) => fields.appendChild(renderField(section, field, fieldIndex, editable)));
  return node;
}

function renderField(section, field, fieldIndex, editable=true) {
  const node = $('#fieldTemplate').content.firstElementChild.cloneNode(true);
  $('.field-enabled', node).checked = field.enabled !== false;
  $('.field-label', node).value = field.label || '';
  $('.field-hint', node).value = field.hint || '';
  $('.field-enabled', node).addEventListener('change', e => { field.enabled = e.target.checked; saveTemplateDebounced(); });
  if (editable) {
    $('.field-label', node).addEventListener('input', e => { field.label = e.target.value; saveTemplateDebounced(); });
    $('.field-hint', node).addEventListener('input', e => { field.hint = e.target.value; saveTemplateDebounced(); });
    $('.delete-field', node).addEventListener('click', () => { section.fields.splice(fieldIndex, 1); renderTemplate(); saveTemplateDebounced(); });
    $('.field-up', node).addEventListener('click', () => moveField(section, fieldIndex, -1));
    $('.field-down', node).addEventListener('click', () => moveField(section, fieldIndex, 1));
  } else {
    $('.field-label', node).readOnly = true;
    $('.field-hint', node).readOnly = true;
    $('.delete-field', node).style.display = 'none';
    $('.field-up', node).style.display = 'none';
    $('.field-down', node).style.display = 'none';
  }
  return node;
}

function moveSection(index, dir) {
  const target = index + dir;
  if (target < 0 || target >= template.sections.length) return;
  [template.sections[index], template.sections[target]] = [template.sections[target], template.sections[index]];
  renderTemplate(); saveTemplateDebounced();
}

function moveField(section, index, dir) {
  const target = index + dir;
  if (target < 0 || target >= section.fields.length) return;
  [section.fields[index], section.fields[target]] = [section.fields[target], section.fields[index]];
  renderTemplate(); saveTemplateDebounced();
}


function switchSubTab(groupName, panelId) {
  const group = $(`.subtabs[data-subtab-group="${groupName}"]`);
  if (!group) return;
  $$('.subtab', group).forEach(btn => btn.classList.toggle('active', btn.dataset.subtab === panelId));
  $$(`[data-subtab-panel="${groupName}"]`).forEach(panel => panel.classList.toggle('active', panel.id === panelId));
  if (panelId === 'output-debug') refreshDebugLog(true);
}

let debugLogTimer = null;
async function refreshDebugLog(force=false) {
  const log = $('#debugLogText');
  if (!log) return;
  const debugPanel = $('#output-debug');
  if (!force && (!debugPanel || !debugPanel.classList.contains('active'))) return;
  try {
    const res = await window.pywebview.api.get_debug_log();
    if (!res.ok) return;
    const next = res.text || '';
    if (log.value !== next) {
      log.value = next;
      log.scrollTop = log.scrollHeight;
    }
  } catch (e) {
    // Avoid noisy UI errors from background log refresh.
  }
}
function startDebugLogAutoRefresh() {
  if (debugLogTimer) clearInterval(debugLogTimer);
  debugLogTimer = setInterval(() => refreshDebugLog(false), 2500);
}

const MULTI_BUILDER_FIELD_IDS = [
  'multiCharacterName',
  'builderPresentation','builderBuild','builderSkin','builderHairLength','builderHairTexture','builderHairColor','builderAccentColor','builderFaceShape','builderEyeShape','builderEyeColor','builderMakeup','builderBust','builderWaistHips','builderLegs','builderClothingStyle','builderClothingExposure','builderClothingDetail','builderClothingColors','builderUnderwearStyle','builderUnderwearCoverage','builderUnderwearColor','builderUnderwearDetail','builderFootwear','builderAccessories','builderFeatures','builderVibe','builderDescription',
  'pbArchetype','pbSocial','pbConfidence','pbEmotion','pbDrive','pbFear','pbMoral','pbDecision','pbOccupation','pbOccupationCustom','pbLikes','pbDislikes','pbHobbies','pbCurrentRelationshipStatus','pbCurrentRelationshipStatusCustom','pbCurrentPartner','pbPublicRelationshipImage','pbPublicRelationshipImageCustom','pbRelationshipPressure','pbRelationshipPressureCustom','pbUserRelationshipRole','pbUserRelationshipRoleCustom','pbUserRelationshipHistory','pbUserRelationshipHistoryCustom','pbUserCurrentDynamic','pbUserCurrentDynamicCustom','pbUserFeelings','pbUserFeelingsCustom','pbUserSecretTension','pbUserSecretTensionCustom','pbUserDesiredDirection','pbUserDesiredDirectionCustom','pbUserBehavior','pbAttachment','pbConflict','pbSecrecy','pbSexualNature','pbLibido','pbPromiscuity','pbDynamic','pbRisk','pbKinkFocus','pbKinkCustom','pbTurnOns','pbTurnOffs','pbNsfwBoundaries','pbSexualPartners','pbSexualPartnersCustom','pbVirginityHistory','pbVirginityHistoryCustom','pbFirstCreampie','pbFirstCreampieCustom','pbBestSexualMemory','pbWorstSexualMemory','pbCurrentSexualSituation','pbSexualReputation','pbSpeech','pbQuirks','pbExtraNotes','personalityBuilderDescription',
  'sbSetting','sbSettingCustom','sbLocation','sbTime','sbTimeCustom','sbSituation','sbSituationCustom','sbJustHappened','sbAboutToHappen','sbTone','sbToneCustom','sbGoal','sbGoalCustom','sbRisk','sbProps','sbExtraNotes','sceneBuilderDescription'
];
let multiBuilderSelectedIndex = 0;
let multiBuilderStates = [];
let suppressMultiBuilderCapture = false;

function isMultiBuilderMode() {
  return $('#cardMode')?.value === 'multi';
}

function multiBuilderCount() {
  return Math.max(2, Math.min(12, Number($('#multiCharacterCount')?.value || 2)));
}

function getMultiBuilderCharacterName(index) {
  const state = multiBuilderStates[index] || {};
  return (state.multiCharacterName || '').trim() || `Character ${index + 1}`;
}

function readBuilderDomState() {
  const state = {};
  MULTI_BUILDER_FIELD_IDS.forEach(id => {
    if (id === 'multiCharacterName') {
      state[id] = $('.multi-builder-character-label')?.value || '';
      return;
    }
    const el = $('#'+id);
    if (el) state[id] = el.value || '';
  });
  return state;
}

function writeBuilderDomState(state={}) {
  suppressMultiBuilderCapture = true;
  try {
    MULTI_BUILDER_FIELD_IDS.forEach(id => {
      if (id === 'multiCharacterName') return;
      const el = $('#'+id);
      if (el) el.value = state[id] || '';
    });
    $$('.multi-builder-character-label').forEach(el => { el.value = state.multiCharacterName || ''; });
    updateBuilderConditionalOptions();
    updateCustomConditionalOptions();
  } finally {
    suppressMultiBuilderCapture = false;
  }
}

function ensureMultiBuilderStates() {
  const count = multiBuilderCount();
  while (multiBuilderStates.length < count) multiBuilderStates.push({});
  if (multiBuilderStates.length > count) multiBuilderStates.length = count;
  if (multiBuilderSelectedIndex >= count) multiBuilderSelectedIndex = count - 1;
  if (multiBuilderSelectedIndex < 0) multiBuilderSelectedIndex = 0;
}

function captureCurrentMultiBuilderState() {
  if (suppressMultiBuilderCapture || !isMultiBuilderMode()) return;
  ensureMultiBuilderStates();
  multiBuilderStates[multiBuilderSelectedIndex] = readBuilderDomState();
  updateMultiBuilderSelectors(false);
}

function updateMultiBuilderSelectors(syncValue=true) {
  const isMulti = isMultiBuilderMode();
  $$('#multiCountCard, [data-multi-builder-switch]').forEach(el => {
    if (el && el.hasAttribute('data-multi-builder-switch')) el.classList.toggle('hidden', !isMulti);
  });
  const multiCard = $('#multiCountCard');
  if (multiCard) multiCard.style.display = isMulti ? '' : 'none';
  const scenePolicyCard = $('#sharedScenePolicyCard');
  if (scenePolicyCard) scenePolicyCard.style.display = isMulti ? '' : 'none';
  if (!isMulti) return;
  ensureMultiBuilderStates();
  $$('.multi-builder-character-select').forEach(select => {
    const old = select.value;
    select.innerHTML = multiBuilderStates.map((_, idx) => `<option value="${idx}">${escapeHtml(getMultiBuilderCharacterName(idx))}</option>`).join('');
    select.value = syncValue ? String(multiBuilderSelectedIndex) : (old || String(multiBuilderSelectedIndex));
  });
}

function switchMultiBuilderCharacter(index) {
  if (!isMultiBuilderMode()) return;
  captureCurrentMultiBuilderState();
  ensureMultiBuilderStates();
  multiBuilderSelectedIndex = Math.max(0, Math.min(multiBuilderCount() - 1, Number(index || 0)));
  writeBuilderDomState(multiBuilderStates[multiBuilderSelectedIndex] || {});
  updateMultiBuilderSelectors(true);
  setStatus(`Editing ${getMultiBuilderCharacterName(multiBuilderSelectedIndex)} across all Builder tabs.`, 'ok');
}

function updateCardModeHint() {
  const wasMulti = isMultiBuilderMode();
  if (wasMulti) {
    ensureMultiBuilderStates();
    if (!Object.keys(multiBuilderStates[multiBuilderSelectedIndex] || {}).length) multiBuilderStates[multiBuilderSelectedIndex] = readBuilderDomState();
  }
  updateMultiBuilderSelectors(true);
}

let saveTimer = null;
function saveTemplateDebounced() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => window.pywebview.api.save_template(template), 350);
}

function bindActions() {
  $('#newCardBtn').addEventListener('click', newCard);
  $('#newCardOutputBtn').addEventListener('click', newCard);
  $('#loadTemplateBtn').addEventListener('click', loadSelectedTemplate);
  $('#saveTemplateAsBtn').addEventListener('click', saveTemplateAs);
  $('#deleteTemplateBtn').addEventListener('click', deleteSelectedTemplate);
  $('#addDescriptionSectionBtn').addEventListener('click', () => { template.sections.push(makeNewSection('description')); renderTemplate(); saveTemplateDebounced(); });
  $('#addPersonalitySectionBtn').addEventListener('click', () => { template.sections.push(makeNewSection('personality')); renderTemplate(); saveTemplateDebounced(); });
  $('#templateSelect').addEventListener('change', () => { activeTemplateName = $('#templateSelect').value || 'Default'; $('#templateNameInput').value = activeTemplateName === 'Default' ? '' : activeTemplateName; });
  $('#addRuleBtn').addEventListener('click', () => { template.globalRules.push('New rule'); renderRules(); saveTemplateDebounced(); });
  $('#addQaSectionBtn')?.addEventListener('click', () => { ensureQaTemplate(); const section = makeQaSection(); section.questions.push({ enabled: true, text: 'What hidden desire, fear, or contradiction should shape your behavior in the opening scenario?' }); template.qa.sections.push(section); renderQaQuestions(); saveTemplateDebounced(); });
  $('#clearQaAnswersBtn')?.addEventListener('click', () => { lastQnaAnswers = ''; const box = $('#qaAnswersText'); if (box) box.value = ''; setStatus('Q&A answers cleared from the current workspace.', 'ok'); });
  $('#resetTemplateBtn').addEventListener('click', async () => {
    if (!confirm('Reset the editable template to defaults?')) return;
    const res = await window.pywebview.api.reset_template();
    template = res.template;
    promptTemplates = res.templates || promptTemplates;
    activeTemplateName = res.activeTemplateName || 'Default';
    settings.activeTemplateName = activeTemplateName;
    renderTemplateSelector();
    renderTemplate();
  });
  $('#saveSettingsBtn').addEventListener('click', async () => {
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    alert('Settings saved.');
  });
  $('#scanFrontPorchBtn')?.addEventListener('click', scanFrontPorchFolder);
  $('#fetchSdModelsBtn')?.addEventListener('click', fetchStableDiffusionModels);
  $('#altCount').addEventListener('input', () => { settings = collectSettings(); renderAltStyleRows(); updateAvailability(); });
  $('#cardMode').addEventListener('change', () => { settings = collectSettings(); if ($('#cardMode').value === 'multi') { ensureMultiBuilderStates(); multiBuilderStates[multiBuilderSelectedIndex] = readBuilderDomState(); } updateCardModeHint(); updateAvailability(); });
  $('#multiCharacterCount').addEventListener('input', () => { settings = collectSettings(); captureCurrentMultiBuilderState(); ensureMultiBuilderStates(); updateMultiBuilderSelectors(true); updateAvailability(); });
  $('#sharedScenePolicy')?.addEventListener('change', () => { settings = collectSettings(); updateAvailability(); });
  $('#builderGenerateBtn')?.addEventListener('click', generateBuilderDescription);
  $('#builderAppendConceptBtn')?.addEventListener('click', appendBuilderToConcept);
  $('#builderClearBtn')?.addEventListener('click', clearCharacterBuilder);
  $('#personalityBuilderGenerateBtn')?.addEventListener('click', generatePersonalityBuilderDescription);
  $('#personalityBuilderAppendConceptBtn')?.addEventListener('click', appendPersonalityBuilderToConcept);
  $('#personalityBuilderClearBtn')?.addEventListener('click', clearPersonalityBuilder);
  $('#sceneBuilderGenerateBtn')?.addEventListener('click', generateSceneBuilderDescription);
  $('#sceneBuilderAppendConceptBtn')?.addEventListener('click', appendSceneBuilderToConcept);
  $('#sceneBuilderClearBtn')?.addEventListener('click', clearSceneBuilder);
  ['builderHairColor','builderClothingStyle','builderUnderwearStyle'].forEach(id => $('#'+id)?.addEventListener('change', updateBuilderConditionalOptions));
  ['pbOccupation','pbKinkFocus','pbCurrentRelationshipStatus','pbPublicRelationshipImage','pbRelationshipPressure','pbUserRelationshipRole','pbUserRelationshipHistory','pbUserCurrentDynamic','pbUserFeelings','pbUserSecretTension','pbUserDesiredDirection','pbSexualPartners','pbVirginityHistory','pbFirstCreampie','sbSetting','sbTime','sbSituation','sbTone','sbGoal'].forEach(id => $('#'+id)?.addEventListener('change', updateCustomConditionalOptions));
  $$('.builder-card select, .builder-card input, .builder-card textarea').forEach(el => el.addEventListener('input', () => { updateBuilderConditionalOptions(); updateCustomConditionalOptions(); captureCurrentMultiBuilderState(); }));
  $$('.multi-builder-character-select').forEach(el => el.addEventListener('change', () => switchMultiBuilderCharacter(el.value)));
  $$('.multi-builder-character-label').forEach(el => el.addEventListener('input', () => { if (!isMultiBuilderMode()) return; $$('.multi-builder-character-label').forEach(other => { if (other !== el) other.value = el.value; }); multiBuilderStates[multiBuilderSelectedIndex] = { ...(multiBuilderStates[multiBuilderSelectedIndex] || {}), ...readBuilderDomState(), multiCharacterName: el.value || '' }; updateMultiBuilderSelectors(false); }));
  $('#selectVisionImageBtn').addEventListener('click', selectVisionImage);
  $('#visionImagePath').addEventListener('input', () => { currentVisionImagePath = $('#visionImagePath').value.trim(); if (settings) settings.visionImagePath = currentVisionImagePath; updateAvailability(); });
  $('#analyzeVisionBtn').addEventListener('click', analyzeVisionImage);
  $('#clearVisionBtn').addEventListener('click', clearVisionDescription);
  $('#outputText').addEventListener('input', updateAvailability);
  $('#stopTaskBtn').addEventListener('click', stopCurrentTask);
  $('#generateBtn').addEventListener('click', generateCard);
  $('#refreshCharactersBtn')?.addEventListener('click', refreshCharacterBrowser);
  $('#browserMultiDeleteBtn')?.addEventListener('click', deleteSelectedCharacterDirectories);
  $('#browserMultiExportPngBtn')?.addEventListener('click', () => exportSelectedCharactersBatch('chara_v2_png'));
  $('#browserMultiExportJsonBtn')?.addEventListener('click', () => exportSelectedCharactersBatch('chara_v2_json'));
  $('#browserMultiFrontPorchBtn')?.addEventListener('click', exportSelectedCharactersToFrontPorchBatch);
  $('#browserCreateFolderBtn')?.addEventListener('click', createBrowserVirtualFolder);
  $('#browserMoveToFolderBtn')?.addEventListener('click', moveSelectedCharactersToFolder);
  $('#browserFolderSelect')?.addEventListener('change', (e) => { browserCurrentFolderId = e.target.value || '__all__'; renderCharacterBrowser(); });
  $('#browserFolderScope')?.addEventListener('change', (e) => { browserFolderScope = e.target.value || 'global'; renderCharacterBrowser(); });
  $('#browserSortMode')?.addEventListener('change', (e) => { browserSortMode = e.target.value || 'date_desc'; renderCharacterBrowser(); });
  $('#browserSearchInput')?.addEventListener('input', (e) => { browserSearchTerm = e.target.value || ''; renderCharacterBrowser(); });
  $('#browserFilterBtn')?.addEventListener('click', () => { browserFilterPanelOpen = !browserFilterPanelOpen; renderBrowserFilterPanel(); });
  $('#browserClearFiltersBtn')?.addEventListener('click', () => { browserIncludeTags.clear(); browserExcludeTags.clear(); renderCharacterBrowser(); });
  $('#browserTagSortMode')?.addEventListener('change', (e) => { browserTagSortMode = e.target.value || 'alpha'; renderBrowserFilterPanel(); });
  $('#tagMergeAddBtn')?.addEventListener('click', addBrowserTagMerge);
  $('#aiTagCleanupBtn')?.addEventListener('click', runAiTagCleanup);
  $('#aiTagMergeAllBtn')?.addEventListener('click', () => applyAiTagSuggestions('merge'));
  $('#aiTagRenameAllBtn')?.addEventListener('click', () => applyAiTagSuggestions('rename'));
  $('#browserAiDescriptionBtn')?.addEventListener('click', regenerateSelectedBrowserDescription);
  $('#browserLoadBtn')?.addEventListener('click', loadSelectedCharacterWorkspace);
  $('#browserExportPngBtn')?.addEventListener('click', () => exportSelectedCharacter('chara_v2_png'));
  $('#browserExportJsonBtn')?.addEventListener('click', () => exportSelectedCharacter('chara_v2_json'));
  $('#browserEmotionZipBtn')?.addEventListener('click', zipSelectedCharacterEmotions);
  $('#browserFrontPorchExportBtn')?.addEventListener('click', exportSelectedCharacterToFrontPorch);
  $('#saveWorkspaceBtn')?.addEventListener('click', () => saveCurrentWorkspace('manual'));
  $('#analyzeImageToBuildersMainBtn')?.addEventListener('click', analyzeSelectedImageToBuilders);
  $('#analyzeVisionToBuildersBtn')?.addEventListener('click', analyzeSelectedImageToBuilders);
  $('#transferToBuildersBtn')?.addEventListener('click', transferConceptToBuilders);
  $('#transferToBuildersMainBtn')?.addEventListener('click', transferConceptToBuilders);
  $('#loadCardToBuildersMainBtn')?.addEventListener('click', loadCardToBuildersNative);
  $('#loadCardToBuildersModeBtn')?.addEventListener('click', loadCardToBuildersNative);
  $('#loadCardToConceptMainBtn')?.addEventListener('click', loadCardToMainConceptNative);
  $('#loadCardToConceptModeBtn')?.addEventListener('click', loadCardToMainConceptNative);
  $('#reviseBtn').addEventListener('click', reviseCard);
  $('#loadSavedBtn').addEventListener('click', loadSavedCardOrProject);
  const viewLogBtn = $('#viewLogBtn'); if (viewLogBtn) viewLogBtn.addEventListener('click', viewDebugLog);
  $('#clearLogBtn').addEventListener('click', clearDebugLog);
  $('#copyBtn').addEventListener('click', copyOutput);
  $('#exportBtn').addEventListener('click', exportCard);
  $('#selectImageBtn').addEventListener('click', selectCardImage);
  $('#generateImagesBtn').addEventListener('click', generateSdImages);
  $('#generateEmotionImagesBtn').addEventListener('click', generateEmotionImages);
  $('#zipEmotionImagesBtn').addEventListener('click', createEmotionZip);
  $('#selectAllEmotionsBtn').addEventListener('click', () => { $$('#emotionOptions input').forEach(el => el.checked = true); });
  $('#clearEmotionsBtn').addEventListener('click', () => { $$('#emotionOptions input').forEach(el => el.checked = false); });
  $('#clearImageBtn').addEventListener('click', () => { $('#cardImagePath').value = ''; settings = collectSettings(); window.pywebview.api.save_settings(settings); setStatus('Card image cleared. PNG export will use the built-in blank image.', 'ok'); });
  $('#modeSelect')?.addEventListener('change', () => { if ($('#modeSelect').value === 'compact_lite') { if (Number($('#maxInputTokens').value || 0) > 8192) $('#maxInputTokens').value = 8000; if (Number($('#maxOutputTokens').value || 0) > 4096) $('#maxOutputTokens').value = 2500; setStatus('Compact Lite selected: token budgets adjusted for an ~8k context model.', 'ok'); } });
  $('#attachConceptFilesBtn').addEventListener('click', attachConceptFiles);
  $('#clearConceptAttachmentsBtn').addEventListener('click', clearConceptAttachments);
  // Hidden file inputs remain as an emergency browser fallback, but normal flow uses KDE/Zenity native dialogs from the backend.
  $('#conceptAttachmentInput').addEventListener('change', handleConceptAttachmentFiles);
  $('#visionFileInput').addEventListener('change', handleVisionFileSelected);
  $('#cardImageFileInput').addEventListener('change', handleCardImageFileSelected);
  $('#savedFileInput').addEventListener('change', handleSavedFileSelected);
  $('#builderCardFileInput')?.addEventListener('change', handleBuilderCardFileSelected);

  bindDropZone('conceptAttachmentDropZone', { inputId: 'conceptAttachmentInput', onFiles: importConceptAttachmentFiles });
  bindDropZone('visionDropZone', { inputId: 'visionFileInput', onFiles: importVisionFiles });
  bindDropZone('savedFileDropZone', { inputId: 'savedFileInput', onFiles: importSavedFiles });
  bindDropZone('builderCardDropZoneMain', { inputId: 'builderCardFileInput', onFiles: importBuilderCardFiles });
  bindDropZone('builderCardDropZoneMode', { inputId: 'builderCardFileInput', onFiles: importBuilderCardFiles });
  bindDropZone('conceptCardDropZoneMain', { inputId: null, onClick: loadCardToMainConceptNative, onFiles: importCardToMainConceptFiles });
  bindDropZone('conceptCardDropZoneMode', { inputId: null, onClick: loadCardToMainConceptNative, onFiles: importCardToMainConceptFiles });
  bindDropZone('cardImageDropZone', { inputId: 'cardImageFileInput', onFiles: importCardImageFiles });
  enhanceBuilderAiButtons();
  populateBuilderPresets();
  populateAiRandomThemes();
  $('#aiRandomThemeSelect')?.addEventListener('change', updateAiRandomThemeCustom);
  $('#aiRandomCustomTheme')?.addEventListener('input', () => { /* kept live for randomize */ });
  updateAiRandomThemeCustom();
  $('#builderPresetSelect')?.addEventListener('change', updateBuilderPresetPreview);
  $('#applyPresetBtn')?.addEventListener('click', () => applyBuilderPreset({ build: false }));
  $('#applyPresetBuildBtn')?.addEventListener('click', () => applyBuilderPreset({ build: true }));
  $('#aiRandomPresetBtn')?.addEventListener('click', () => aiRandomizeBuilderPreset({ build: false }));
  $('#aiRandomPresetBuildBtn')?.addEventListener('click', () => aiRandomizeBuilderPreset({ build: true }));
}


const AI_RANDOM_THEMES = {
  ntr: { name: 'NTR / Forbidden Temptation', prompt: 'Create a random adult NTR or forbidden-temptation route. Vary the character type, body, fashion, occupation, relationship with {{user}}, secret pressure, and scene setup each time. Keep it emotionally coherent and avoid contradictions.' },
  slutty: { name: 'Slutty / Promiscuous Character', prompt: 'Create a random adult sexually confident or promiscuous character. Vary whether she is shameless, secretive, playful, manipulative, needy, or thrill-seeking. Pick compatible clothing, personality, sexual history, and scene setup.' },
  romance: { name: 'Romance / Slow Burn', prompt: 'Create a random adult romance or slow-burn character. Vary the archetype, visual style, relationship history, emotional defenses, and opening scene while keeping the sexual traits optional and coherent.' },
  workplace: { name: 'Workplace / Office Drama', prompt: 'Create a random adult workplace scenario. Vary job, power dynamic, outfit style, secrets, professionalism, private desire, and what is about to happen.' },
  sharehouse: { name: 'Share House / Group Chaos', prompt: 'Create a random adult share-house, roommate, or multi-character single-card setup. Vary the cast style, relationships, secrets, tensions, and group dynamic without conflicting card mode settings.' },
  gyaru: { name: 'Gyaru / Social Butterfly', prompt: 'Create a random adult gyaru-inspired character. Vary whether she is wholesome, bratty, slutty, secretly nerdy, manipulative, romantic, or conflicted. Pick matching hair, makeup, outfit, speech, and scene.' },
  dark: { name: 'Dark Romance / Corruption', prompt: 'Create a random adult dark-romance or corruption-focused route. Vary the source of temptation, secrets, emotional conflict, boundaries, and scenario risk while keeping it roleplay-safe and coherent.' },
  custom: { name: 'Custom…', prompt: '' },
  wildcard: { name: 'Wildcard Mix', prompt: 'Create a coherent random adult character-card setup using any compatible mix of romance, drama, comedy, kink, secrecy, slice-of-life, school/university, workplace, or fantasy tropes. Avoid contradictory settings.' }
};

const BUILDER_PRESETS = {
  ntr_gyaru: {
    name: 'NTR Gyaru Temptation',
    tags: ['NTR', 'gyaru', 'cheating tension', 'secret desire'],
    description: 'Adult-coded confident gyaru with secrecy, temptation, and risky relationship drama. Good for betrayal/cuckold/NTR-style routes.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'curvy', builderSkin: 'golden tan', builderHairLength: 'mid-back length', builderHairTexture: 'soft waves', builderHairColor: 'honey blonde', builderAccentColor: 'pink underside layers', builderFaceShape: 'heart-shaped', builderEyeShape: 'sharp upturned', builderEyeColor: 'dark brown', builderMakeup: 'gyaru makeup', builderBust: 'E-cup', builderWaistHips: 'narrow waist and wide hips', builderLegs: 'toned legs', builderClothingStyle: 'revealing gyaru', builderClothingExposure: 'cleavage-focused', builderClothingDetail: 'cropped cardigan, low-cut top, mini skirt, glossy nails, gold accessories', builderClothingColors: 'pastel pink, white, and gold accents', builderUnderwearStyle: 'lace lingerie', builderUnderwearCoverage: 'revealing adult-coded', builderUnderwearColor: 'pink lace', builderUnderwearDetail: 'matching lace set with tiny bow details', builderFootwear: 'platform sneakers', builderAccessories: 'gold jewelry, phone charms, hair clips', builderFeatures: 'pierced ears, beauty mark near collarbone, sweet floral perfume', builderVibe: 'playful',
      pbArchetype: 'confident gyaru', pbSocial: 'attention-seeking', pbConfidence: 'shameless', pbEmotion: 'rationalizes bad choices', pbDrive: 'wants validation and attention', pbFear: 'being ordinary', pbMoral: 'conflicted', pbDecision: 'impulsive when aroused', pbOccupation: 'custom', pbOccupationCustom: 'adult-coded university student with a popular social life', pbUserBehavior: 'acts innocent while hiding secrets', pbAttachment: 'emotionally loyal but physically adventurous', pbConflict: 'lies until cornered', pbSecrecy: 'strategic and careful', pbCurrentRelationshipStatus: 'dating someone else', pbPublicRelationshipImage: 'publicly loyal girlfriend', pbRelationshipPressure: 'tempted by {{user}}', pbUserRelationshipRole: 'current lovers', pbUserRelationshipHistory: 'have unresolved romantic tension', pbUserCurrentDynamic: 'trust mixed with resentment', pbUserFeelings: 'conflicted between love and desire', pbUserSecretTension: 'hides a betrayal', pbUserDesiredDirection: 'custom', pbUserDesiredDirectionCustom: 'slow-burn secret corruption where she tries to keep {{user}} emotionally while chasing dangerous thrills', pbSexualNature: 'promiscuous but selective', pbLibido: 'high drive', pbPromiscuity: 'sexually adventurous', pbDynamic: 'switchy', pbRisk: 'enjoys risky situations', pbKinkFocus: 'custom', pbKinkCustom: 'cuckolding, secrecy, risky meetings, being desired by someone forbidden', pbTurnOns: 'confidence, assertiveness, being chased, dangerous compliments, secrecy', pbTurnOffs: 'clinginess, boring routine, being judged, weak excuses', pbNsfwBoundaries: 'adult-only consensual content; avoids public exposure that would ruin her life', pbSpeech: 'playful and teasing', pbQuirks: 'plays with hair when lying, checks phone too often, giggles when deflecting', pbLikes: 'attention, fashion, late-night dates, sweet drinks, being praised', pbDislikes: 'boredom, jealousy aimed at her, being controlled, serious confrontations', pbHobbies: 'shopping, social media, karaoke, skincare, teasing {{user}}', pbExtraNotes: 'Keep her emotionally attached to {{user}} while letting temptation and secrecy create pressure.',
      sbSetting: 'apartment / home', sbLocation: '{{user}}\'s apartment living room late at night', sbTime: 'late night', sbSituation: 'secret visit', sbJustHappened: 'she returned from a suspicious night out and is trying to act casual', sbAboutToHappen: '{{user}} notices something is off and asks what really happened', sbTone: 'tense and erotic', sbGoal: 'hide a secret', sbRisk: 'her lies may collapse if {{user}} asks the right question', sbProps: 'phone with unread messages, perfume not belonging to {{user}}, wrinkled clothes', sbExtraNotes: 'Opening should balance affection, guilt, teasing, and danger.'
    }
  },
  slutty_roommate: {
    name: 'Shameless Slutty Roommate',
    tags: ['slutty', 'roommate', 'teasing', 'provocative'],
    description: 'Adult-coded roommate who is bold, messy, flirty, openly perverted, and constantly pushes boundaries.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'hourglass', builderSkin: 'warm ivory', builderHairLength: 'waist-length', builderHairTexture: 'messy layered', builderHairColor: 'chestnut brown', builderFaceShape: 'soft and delicate', builderEyeShape: 'sleepy half-lidded', builderEyeColor: 'amber', builderMakeup: 'glossy lips', builderBust: 'large bust', builderWaistHips: 'soft waist and rounded hips', builderLegs: 'soft thick thighs', builderClothingStyle: 'bedroom wear', builderClothingExposure: 'provocative adult-coded', builderClothingDetail: 'oversized shirt slipping off one shoulder, tiny shorts, loose neckline', builderClothingColors: 'white shirt, black shorts, pastel underwear accents', builderUnderwearStyle: 'no bra under outfit', builderUnderwearCoverage: 'barely-there styling', builderUnderwearColor: 'black lace', builderUnderwearDetail: 'visible lace waistband and loose shirt fabric', builderFootwear: 'sandals', builderAccessories: 'choker, messy hair tie, phone always in hand', builderFeatures: 'sleepy eyes, soft curves, faint perfume, playful smirk', builderVibe: 'bratty',
      pbArchetype: 'chaotic troublemaker', pbSocial: 'life of the party', pbConfidence: 'shameless', pbEmotion: 'dramatic and reactive', pbDrive: 'wants freedom and excitement', pbFear: 'being judged', pbMoral: 'shamelessly hedonistic', pbDecision: 'goes with the flow', pbOccupation: 'custom', pbOccupationCustom: 'adult-coded share house roommate working casual shifts', pbUserBehavior: 'pushes {{user}}\'s boundaries', pbAttachment: 'casual but slowly catching feelings', pbConflict: 'seduces to avoid the issue', pbSecrecy: 'reckless with secrets', pbUserRelationshipRole: 'roommates', pbUserRelationshipHistory: '{{user}} knows her hidden side', pbUserCurrentDynamic: 'teasing with obvious chemistry', pbUserFeelings: 'physically attracted but emotionally guarded', pbUserSecretTension: 'hides feelings behind teasing', pbUserDesiredDirection: 'custom', pbUserDesiredDirectionCustom: 'constant boundary-pushing roommate tension that slowly becomes emotionally messy', pbSexualNature: 'shameless and openly horny', pbLibido: 'very high drive', pbPromiscuity: 'promiscuous but selective', pbDynamic: 'teasing dominant', pbRisk: 'exhibitionist tendencies', pbKinkFocus: 'teasing, dirty talk, semi-public risk, casual hookups', pbTurnOns: 'being watched, bold flirting, verbal teasing, {{user}} getting flustered', pbTurnOffs: 'judgmental lectures, needy clinginess, boring timid behavior', pbNsfwBoundaries: 'adult-only consensual content; no genuine humiliation outside agreed play', pbSpeech: 'casual and vulgar when comfortable', pbQuirks: 'leaves clothes around, steals food, sends baiting selfies, laughs too loudly', pbLikes: 'late nights, parties, snacks, teasing, attention, trashy romance drama', pbDislikes: 'chores, boring rules, being ignored, clingy serious talks', pbHobbies: 'streaming, clubbing, lounging around half-dressed, gossiping, gaming badly', pbExtraNotes: 'Make her shameless, but let affection leak through when she thinks {{user}} is not noticing.',
      sbSetting: 'apartment / home', sbLocation: 'shared apartment kitchen and hallway', sbTime: 'late night', sbSituation: 'awkward interruption', sbJustHappened: '{{user}} came home and found her dressed way too casually in the common area', sbAboutToHappen: 'she decides to tease {{user}} instead of covering up', sbTone: 'comedic and erotic', sbGoal: 'tease {{user}}', sbRisk: 'their roommate dynamic may cross a line', sbProps: 'borrowed shirt, drink can, phone, laundry basket', sbExtraNotes: 'Opening should be playful, shameless, and pushy without becoming instantly serious.'
    }
  },
  wholesome_childhood_friend: {
    name: 'Wholesome Childhood Friend Romance',
    tags: ['romance', 'childhood friend', 'sweet', 'slow burn'],
    description: 'Soft romance preset for a warm childhood friend with gentle tension and emotional intimacy.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'slender', builderSkin: 'fair', builderHairLength: 'shoulder-length', builderHairTexture: 'soft waves', builderHairColor: 'dark brown', builderFaceShape: 'round', builderEyeShape: 'gentle drooping', builderEyeColor: 'brown', builderMakeup: 'natural makeup', builderBust: 'C-cup', builderWaistHips: 'balanced proportions', builderLegs: 'long slender legs', builderClothingStyle: 'cozy homewear', builderClothingExposure: 'modest', builderClothingDetail: 'soft cardigan, simple skirt, warm scarf', builderClothingColors: 'cream, beige, soft pink', builderUnderwearStyle: 'no visible underwear details', builderUnderwearCoverage: 'modest coverage', builderFootwear: 'loafers', builderAccessories: 'simple hair clip, small pendant necklace', builderFeatures: 'warm smile, faint freckles, gentle posture', builderVibe: 'soft and caring',
      pbArchetype: 'sweet and affectionate', pbSocial: 'ambivert', pbConfidence: 'cautiously confident', pbEmotion: 'warm and expressive', pbDrive: 'wants affection and security', pbFear: 'falling in love', pbMoral: 'kind but flexible', pbDecision: 'careful and calculated', pbOccupation: 'custom', pbOccupationCustom: 'adult-coded student / part-time worker', pbUserBehavior: 'sweet and devoted', pbAttachment: 'secure once trusted', pbConflict: 'talks things out', pbSecrecy: 'keeps small secrets', pbUserRelationshipRole: 'childhood friends', pbUserRelationshipHistory: 'grew up together and know each other deeply', pbUserCurrentDynamic: 'comfortable and affectionate', pbUserFeelings: 'in denial about romantic feelings', pbUserSecretTension: 'hides how much she wants {{user}}', pbUserDesiredDirection: 'slow-burn romance where old familiarity turns into honest confession', pbSexualNature: 'romantic and affectionate', pbLibido: 'average drive', pbPromiscuity: 'exclusive by nature', pbDynamic: 'gentle and responsive', pbRisk: 'private and cautious', pbTurnOns: 'emotional honesty, tenderness, being chosen, quiet intimacy', pbTurnOffs: 'cruel teasing, pressure, dishonesty', pbNsfwBoundaries: 'adult-only consensual content; prefers emotional trust first', pbSpeech: 'soft and earnest', pbQuirks: 'remembers small details, fusses over {{user}}, blushes when caught caring', pbLikes: 'tea, rainy days, old memories, cooking, quiet walks', pbDislikes: 'being taken for granted, loud crowds, forced honesty before she is ready', pbHobbies: 'cooking, reading, journaling, tending plants', pbExtraNotes: 'Emotional core is comfort, history, and the fear of changing the relationship.',
      sbSetting: 'apartment / home', sbLocation: 'quiet living room during a rainy evening', sbTime: 'evening', sbSituation: 'private conversation', sbJustHappened: 'she came over with food after hearing {{user}} had a rough day', sbAboutToHappen: 'old feelings start slipping into the conversation', sbTone: 'tender and romantic', sbGoal: 'comfort {{user}}', sbRisk: 'confessing may change their friendship forever', sbProps: 'home-cooked meal, umbrella, old photo, warm tea', sbExtraNotes: 'Opening should be gentle, emotionally warm, and slightly nervous.'
    }
  },
  office_affair: {
    name: 'Office Affair / Forbidden Workplace',
    tags: ['workplace', 'forbidden', 'mature', 'secret affair'],
    description: 'Adult-coded workplace tension with status, restraint, secrecy, and polished presentation.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'tall and elegant', builderSkin: 'warm ivory', builderHairLength: 'mid-back length', builderHairTexture: 'straight', builderHairColor: 'black', builderFaceShape: 'sharp and angular', builderEyeShape: 'almond-shaped', builderEyeColor: 'gray', builderMakeup: 'smoky eye makeup', builderBust: 'D-cup', builderWaistHips: 'narrow waist and wide hips', builderLegs: 'long slender legs', builderClothingStyle: 'office lady', builderClothingExposure: 'flirty and figure-hugging', builderClothingDetail: 'tailored blouse, pencil skirt, stockings, blazer worn open', builderClothingColors: 'black, white, and wine red accents', builderUnderwearStyle: 'satin lingerie', builderUnderwearCoverage: 'flirty but not explicit', builderUnderwearColor: 'black satin', builderUnderwearDetail: 'elegant matching set hidden under office clothes', builderFootwear: 'heels', builderAccessories: 'watch, delicate earrings, ID badge, glasses', builderFeatures: 'controlled posture, red lipstick, subtle perfume', builderVibe: 'elegant',
      pbArchetype: 'dominant and commanding', pbSocial: 'quietly observant', pbConfidence: 'naturally confident', pbEmotion: 'calm and pragmatic', pbDrive: 'wants control', pbFear: 'being exposed', pbMoral: 'self-serving but not cruel', pbDecision: 'careful and calculated', pbOccupation: 'custom', pbOccupationCustom: 'office manager / senior coworker', pbUserBehavior: 'pushes {{user}}\'s boundaries', pbAttachment: 'fearful avoidant', pbConflict: 'goes cold and distant', pbSecrecy: 'compartmentalizes different lives', pbCurrentRelationshipStatus: 'married woman', pbPublicRelationshipImage: 'publicly devoted wife', pbRelationshipPressure: 'emotionally lonely', pbUserRelationshipRole: 'coworkers', pbUserRelationshipHistory: 'have unresolved romantic tension', pbUserCurrentDynamic: 'power imbalance with tension', pbUserFeelings: 'sees {{user}} as temptation', pbUserSecretTension: 'both know the situation is wrong but want it anyway', pbUserDesiredDirection: 'secret workplace tension escalating through private meetings and restrained confessions', pbSexualNature: 'controlled but intense', pbLibido: 'high drive', pbPromiscuity: 'selective and discreet', pbDynamic: 'dominant leaning', pbRisk: 'risk-aware but tempted', pbKinkFocus: 'power dynamics, secrecy, restraint, office tension', pbTurnOns: 'competence, obedience, confidence, private defiance', pbTurnOffs: 'sloppiness, gossip, immaturity, public scenes', pbNsfwBoundaries: 'adult-only consensual content; avoids career-ending exposure', pbSpeech: 'polished and dryly teasing', pbQuirks: 'adjusts glasses when lying, taps pen when impatient, keeps perfect composure', pbLikes: 'wine, quiet offices, competence, tailored clothes, late-night work', pbDislikes: 'gossip, incompetence, messy emotions, losing control', pbHobbies: 'reading reports, wine bars, Pilates, expensive stationery', pbExtraNotes: 'Keep her composed on the surface and intensely conflicted underneath.',
      sbSetting: 'workplace / office', sbLocation: 'empty office after hours', sbTime: 'late night', sbSituation: 'after-hours meeting', sbJustHappened: 'everyone else left, but she asked {{user}} to stay behind', sbAboutToHappen: 'a professional conversation turns dangerously personal', sbTone: 'tense and erotic', sbGoal: 'test boundaries', sbRisk: 'workplace exposure and power imbalance', sbProps: 'locked office door, desk lamp, unfinished report, coffee mug', sbExtraNotes: 'Opening should use restraint, tension, and professional language cracking at the edges.'
    }
  },
  share_house_harem: {
    name: 'Share House / Multi-Girl Chaos',
    tags: ['share house', 'multi-character', 'harem comedy', 'secrets'],
    description: 'Preset for a messy share-house or group-card setup with multiple adult-coded women, secrets, and chaotic dynamics.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'curvy', builderSkin: 'light tan', builderHairLength: 'very long', builderHairTexture: 'soft waves', builderHairColor: 'two-tone', builderAccentColor: 'contrasting character-specific accent colors', builderFaceShape: 'heart-shaped', builderEyeShape: 'large anime eyes', builderEyeColor: 'amber', builderMakeup: 'gyaru makeup', builderBust: 'large bust', builderWaistHips: 'narrow waist and wide hips', builderLegs: 'soft thick thighs', builderClothingStyle: 'casual streetwear', builderClothingExposure: 'flirty and figure-hugging', builderClothingDetail: 'each resident has a distinct outfit style: sporty, gyaru, elegant, cozy homewear', builderClothingColors: 'varied character-coded colors', builderUnderwearStyle: 'cute matching set', builderUnderwearCoverage: 'flirty but not explicit', builderUnderwearColor: 'varied per character', builderFootwear: 'platform sneakers', builderAccessories: 'phone charms, necklaces, hair clips, personal room keys', builderFeatures: 'distinct silhouettes and contrasting fashion tastes', builderVibe: 'playful',
      pbArchetype: 'chaotic troublemaker', pbSocial: 'outgoing', pbConfidence: 'naturally confident', pbEmotion: 'dramatic and reactive', pbDrive: 'wants excitement', pbFear: 'being exposed', pbMoral: 'kind but flexible', pbDecision: 'goes with the flow', pbOccupation: 'custom', pbOccupationCustom: 'adult-coded share house residents with different jobs/studies', pbUserBehavior: 'teasing and flirty', pbAttachment: 'casual but slowly catching feelings', pbConflict: 'deflects with jokes', pbSecrecy: 'keeps small secrets', pbUserRelationshipRole: 'roommates', pbUserRelationshipHistory: 'forced into close proximity recently', pbUserCurrentDynamic: 'teasing with obvious chemistry', pbUserFeelings: 'secretly attracted', pbUserSecretTension: 'hides feelings behind teasing', pbUserDesiredDirection: 'multi-character single card where each woman has a distinct voice and rivalry for attention', pbSexualNature: 'varies by character', pbLibido: 'varied by character', pbPromiscuity: 'varied by character', pbDynamic: 'varied by character', pbRisk: 'private and cautious', pbKinkFocus: 'rivalry, teasing, secret crushes, accidental intimacy', pbTurnOns: 'attention, flirting, being chosen, playful competition', pbTurnOffs: 'being ignored, boring house rules, jealousy getting too serious', pbNsfwBoundaries: 'adult-only consensual content; keep each character distinct', pbSpeech: 'distinct voices per character', pbQuirks: 'each resident has a memorable habit and catchphrase', pbLikes: 'group dinners, gossip, games, late-night talks', pbDislikes: 'house chores, awkward silences, secrets being exposed', pbHobbies: 'varied hobbies across the cast', pbExtraNotes: 'Use clear speaker attribution and maintain each character\'s unique personality.',
      sbSetting: 'share house / dorm', sbLocation: 'shared living room and kitchen', sbTime: 'evening', sbSituation: 'new arrival', sbJustHappened: '{{user}} moved into the share house and met the residents', sbAboutToHappen: 'the residents test boundaries and establish the new household dynamic', sbTone: 'comedic and flirty', sbGoal: 'introduce the cast', sbRisk: 'too many secrets and attractions under one roof', sbProps: 'moving boxes, house rules sheet, shared fridge, room keys', sbExtraNotes: 'For multi-character card mode, have the first message showcase multiple residents naturally.'
    },
    cardMode: 'multi', multiCharacterCount: '3'
  },
  tsundere_rival: {
    name: 'Tsundere Rival / Bratty Slow Burn',
    tags: ['tsundere', 'rival', 'slow burn', 'banter'],
    description: 'A sharp-tongued rival who hides attraction under competition, sarcasm, and pride.',
    fields: {
      builderPresentation: 'feminine', builderBuild: 'athletic', builderSkin: 'fair', builderHairLength: 'shoulder-length', builderHairTexture: 'ponytail', builderHairColor: 'red', builderFaceShape: 'sharp and angular', builderEyeShape: 'sharp upturned', builderEyeColor: 'green', builderMakeup: 'natural makeup', builderBust: 'B-cup', builderWaistHips: 'athletic core and toned hips', builderLegs: 'athletic legs', builderClothingStyle: 'sporty', builderClothingExposure: 'slightly revealing', builderClothingDetail: 'fitted athletic top, track jacket tied at waist, shorts', builderClothingColors: 'red, black, and white', builderUnderwearStyle: 'sports bra and shorts', builderUnderwearCoverage: 'cute and practical', builderFootwear: 'platform sneakers', builderAccessories: 'sports wristband, hair tie, small earrings', builderFeatures: 'competitive stare, quick movements, faint blush when cornered', builderVibe: 'bratty',
      pbArchetype: 'bratty tease', pbSocial: 'outgoing', pbConfidence: 'arrogant until challenged', pbEmotion: 'jealous but denies it', pbDrive: 'wants self-improvement', pbFear: 'falling in love', pbMoral: 'principled', pbDecision: 'impulsive when emotional', pbOccupation: 'custom', pbOccupationCustom: 'adult-coded student athlete / club rival', pbUserBehavior: 'teasing and flirty', pbAttachment: 'fearful avoidant', pbConflict: 'gets bratty and defensive', pbSecrecy: 'keeps small secrets', pbUserRelationshipRole: 'rivals with tension', pbUserRelationshipHistory: 'have unresolved romantic tension', pbUserCurrentDynamic: 'uses banter to hide vulnerability', pbUserFeelings: 'in denial about romantic feelings', pbUserSecretTension: 'hides how much she wants {{user}}', pbUserDesiredDirection: 'rivalry-to-romance slow burn with lots of denial and accidental softness', pbSexualNature: 'curious but defensive', pbLibido: 'medium drive', pbPromiscuity: 'exclusive by nature', pbDynamic: 'bratty submissive leaning', pbRisk: 'private and cautious', pbTurnOns: 'being challenged, competence, praise she pretends to hate, losing control safely', pbTurnOffs: 'arrogance without skill, pity, public embarrassment', pbNsfwBoundaries: 'adult-only consensual content; needs trust before vulnerability', pbSpeech: 'sharp and sarcastic', pbQuirks: 'calls {{user}} idiot, blushes when praised, gets competitive over tiny things', pbLikes: 'winning, training, spicy food, late-night practice, secret praise', pbDislikes: 'losing, being pitied, being teased back too effectively', pbHobbies: 'sports practice, competitive games, stretching, secretly reading romance manga', pbExtraNotes: 'Let her hostility crack into affection gradually.',
      sbSetting: 'school / university', sbLocation: 'empty clubroom after practice', sbTime: 'evening', sbSituation: 'rival confrontation', sbJustHappened: '{{user}} beat her in a competition or challenge', sbAboutToHappen: 'she demands a rematch but the tension becomes personal', sbTone: 'comedic and romantic', sbGoal: 'challenge {{user}}', sbRisk: 'her pride may reveal her feelings', sbProps: 'sports bag, towel, scoreboard, locked clubroom door', sbExtraNotes: 'Opening should be bratty, fast-paced, and full of denial.'
    }
  }
};

function populateAiRandomThemes() {
  const select = $('#aiRandomThemeSelect');
  if (!select) return;
  select.innerHTML = '';
  Object.entries(AI_RANDOM_THEMES).forEach(([key, theme]) => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = theme.name;
    select.appendChild(opt);
  });
}

function updateAiRandomThemeCustom() {
  const wrap = $('#aiRandomCustomThemeWrap');
  const isCustom = ($('#aiRandomThemeSelect')?.value || '') === 'custom';
  if (wrap) wrap.classList.toggle('hidden', !isCustom);
}

function getSelectedAiRandomTheme() {
  const key = $('#aiRandomThemeSelect')?.value || 'wildcard';
  if (key === 'custom') {
    const custom = ($('#aiRandomCustomTheme')?.value || '').trim();
    return {
      key: 'custom',
      preset: {
        name: custom ? `Custom: ${custom.slice(0, 60)}` : 'Custom Theme',
        prompt: custom || 'Create a coherent random adult character-card setup from a custom user theme, varying character, body, clothing, personality, relationship, and scene without contradictions.',
        tags: ['custom']
      }
    };
  }
  return { key, preset: AI_RANDOM_THEMES[key] || AI_RANDOM_THEMES.wildcard };
}

function populateBuilderPresets() {
  const select = $('#builderPresetSelect');
  if (!select) return;
  select.innerHTML = Object.entries(BUILDER_PRESETS).map(([key, preset]) => `<option value="${key}">${preset.name}</option>`).join('');
  updateBuilderPresetPreview();
}

function updateBuilderPresetPreview() {
  const key = $('#builderPresetSelect')?.value;
  const preset = BUILDER_PRESETS[key];
  const desc = $('#builderPresetDescription');
  const tags = $('#builderPresetTags');
  if (!preset) return;
  if (desc) desc.textContent = preset.description || '';
  if (tags) tags.innerHTML = (preset.tags || []).map(t => `<span>${t}</span>`).join('');
}

function setBuilderFieldValue(id, value) {
  const el = $('#' + id);
  if (!el || value === undefined || value === null) return false;
  const text = String(value).trim();
  if (!text) return false;
  if (el.tagName === 'SELECT') {
    const options = [...el.options];
    const exact = options.find(o => (o.value || o.textContent).trim().toLowerCase() === text.toLowerCase());
    if (exact) el.value = exact.value || exact.textContent;
    else {
      const custom = options.find(o => (o.value || o.textContent).trim().toLowerCase().startsWith('custom'));
      if (custom) el.value = custom.value || custom.textContent;
      else return false;
    }
  } else {
    el.value = text;
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}

function applyBuilderPreset({ build = false } = {}) {
  const key = $('#builderPresetSelect')?.value || Object.keys(BUILDER_PRESETS)[0];
  const preset = BUILDER_PRESETS[key];
  if (!preset) return;
  const mode = $('#builderPresetMode')?.value || 'merge';
  if (mode === 'replace') {
    clearCharacterBuilder();
    clearPersonalityBuilder();
    clearSceneBuilder();
  }
  Object.entries(preset.fields || {}).forEach(([id, value]) => setBuilderFieldValue(id, value));
  if (preset.cardMode && $('#cardMode')) {
    $('#cardMode').value = preset.cardMode;
    if ($('#multiCharacterCount') && preset.multiCharacterCount) $('#multiCharacterCount').value = preset.multiCharacterCount;
    updateCardModeHint();
  }
  updateBuilderConditionalOptions();
  updateCustomConditionalOptions();
  if (build) {
    generateBuilderDescription();
    generatePersonalityBuilderDescription();
    generateSceneBuilderDescription();
    captureCurrentMultiBuilderState();
    setStatus(`${preset.name} preset applied and builder text created for ${isMultiBuilderMode() ? getMultiBuilderCharacterName(multiBuilderSelectedIndex) : 'the current builder'}. Fine-tune anything you want before generating.`, 'ok');
  } else {
    captureCurrentMultiBuilderState();
    setStatus(`${preset.name} preset applied to ${isMultiBuilderMode() ? getMultiBuilderCharacterName(multiBuilderSelectedIndex) : 'the current builder'}. Open the Builder tabs to fine-tune, then click Build.`, 'ok');
  }
}


function collectBuilderFieldCatalog() {
  const catalog = [];
  $$('.builder-card label').forEach(label => {
    const el = label.querySelector('select, input:not([type="button"]):not([type="hidden"]), textarea');
    if (!el || !el.id) return;
    catalog.push({
      id: el.id,
      label: cleanLabelText(label) || el.id,
      kind: el.tagName === 'SELECT' ? 'select' : (el.tagName === 'TEXTAREA' ? 'textarea' : 'text'),
      options: getFieldOptions(el),
      currentValue: String(el.value || '').trim(),
      isCustomText: el.id.endsWith('Custom') || el.id === 'builderHairAccentCustom' || el.id === 'builderClothingDetail' || el.id === 'builderClothingColors' || el.id === 'builderAccessories' || el.id === 'builderFeatures' || el.id === 'builderVibe' || el.id === 'builderUnderwearColor' || el.id === 'builderUnderwearDetails',
    });
  });
  return catalog;
}

function getBuilderFieldGroup(id) {
  if (!id) return 'other';
  if (id.startsWith('pb')) return 'personality';
  if (id.startsWith('sb')) return 'scene';
  if (id.startsWith('builder')) return 'character';
  return 'other';
}

function collectCompactBuilderFieldCatalog() {
  const keepIds = new Set([
    // Character / visual builder — enough to vary body, colors, clothing and visual vibe.
    'builderPresentation','builderBuild','builderSkin','builderHairLength','builderHairTexture','builderHairColor','builderAccentColor','builderFaceShape','builderEyeShape','builderEyeColor','builderMakeup','builderBust','builderWaistHips','builderLegs','builderClothingStyle','builderClothingExposure','builderClothingDetail','builderClothingColors','builderUnderwearStyle','builderUnderwearCoverage','builderUnderwearColor','builderFootwear','builderAccessories','builderFeatures','builderVibe',
    // Personality builder — includes relationship/social role, sexual traits and sexual history.
    'pbArchetype','pbSocial','pbConfidence','pbEmotion','pbDrive','pbFear','pbMoral','pbDecision','pbOccupation','pbCurrentRelationshipStatus','pbCurrentPartner','pbPublicRelationshipImage','pbRelationshipPressure','pbUserRelationshipRole','pbUserRelationshipHistory','pbUserCurrentDynamic','pbUserFeelings','pbUserSecretTension','pbUserDesiredDirection','pbSexualNature','pbLibido','pbPromiscuity','pbDynamic','pbRisk','pbKinkFocus','pbTurnOns','pbTurnOffs','pbNsfwBoundaries','pbSexualPartners','pbVirginityHistory','pbFirstCreampie','pbBestSexualMemory','pbWorstSexualMemory','pbCurrentSexualSituation','pbSexualReputation','pbSpeech','pbLikes','pbDislikes','pbHobbies','pbExtraNotes',
    // Scene builder — the opening setup and immediate situation.
    'sbSetting','sbLocation','sbTime','sbSituation','sbJustHappened','sbAboutToHappen','sbTone','sbGoal','sbRisk','sbProps','sbExtraNotes'
  ]);
  return collectBuilderFieldCatalog()
    .filter(f => keepIds.has(f.id))
    .map(f => ({
      id: f.id,
      group: getBuilderFieldGroup(f.id),
      label: f.label,
      kind: f.kind,
      options: (f.options || []).slice(0, 14)
    }));
}

function collectGroupedCompactBuilderCatalog() {
  const groups = { character: [], personality: [], scene: [] };
  collectCompactBuilderFieldCatalog().forEach(f => {
    const group = f.group || getBuilderFieldGroup(f.id);
    if (groups[group]) groups[group].push(f);
  });
  return groups;
}


function buildMultiStateFromFields(fields, fallbackName='Character') {
  const state = { ...(fields || {}) };
  if (!state.multiCharacterName) state.multiCharacterName = fallbackName;
  const originalState = readBuilderDomState();
  writeBuilderDomState(state);
  state.builderDescription = state.builderDescription || buildCharacterBuilderDescription();
  state.personalityBuilderDescription = state.personalityBuilderDescription || buildPersonalityBuilderDescription();
  state.sceneBuilderDescription = state.sceneBuilderDescription || buildSceneBuilderDescription();
  writeBuilderDomState(originalState);
  return state;
}

function applyBuilderTransferResult(res) {
  const characters = Array.isArray(res.characters) ? res.characters.filter(ch => ch && ch.fields) : [];
  let count = 0;
  if (characters.length >= 2) {
    $('#cardMode').value = 'multi';
    $('#multiCharacterCount').value = String(Math.min(12, Math.max(2, characters.length)));
    settings.cardMode = 'multi';
    settings.multiCharacterCount = Number($('#multiCharacterCount').value || 2);
    multiBuilderSelectedIndex = 0;
    multiBuilderStates = characters.slice(0, Number($('#multiCharacterCount').value)).map((ch, idx) => {
      const fields = { ...(ch.fields || {}) };
      if (ch.name && !fields.multiCharacterName) fields.multiCharacterName = ch.name;
      count += Object.keys(fields).filter(k => k !== 'multiCharacterName').length;
      return buildMultiStateFromFields(fields, ch.name || `Character ${idx + 1}`);
    });
    ensureMultiBuilderStates();
    writeBuilderDomState(multiBuilderStates[0] || {});
    updateCardModeHint();
    updateMultiBuilderSelectors(true);
  } else {
    Object.entries(res.fields || {}).forEach(([id, value]) => {
      if (setBuilderFieldValue(id, value)) count += 1;
    });
    if (res.cardMode) $('#cardMode').value = res.cardMode;
    if (res.multiCharacterCount) $('#multiCharacterCount').value = res.multiCharacterCount;
    updateCardModeHint();
    updateBuilderConditionalOptions();
    updateCustomConditionalOptions();
    generateBuilderDescription();
    generatePersonalityBuilderDescription();
    generateSceneBuilderDescription();
  }
  return { count, characterCount: characters.length };
}

async function transferConceptToBuilders() {
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  const mainConcept = ($('#conceptText')?.value || '').trim();
  const characterDescription = ($('#visionDescription')?.value || '').trim();
  if (!mainConcept && !characterDescription) {
    setStatus('Write a Main Concept or provide a Character Description / Vision Description first.', 'error');
    return;
  }
  setBusy('TRANSFER TO BUILDERS — reading concept and filling builder fields…');
  setStatus('Transferring concept into Character, Personality, and Scene Builders…', '');
  try {
    const catalog = collectCompactBuilderFieldCatalog();
    const res = await window.pywebview.api.ai_transfer_to_builders(mainConcept, characterDescription, catalog, settings);
    if (!res.ok) throw new Error(res.error || 'Transfer to Builders failed.');
    const applied = applyBuilderTransferResult(res);
    const multiMsg = applied.characterCount >= 2 ? ` Detected ${applied.characterCount} main characters and switched to Multi-Character Single Card. Side characters remain in concept/lore context, not builder slots.` : '';
    setStatus(`Transferred concept to builders: filled ${applied.count} field(s). Builder guidance now takes priority over Main Concept / Character Description during generation.${multiMsg}${res.notes ? ' ' + res.notes : ''}`, 'ok');
    switchSubTab('concept', 'concept-builder');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
  }
}

async function aiRandomizeBuilderPreset({ build = false } = {}) {
  if (isBusy) return;
  settings = collectSettings();
  const missing = validateTextApiSettings({ ...settings, model: settings.aiSuggestionModel || settings.model });
  if (missing) {
    setStatus(missing.replace('Text Model', 'AI Suggestion Model or Text Model'), 'error');
    switchToSettingsTab();
    return;
  }
  const { preset } = getSelectedAiRandomTheme();
  if (!preset) return;
  if (($('#aiRandomThemeSelect')?.value || '') === 'custom' && !($('#aiRandomCustomTheme')?.value || '').trim()) {
    setStatus('Enter a custom AI random theme first, or choose a built-in theme.', 'error');
    return;
  }
  const mode = $('#builderPresetMode')?.value || 'merge';
  if (mode === 'replace') {
    clearCharacterBuilder();
    clearPersonalityBuilder();
    clearSceneBuilder();
  }
  setBusy(`AI RANDOM THEME — creating ${preset.name} builder choices…`);
  try {
    const groupedCatalog = collectGroupedCompactBuilderCatalog();
    const builderState = collectBuilderStateForSuggestion();
    const combined = { fields: {}, notes: [] };
    const groupOrder = [
      ['character', 'Character Builder'],
      ['personality', 'Personality Builder'],
      ['scene', 'Scene Builder']
    ];
    for (const [groupKey, groupLabel] of groupOrder) {
      const catalog = groupedCatalog[groupKey] || [];
      if (!catalog.length) continue;
      setBusy(`AI RANDOM THEME — ${groupLabel} choices for ${preset.name}…`);
      const groupPreset = { ...preset, groupFocus: groupKey, groupLabel };
      const res = await window.pywebview.api.ai_builder_randomize_preset(groupPreset, catalog, builderState, settings);
      if (!res.ok) throw new Error(res.error || `AI preset randomization failed during ${groupLabel}.`);
      Object.assign(combined.fields, res.fields || {});
      if (res.notes) combined.notes.push(`${groupLabel}: ${res.notes}`);
      if (res.cardMode && !combined.cardMode) combined.cardMode = res.cardMode;
      if (res.multiCharacterCount && !combined.multiCharacterCount) combined.multiCharacterCount = res.multiCharacterCount;
    }
    Object.entries(combined.fields || {}).forEach(([id, value]) => setBuilderFieldValue(id, value));
    if (combined.cardMode && $('#cardMode')) {
      $('#cardMode').value = combined.cardMode;
      if ($('#multiCharacterCount') && combined.multiCharacterCount) $('#multiCharacterCount').value = combined.multiCharacterCount;
      updateCardModeHint();
    } else if (preset.cardMode && $('#cardMode')) {
      $('#cardMode').value = preset.cardMode;
      if ($('#multiCharacterCount') && preset.multiCharacterCount) $('#multiCharacterCount').value = preset.multiCharacterCount;
      updateCardModeHint();
    }
    const res = { notes: combined.notes.join(' ') };
    updateBuilderConditionalOptions();
    updateCustomConditionalOptions();
    if (build) {
      generateBuilderDescription();
      generatePersonalityBuilderDescription();
      generateSceneBuilderDescription();
      captureCurrentMultiBuilderState();
      setStatus(`AI randomized ${preset.name} theme for ${isMultiBuilderMode() ? getMultiBuilderCharacterName(multiBuilderSelectedIndex) : 'the current builder'} and built the builder text.${res.notes ? ' ' + res.notes : ''}`, 'ok');
    } else {
      captureCurrentMultiBuilderState();
      setStatus(`AI randomized ${preset.name} theme for ${isMultiBuilderMode() ? getMultiBuilderCharacterName(multiBuilderSelectedIndex) : 'the current builder'}. Fine-tune the builders, then click Build.${res.notes ? ' ' + res.notes : ''}`, 'ok');
    }
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

const AI_SUGGEST_CUSTOM_MAP = {
  pbOccupation: 'pbOccupationCustom',
  pbCurrentRelationshipStatus: 'pbCurrentRelationshipStatusCustom',
  pbPublicRelationshipImage: 'pbPublicRelationshipImageCustom',
  pbRelationshipPressure: 'pbRelationshipPressureCustom',
  pbKinkFocus: 'pbKinkCustom',
  pbUserRelationshipRole: 'pbUserRelationshipRoleCustom',
  pbUserRelationshipHistory: 'pbUserRelationshipHistoryCustom',
  pbUserCurrentDynamic: 'pbUserCurrentDynamicCustom',
  pbUserFeelings: 'pbUserFeelingsCustom',
  pbUserSecretTension: 'pbUserSecretTensionCustom',
  pbUserDesiredDirection: 'pbUserDesiredDirectionCustom',
  sbSetting: 'sbSettingCustom',
  sbTime: 'sbTimeCustom',
  sbSituation: 'sbSituationCustom',
  sbTone: 'sbToneCustom',
  sbGoal: 'sbGoalCustom',
};

function cleanLabelText(label) {
  if (!label) return '';
  const clone = label.cloneNode(true);
  clone.querySelectorAll('button, input, select, textarea').forEach(n => n.remove());
  return clone.textContent.trim().replace(/\s+/g, ' ');
}

function collectBuilderStateForSuggestion() {
  const state = {};
  $$('.builder-card select, .builder-card input, .builder-card textarea').forEach(el => {
    if (!el.id || el.type === 'button' || el.type === 'hidden') return;
    const value = String(el.value || '').trim();
    if (!value) return;
    const label = el.closest('label');
    state[el.id] = { label: cleanLabelText(label) || el.id, value };
  });
  return state;
}

function getFieldOptions(el) {
  if (!el || el.tagName !== 'SELECT') return [];
  return [...el.options].map(o => o.value || o.textContent).map(v => String(v || '').trim()).filter(v => v && v.toLowerCase() !== 'unspecified');
}

function enhanceBuilderAiButtons() {
  $$('.builder-card label').forEach(label => {
    if (label.dataset.aiEnhanced === '1') return;
    const target = label.querySelector('select, input:not([type="button"]):not([type="hidden"]), textarea');
    if (!target || !target.id) return;
    label.dataset.aiEnhanced = '1';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ai-suggest-btn';
    btn.title = 'Ask AI for a suggestion using only current Builder fields';
    btn.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7.5 14.5 3 19l2 2 4.5-4.5-2-2Zm1.42-1.42 8.49-8.49a2 2 0 0 1 2.83 2.83l-8.49 8.49-2.83-2.83Zm8.49-5.66-5.66 5.66.83.83 5.66-5.66-.83-.83ZM5 3l.78 1.72L7.5 5.5l-1.72.78L5 8l-.78-1.72L2.5 5.5l1.72-.78L5 3Zm8-1 1.1 2.4L16.5 5.5l-2.4 1.1L13 9l-1.1-2.4-2.4-1.1 2.4-1.1L13 2Zm6 10 .78 1.72 1.72.78-1.72.78L19 17l-.78-1.72-1.72-.78 1.72-.78L19 12Z"/></svg>`;
    btn.setAttribute('aria-label', 'AI suggestion');
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      suggestBuilderField(target.id);
    });
    label.appendChild(btn);
  });
}

function applySuggestionToField(fieldId, value, custom) {
  const el = $('#' + fieldId);
  if (!el) return false;
  const text = String(value || '').trim();
  if (!text) return false;
  if (el.tagName === 'SELECT') {
    const options = [...el.options];
    const exact = options.find(o => (o.value || o.textContent).trim().toLowerCase() === text.toLowerCase());
    if (exact && !custom) {
      el.value = exact.value || exact.textContent;
    } else if (AI_SUGGEST_CUSTOM_MAP[fieldId] && options.some(o => (o.value || o.textContent).trim().toLowerCase() === 'custom')) {
      el.value = 'custom';
      updateCustomConditionalOptions();
      const customEl = $('#' + AI_SUGGEST_CUSTOM_MAP[fieldId]);
      if (customEl) customEl.value = text;
    } else {
      const fuzzy = options.find(o => text.toLowerCase().includes((o.value || o.textContent).trim().toLowerCase()) && (o.value || o.textContent).trim());
      if (fuzzy) el.value = fuzzy.value || fuzzy.textContent;
      else return false;
    }
  } else {
    el.value = text;
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  updateBuilderConditionalOptions();
  updateCustomConditionalOptions();
  return true;
}

async function suggestBuilderField(fieldId) {
  if (isBusy) return;
  settings = collectSettings();
  const missing = validateTextApiSettings({ ...settings, model: settings.aiSuggestionModel || settings.model });
  if (missing) {
    setStatus(missing.replace('Text Model', 'AI Suggestion Model or Text Model'), 'error');
    switchToSettingsTab();
    return;
  }
  const el = $('#' + fieldId);
  if (!el) return;
  const label = el.closest('label');
  const meta = {
    id: fieldId,
    label: cleanLabelText(label) || fieldId,
    kind: el.tagName === 'SELECT' ? 'select' : (el.tagName === 'TEXTAREA' ? 'textarea' : 'text'),
    currentValue: String(el.value || '').trim(),
    options: getFieldOptions(el),
  };
  const builderState = collectBuilderStateForSuggestion();
  setBusy(`AI SUGGESTION — choosing ${meta.label}…`);
  try {
    const res = await window.pywebview.api.ai_builder_suggest(meta, builderState, settings);
    if (!res.ok) throw new Error(res.error || 'AI suggestion failed.');
    const applied = applySuggestionToField(fieldId, res.value, res.custom);
    if (!applied) throw new Error(`AI suggested “${res.value}”, but it could not be applied to this field.`);
    setStatus(`AI suggested ${meta.label}: ${res.value}${res.reason ? ' — ' + res.reason : ''}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}


async function newCard() {
  if (isBusy) return;
  const hasWork = $('#conceptText').value.trim() || $('#outputText').value.trim() || $('#followupText').value.trim() || $('#visionDescription').value.trim() || $('#visionImagePath').value.trim() || $('#cardImagePath').value.trim();
  if (hasWork && !confirm('Clear the current character draft and start a new card?')) return;
  $('#conceptText').value = '';
  $('#outputText').value = '';
  $('#followupText').value = '';
  $('#visionDescription').value = '';
  if ($('#builderDescription')) clearCharacterBuilder();
  if ($('#personalityBuilderDescription')) clearPersonalityBuilder();
  if ($('#sceneBuilderDescription')) clearSceneBuilder();
  setVisionImagePath('');
  $('#cardImagePath').value = '';
  $('#generatedImages').innerHTML = '';
  emotionImageState = [];
  $('#emotionImages').innerHTML = '';
  conceptAttachments = [];
  renderConceptAttachments();
  $('#debugLogText').value = '';
  lastQnaAnswers = '';
  const qaBox = $('#qaAnswersText');
  if (qaBox) qaBox.value = '';
  $('#cardMode').value = 'single';
  $('#multiCharacterCount').value = 2;
  if ($('#sharedScenePolicy')) $('#sharedScenePolicy').value = 'ai_reconcile';
  multiBuilderSelectedIndex = 0;
  multiBuilderStates = [];
  settings = collectSettings();
  settings.cardMode = 'single';
  settings.multiCharacterCount = 2;
  settings.visionImagePath = '';
  settings.cardImagePath = '';
  await window.pywebview.api.save_settings(settings);
  updateCardModeHint();
  updateAvailability();
  setStatus('New card started. Card Mode reset to Single Character.', 'ok');
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="concept"]').classList.add('active');
  $('#concept').classList.add('active');
  switchSubTab('concept', 'concept-main');
}

async function loadSelectedTemplate() {
  if (isBusy) return;
  const name = $('#templateSelect').value || 'Default';
  if (!confirm(`Load prompt template "${name}"? Unsaved edits to the current template will be replaced.`)) return;
  setBusy('LOADING PROMPT TEMPLATE…');
  try {
    const res = await window.pywebview.api.load_prompt_template(name);
    if (!res.ok) throw new Error(res.error || 'Could not load template.');
    template = res.template;
    promptTemplates = res.templates || promptTemplates;
    activeTemplateName = res.activeTemplateName || name;
    settings.activeTemplateName = activeTemplateName;
    renderTemplateSelector();
    renderTemplate();
    setStatus(`Loaded prompt template: ${activeTemplateName}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function saveTemplateAs() {
  if (isBusy) return;
  const name = ($('#templateNameInput').value || '').trim();
  if (!name) { setStatus('Enter a template name first.', 'error'); return; }
  setBusy('SAVING PROMPT TEMPLATE…');
  try {
    const res = await window.pywebview.api.save_template_as(name, template);
    if (!res.ok) throw new Error(res.error || 'Could not save template.');
    promptTemplates = res.templates || promptTemplates;
    activeTemplateName = res.activeTemplateName || name;
    settings.activeTemplateName = activeTemplateName;
    renderTemplateSelector();
    setStatus(`Saved prompt template: ${activeTemplateName}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function deleteSelectedTemplate() {
  if (isBusy) return;
  const name = $('#templateSelect').value || 'Default';
  if (name === 'Default') { setStatus('Default template cannot be deleted.', 'error'); return; }
  if (!confirm(`Delete prompt template "${name}"?`)) return;
  setBusy('DELETING PROMPT TEMPLATE…');
  try {
    const res = await window.pywebview.api.delete_prompt_template(name);
    if (!res.ok) throw new Error(res.error || 'Could not delete template.');
    template = res.template;
    promptTemplates = res.templates || ['Default'];
    activeTemplateName = res.activeTemplateName || 'Default';
    settings.activeTemplateName = activeTemplateName;
    renderTemplateSelector();
    renderTemplate();
    setStatus(`Deleted prompt template: ${name}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function stopCurrentTask() {
  const btn = $('#stopTaskBtn');
  if (btn) btn.disabled = true;
  setStatus('Stop requested. Waiting for the current network call to return…', 'error');
  try {
    const res = await window.pywebview.api.cancel_current_task();
    if (!res.ok) throw new Error(res.error || 'Could not request cancellation.');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  }
}

async function selectVisionImage() {
  if (isBusy) return;
  setBusy('SELECTING VISION IMAGE…');
  try {
    const res = await window.pywebview.api.pick_image_file('vision');
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Vision image selection failed.');
      return;
    }
    setVisionImagePath(res.path);
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    setStatus('Selected vision image: ' + res.path, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    setVisionImagePath(getVisionImagePath());
    updateAvailability();
  }
}

async function importVisionFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  setBusy('IMPORTING VISION IMAGE…');
  try {
    const dataUrl = await fileToDataUrl(file);
    const res = await window.pywebview.api.save_uploaded_image(file.name, dataUrl, 'vision');
    if (!res.ok) throw new Error(res.error || 'Vision image import failed.');
    setVisionImagePath(res.path);
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    updateAvailability();
    setStatus('Selected vision image: ' + res.path, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    setVisionImagePath(getVisionImagePath());
    updateAvailability();
  }
}

async function handleVisionFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importVisionFiles([file]);
}

async function analyzeVisionImage() {
  const visionPath = getVisionImagePath();
  if (!visionPath) {
    setStatus('Select a vision image before analyzing.', 'error');
    updateAvailability();
    return;
  }
  setVisionImagePath(visionPath);
  settings = collectSettings();
  settings.visionImagePath = visionPath;
  const settingsError = validateVisionApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  await window.pywebview.api.save_settings(settings);
  setBusy('ANALYZING IMAGE WITH VISION MODEL — creating physical character description…');
  try {
    const res = await window.pywebview.api.analyze_vision_image(visionPath, settings);
    if (!res.ok) throw new Error(res.error || 'Vision analysis failed.');
    if (!(res.description || '').trim()) throw new Error('Vision model returned an empty description. Try a different vision model or enter the description manually.');
    $('#visionDescription').value = res.description || '';
    if (res.imagePath) setVisionImagePath(res.imagePath);
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    setStatus(res.retryUsed ? 'Vision model refused once, then succeeded with a SFW retry. Description ready.' : 'Vision description ready. It will be included when generating/revising the card.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function clearVisionDescription() {
  setVisionImagePath('');
  $('#visionDescription').value = '';
  settings = collectSettings();
  window.pywebview.api.save_settings(settings);
  updateAvailability();
  setStatus('Vision reference cleared.', 'ok');
}

async function viewDebugLog() {
  setBusy('Loading debug log…');
  try {
    const res = await window.pywebview.api.get_debug_log();
    if (!res.ok) throw new Error(res.error || 'Could not read debug log.');
    $('#debugLogText').value = res.text || '';
    setStatus('Debug log loaded: ' + (res.path || ''), 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function clearDebugLog() {
  setBusy('Clearing debug log…');
  try {
    const res = await window.pywebview.api.clear_debug_log();
    if (!res.ok) throw new Error(res.error || 'Could not clear debug log.');
    $('#debugLogText').value = '';
    setStatus('Debug log cleared.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function copyOutput() {
  if (!hasOutput()) return;
  setBusy('Copying output to clipboard…');
  try {
    const res = await window.pywebview.api.copy_to_clipboard($('#outputText').value);
    if (!res.ok) throw new Error(res.error || 'Copy failed.');
    setStatus('Copied output to clipboard.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function renderConceptAttachments() {
  const holder = $('#conceptAttachmentsList');
  if (!holder) return;
  holder.innerHTML = '';
  holder.classList.toggle('empty', conceptAttachments.length === 0);
  if (!conceptAttachments.length) {
    holder.textContent = 'No concept attachments yet.';
    return;
  }
  conceptAttachments.forEach((att, index) => {
    const row = document.createElement('div');
    row.className = 'attachment-row';
    const meta = document.createElement('div');
    meta.className = 'attachment-meta';
    const title = document.createElement('strong');
    title.textContent = att.filename || 'attachment';
    const sub = document.createElement('small');
    sub.textContent = `${att.chars || 0} chars extracted${att.truncated ? ' — truncated' : ''}`;
    meta.appendChild(title);
    meta.appendChild(sub);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'danger-ghost';
    btn.textContent = 'Remove';
    btn.addEventListener('click', () => {
      conceptAttachments.splice(index, 1);
      renderConceptAttachments();
      updateAvailability();
    });
    row.appendChild(meta);
    row.appendChild(btn);
    holder.appendChild(row);
  });
}

async function attachConceptFiles() {
  if (isBusy) return;
  setBusy('ATTACHING CONCEPT FILE(S)…');
  try {
    const res = await window.pywebview.api.pick_concept_attachments();
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Attachment import failed.');
      return;
    }
    conceptAttachments.push(...(res.attachments || []));
    renderConceptAttachments();
    updateAvailability();
    setStatus(`Attached ${res.attachments?.length || 0} concept file(s). Their extracted text will be sent with the concept.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function importConceptAttachmentFiles(files) {
  files = [...(files || [])];
  if (!files.length) return;
  setBusy('IMPORTING CONCEPT ATTACHMENT(S)…');
  try {
    for (const file of files) {
      const dataUrl = await fileToDataUrl(file);
      const res = await window.pywebview.api.save_concept_attachment(file.name, dataUrl);
      if (!res.ok) throw new Error(res.error || `Could not import ${file.name}`);
      conceptAttachments.push(res);
    }
    renderConceptAttachments();
    updateAvailability();
    setStatus(`Attached ${files.length} concept file(s). Their extracted text will be sent with the concept.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function handleConceptAttachmentFiles(event) {
  const files = [...(event.target.files || [])];
  event.target.value = '';
  if (!files.length) return;
  await importConceptAttachmentFiles(files);
}

function clearConceptAttachments() {
  if (!conceptAttachments.length) return;
  if (!confirm('Clear all concept attachments from this draft?')) return;
  conceptAttachments = [];
  renderConceptAttachments();
  updateAvailability();
  setStatus('Concept attachments cleared.', 'ok');
}

function buildAttachmentTextForModel() {
  if (!conceptAttachments.length) return '';
  const blocks = conceptAttachments.map((att, i) => [
    `ATTACHMENT ${i + 1}: ${att.filename}`,
    `Source path: ${att.path || ''}`,
    'Extracted text:',
    att.text || ''
  ].join('\n'));
  return [
    'CONCEPT ATTACHMENTS — use these as source material for adaptation. They may include scripts, subtitles, transcripts, or notes. Preserve useful character/scenario details, but do not copy unnecessary formatting noise directly into the card.',
    blocks.join('\n\n---\n\n')
  ].join('\n');
}

function builderValue(id) {
  const el = $('#' + id);
  return el ? String(el.value || '').trim() : '';
}

function updateBuilderConditionalOptions() {
  const hairColor = builderValue('builderHairColor').toLowerCase();
  const accentWrap = $('#builderAccentColorWrap');
  if (accentWrap) accentWrap.classList.toggle('hidden', !(hairColor.includes('two-tone') || hairColor.includes('blonde') || hairColor.includes('black') || hairColor.includes('brown')));
  const clothing = builderValue('builderClothingStyle');
  const clothingWrap = $('#builderClothingDetailWrap');
  if (clothingWrap) clothingWrap.classList.toggle('hidden', !clothing);
  const underwear = builderValue('builderUnderwearStyle');
  const underwearWrap = $('#builderUnderwearDetailWrap');
  if (underwearWrap) underwearWrap.classList.toggle('hidden', !underwear || underwear === 'no visible underwear details');
}

function selectedOrCustom(selectId, customId) {
  const val = builderValue(selectId);
  if (val === 'custom') return builderValue(customId);
  return val;
}

function updateCustomConditionalOptions() {
  const pairs = [
    ['pbOccupation','pbOccupationCustomWrap'], ['pbKinkFocus','pbKinkCustomWrap'],
    ['pbCurrentRelationshipStatus','pbCurrentRelationshipStatusCustomWrap'], ['pbPublicRelationshipImage','pbPublicRelationshipImageCustomWrap'], ['pbRelationshipPressure','pbRelationshipPressureCustomWrap'],
    ['pbUserRelationshipRole','pbUserRelationshipRoleCustomWrap'], ['pbUserRelationshipHistory','pbUserRelationshipHistoryCustomWrap'],
    ['pbUserCurrentDynamic','pbUserCurrentDynamicCustomWrap'], ['pbUserFeelings','pbUserFeelingsCustomWrap'],
    ['pbUserSecretTension','pbUserSecretTensionCustomWrap'], ['pbUserDesiredDirection','pbUserDesiredDirectionCustomWrap'],
    ['pbSexualPartners','pbSexualPartnersCustomWrap'], ['pbVirginityHistory','pbVirginityHistoryCustomWrap'], ['pbFirstCreampie','pbFirstCreampieCustomWrap'],
    ['sbSetting','sbSettingCustomWrap'], ['sbTime','sbTimeCustomWrap'], ['sbSituation','sbSituationCustomWrap'],
    ['sbTone','sbToneCustomWrap'], ['sbGoal','sbGoalCustomWrap']
  ];
  pairs.forEach(([selectId, wrapId]) => {
    const wrap = $('#' + wrapId);
    const val = builderValue(selectId);
    if (wrap) wrap.classList.toggle('hidden', val !== 'custom');
  });
}

function hasFilledInputs(ids) {
  return ids.some(id => builderValue(id));
}

function hasUnbuiltCharacterBuilder() {
  const output = ($('#builderDescription')?.value || '').trim();
  const ids = ['builderPresentation','builderBuild','builderSkin','builderHairLength','builderHairTexture','builderHairColor','builderAccentColor','builderFaceShape','builderEyeShape','builderEyeColor','builderMakeup','builderBust','builderWaistHips','builderLegs','builderClothingStyle','builderClothingExposure','builderClothingDetail','builderClothingColors','builderUnderwearStyle','builderUnderwearCoverage','builderUnderwearColor','builderUnderwearDetail','builderFootwear','builderAccessories','builderFeatures','builderVibe'];
  return !output && hasFilledInputs(ids);
}

function hasUnbuiltPersonalityBuilder() {
  const output = ($('#personalityBuilderDescription')?.value || '').trim();
  const ids = ['pbArchetype','pbSocial','pbConfidence','pbEmotion','pbDrive','pbFear','pbMoral','pbDecision','pbOccupation','pbOccupationCustom','pbLikes','pbDislikes','pbHobbies','pbUserBehavior','pbAttachment','pbConflict','pbSecrecy','pbCurrentRelationshipStatus','pbCurrentRelationshipStatusCustom','pbCurrentPartner','pbPublicRelationshipImage','pbPublicRelationshipImageCustom','pbRelationshipPressure','pbRelationshipPressureCustom','pbUserRelationshipRole','pbUserRelationshipRoleCustom','pbUserRelationshipHistory','pbUserRelationshipHistoryCustom','pbUserCurrentDynamic','pbUserCurrentDynamicCustom','pbUserFeelings','pbUserFeelingsCustom','pbUserSecretTension','pbUserSecretTensionCustom','pbUserDesiredDirection','pbUserDesiredDirectionCustom','pbSexualNature','pbLibido','pbPromiscuity','pbDynamic','pbRisk','pbKinkFocus','pbKinkCustom','pbTurnOns','pbTurnOffs','pbNsfwBoundaries','pbSpeech','pbQuirks','pbExtraNotes'];
  return !output && hasFilledInputs(ids);
}

function hasUnbuiltSceneBuilder() {
  const output = ($('#sceneBuilderDescription')?.value || '').trim();
  const ids = ['sbSetting','sbSettingCustom','sbLocation','sbTime','sbTimeCustom','sbSituation','sbSituationCustom','sbJustHappened','sbAboutToHappen','sbTone','sbToneCustom','sbGoal','sbGoalCustom','sbRisk','sbProps','sbExtraNotes'];
  return !output && hasFilledInputs(ids);
}

function handleUnbuiltBuilderWarning() {
  const pending = [];
  if (hasUnbuiltCharacterBuilder()) pending.push('Character Builder');
  if (hasUnbuiltPersonalityBuilder()) pending.push('Personality Builder');
  if (hasUnbuiltSceneBuilder()) pending.push('Scene Builder');
  if (!pending.length) return true;
  const choice = prompt(`${pending.join(', ')} has filled-in options but you have not clicked Build yet. These options will NOT be included unless built.

Type BUILD to build them now, CONTINUE to generate anyway, or CANCEL to go back to editing.`, 'BUILD');
  if (!choice) return false;
  const normalized = choice.trim().toUpperCase();
  if (normalized === 'CONTINUE') return true;
  if (normalized === 'BUILD') {
    if (pending.includes('Character Builder')) generateBuilderDescription();
    if (pending.includes('Personality Builder')) generatePersonalityBuilderDescription();
    if (pending.includes('Scene Builder')) generateSceneBuilderDescription();
    setStatus('Builder guidance has been built. Review it, then click Generate Card again when ready.', 'ok');
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    $('[data-tab="concept"]').classList.add('active');
    $('#concept').classList.add('active');
    if (pending.includes('Scene Builder')) switchSubTab('concept', 'concept-scene-builder');
    else if (pending.includes('Personality Builder')) switchSubTab('concept', 'concept-personality-builder');
    else switchSubTab('concept', 'concept-builder');
    return false;
  }
  return false;
}

function buildCharacterBuilderDescription() {
  const lines = [];
  const overall = [];
  if (builderValue('builderPresentation')) overall.push(`${builderValue('builderPresentation')} presentation`);
  if (builderValue('builderBuild')) overall.push(`${builderValue('builderBuild')} build`);
  if (builderValue('builderSkin')) overall.push(`${builderValue('builderSkin')} skin tone`);
  if (overall.length) lines.push(`- Overall: ${overall.join(', ')}.`);

  const hair = [];
  if (builderValue('builderHairLength')) hair.push(builderValue('builderHairLength'));
  if (builderValue('builderHairTexture')) hair.push(builderValue('builderHairTexture'));
  if (builderValue('builderHairColor')) hair.push(builderValue('builderHairColor'));
  if (builderValue('builderAccentColor')) hair.push(`with ${builderValue('builderAccentColor')}`);
  if (hair.length) lines.push(`- Hair: ${hair.join(', ')}.`);

  const face = [];
  if (builderValue('builderFaceShape')) face.push(`${builderValue('builderFaceShape')} face`);
  if (builderValue('builderEyeShape')) face.push(`${builderValue('builderEyeShape')} eyes`);
  if (builderValue('builderEyeColor')) face.push(`${builderValue('builderEyeColor')} eye color`);
  if (builderValue('builderMakeup')) face.push(builderValue('builderMakeup'));
  if (face.length) lines.push(`- Face: ${face.join(', ')}.`);

  const body = [];
  if (builderValue('builderBust')) body.push(builderValue('builderBust'));
  if (builderValue('builderWaistHips')) body.push(builderValue('builderWaistHips'));
  if (builderValue('builderLegs')) body.push(builderValue('builderLegs'));
  if (body.length) lines.push(`- Body: ${body.join(', ')}.`);

  const outfit = [];
  if (builderValue('builderClothingStyle')) outfit.push(builderValue('builderClothingStyle'));
  if (builderValue('builderClothingExposure')) outfit.push(`revealing level: ${builderValue('builderClothingExposure')}`);
  if (builderValue('builderClothingDetail')) outfit.push(builderValue('builderClothingDetail'));
  if (builderValue('builderClothingColors')) outfit.push(`main colors: ${builderValue('builderClothingColors')}`);
  if (builderValue('builderUnderwearStyle')) outfit.push(`underwear: ${builderValue('builderUnderwearStyle')}`);
  if (builderValue('builderUnderwearCoverage')) outfit.push(`underwear coverage: ${builderValue('builderUnderwearCoverage')}`);
  if (builderValue('builderUnderwearColor')) outfit.push(`underwear color/style: ${builderValue('builderUnderwearColor')}`);
  if (builderValue('builderUnderwearDetail')) outfit.push(`underwear details: ${builderValue('builderUnderwearDetail')}`);
  if (builderValue('builderFootwear')) outfit.push(`footwear: ${builderValue('builderFootwear')}`);
  if (outfit.length) lines.push(`- Clothing Style: ${outfit.join(', ')}.`);

  const extras = [];
  if (builderValue('builderAccessories')) extras.push(`accessories: ${builderValue('builderAccessories')}`);
  if (builderValue('builderFeatures')) extras.push(`distinguishing features: ${builderValue('builderFeatures')}`);
  if (builderValue('builderVibe')) extras.push(`visual vibe: ${builderValue('builderVibe')}`);
  if (extras.length) lines.push(`- External Traits: ${extras.join(', ')}.`);

  return lines.join('\n');
}

function generateBuilderDescription() {
  const desc = buildCharacterBuilderDescription();
  if (!desc) {
    setStatus('Choose at least one builder option first.', 'error');
    return;
  }
  $('#builderDescription').value = desc;
  setStatus('Character Builder description created. Edit it or append it to the concept when ready.', 'ok');
}

function appendBuilderToConcept() {
  const desc = ($('#builderDescription')?.value || '').trim() || buildCharacterBuilderDescription();
  if (!desc) {
    setStatus('Build a description first.', 'error');
    return;
  }
  const box = $('#conceptText');
  const block = `CHARACTER BUILDER VISUAL DESCRIPTION:\n${desc}`;
  box.value = (box.value || '').trim() ? `${box.value.trim()}\n\n${block}` : block;
  setStatus('Builder description appended to Main Concept.', 'ok');
}

function clearCharacterBuilder() {
  ['builderPresentation','builderBuild','builderSkin','builderHairLength','builderHairTexture','builderHairColor','builderFaceShape','builderEyeShape','builderEyeColor','builderMakeup','builderBust','builderWaistHips','builderLegs','builderClothingStyle','builderClothingExposure','builderUnderwearStyle','builderUnderwearCoverage','builderFootwear','builderVibe'].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  ['builderAccentColor','builderClothingDetail','builderClothingColors','builderUnderwearColor','builderUnderwearDetail','builderAccessories','builderFeatures','builderDescription'].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  updateBuilderConditionalOptions();
  captureCurrentMultiBuilderState();
  setStatus(`Character Builder cleared${isMultiBuilderMode() ? ' for ' + getMultiBuilderCharacterName(multiBuilderSelectedIndex) : ''}.`, 'ok');
}

function personalityBuilderValue(id) {
  const el = $('#' + id);
  return el ? String(el.value || '').trim() : '';
}

function buildPersonalityBuilderDescription() {
  const lines = [];
  const core = [];
  if (personalityBuilderValue('pbArchetype')) core.push(`archetype: ${personalityBuilderValue('pbArchetype')}`);
  if (personalityBuilderValue('pbSocial')) core.push(`social energy: ${personalityBuilderValue('pbSocial')}`);
  if (personalityBuilderValue('pbConfidence')) core.push(`confidence: ${personalityBuilderValue('pbConfidence')}`);
  if (personalityBuilderValue('pbEmotion')) core.push(`emotional style: ${personalityBuilderValue('pbEmotion')}`);
  if (core.length) lines.push(`- Core Personality: ${core.join(', ')}.`);

  const mind = [];
  if (personalityBuilderValue('pbDrive')) mind.push(`main drive: ${personalityBuilderValue('pbDrive')}`);
  if (personalityBuilderValue('pbFear')) mind.push(`hidden fear: ${personalityBuilderValue('pbFear')}`);
  if (personalityBuilderValue('pbMoral')) mind.push(`moral alignment: ${personalityBuilderValue('pbMoral')}`);
  if (personalityBuilderValue('pbDecision')) mind.push(`decision style: ${personalityBuilderValue('pbDecision')}`);
  if (mind.length) lines.push(`- Mind and Motivation: ${mind.join(', ')}.`);

  const daily = [];
  const occupation = selectedOrCustom('pbOccupation', 'pbOccupationCustom');
  if (occupation) daily.push(`occupation: ${occupation}`);
  if (personalityBuilderValue('pbLikes')) daily.push(`likes: ${personalityBuilderValue('pbLikes')}`);
  if (personalityBuilderValue('pbDislikes')) daily.push(`dislikes: ${personalityBuilderValue('pbDislikes')}`);
  if (personalityBuilderValue('pbHobbies')) daily.push(`hobbies: ${personalityBuilderValue('pbHobbies')}`);
  if (daily.length) lines.push(`- Daily Life Traits: ${daily.join(', ')}.`);

  const relation = [];
  if (personalityBuilderValue('pbUserBehavior')) relation.push(`toward {{user}}: ${personalityBuilderValue('pbUserBehavior')}`);
  if (personalityBuilderValue('pbAttachment')) relation.push(`attachment style: ${personalityBuilderValue('pbAttachment')}`);
  if (personalityBuilderValue('pbConflict')) relation.push(`conflict style: ${personalityBuilderValue('pbConflict')}`);
  if (personalityBuilderValue('pbSecrecy')) relation.push(`secrecy: ${personalityBuilderValue('pbSecrecy')}`);
  if (relation.length) lines.push(`- Relationship Behavior: ${relation.join(', ')}.`);

  const currentRel = [];
  const currentStatus = selectedOrCustom('pbCurrentRelationshipStatus', 'pbCurrentRelationshipStatusCustom');
  const publicImage = selectedOrCustom('pbPublicRelationshipImage', 'pbPublicRelationshipImageCustom');
  const pressure = selectedOrCustom('pbRelationshipPressure', 'pbRelationshipPressureCustom');
  if (currentStatus) currentRel.push(`status/role: ${currentStatus}`);
  if (personalityBuilderValue('pbCurrentPartner')) currentRel.push(`current partner/important person: ${personalityBuilderValue('pbCurrentPartner')}`);
  if (publicImage) currentRel.push(`public image: ${publicImage}`);
  if (pressure) currentRel.push(`relationship pressure: ${pressure}`);
  if (currentRel.length) lines.push(`- Current Relationship / Social Role: ${currentRel.join(', ')}.`);

  const userRelation = [];
  const userRole = selectedOrCustom('pbUserRelationshipRole', 'pbUserRelationshipRoleCustom');
  const userHistory = selectedOrCustom('pbUserRelationshipHistory', 'pbUserRelationshipHistoryCustom');
  const userDynamic = selectedOrCustom('pbUserCurrentDynamic', 'pbUserCurrentDynamicCustom');
  const userFeelings = selectedOrCustom('pbUserFeelings', 'pbUserFeelingsCustom');
  const userSecret = selectedOrCustom('pbUserSecretTension', 'pbUserSecretTensionCustom');
  const userDirection = selectedOrCustom('pbUserDesiredDirection', 'pbUserDesiredDirectionCustom');
  if (userRole) userRelation.push(`relationship role: ${userRole}`);
  if (userHistory) userRelation.push(`shared history: ${userHistory}`);
  if (userDynamic) userRelation.push(`current dynamic: ${userDynamic}`);
  if (userFeelings) userRelation.push(`feelings toward {{user}}: ${userFeelings}`);
  if (userSecret) userRelation.push(`secret/tension: ${userSecret}`);
  if (userDirection) userRelation.push(`desired roleplay direction: ${userDirection}`);
  if (userRelation.length) lines.push(`- Relationship with {{user}}: ${userRelation.join(', ')}.`);

  const nsfw = [];
  if (personalityBuilderValue('pbSexualNature')) nsfw.push(`sexual nature: ${personalityBuilderValue('pbSexualNature')}`);
  if (personalityBuilderValue('pbLibido')) nsfw.push(`libido/drive: ${personalityBuilderValue('pbLibido')}`);
  if (personalityBuilderValue('pbPromiscuity')) nsfw.push(`promiscuity/exclusivity: ${personalityBuilderValue('pbPromiscuity')}`);
  if (personalityBuilderValue('pbDynamic')) nsfw.push(`dominance dynamic: ${personalityBuilderValue('pbDynamic')}`);
  if (personalityBuilderValue('pbRisk')) nsfw.push(`risk/exhibitionism: ${personalityBuilderValue('pbRisk')}`);
  const kink = selectedOrCustom('pbKinkFocus', 'pbKinkCustom');
  if (kink) nsfw.push(`kinks: ${kink}`);
  if (personalityBuilderValue('pbTurnOns')) nsfw.push(`turn-ons: ${personalityBuilderValue('pbTurnOns')}`);
  if (personalityBuilderValue('pbTurnOffs')) nsfw.push(`turn-offs: ${personalityBuilderValue('pbTurnOffs')}`);
  if (personalityBuilderValue('pbNsfwBoundaries')) nsfw.push(`boundaries: ${personalityBuilderValue('pbNsfwBoundaries')}`);
  if (nsfw.length) lines.push(`- Adult/NSFW Traits: ${nsfw.join(', ')}.`);

  const history = [];
  const sexualPartners = selectedOrCustom('pbSexualPartners', 'pbSexualPartnersCustom');
  const virginityHistory = selectedOrCustom('pbVirginityHistory', 'pbVirginityHistoryCustom');
  const firstCreampie = selectedOrCustom('pbFirstCreampie', 'pbFirstCreampieCustom');
  if (sexualPartners) history.push(`sexual partners: ${sexualPartners}`);
  if (virginityHistory) history.push(`how they lost virginity: ${virginityHistory}`);
  if (firstCreampie) history.push(`first creampie/unprotected experience: ${firstCreampie}`);
  if (personalityBuilderValue('pbBestSexualMemory')) history.push(`best sexual memory: ${personalityBuilderValue('pbBestSexualMemory')}`);
  if (personalityBuilderValue('pbWorstSexualMemory')) history.push(`worst/most awkward sexual memory: ${personalityBuilderValue('pbWorstSexualMemory')}`);
  if (personalityBuilderValue('pbCurrentSexualSituation')) history.push(`current sexual situation: ${personalityBuilderValue('pbCurrentSexualSituation')}`);
  if (personalityBuilderValue('pbSexualReputation')) history.push(`sexual reputation: ${personalityBuilderValue('pbSexualReputation')}`);
  if (history.length) lines.push(`- Sexual History: ${history.join(', ')}.`);

  const flavor = [];
  if (personalityBuilderValue('pbSpeech')) flavor.push(`speech style: ${personalityBuilderValue('pbSpeech')}`);
  if (personalityBuilderValue('pbQuirks')) flavor.push(`quirks: ${personalityBuilderValue('pbQuirks')}`);
  if (flavor.length) lines.push(`- Speech and Flavor: ${flavor.join(', ')}.`);

  if (personalityBuilderValue('pbExtraNotes')) lines.push(`- Extra Notes: ${personalityBuilderValue('pbExtraNotes')}`);
  return lines.join('\n');
}

function generatePersonalityBuilderDescription() {
  const desc = buildPersonalityBuilderDescription();
  if (!desc) {
    setStatus('Choose at least one personality builder option first.', 'error');
    return;
  }
  $('#personalityBuilderDescription').value = desc;
  captureCurrentMultiBuilderState();
  setStatus(`Personality Builder guidance created${isMultiBuilderMode() ? ' for ' + getMultiBuilderCharacterName(multiBuilderSelectedIndex) : ''}. Edit it or append it to the concept when ready.`, 'ok');
}

function appendPersonalityBuilderToConcept() {
  const desc = ($('#personalityBuilderDescription')?.value || '').trim() || buildPersonalityBuilderDescription();
  if (!desc) {
    setStatus('Build personality guidance first.', 'error');
    return;
  }
  const box = $('#conceptText');
  const block = `PERSONALITY BUILDER TRAIT GUIDANCE:\n${desc}`;
  box.value = (box.value || '').trim() ? `${box.value.trim()}\n\n${block}` : block;
  setStatus('Personality Builder guidance appended to Main Concept.', 'ok');
}

function clearPersonalityBuilder() {
  [
    'pbArchetype','pbSocial','pbConfidence','pbEmotion','pbDrive','pbFear','pbMoral','pbDecision',
    'pbUserBehavior','pbAttachment','pbConflict','pbSecrecy','pbSexualNature','pbLibido','pbPromiscuity',
    'pbDynamic','pbRisk','pbKinkFocus','pbOccupation','pbCurrentRelationshipStatus','pbPublicRelationshipImage','pbRelationshipPressure','pbSpeech','pbSexualPartners','pbVirginityHistory','pbFirstCreampie','pbUserRelationshipRole','pbUserRelationshipHistory','pbUserCurrentDynamic','pbUserFeelings','pbUserSecretTension','pbUserDesiredDirection'
  ].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  ['pbOccupationCustom','pbCurrentRelationshipStatusCustom','pbCurrentPartner','pbPublicRelationshipImageCustom','pbRelationshipPressureCustom','pbNsfwBoundaries','pbKinkCustom','pbSexualPartnersCustom','pbVirginityHistoryCustom','pbFirstCreampieCustom','pbBestSexualMemory','pbWorstSexualMemory','pbCurrentSexualSituation','pbSexualReputation','pbUserRelationshipRoleCustom','pbUserRelationshipHistoryCustom','pbUserCurrentDynamicCustom','pbUserFeelingsCustom','pbUserSecretTensionCustom','pbUserDesiredDirectionCustom','pbTurnOns','pbTurnOffs','pbQuirks','pbLikes','pbDislikes','pbHobbies','pbExtraNotes','personalityBuilderDescription'].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  updateCustomConditionalOptions();
  captureCurrentMultiBuilderState();
  setStatus(`Personality Builder cleared${isMultiBuilderMode() ? ' for ' + getMultiBuilderCharacterName(multiBuilderSelectedIndex) : ''}.`, 'ok');
}

function sceneBuilderValue(id) { return builderValue(id); }

function buildSceneBuilderDescription() {
  const lines = [];
  const setting = [];
  const settingType = selectedOrCustom('sbSetting', 'sbSettingCustom');
  const time = selectedOrCustom('sbTime', 'sbTimeCustom');
  if (settingType) setting.push(`setting type: ${settingType}`);
  if (sceneBuilderValue('sbLocation')) setting.push(`specific location: ${sceneBuilderValue('sbLocation')}`);
  if (time) setting.push(`time/atmosphere: ${time}`);
  if (setting.length) lines.push(`- Setting: ${setting.join(', ')}.`);

  const situation = [];
  const situationType = selectedOrCustom('sbSituation', 'sbSituationCustom');
  if (situationType) situation.push(`opening situation: ${situationType}`);
  if (sceneBuilderValue('sbJustHappened')) situation.push(`what just happened: ${sceneBuilderValue('sbJustHappened')}`);
  if (sceneBuilderValue('sbAboutToHappen')) situation.push(`what is about to happen: ${sceneBuilderValue('sbAboutToHappen')}`);
  if (situation.length) lines.push(`- Situation: ${situation.join(', ')}.`);

  const stakes = [];
  const tone = selectedOrCustom('sbTone', 'sbToneCustom');
  const goal = selectedOrCustom('sbGoal', 'sbGoalCustom');
  if (tone) stakes.push(`tone: ${tone}`);
  if (goal) stakes.push(`immediate goal: ${goal}`);
  if (sceneBuilderValue('sbRisk')) stakes.push(`complication/risk: ${sceneBuilderValue('sbRisk')}`);
  if (stakes.length) lines.push(`- Tension and Stakes: ${stakes.join(', ')}.`);

  const notes = [];
  if (sceneBuilderValue('sbProps')) notes.push(`props/objects: ${sceneBuilderValue('sbProps')}`);
  if (sceneBuilderValue('sbExtraNotes')) notes.push(`extra notes: ${sceneBuilderValue('sbExtraNotes')}`);
  if (notes.length) lines.push(`- Scenario Notes: ${notes.join(', ')}.`);
  return lines.join('\n');
}

function generateSceneBuilderDescription() {
  const desc = buildSceneBuilderDescription();
  if (!desc) {
    setStatus('Choose at least one scene builder option first.', 'error');
    return;
  }
  $('#sceneBuilderDescription').value = desc;
  captureCurrentMultiBuilderState();
  setStatus(`Scene Builder guidance created${isMultiBuilderMode() ? ' for ' + getMultiBuilderCharacterName(multiBuilderSelectedIndex) : ''}. Edit it or append it to the concept when ready.`, 'ok');
}

function appendSceneBuilderToConcept() {
  const desc = ($('#sceneBuilderDescription')?.value || '').trim() || buildSceneBuilderDescription();
  if (!desc) {
    setStatus('Build scene guidance first.', 'error');
    return;
  }
  const box = $('#conceptText');
  const block = `SCENE BUILDER SCENARIO GUIDANCE:
${desc}`;
  box.value = (box.value || '').trim() ? `${box.value.trim()}

${block}` : block;
  setStatus('Scene Builder guidance appended to Main Concept.', 'ok');
}

function clearSceneBuilder() {
  ['sbSetting','sbTime','sbSituation','sbTone','sbGoal'].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  ['sbSettingCustom','sbLocation','sbTimeCustom','sbSituationCustom','sbJustHappened','sbAboutToHappen','sbToneCustom','sbGoalCustom','sbRisk','sbProps','sbExtraNotes','sceneBuilderDescription'].forEach(id => { const el = $('#'+id); if (el) el.value = ''; });
  updateCustomConditionalOptions();
  captureCurrentMultiBuilderState();
  setStatus(`Scene Builder cleared${isMultiBuilderMode() ? ' for ' + getMultiBuilderCharacterName(multiBuilderSelectedIndex) : ''}.`, 'ok');
}

function collectBuilderGuidanceForModel() {
  if (!isMultiBuilderMode()) {
    return {
      visual: ($('#builderDescription')?.value || '').trim(),
      personality: ($('#personalityBuilderDescription')?.value || '').trim(),
      scene: ($('#sceneBuilderDescription')?.value || '').trim(),
      hasAny: !!(($('#builderDescription')?.value || '').trim() || ($('#personalityBuilderDescription')?.value || '').trim() || ($('#sceneBuilderDescription')?.value || '').trim())
    };
  }
  captureCurrentMultiBuilderState();
  ensureMultiBuilderStates();
  const originalIndex = multiBuilderSelectedIndex;
  const originalState = readBuilderDomState();
  const visuals = [];
  const personalities = [];
  const scenes = [];
  try {
    multiBuilderStates.forEach((state, idx) => {
      writeBuilderDomState(state || {});
      const name = getMultiBuilderCharacterName(idx);
      const visual = ((state || {}).builderDescription || buildCharacterBuilderDescription() || '').trim();
      const personality = ((state || {}).personalityBuilderDescription || buildPersonalityBuilderDescription() || '').trim();
      const scene = ((state || {}).sceneBuilderDescription || buildSceneBuilderDescription() || '').trim();
      if (visual) visuals.push(`${name}:\n${visual}`);
      if (personality) personalities.push(`${name}:\n${personality}`);
      if (scene) scenes.push(`${name}:\n${scene}`);
    });
  } finally {
    multiBuilderSelectedIndex = originalIndex;
    writeBuilderDomState({ ...(multiBuilderStates[originalIndex] || {}), ...originalState });
    updateMultiBuilderSelectors(true);
  }
  return {
    visual: visuals.join('\n\n'),
    personality: personalities.join('\n\n'),
    scene: scenes.join('\n\n'),
    hasAny: !!(visuals.length || personalities.length || scenes.length)
  };
}

function buildConceptForModel() {
  const concept = ($('#conceptText').value || '').trim();
  const visual = ($('#visionDescription').value || '').trim();
  const builderGuidance = collectBuilderGuidanceForModel();
  const builderVisual = builderGuidance.visual;
  const personalityBuilder = builderGuidance.personality;
  const sceneBuilder = builderGuidance.scene;
  const attachmentText = buildAttachmentTextForModel();
  const parts = [];
  const hasBuilder = !!builderGuidance.hasAny;
  if (hasBuilder) {
    parts.push('BUILDER PRIORITY RULE — if Main Concept, attachments, or Character Description conflict with any Builder guidance below, the Builder guidance wins. Treat Builder guidance as the newest and most intentional version. Do not let older concept text override it.');
  }
  if (concept) parts.push(concept);
  if (attachmentText) parts.push(attachmentText);
  if (visual) {
    parts.push([
      'CHARACTER DESCRIPTION / VISION REFERENCE — use this as physical appearance/clothing reference only when it does not conflict with Character Builder Visual Description. Builder visual fields take priority:',
      visual
    ].join('\n'));
  }
  if (builderVisual) {
    parts.push([
      (isMultiBuilderMode() ? 'MULTI-CHARACTER BUILDER VISUAL DESCRIPTIONS — AUTHORITATIVE per character for physical appearance, body, clothing, underwear, accessories, and visual style. Preserve the per-character headings. Put this in the Description field, not Personality:' : 'CHARACTER BUILDER VISUAL DESCRIPTION — AUTHORITATIVE for physical appearance, body, clothing, underwear, accessories, and visual style. Put this in the Description field, not Personality:'),
      builderVisual
    ].join('\n'));
  }
  if (personalityBuilder) {
    parts.push([
      (isMultiBuilderMode() ? 'MULTI-CHARACTER PERSONALITY BUILDER TRAIT GUIDANCE — AUTHORITATIVE per character for Personality, Sexual Traits, occupation, hobbies, likes/dislikes, kinks, turn-ons, turn-offs, current relationship/social role, relationship with {{user}}, sexual history, speech style, and boundaries. Preserve the per-character headings. Do not put this in the Description field. Treat all adult/NSFW traits as adult-coded only:' : 'PERSONALITY BUILDER TRAIT GUIDANCE — AUTHORITATIVE for Personality, Sexual Traits, occupation, hobbies, likes/dislikes, kinks, turn-ons, turn-offs, current relationship/social role, relationship with {{user}}, sexual history, speech style, and boundaries. Do not put this in the Description field. Treat all adult/NSFW traits as adult-coded only:'),
      personalityBuilder
    ].join('\n'));
  }
  if (sceneBuilder) {
    parts.push([
      (isMultiBuilderMode() ? `MULTI-CHARACTER SCENE BUILDER SCENARIO GUIDANCE — AUTHORITATIVE per character for how each character fits the Scenario and opening First Message. Preserve the per-character headings, but generate ONE coherent shared Scenario. Setting logic: ${getSharedScenePolicyText()}. Keep this out of Description/Personality unless a detail clearly belongs there:` : 'SCENE BUILDER SCENARIO GUIDANCE — AUTHORITATIVE for Scenario, Background context where relevant, and the opening First Message. Keep this out of Description/Personality unless a detail clearly belongs there:'),
      sceneBuilder
    ].join('\n'));
  }
  return parts.join('\n\n');
}

function collectBuilderWorkspaceState() {
  if (isMultiBuilderMode()) {
    captureCurrentMultiBuilderState();
    ensureMultiBuilderStates();
    return {
      mode: 'multi',
      selectedIndex: multiBuilderSelectedIndex,
      states: multiBuilderStates.map(s => ({ ...(s || {}) })),
    };
  }
  return { mode: 'single', selectedIndex: 0, states: [{ ...readBuilderDomState() }] };
}

function restoreBuilderWorkspaceState(builderState) {
  if (!builderState || typeof builderState !== 'object') return;
  const states = Array.isArray(builderState.states) ? builderState.states : [];
  if (builderState.mode === 'multi' || states.length >= 2) {
    $('#cardMode').value = 'multi';
    $('#multiCharacterCount').value = String(Math.max(2, Math.min(12, states.length || 2)));
    settings.cardMode = 'multi';
    settings.multiCharacterCount = Number($('#multiCharacterCount').value || 2);
    multiBuilderStates = states.map(s => ({ ...(s || {}) }));
    multiBuilderSelectedIndex = Math.max(0, Math.min(multiBuilderStates.length - 1, Number(builderState.selectedIndex || 0)));
    ensureMultiBuilderStates();
    writeBuilderDomState(multiBuilderStates[multiBuilderSelectedIndex] || {});
    updateCardModeHint();
  } else if (states[0]) {
    $('#cardMode').value = 'single';
    settings.cardMode = 'single';
    multiBuilderStates = [];
    multiBuilderSelectedIndex = 0;
    writeBuilderDomState(states[0]);
    updateCardModeHint();
  }
  updateBuilderConditionalOptions();
  updateCustomConditionalOptions();
}

function collectWorkspacePayload() {
  settings = collectSettings();
  return {
    concept: $('#conceptText')?.value || '',
    output: $('#outputText')?.value || '',
    template,
    settings,
    builderState: collectBuilderWorkspaceState(),
    qnaAnswers: lastQnaAnswers || ($('#qaAnswersText')?.value || ''),
    emotionImages: emotionImageState || [],
    visionDescription: $('#visionDescription')?.value || '',
    conceptAttachments: conceptAttachments || [],
    cardImagePath: settings.cardImagePath || $('#cardImagePath')?.value || '',
    browserDescription: currentBrowserDescription || '',
  };
}

async function saveCurrentWorkspace(reason='autosave') {
  if (!hasOutput()) return null;
  try {
    const payload = collectWorkspacePayload();
    const res = await window.pywebview.api.save_character_workspace(payload);
    if (!res.ok) throw new Error(res.error || 'Workspace save failed.');
    if (reason !== 'silent') setStatus(`Workspace saved to ${res.folder}`, 'ok');
    refreshCharacterBrowser(false);
    return res;
  } catch (err) {
    setStatus(`Workspace autosave failed: ${err.message || err}`, 'error');
    return null;
  }
}

async function refreshCharacterBrowser(showStatus=true) {
  try {
    const res = await window.pywebview.api.list_character_library();
    if (!res.ok) throw new Error(res.error || 'Could not load character browser.');
    characterBrowserCards = res.cards || [];
    if (selectedCharacterProjectPath && !characterBrowserCards.some(c => c.projectPath === selectedCharacterProjectPath)) {
      selectedCharacterProjectPath = '';
    }
    browserSelectedProjects = new Set([...browserSelectedProjects].filter(path => characterBrowserCards.some(c => c.projectPath === path)));
    renderCharacterBrowser();
    renderSelectedCharacterTags(characterBrowserCards.find(c => c.projectPath === selectedCharacterProjectPath));
    if (showStatus) setStatus(`Character Browser refreshed: ${characterBrowserCards.length} character(s).`, 'ok');
  } catch (err) {
    if (showStatus) setStatus(err.message || String(err), 'error');
  }
}


function normaliseFolderId(value) {
  return String(value || '').trim();
}

function browserFolderChildren(parentId) {
  const key = normaliseFolderId(parentId);
  return (browserVirtualFolders || []).filter(f => normaliseFolderId(f.parentId) === key);
}

function browserFolderDescendantIds(folderId) {
  const out = new Set();
  const walk = (id) => {
    browserFolderChildren(id).forEach(child => {
      const cid = normaliseFolderId(child.id);
      if (cid && !out.has(cid)) {
        out.add(cid);
        walk(cid);
      }
    });
  };
  walk(folderId);
  return out;
}

function browserCardFolderId(card) {
  return normaliseFolderId(card?.virtualFolderId || '');
}

function browserCardMatchesFolderScope(card) {
  if (browserFolderScope === 'global' || browserCurrentFolderId === '__all__') return true;
  const current = normaliseFolderId(browserCurrentFolderId);
  const cardFolder = browserCardFolderId(card);
  if (browserFolderScope === 'current') return cardFolder === current;
  if (browserFolderScope === 'current_subfolders') {
    if (cardFolder === current) return true;
    return browserFolderDescendantIds(current).has(cardFolder);
  }
  return true;
}

function browserScopeCards() {
  return characterBrowserCards.filter(browserCardMatchesFolderScope);
}

function browserFolderLabel(folderId) {
  if (!folderId) return 'Unfiled';
  const folder = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === normaliseFolderId(folderId));
  return folder ? folder.name : 'Unknown Folder';
}

function browserFolderPathLabel(folderId) {
  const parts = [];
  let current = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === normaliseFolderId(folderId));
  const guard = new Set();
  while (current && !guard.has(current.id)) {
    guard.add(current.id);
    parts.unshift(current.name);
    current = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === normaliseFolderId(current.parentId));
  }
  return parts.join(' / ') || 'Unfiled';
}

function renderBrowserFolderControls() {
  const folderSelect = $('#browserFolderSelect');
  const moveSelect = $('#browserMoveFolderSelect');
  const scopeSelect = $('#browserFolderScope');
  const options = ['<option value="__all__">All folders</option>', '<option value="">Unfiled</option>']
    .concat((browserVirtualFolders || [])
      .slice()
      .sort((a,b) => browserFolderPathLabel(a.id).localeCompare(browserFolderPathLabel(b.id), undefined, { sensitivity: 'base' }))
      .map(f => `<option value="${escapeAttr(f.id)}">${escapeHtml(browserFolderPathLabel(f.id))}</option>`));
  if (folderSelect) {
    folderSelect.innerHTML = options.join('');
    if (![...folderSelect.options].some(o => o.value === browserCurrentFolderId)) browserCurrentFolderId = '__all__';
    folderSelect.value = browserCurrentFolderId;
  }
  if (moveSelect) {
    const moveOptions = ['<option value="">Unfiled</option>'].concat((browserVirtualFolders || [])
      .slice()
      .sort((a,b) => browserFolderPathLabel(a.id).localeCompare(browserFolderPathLabel(b.id), undefined, { sensitivity: 'base' }))
      .map(f => `<option value="${escapeAttr(f.id)}">${escapeHtml(browserFolderPathLabel(f.id))}</option>`));
    moveSelect.innerHTML = moveOptions.join('');
  }
  if (scopeSelect) scopeSelect.value = browserFolderScope;
}

function selectedBrowserProjectPaths() {
  if (browserSelectedProjects.size) return [...browserSelectedProjects];
  return selectedCharacterProjectPath ? [selectedCharacterProjectPath] : [];
}

function updateBrowserMultiActionState() {
  const count = selectedBrowserProjectPaths().length;
  const el = $('#browserSelectedCount');
  if (el) el.textContent = count ? `${count} selected` : 'No multi-select';
}

async function saveBrowserVirtualFolders() {
  settings = { ...(settings || {}), browserVirtualFolders: browserVirtualFolders || [] };
  try {
    await window.pywebview.api.save_settings(settings);
    if (window.pywebview.api.save_browser_virtual_folders) await window.pywebview.api.save_browser_virtual_folders(browserVirtualFolders || []);
  } catch (err) {
    setStatus(`Could not save virtual folders: ${err.message || err}`, 'error');
  }
}

async function createBrowserVirtualFolder() {
  const name = prompt('New virtual folder name:');
  const clean = String(name || '').trim();
  if (!clean) return;
  const parentId = (browserCurrentFolderId && browserCurrentFolderId !== '__all__') ? browserCurrentFolderId : '';
  const folder = { id: `vf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`, name: clean, parentId };
  browserVirtualFolders.push(folder);
  await saveBrowserVirtualFolders();
  browserCurrentFolderId = folder.id;
  renderCharacterBrowser();
  setStatus(`Created virtual folder: ${clean}`, 'ok');
}

async function moveSelectedCharactersToFolder() {
  const paths = selectedBrowserProjectPaths();
  if (!paths.length) { setStatus('Select one or more characters first.', 'error'); return; }
  const folderId = $('#browserMoveFolderSelect')?.value || '';
  setBusy('MOVING SELECTED CHARACTERS…');
  try {
    const res = await window.pywebview.api.move_character_projects_to_folder(paths, folderId);
    if (!res.ok) throw new Error(res.error || 'Move failed.');
    await refreshCharacterBrowser(false);
    setStatus(`Moved ${res.updated || 0} character(s) to ${browserFolderLabel(folderId)}.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function deleteSelectedCharacterDirectories() {
  const paths = selectedBrowserProjectPaths();
  if (!paths.length) { setStatus('Select one or more characters first.', 'error'); return; }
  const ok = confirm(`Delete ${paths.length} local Character Card Forge director${paths.length === 1 ? 'y' : 'ies'}?\n\nThis only removes the local saved/export folder. It does not touch Front Porch AI database entries.`);
  if (!ok) return;
  setBusy('DELETING LOCAL CHARACTER DIRECTORIES…');
  try {
    const res = await window.pywebview.api.delete_character_project_directories(paths);
    if (!res.ok) throw new Error(res.error || 'Delete failed.');
    browserSelectedProjects.clear();
    selectedCharacterProjectPath = '';
    await refreshCharacterBrowser(false);
    setStatus(`Deleted ${res.deleted || 0} local character director${res.deleted === 1 ? 'y' : 'ies'}. Front Porch was not touched.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function exportSelectedCharactersBatch(format) {
  const paths = selectedBrowserProjectPaths();
  if (!paths.length) { setStatus('Select one or more characters first.', 'error'); return; }
  setBusy('BATCH EXPORTING SELECTED CHARACTERS…');
  let ok = 0;
  let failed = 0;
  for (const path of paths) {
    try {
      const res = await window.pywebview.api.export_character_from_project(path, format);
      if (res.ok) ok += 1;
      else failed += 1;
    } catch (_) { failed += 1; }
  }
  setBusy('');
  await refreshCharacterBrowser(false);
  setStatus(`Batch export complete: ${ok} succeeded${failed ? `, ${failed} failed` : ''}.`, failed ? 'error' : 'ok');
}

async function exportSelectedCharactersToFrontPorchBatch() {
  const paths = selectedBrowserProjectPaths();
  if (!paths.length) { setStatus('Select one or more characters first.', 'error'); return; }
  settings = collectSettings();
  if (!settings.frontPorchDataFolder) { setStatus('Set Front Porch Data Folder in AI Settings first.', 'error'); return; }
  const okConfirm = confirm(`Export ${paths.length} selected character(s) to Front Porch AI?\n\nA database backup is created by the exporter. Close Front Porch before exporting if possible.`);
  if (!okConfirm) return;
  setBusy('BATCH EXPORTING TO FRONT PORCH AI…');
  let ok = 0;
  let failed = 0;
  try { await window.pywebview.api.save_settings(settings); } catch (_) {}
  for (const path of paths) {
    try {
      const res = await window.pywebview.api.export_front_porch_from_project(path);
      if (res.ok) ok += 1;
      else failed += 1;
    } catch (_) { failed += 1; }
  }
  setBusy('');
  setStatus(`Front Porch batch export complete: ${ok} succeeded${failed ? `, ${failed} failed` : ''}.`, failed ? 'error' : 'ok');
}

function normaliseBrowserTag(tag) {
  return String(tag || '').trim();
}

function browserTagKey(tag) {
  return normaliseBrowserTag(tag).toLowerCase();
}

function cleanBrowserTagMerges(map) {
  const cleaned = {};
  Object.entries(map || {}).forEach(([from, to]) => {
    const key = browserTagKey(from);
    const display = normaliseBrowserTag(to);
    if (!key || !display || key === display.toLowerCase()) return;
    cleaned[key] = display;
  });
  return cleaned;
}

function cardTags(card) {
  return Array.isArray(card?.tags) ? card.tags.map(normaliseBrowserTag).filter(Boolean) : [];
}

function effectiveBrowserTag(tag) {
  const original = normaliseBrowserTag(tag);
  const key = browserTagKey(original);
  return normaliseBrowserTag(browserTagMerges[key] || original);
}

function isMergedBrowserTag(tag) {
  const key = browserTagKey(tag);
  return !!(key && browserTagMerges[key] && browserTagMerges[key].toLowerCase() !== key);
}

function cardEffectiveTags(card) {
  const tags = new Map();
  cardTags(card).forEach(tag => {
    const display = effectiveBrowserTag(tag);
    const key = browserTagKey(display);
    if (key && !tags.has(key)) tags.set(key, display);
  });
  return [...tags.values()];
}

function cardEffectiveTagKeys(card) {
  return cardEffectiveTags(card).map(browserTagKey);
}

function allBrowserTags() {
  const tags = new Map();
  browserScopeCards().forEach(card => {
    cardEffectiveTags(card).forEach(tag => {
      const key = browserTagKey(tag);
      if (!tags.has(key)) tags.set(key, tag);
    });
  });
  return [...tags.values()].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function allOriginalBrowserTags() {
  const tags = new Map();
  characterBrowserCards.forEach(card => {
    cardTags(card).forEach(tag => {
      const key = browserTagKey(tag);
      if (key && !tags.has(key)) tags.set(key, tag);
    });
  });
  return [...tags.values()].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function browserCardMatchesSearch(card) {
  const search = browserSearchTerm.trim().toLowerCase();
  if (!search) return true;
  const tags = cardTags(card);
  const effectiveTags = cardEffectiveTags(card);
  const haystack = [
    card.name,
    card.browserDescription,
    card.outputPreview,
    card.folder,
    ...tags,
    ...effectiveTags,
  ].join(' ').toLowerCase();
  return haystack.includes(search);
}

function browserCardMatchesTagFilters(card) {
  const lowerTags = cardEffectiveTagKeys(card);
  for (const tag of browserIncludeTags) {
    if (!lowerTags.includes(tag.toLowerCase())) return false;
  }
  for (const tag of browserExcludeTags) {
    if (lowerTags.includes(tag.toLowerCase())) return false;
  }
  return true;
}

function visibleBrowserTagStats() {
  const stats = new Map();

  // Faceted tag list: once filters/search are active, only show tags that exist
  // on cards still matching the current result set. Count once per card.
  browserScopeCards()
    .filter(card => browserCardMatchesTagFilters(card) && browserCardMatchesSearch(card))
    .forEach(card => {
      cardEffectiveTags(card).forEach(tag => {
        const key = browserTagKey(tag);
        const existing = stats.get(key) || { tag, count: 0 };
        existing.count += 1;
        stats.set(key, existing);
      });
    });

  // Keep active filters visible even if the current result set would hide them.
  for (const key of [...browserIncludeTags, ...browserExcludeTags]) {
    if (!stats.has(key)) {
      const canonical = allBrowserTags().find(tag => browserTagKey(tag) === key) || key;
      stats.set(key, { tag: canonical, count: 0 });
    }
  }

  const values = [...stats.values()];
  if (browserTagSortMode === 'usage') {
    values.sort((a, b) => (b.count - a.count) || a.tag.localeCompare(b.tag, undefined, { sensitivity: 'base' }));
  } else {
    values.sort((a, b) => a.tag.localeCompare(b.tag, undefined, { sensitivity: 'base' }));
  }
  return values;
}

function visibleBrowserTags() {
  return visibleBrowserTagStats().map(item => item.tag);
}

function browserCardMatches(card) {
  return browserCardMatchesTagFilters(card) && browserCardMatchesSearch(card);
}

function browserUpdatedTime(card) {
  const parsed = Date.parse(card?.updated || '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function getVisibleBrowserCards() {
  const cards = browserScopeCards().filter(browserCardMatches);
  const byName = (a, b) => String(a.name || '').localeCompare(String(b.name || ''), undefined, { sensitivity: 'base' });
  const byDate = (a, b) => browserUpdatedTime(b) - browserUpdatedTime(a);
  if (browserSortMode === 'alpha_asc') cards.sort(byName);
  else if (browserSortMode === 'alpha_desc') cards.sort((a, b) => byName(b, a));
  else if (browserSortMode === 'date_asc') cards.sort((a, b) => browserUpdatedTime(a) - browserUpdatedTime(b));
  else cards.sort(byDate);
  return cards;
}

function renderBrowserFilterPanel() {
  const panel = $('#browserFilterPanel');
  if (!panel) return;
  panel.classList.toggle('hidden', !browserFilterPanelOpen);
  const tagStats = visibleBrowserTagStats();
  const count = browserIncludeTags.size + browserExcludeTags.size;
  const filterBtn = $('#browserFilterBtn');
  if (filterBtn) filterBtn.textContent = count ? `Filter Tags (${count})` : 'Filter Tags';
  const summary = $('#browserFilterSummary');
  if (summary) {
    const inc = [...browserIncludeTags].sort((a,b) => a.localeCompare(b)).map(t => `+${t}`);
    const exc = [...browserExcludeTags].sort((a,b) => a.localeCompare(b)).map(t => `-${t}`);
    summary.textContent = [...inc, ...exc].join('   ') || 'Click a tag once to include it, twice to exclude it, and a third time to clear it.';
  }
  const wrap = $('#browserTagFilterList');
  if (!wrap) return;
  if (!tagStats.length) {
    wrap.innerHTML = '<div class="empty small">No tags are available for the current search/filter.</div>';
  } else {
    wrap.innerHTML = tagStats.map(({ tag, count }) => {
      const key = browserTagKey(tag);
      const state = browserIncludeTags.has(key) ? 'include' : browserExcludeTags.has(key) ? 'exclude' : 'neutral';
      const prefix = state === 'include' ? '+' : state === 'exclude' ? '−' : '';
      return `<button type="button" class="tag-filter-chip ${state}" data-tag="${escapeAttr(tag)}">${prefix}${escapeHtml(tag)} <span class="tag-count">(${count})</span></button>`;
    }).join('');
  }
  renderTagMergePanel();
  renderAiTagSuggestions();
  $$('.tag-filter-chip', wrap).forEach(btn => {
    btn.addEventListener('click', () => {
      const key = browserTagKey(btn.dataset.tag);
      if (!key) return;
      if (!browserIncludeTags.has(key) && !browserExcludeTags.has(key)) {
        browserIncludeTags.add(key);
      } else if (browserIncludeTags.has(key)) {
        browserIncludeTags.delete(key);
        browserExcludeTags.add(key);
      } else {
        browserExcludeTags.delete(key);
      }
      renderCharacterBrowser();
    });
  });
}

function renderTagMergePanel() {
  const originalSelect = $('#tagMergeOriginal');
  const aliasInput = $('#tagMergeAlias');
  const list = $('#tagMergeList');
  if (!originalSelect || !aliasInput || !list) return;
  const originalTags = allOriginalBrowserTags();
  const current = originalSelect.value;
  originalSelect.innerHTML = '<option value="">Choose original tag…</option>' + originalTags.map(tag => `<option value="${escapeAttr(tag)}">${escapeHtml(tag)}</option>`).join('');
  if (current && originalTags.some(t => browserTagKey(t) === browserTagKey(current))) originalSelect.value = current;
  const entries = Object.entries(browserTagMerges || {}).sort((a, b) => a[0].localeCompare(b[0]));
  if (!entries.length) {
    list.innerHTML = '<div class="empty small">No tag merges yet. Real character tags are untouched.</div>';
  } else {
    const originalLookup = new Map(allOriginalBrowserTags().map(t => [browserTagKey(t), t]));
    list.innerHTML = entries.map(([fromKey, to]) => {
      const from = originalLookup.get(fromKey) || fromKey;
      return `<div class="tag-merge-row"><span><b>${escapeHtml(from)}</b> → <span class="merged-tag-label">${escapeHtml(to)}</span></span><button type="button" class="remove-tag-merge" data-tag="${escapeAttr(fromKey)}">Remove</button></div>`;
    }).join('');
  }
  $$('.remove-tag-merge', list).forEach(btn => {
    btn.addEventListener('click', async () => {
      delete browserTagMerges[btn.dataset.tag];
      await saveBrowserTagMerges();
      renderCharacterBrowser();
      renderSelectedCharacterTags(getSelectedBrowserCard());
    });
  });
}

async function saveBrowserTagMerges() {
  browserTagMerges = cleanBrowserTagMerges(browserTagMerges);
  settings = { ...(settings || {}), browserTagMerges };
  try {
    await window.pywebview.api.save_settings(settings);
  } catch (err) {
    setStatus(`Could not save tag merges: ${err.message || err}`, 'error');
  }
}

async function addBrowserTagMerge() {
  const original = normaliseBrowserTag($('#tagMergeOriginal')?.value || '');
  const alias = normaliseBrowserTag($('#tagMergeAlias')?.value || '');
  const key = browserTagKey(original);
  if (!key || !alias) { setStatus('Choose an original tag and enter the display tag to merge into.', 'error'); return; }
  if (key === alias.toLowerCase()) { setStatus('The merged display tag must be different from the original tag.', 'error'); return; }
  browserTagMerges[key] = alias;
  await saveBrowserTagMerges();
  const aliasInput = $('#tagMergeAlias');
  if (aliasInput) aliasInput.value = '';
  renderCharacterBrowser();
  renderSelectedCharacterTags(getSelectedBrowserCard());
  setStatus(`Merged ${original} into display tag ${alias}. Original character tags were not changed.`, 'ok');
}

function aiSuggestionKey(item) {
  return `${browserTagKey(item?.from)}=>${browserTagKey(item?.to)}`;
}

function renderAiTagSuggestions() {
  const list = $('#aiTagSuggestionList');
  if (!list) return;
  if (!aiTagCleanupSuggestions.length) {
    list.innerHTML = '<div class="empty small">No AI suggestions yet.</div>';
    return;
  }
  list.innerHTML = aiTagCleanupSuggestions.map((item, idx) => `
    <div class="tag-merge-row ai-tag-suggestion" data-index="${idx}">
      <span><b>${escapeHtml(item.from)}</b> <span class="tag-count">(${Number(item.fromCount || 0)})</span> → <span class="merged-tag-label">${escapeHtml(item.to)}</span> <span class="tag-count">(${Number(item.toCount || 0)})</span><br><small>${escapeHtml(item.reason || 'Near-duplicate tag.')}</small></span>
      <span class="tag-suggestion-actions">
        <button type="button" class="ai-tag-merge-one" data-index="${idx}">Merge Only</button>
        <button type="button" class="ai-tag-rename-one danger" data-index="${idx}">Rename</button>
      </span>
    </div>`).join('');
  $$('.ai-tag-merge-one', list).forEach(btn => btn.addEventListener('click', () => applyAiTagSuggestion(Number(btn.dataset.index), 'merge')));
  $$('.ai-tag-rename-one', list).forEach(btn => btn.addEventListener('click', () => applyAiTagSuggestion(Number(btn.dataset.index), 'rename')));
}

async function runAiTagCleanup() {
  setBusy('AI TAG CLEANUP — SCANNING LIBRARY TAGS…');
  try {
    const res = await window.pywebview.api.ai_suggest_tag_cleanup(settings || {});
    if (!res.ok) throw new Error(res.error || 'AI tag cleanup failed.');
    aiTagCleanupSuggestions = res.suggestions || [];
    renderAiTagSuggestions();
    const msg = aiTagCleanupSuggestions.length
      ? `AI found ${aiTagCleanupSuggestions.length} possible tag merge(s) from ${res.tagCount || 0} tag(s).`
      : `AI found no obvious redundant tags among ${res.tagCount || 0} tag(s).`;
    setStatus(msg, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function applyAiTagSuggestion(index, mode) {
  const item = aiTagCleanupSuggestions[index];
  if (!item) return;
  await applyAiTagSuggestions(mode, [item]);
  aiTagCleanupSuggestions = aiTagCleanupSuggestions.filter((x, i) => i !== index);
  renderAiTagSuggestions();
}

async function applyAiTagSuggestions(mode, items=null) {
  const suggestions = (items || aiTagCleanupSuggestions || []).filter(x => normaliseBrowserTag(x?.from) && normaliseBrowserTag(x?.to));
  if (!suggestions.length) { setStatus('No AI tag suggestions to apply.', 'error'); return; }
  if (mode === 'merge') {
    suggestions.forEach(item => { browserTagMerges[browserTagKey(item.from)] = normaliseBrowserTag(item.to); });
    await saveBrowserTagMerges();
    renderCharacterBrowser();
    renderSelectedCharacterTags(getSelectedBrowserCard());
    setStatus(`Applied ${suggestions.length} display-only tag merge(s). Real character tags were not changed.`, 'ok');
    return;
  }
  if (mode === 'rename') {
    const renameMap = {};
    suggestions.forEach(item => { renameMap[normaliseBrowserTag(item.from)] = normaliseBrowserTag(item.to); });
    setBusy('RENAMING TAGS IN CHARACTER PROJECTS…');
    try {
      const res = await window.pywebview.api.rename_tags_across_library(renameMap);
      if (!res.ok) throw new Error(res.error || 'Could not rename tags.');
      // Remove display-only aliases that are now real renamed tags.
      suggestions.forEach(item => { delete browserTagMerges[browserTagKey(item.from)]; });
      await saveBrowserTagMerges();
      await refreshCharacterBrowser(false);
      setStatus(`Renamed tags in ${res.updated || 0} character project(s).`, 'ok');
    } catch (err) {
      setStatus(err.message || String(err), 'error');
    } finally {
      setBusy('');
    }
  }
}

async function regenerateSelectedBrowserDescription() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  setBusy('AI DESCRIPTION — READING CHARACTER CARD…');
  try {
    const res = await window.pywebview.api.regenerate_browser_description_for_project(selectedCharacterProjectPath, settings || {});
    if (!res.ok) throw new Error(res.error || 'Could not regenerate description.');
    const card = getSelectedBrowserCard();
    if (card) card.browserDescription = res.browserDescription || card.browserDescription || '';
    const preview = $('#browserPreview');
    if (preview) preview.value = res.browserDescription || '';
    await refreshCharacterBrowser(false);
    setStatus('AI browser description updated.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function cycleBrowserTagFilter(tag, preferInclude=true) {
  const key = browserTagKey(tag);
  if (!key) return;
  if (preferInclude) {
    if (browserExcludeTags.has(key)) browserExcludeTags.delete(key);
    browserIncludeTags.add(key);
  } else if (!browserIncludeTags.has(key) && !browserExcludeTags.has(key)) {
    browserIncludeTags.add(key);
  } else if (browserIncludeTags.has(key)) {
    browserIncludeTags.delete(key);
    browserExcludeTags.add(key);
  } else {
    browserExcludeTags.delete(key);
  }
  renderCharacterBrowser();
}

function getSelectedBrowserCard() {
  return characterBrowserCards.find(c => c.projectPath === selectedCharacterProjectPath) || null;
}

function tagEditorMarkup(tags) {
  return `
    <div id="browserTagEditor" class="tag-editor hidden">
      <div class="tag-editor-row">
        <input id="browserTagInput" type="text" placeholder="Add tag..." />
        <button id="browserAddTagBtn" type="button">Add</button>
        <button id="browserSaveTagsBtn" type="button" class="primary">Save Tags</button>
        <button id="browserCancelTagsBtn" type="button">Cancel</button>
      </div>
      <div id="browserEditableTagList" class="editable-tag-list">${tags.map(tag => `<button type="button" class="editable-tag" data-tag="${escapeAttr(tag)}" title="Remove tag">${escapeHtml(tag)} ×</button>`).join('')}</div>
      <div class="tag-editor-hint">Click a character tag to filter. In edit mode, click a tag to remove it.</div>
    </div>`;
}

function currentEditorTags() {
  return $$('.editable-tag', $('#browserEditableTagList')).map(btn => normaliseBrowserTag(btn.dataset.tag)).filter(Boolean);
}

function addEditorTag(tag) {
  const wrap = $('#browserEditableTagList');
  if (!wrap) return;
  tag = normaliseBrowserTag(tag);
  if (!tag) return;
  const exists = currentEditorTags().some(t => t.toLowerCase() === tag.toLowerCase());
  if (exists) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'editable-tag';
  btn.dataset.tag = tag;
  btn.title = 'Remove tag';
  btn.textContent = `${tag} ×`;
  btn.addEventListener('click', () => btn.remove());
  wrap.appendChild(btn);
}

function wireTagEditor() {
  $('#browserEditTagsBtn')?.addEventListener('click', () => $('#browserTagEditor')?.classList.toggle('hidden'));
  $('#browserCancelTagsBtn')?.addEventListener('click', () => renderSelectedCharacterTags(getSelectedBrowserCard()));
  $('#browserAddTagBtn')?.addEventListener('click', () => {
    const input = $('#browserTagInput');
    if (!input) return;
    addEditorTag(input.value);
    input.value = '';
    input.focus();
  });
  $('#browserTagInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addEditorTag(e.currentTarget.value.replace(/,$/, ''));
      e.currentTarget.value = '';
    }
  });
  $$('.editable-tag', $('#browserEditableTagList')).forEach(btn => btn.addEventListener('click', () => btn.remove()));
  $('#browserSaveTagsBtn')?.addEventListener('click', saveSelectedCharacterTags);
}

async function saveSelectedCharacterTags() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  const tags = currentEditorTags();
  setBusy('SAVING CHARACTER TAGS…');
  try {
    const res = await window.pywebview.api.update_character_project_tags(selectedCharacterProjectPath, tags);
    if (!res.ok) throw new Error(res.error || 'Could not update tags.');
    const card = getSelectedBrowserCard();
    if (card) card.tags = res.tags || tags;
    const output = $('#outputText');
    if (output && res.output && output.value) output.value = res.output;
    await refreshCharacterBrowser(false);
    setStatus('Character tags updated.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function renderBrowserLetterStrip(cards) {
  const strip = $('#browserLetterStrip');
  if (!strip) return;
  const isAlpha = browserSortMode === 'alpha_asc' || browserSortMode === 'alpha_desc';
  if (!isAlpha || characterBrowserCards.length <= 50 || !cards.length) {
    strip.classList.add('hidden');
    strip.innerHTML = '';
    return;
  }
  const letters = [];
  const seen = new Set();
  cards.forEach(card => {
    const ch = String(card.name || '#').trim().charAt(0).toUpperCase();
    const letter = /^[A-Z]$/.test(ch) ? ch : '#';
    if (!seen.has(letter)) { seen.add(letter); letters.push(letter); }
  });
  strip.classList.remove('hidden');
  strip.innerHTML = letters.map(letter => `<button type="button" class="letter-jump" data-letter="${escapeAttr(letter)}">${escapeHtml(letter)}</button>`).join('');
  $$('.letter-jump', strip).forEach(btn => {
    btn.addEventListener('click', () => {
      const target = $(`.character-card-tile[data-letter="${btn.dataset.letter}"]`, $('#characterGrid'));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function renderCharacterBrowser() {
  const grid = $('#characterGrid');
  if (!grid) return;
  renderBrowserFolderControls();
  renderBrowserFilterPanel();
  const visibleCards = getVisibleBrowserCards();
  renderBrowserLetterStrip(visibleCards);
  const countEl = $('#browserResultCount');
  const scopedTotal = browserScopeCards().length;
  if (countEl) countEl.textContent = `${visibleCards.length} / ${scopedTotal} in scope (${characterBrowserCards.length} total)`;
  if (!characterBrowserCards.length) {
    grid.innerHTML = '<div class="empty">No saved characters yet. Generate a card first.</div>';
    return;
  }
  if (!visibleCards.length) {
    grid.innerHTML = '<div class="empty">No characters match the current search/filter.</div>';
    return;
  }
  updateBrowserMultiActionState();
  grid.innerHTML = visibleCards.map(card => {
    const name = card.name || 'Unnamed';
    const ch = String(name).trim().charAt(0).toUpperCase();
    const letter = /^[A-Z]$/.test(ch) ? ch : '#';
    const multiSelected = browserSelectedProjects.has(card.projectPath);
    return `
    <div class="character-card-tile ${card.projectPath === selectedCharacterProjectPath ? 'selected' : ''} ${multiSelected ? 'multi-selected' : ''}" data-project="${escapeAttr(card.projectPath)}" data-letter="${escapeAttr(letter)}">
      <label class="character-multi-check"><input type="checkbox" class="browser-card-checkbox" data-project="${escapeAttr(card.projectPath)}" ${multiSelected ? 'checked' : ''} /> Select</label>
      <div class="character-thumb">${card.thumbnail ? `<img src="${card.thumbnail}" alt="${escapeAttr(name)}" />` : '<div class="no-thumb">No Image</div>'}</div>
      <div class="character-tile-name">${escapeHtml(name)}</div>
      <div class="character-tile-summary">${escapeHtml(card.browserDescription || card.outputPreview || '')}</div>
      <div class="character-tile-tags">${cardEffectiveTags(card).slice(0, 5).map(t => `<button type="button" class="character-tag-chip ${isMergedBrowserTag(t) ? 'merged-display' : ''}" data-tag="${escapeAttr(t)}">${escapeHtml(t)}</button>`).join('')}</div>
      <div class="character-tile-folder">${escapeHtml(browserFolderPathLabel(card.virtualFolderId || ''))}</div>
      <div class="character-tile-date">${escapeHtml(card.updated || '')}</div>
    </div>
  `}).join('');
  $$('.browser-card-checkbox', grid).forEach(box => {
    box.addEventListener('click', (e) => {
      e.stopPropagation();
      const path = box.dataset.project;
      if (!path) return;
      if (box.checked) browserSelectedProjects.add(path);
      else browserSelectedProjects.delete(path);
      renderCharacterBrowser();
    });
  });
  $$('.character-card-tile', grid).forEach(tile => {
    tile.addEventListener('click', () => selectCharacterBrowserCard(tile.dataset.project));
    tile.addEventListener('dblclick', () => { selectCharacterBrowserCard(tile.dataset.project); loadSelectedCharacterWorkspace(); });
    tile.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      selectCharacterBrowserCard(tile.dataset.project);
      setStatus('Selected. Use Export PNG / Export JSON / Emotion ZIP buttons at the top.', 'ok');
    });
  });
  $$('.character-tag-chip', grid).forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      cycleBrowserTagFilter(chip.dataset.tag, true);
    });
  });
}

function renderSelectedCharacterTags(card) {
  const wrap = $('#browserSelectedTags');
  if (!wrap) return;
  const tags = cardTags(card);
  const chips = tags.length
    ? tags.map(tag => {
        const effective = effectiveBrowserTag(tag);
        const merged = browserTagKey(effective) !== browserTagKey(tag);
        const realChip = `<button type="button" class="selected-tag clickable real-tag" data-tag="${escapeAttr(effective)}" title="Filter by ${escapeAttr(effective)}">${escapeHtml(tag)}</button>`;
        const mergeChip = merged ? `<button type="button" class="selected-tag clickable merged-display" data-tag="${escapeAttr(effective)}" title="Merged display tag. Filter by ${escapeAttr(effective)}">→ ${escapeHtml(effective)}</button>` : '';
        return `<span class="selected-tag-pair">${realChip}${mergeChip}</span>`;
      }).join('')
    : '<div class="empty small">No tags saved for this character.</div>';
  wrap.innerHTML = `
    <div class="selected-tag-row">${chips}</div>
    <div class="tag-editor-actions"><button id="browserEditTagsBtn" type="button">Edit Tags</button></div>
    ${tagEditorMarkup(tags)}
  `;
  $$('.selected-tag.clickable', wrap).forEach(btn => {
    btn.addEventListener('click', () => cycleBrowserTagFilter(btn.dataset.tag, true));
  });
  wireTagEditor();
}

function selectCharacterBrowserCard(projectPath) {
  selectedCharacterProjectPath = projectPath || '';
  const card = characterBrowserCards.find(c => c.projectPath === selectedCharacterProjectPath);
  $$('.character-card-tile').forEach(el => el.classList.toggle('selected', el.dataset.project === selectedCharacterProjectPath));
  $('#selectedCharacterInfo').textContent = card ? `${card.name} — ${browserFolderPathLabel(card.virtualFolderId || '')} — ${card.folder}` : 'Select a character card.';
  $('#browserPreview').value = card ? (card.browserDescription || card.outputPreview || '') : '';
  renderSelectedCharacterTags(card);
}

async function loadSelectedCharacterWorkspace() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  setBusy('LOADING CHARACTER WORKSPACE…');
  try {
    const res = await window.pywebview.api.load_character_project(selectedCharacterProjectPath);
    if (!res.ok) throw new Error(res.error || 'Could not load character project.');
    applyLoadedState(res);
    updateAvailability();
    setStatus(res.message || 'Character workspace loaded.', 'ok');
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    $('[data-tab="concept"]').classList.add('active');
    $('#concept').classList.add('active');
    switchSubTab('concept', 'concept-main');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function exportSelectedCharacter(format) {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  setBusy('EXPORTING SELECTED CHARACTER…');
  try {
    const res = await window.pywebview.api.export_character_from_project(selectedCharacterProjectPath, format);
    if (!res.ok) throw new Error(res.error || 'Export failed.');
    setStatus(`Exported selected character to: ${res.path}`, 'ok');
    refreshCharacterBrowser(false);
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function zipSelectedCharacterEmotions() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  setBusy('CREATING SELECTED CHARACTER EMOTION ZIP…');
  try {
    const res = await window.pywebview.api.create_emotion_zip_for_project(selectedCharacterProjectPath);
    if (!res.ok) throw new Error(res.error || 'Could not create emotion zip.');
    setStatus(`Created emotion ZIP: ${res.path}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}


async function scanFrontPorchFolder() {
  settings = collectSettings();
  setBusy('SCANNING FRONT PORCH FOLDER…');
  try {
    await window.pywebview.api.save_settings(settings);
    const res = await window.pywebview.api.scan_front_porch_folder(settings);
    if (!res.ok) throw new Error(res.error || 'Could not find Front Porch database.');
    setStatus(`Front Porch found: ${res.databaseName} — Characters folder: ${res.charactersDir}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function exportSelectedCharacterToFrontPorch() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  settings = collectSettings();
  if (!settings.frontPorchDataFolder) {
    setStatus('Set Front Porch Data Folder in AI Settings first. Use the folder shown in Front Porch → Settings.', 'error');
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    $('[data-tab="settings"]').classList.add('active');
    $('#settings').classList.add('active');
    return;
  }
  const ok = confirm('Export this saved character directly into Front Porch AI?\n\nThis will write to the Front Porch SQLite database and copy the character card/emotion images into KoboldManager/Characters. A timestamped database backup will be created first. Close Front Porch before exporting if possible.');
  if (!ok) return;
  setBusy('EXPORTING TO FRONT PORCH AI…');
  try {
    await window.pywebview.api.save_settings(settings);
    const res = await window.pywebview.api.export_front_porch_from_project(selectedCharacterProjectPath);
    if (!res.ok) throw new Error(res.error || 'Front Porch export failed.');
    setStatus(`Exported to Front Porch AI: ${res.name} — DB: ${res.database} — emotions: ${res.emotionImages}. Backup: ${res.backup}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function analyzeSelectedImageToBuilders() {
  const img = ($('#cardImagePath')?.value || settings?.cardImagePath || getVisionImagePath() || '').trim();
  if (!img) { setStatus('Select/import a card image first.', 'error'); return; }
  setVisionImagePath(img);
  await analyzeVisionImage();
  if (($('#visionDescription')?.value || '').trim()) {
    await transferConceptToBuilders();
  }
}

async function generateCard() {
  if (!handleUnbuiltBuilderWarning()) return;
  setStatus('Starting generation…', '');
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="output"]').classList.add('active');
  $('#output').classList.add('active');
  switchSubTab('output', 'output-fulltext');
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    setBusy('');
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  const conceptForModel = buildConceptForModel();
  try {
    let qaAnswers = '';
    if (template?.qa?.enabled) {
      setBusy('PRE-GENERATION Q&A — interviewing the character(s)…');
      setStatus('Running Q&A interview pass before card generation…', '');
      const qaRes = await window.pywebview.api.generate_qa_context(conceptForModel, template, settings);
      if (!qaRes.ok) throw new Error(qaRes.error || 'Q&A generation failed.');
      qaAnswers = qaRes.qaAnswers || '';
      lastQnaAnswers = qaAnswers;
      const qaBox = $('#qaAnswersText');
      if (qaBox) qaBox.value = qaAnswers || 'Q&A was enabled but returned no answers.';
      if (qaRes.backupInfo?.used) {
        showBackupTriggered(qaRes.backupInfo, 'qa_interview');
      } else {
        setStatus('Q&A interview complete. Now generating the character card…', 'ok');
      }
    } else {
      lastQnaAnswers = '';
      const qaBox = $('#qaAnswersText');
      if (qaBox) qaBox.value = 'Q&A was disabled for this generation.';
    }
    setBusy('CHARACTER GENERATION — writing the final card…');
    const res = await window.pywebview.api.generate_with_qa_answers(conceptForModel, template, settings, qaAnswers);
    if (!res.ok) throw new Error(res.error || 'Generation failed.');
    $('#outputText').value = res.output;
    currentBrowserDescription = '';
    lastQnaAnswers = res.qaAnswers || qaAnswers || '';
    const qaBox = $('#qaAnswersText');
    if (qaBox) qaBox.value = lastQnaAnswers || 'Q&A was disabled or returned no answers for this generation.';
    updateAvailability();
    const backupMsg = describeBackupInfo(res.backupInfo, 'character_generation');
    if (res.backupInfo?.used) {
      setBusy('BACKUP TEXT MODEL TRIGGERED — ' + backupMsg);
    }
    if (res.repair?.repaired) {
      const stillMissing = res.validation?.missing?.length || 0;
      const baseMsg = stillMissing ? `Generation repaired missing content, but ${stillMissing} item(s) may still need manual review.` : 'Generation complete. Missing fields were detected and automatically filled by a repair pass.';
      setStatus((backupMsg ? backupMsg + ' ' : '') + baseMsg + ' Autosaving workspace…', stillMissing ? 'error' : 'ok');
      await saveCurrentWorkspace('silent');
    } else {
      setStatus((backupMsg ? backupMsg + ' ' : '') + 'Generation complete. Structure check passed. Autosaving workspace…', 'ok');
      await saveCurrentWorkspace('silent');
    }
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function reviseCard() {
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  setBusy('REVISING CHARACTER CARD — waiting for AI response…');
  setStatus('Sending follow-up revision to the model…', '');
  try {
    const res = await window.pywebview.api.revise_card(
      $('#outputText').value,
      $('#followupText').value,
      buildConceptForModel(),
      template,
      settings
    );
    if (!res.ok) throw new Error(res.error || 'Revision failed.');
    $('#outputText').value = res.output;
    currentBrowserDescription = '';
    updateAvailability();
    $('#followupText').value = '';
    const backupMsg = describeBackupInfo(res.backupInfo, 'followup_revision');
    if (res.backupInfo?.used) {
      setBusy('BACKUP TEXT MODEL TRIGGERED — ' + backupMsg);
    }
    setStatus((backupMsg ? backupMsg + ' ' : '') + 'Revision complete. Autosaving workspace…', 'ok');
    await saveCurrentWorkspace('silent');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function selectCardImage() {
  if (isBusy) return;
  setBusy('SELECTING CARD IMAGE…');
  try {
    const res = await window.pywebview.api.pick_image_file('card');
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Card image selection failed.');
      return;
    }
    $('#cardImagePath').value = res.path;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    if (hasOutput()) await saveCurrentWorkspace('silent');
    setStatus('Selected card image: ' + res.path + (hasOutput() ? ' and updated the saved workspace.' : ''), 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function importCardImageFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  setBusy('IMPORTING CARD IMAGE…');
  try {
    const dataUrl = await fileToDataUrl(file);
    const res = await window.pywebview.api.save_uploaded_image(file.name, dataUrl, 'card');
    if (!res.ok) throw new Error(res.error || 'Card image import failed.');
    $('#cardImagePath').value = res.path;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    if (hasOutput()) await saveCurrentWorkspace('silent');
    setStatus('Selected card image: ' + res.path + (hasOutput() ? ' and updated the saved workspace.' : ''), 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function handleCardImageFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importCardImageFiles([file]);
}

async function generateSdImages() {
  settings = collectSettings();
  await window.pywebview.api.save_settings(settings);
  if (!hasStableDiffusionPrompt()) { setStatus('No Stable Diffusion prompt found. Add a Positive Prompt line or raw comma-separated tags under Stable Diffusion Prompt.', 'error'); return; }
  setBusy('GENERATING 4 SD IMAGES — SD Forge / Automatic1111 is working…');
  setStatus('Generating 4 images in SD Forge / Automatic1111 at 1024×1024…', '');
  try {
    const res = await window.pywebview.api.generate_sd_images($('#outputText').value, settings);
    if (!res.ok) throw new Error(res.error || 'Image generation failed.');
    renderGeneratedImages(res.images || []);
    setStatus('Generated 4 image candidates. Select the one you like, delete rejects, or regenerate.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function renderGeneratedImages(images) {
  const holder = $('#generatedImages');
  holder.innerHTML = '';
  if (!images.length) return;
  images.forEach((img, index) => {
    const card = document.createElement('div');
    card.className = 'generated-image-card';
    card.innerHTML = `
      <img src="${img.dataUrl}" alt="Generated image ${index + 1}" />
      <div class="generated-image-actions">
        <button type="button" class="select-generated">Use This</button>
        <button type="button" class="delete-generated danger-ghost">Delete</button>
      </div>
      <small>${escapeAttr(img.path)}</small>
    `;
    $('.select-generated', card).addEventListener('click', async () => {
      $('#cardImagePath').value = img.path;
      settings = collectSettings();
      await window.pywebview.api.save_settings(settings);
      if (hasOutput()) await saveCurrentWorkspace('silent');
      setStatus('Selected generated image for Character Card V2 PNG export' + (hasOutput() ? ' and updated the saved workspace.' : '.'), 'ok');
    });
    $('.delete-generated', card).addEventListener('click', async () => {
      const res = await window.pywebview.api.delete_generated_image(img.path);
      if (!res.ok) {
        setStatus(res.error || 'Could not delete image.', 'error');
        return;
      }
      card.remove();
      if ($('#cardImagePath').value === img.path) {
        $('#cardImagePath').value = '';
        settings = collectSettings();
        await window.pywebview.api.save_settings(settings);
      }
      setStatus('Deleted generated image.', 'ok');
    });
    holder.appendChild(card);
  });
}


function renderEmotionImageResults(images, replace=true) {
  const holder = $('#emotionImages');
  if (replace) {
    emotionImageState = images.map(img => ({...img}));
  }
  holder.innerHTML = '';
  if (!emotionImageState.length) return;
  emotionImageState.forEach((img, index) => {
    const card = document.createElement('div');
    card.className = 'generated-image-card emotion-image-card';
    card.dataset.emotion = img.emotion;
    card.innerHTML = `
      <div class="emotion-image-head">
        <strong>${escapeAttr(img.emotion)}</strong>
        <button class="regen-emotion-btn" type="button" title="Regenerate this one image using the prompt below">↻ Regenerate</button>
      </div>
      <img src="${img.dataUrl}" alt="${escapeAttr(img.emotion)} emotion image" />
      <label class="tiny-label">Prompt</label>
      <textarea class="emotion-prompt-editor" rows="5">${escapeText(img.prompt || '')}</textarea>
      <label class="tiny-label">Negative Prompt</label>
      <textarea class="emotion-negative-editor" rows="2">${escapeText(img.negativePrompt || '')}</textarea>
      <small>${escapeAttr(img.path)}</small>
    `;
    $('.emotion-prompt-editor', card).addEventListener('input', (ev) => { emotionImageState[index].prompt = ev.target.value; });
    $('.emotion-negative-editor', card).addEventListener('input', (ev) => { emotionImageState[index].negativePrompt = ev.target.value; });
    $('.regen-emotion-btn', card).addEventListener('click', async () => {
      if (isBusy) return;
      await regenerateEmotionImage(index);
    });
    holder.appendChild(card);
  });
}

async function regenerateEmotionImage(index) {
  const img = emotionImageState[index];
  if (!img) return;
  settings = collectSettings();
  await window.pywebview.api.save_settings(settings);
  setBusy(`REGENERATING ${String(img.emotion).toUpperCase()} EMOTION IMAGE…`);
  setStatus(`Regenerating ${img.emotion}.png using the edited prompt…`, '');
  try {
    const res = await window.pywebview.api.regenerate_emotion_image(
      $('#outputText').value,
      img.emotion,
      img.prompt,
      img.negativePrompt || '',
      settings
    );
    if (!res.ok) throw new Error(res.error || 'Emotion image regeneration failed.');
    emotionImageState[index] = {...res.image};
    renderEmotionImageResults([], false);
    setStatus(`Regenerated ${img.emotion}.png`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function generateEmotionImages() {
  settings = collectSettings();
  await window.pywebview.api.save_settings(settings);
  if (!hasOutput()) { setStatus('Generate or load a card first.', 'error'); return; }
  setBusy('GENERATING EMOTION IMAGES — SD Forge / Automatic1111 is working…');
  setStatus('Generating emotion images for the selected Front Porch emotions…', '');
  try {
    const res = await window.pywebview.api.generate_emotion_images($('#outputText').value, settings.emotionImageEmotions, settings);
    if (!res.ok) throw new Error(res.error || 'Emotion image generation failed.');
    renderEmotionImageResults(res.images || []);
    setStatus(`Generated ${res.images?.length || 0} emotion image(s) in ${res.folder}. Autosaving workspace…`, 'ok');
    await saveCurrentWorkspace('silent');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function createEmotionZip() {
  if (isBusy) return;
  if (!hasOutput()) { setStatus('Generate or load a card first.', 'error'); return; }
  setBusy('CREATING FRONT PORCH EMOTION ZIP…');
  setStatus('Creating import-ready emotion image zip…', '');
  try {
    const res = await window.pywebview.api.create_emotion_zip($('#outputText').value);
    if (!res.ok) throw new Error(res.error || 'Could not create emotion image zip.');
    setStatus(`Created Front Porch emotion ZIP with ${res.count} image(s): ${res.path}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}


async function loadSavedCardOrProject() {
  if (isBusy) return;
  setBusy('LOADING SAVED CARD / PROJECT…');
  setStatus('Loading saved character card or project…', '');
  try {
    const res = await window.pywebview.api.pick_saved_file();
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Load failed.');
      return;
    }
    applyLoadedState(res);
    updateAvailability();
    setStatus(res.message || 'Loaded saved card/project.', 'ok');
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    $('[data-tab="output"]').classList.add('active');
    $('#output').classList.add('active');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function importSavedFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  setBusy('LOADING SAVED CARD / PROJECT…');
  setStatus('Loading saved character card or project…', '');
  try {
    const dataUrl = await fileToDataUrl(file);
    const res = await window.pywebview.api.load_import_upload(file.name, dataUrl);
    if (!res.ok) throw new Error(res.error || 'Load failed.');
    applyLoadedState(res);
    updateAvailability();
    setStatus(res.message || 'Loaded saved card/project.', 'ok');
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    $('[data-tab="output"]').classList.add('active');
    $('#output').classList.add('active');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}


function confirmLoadCardToMainConceptWarning() {
  const currentConcept = ($('#conceptText')?.value || '').trim();
  const warning = [
    'Loading a card to Main Concept will avoid AI entirely.',
    'It will read the card metadata/text and place it directly into Main Concept without filling Builder fields.',
    '',
    currentConcept ? 'Your current Main Concept is not empty and will be erased/replaced.' : 'Your Main Concept is currently empty.',
    '',
    'Continue?'
  ].join('\n');
  return window.confirm(warning);
}

async function applyCardToMainConceptResult(res, sourceLabel) {
  if (!res.ok) throw new Error(res.error || 'Load card to Main Concept failed.');
  if ($('#conceptText')) $('#conceptText').value = res.mainConcept || '';
  if (res.imagePath && $('#cardImagePath')) {
    $('#cardImagePath').value = res.imagePath;
    settings.cardImagePath = res.imagePath;
    await window.pywebview.api.save_settings(settings);
  }
  const imageMsg = res.embeddedImagePaths?.length ? ` Extracted ${res.embeddedImagePaths.length} embedded image(s).` : '';
  setStatus(`Loaded ${sourceLabel || 'card'} directly into Main Concept without AI.${res.loadedType ? ' Source: ' + res.loadedType + '.' : ''}${imageMsg}`, 'ok');
  switchSubTab('concept', 'concept-main');
}

async function loadCardToMainConceptNative() {
  if (isBusy) return;
  if (!confirmLoadCardToMainConceptWarning()) return;
  settings = collectSettings();
  setBusy('LOAD CARD TO MAIN CONCEPT — choose V2/V3 card…');
  setStatus('Choose an existing character card to load directly into Main Concept…', '');
  try {
    const res = await window.pywebview.api.pick_card_to_main_concept(settings);
    if (res.cancelled) {
      setStatus('Load card to Main Concept cancelled.', '');
      return;
    }
    await applyCardToMainConceptResult(res, res.sourcePath || 'selected card');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
  }
}

async function importCardToMainConceptFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  if (isBusy) return;
  if (!confirmLoadCardToMainConceptWarning()) return;
  settings = collectSettings();
  setBusy('LOAD CARD TO MAIN CONCEPT — reading V2/V3 card…');
  setStatus('Loading existing character card directly into Main Concept…', '');
  try {
    if (file.size && file.size > 8 * 1024 * 1024) {
      setStatus('Large V3 card detected. Loading may take a moment; the Load Card to Main Concept button is safer for very large embedded-image cards.', '');
    }
    const dataUrl = await fileToDataUrl(file);
    const res = await window.pywebview.api.card_upload_to_main_concept(file.name, dataUrl, settings);
    await applyCardToMainConceptResult(res, file.name);
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
  }
}

function confirmLoadCardToBuildersWarning() {
  const currentConcept = ($('#conceptText')?.value || '').trim();
  const warning = [
    'Loading a card into the Builders will replace the current Main Concept with any imported card information that does not map cleanly to Builder fields, such as First Message, Example Dialogues, Lorebook, Tags, State Tracking, or Stable Diffusion Prompt.',
    '',
    currentConcept ? 'Your current Main Concept is not empty and will be erased/replaced.' : 'Your Main Concept is currently empty.',
    '',
    'Continue?'
  ].join('\n');
  return window.confirm(warning);
}

async function applyCardToBuildersResult(res, sourceLabel) {
  if (!res.ok) throw new Error(res.error || 'Load card to builders failed.');
  const applied = applyBuilderTransferResult(res);
  let count = applied.count;
  if ($('#conceptText')) $('#conceptText').value = res.mainConcept || '';
  if (res.imagePath && $('#cardImagePath')) {
    $('#cardImagePath').value = res.imagePath;
    settings.cardImagePath = res.imagePath;
    await window.pywebview.api.save_settings(settings);
  }
  updateBuilderConditionalOptions();
  updateCustomConditionalOptions();
  generateBuilderDescription();
  generatePersonalityBuilderDescription();
  generateSceneBuilderDescription();
  const imageMsg = res.embeddedImagePaths?.length ? ` Extracted ${res.embeddedImagePaths.length} embedded image(s).` : '';
  const conceptMsg = res.mainConcept ? ' Unmatched card info was moved into Main Concept.' : ' No unmatched card info was found for Main Concept.';
  const multiMsg = (Array.isArray(res.characters) && res.characters.length >= 2) ? ` Detected ${res.characters.length} main characters and switched to Multi-Character Single Card. Side characters remain in Main Concept/lore context.` : '';
  setStatus(`Loaded ${sourceLabel || 'card'} into builders: filled ${count} field(s). Builder guidance now takes priority during generation.${multiMsg}${res.loadedType ? ' Source: ' + res.loadedType + '.' : ''}${imageMsg}${conceptMsg}${res.notes ? ' ' + res.notes : ''}`, 'ok');
  switchSubTab('concept', 'concept-builder');
}

async function loadCardToBuildersNative() {
  if (isBusy) return;
  if (!confirmLoadCardToBuildersWarning()) return;
  settings = collectSettings();
  const missing = validateTextApiSettings(settings);
  if (missing) {
    setStatus(missing, 'error');
    switchToSettingsTab();
    return;
  }
  setBusy('LOAD CARD TO BUILDERS — choose V2/V3 card and filling builder fields…');
  setStatus('Choose an existing character card to load into the builders…', '');
  try {
    const catalog = collectCompactBuilderFieldCatalog();
    const res = await window.pywebview.api.pick_card_to_builders(catalog, settings);
    if (res.cancelled) {
      setStatus('Load card to builders cancelled.', '');
      return;
    }
    await applyCardToBuildersResult(res, res.sourcePath || 'selected card');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
  }
}

async function importBuilderCardFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  if (isBusy) return;
  if (!confirmLoadCardToBuildersWarning()) return;
  settings = collectSettings();
  const missing = validateTextApiSettings(settings);
  if (missing) {
    setStatus(missing, 'error');
    switchToSettingsTab();
    return;
  }
  setBusy('LOAD CARD TO BUILDERS — reading V2/V3 card and filling builder fields…');
  setStatus('Loading existing character card into the builders…', '');
  try {
    // Embedded-image-heavy V3 cards can be very large; clicking the Load Card
    // button uses the native picker to avoid the JS bridge size overhead. Drag
    // and drop remains supported, but warn for unusually large files.
    if (file.size && file.size > 8 * 1024 * 1024) {
      setStatus('Large V3 card detected. Loading may take a moment; using the Load Card button is safer for very large embedded-image cards.', '');
    }
    const dataUrl = await fileToDataUrl(file);
    const catalog = collectCompactBuilderFieldCatalog();
    const res = await window.pywebview.api.card_upload_to_builders(file.name, dataUrl, catalog, settings);
    await applyCardToBuildersResult(res, file.name);
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
  }
}

async function handleBuilderCardFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importBuilderCardFiles([file]);
}

async function handleSavedFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importSavedFiles([file]);
}


async function exportCard() {
  if (!hasOutput()) return;
  settings = collectSettings();
  setBusy('EXPORTING CHARACTER CARD — writing files…');
  try {
    await window.pywebview.api.save_settings(settings);
    const res = await window.pywebview.api.export_card(
      $('#outputText').value,
      settings.frontend,
      settings.exportFormat,
      settings.cardImagePath,
      buildConceptForModel(),
      template,
      settings
    );
    if (res.ok) { setStatus('Exported to: ' + res.path + (res.folder ? ' — folder: ' + res.folder : '') + (res.projectPath ? ' — project: ' + res.projectPath : ''), 'ok'); await saveCurrentWorkspace('silent'); }
    else setStatus(res.error || 'Export failed.', 'error');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function escapeAttr(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
}

function escapeText(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

window.addEventListener('pywebviewready', init);
