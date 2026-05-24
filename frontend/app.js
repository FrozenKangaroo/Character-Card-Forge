let frontPorchExportTargetModalResolve = null;
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
let currentCardRating = "";
let currentCardRatingReasoning = "";
let currentCardRatingDetails = [];
let currentCardRatingSourceHash = "";
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
let browserCurrentFolderId = "";
let browserFolderScope = "global";
let outputEditorSaveTimer = null;
let browserShowSubfolders = false;
let sdModelCatalog = [];
let sdCurrentServerModel = "";
let recentModels = [];
let appVersion = "unknown";
let modelTokenFetchTimer = null;
let conceptImportFile = null;
let conceptImportUrlValue = "";
let quickImportFile = null;
let quickImportUrlValue = "";
let cardImagePreviewToken = 0;
let currentLoadedType = "";
let characterOutputTabs = [];
let activeOutputTabIndex = 0;
let updateCheckTimer = null;
let updateCheckInProgress = false;
let lastShownUpdateVersion = '';
let updateReleaseUrl = '';
let updateRepositoryUrl = 'https://github.com/FrozenKangaroo/Character-Card-Forge/';
let ratingImprovementProjectPath = '';
let ratingImproveFieldDiffs = [];
let ratingImproveLostDetails = [];
let ratingImproveLostSummary = '';
let manualGuidePageIndex = 0;
let manualGuideState = {};
let conceptWorkspaceTabs = [];
let activeConceptTabIndex = 0;
let manualGuideTabs = [];
let activeManualGuideTabIndex = 0;
let workspaceTabCloseInProgress = false;
let workspaceTabRenderSuspendAutoScroll = false;
let relationshipMatrixText = '';


const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const uid = () => Math.random().toString(36).slice(2, 10);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

const NEW_USER_TIPS = [
  'Start with Main Concept, then use Transfer to Builders when you want the structured fields filled for you.',
  'Use Lite or Compact Lite when your text model has a small context window. It keeps the card focused instead of trying to write a whole visual novel.',
  'Concept Attachments are best for scripts, transcripts, subtitles, and notes you want the AI to learn from before generating.',
  'Character Browser uses SQLite caching, so refreshing should stay quick unless saved card files actually changed.',
  'Virtual folders only organize the browser. They do not move your physical saved card folders on disk.',
  'Use AI Browser Analysis when the card description is only physical appearance and you want a useful scenario summary, quality rating, and NSFW-tag detection.',
  'Tag filters are faceted: active filters shrink the tag list to tags that still exist in the current result set.',
  'Merge Tags is display-only unless you choose a rename action. It is safe for cleaning up noisy tag lists.',
  'Fetch SD Models in Settings before image generation if you switch between anime, Pony, or realistic checkpoints.',
  'The Output / Editor tab autosaves after edits, so the browser cache and latest card stay in sync.',
];

function showRandomTip(forceDifferent = false) {
  const tipText = $('#tipText');
  if (!tipText || !NEW_USER_TIPS.length) return;
  const current = tipText.textContent || '';
  let next = NEW_USER_TIPS[Math.floor(Math.random() * NEW_USER_TIPS.length)];
  if (forceDifferent && NEW_USER_TIPS.length > 1) {
    let guard = 0;
    while (next === current && guard++ < 8) next = NEW_USER_TIPS[Math.floor(Math.random() * NEW_USER_TIPS.length)];
  }
  tipText.textContent = next;
}

function updateAppVersionDisplay() {
  const el = $('#appVersionText');
  if (el) { const shown = (!appVersion || appVersion === 'unknown') ? 'unknown' : appVersion; el.textContent = `Version ${shown}`; }
}

function closeUpdateAvailableModal() {
  const modal = $('#updateAvailableModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function isUpdateAvailableModalOpen() {
  const modal = $('#updateAvailableModal');
  return !!(modal && !modal.classList.contains('hidden'));
}

function describeUpdateKind(info, current, latest) {
  const kind = String(info?.updateKind || '').trim();
  const currentIsPrerelease = !!info?.currentIsPrerelease || /-/.test(current);
  if (kind === 'stable_for_beta' || (currentIsPrerelease && latest && !/-/.test(latest))) {
    return `A stable Character Card Forge ${latest} release is available on GitHub. You are currently running the beta build ${current}.`;
  }
  if (kind === 'prerelease_newer') return `A newer beta Character Card Forge ${latest} build is available on GitHub.`;
  return `Character Card Forge ${latest} is available on GitHub.`;
}

function showUpdateAvailableModal(info) {
  const modal = $('#updateAvailableModal');
  if (!modal || !info) return;
  const current = String(info.currentVersion || appVersion || 'unknown').trim() || 'unknown';
  const latest = String(info.latestVersion || info.latestTag || 'unknown').trim() || 'unknown';
  updateReleaseUrl = String(info.releaseUrl || 'https://github.com/FrozenKangaroo/Character-Card-Forge/releases/latest');
  updateRepositoryUrl = String(info.repositoryUrl || 'https://github.com/FrozenKangaroo/Character-Card-Forge/');
  const summary = $('#updateAvailableSummary');
  if (summary) summary.textContent = describeUpdateKind(info, current, latest);
  const currentEl = $('#updateCurrentVersion');
  if (currentEl) currentEl.textContent = current;
  const latestEl = $('#updateLatestVersion');
  if (latestEl) latestEl.textContent = latest;
  const typeEl = $('#updateKindText');
  if (typeEl) {
    const kind = String(info.updateKind || '').replace(/_/g, ' ');
    typeEl.textContent = kind ? `Update type: ${kind}` : '';
  }
  const preview = $('#updateReleaseNotesPreview');
  if (preview) {
    const body = String(info.bodyPreview || '').trim();
    preview.textContent = body ? body : '';
  }
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  lastShownUpdateVersion = latest;
}

async function openAllowedExternalPage(url, fallbackMessage = 'Open this page') {
  try {
    const res = await window.pywebview.api.open_external_url(url);
    if (res && !res.ok) throw new Error(res.error || 'Could not open page.');
  } catch (err) {
    try { window.open(url, '_blank'); }
    catch (_) { setStatus(`${fallbackMessage}: ${url}`, 'ok'); }
  }
}

async function openUpdateReleasePage() {
  const url = updateReleaseUrl || 'https://github.com/FrozenKangaroo/Character-Card-Forge/releases/latest';
  await openAllowedExternalPage(url, 'Update available');
}

async function openUpdateRepositoryPage() {
  const url = updateRepositoryUrl || 'https://github.com/FrozenKangaroo/Character-Card-Forge/';
  await openAllowedExternalPage(url, 'GitHub page');
}

async function checkForAppUpdates(manual = false) {
  if (updateCheckInProgress) return;
  updateCheckInProgress = true;
  try {
    const res = await window.pywebview.api.check_for_updates();
    if (res?.ok && res.isNewer && res.latestVersion) {
      if (manual || !isUpdateAvailableModalOpen()) showUpdateAvailableModal(res);
    } else if (manual) {
      const latest = res?.latestVersion || res?.latestTag || 'unknown';
      if (res?.ok) setStatus(`No newer release found. Latest GitHub release is ${latest}.`, 'ok');
      else setStatus(res?.error || 'Could not check for updates.', 'error');
    }
  } catch (err) {
    if (manual) setStatus(err.message || String(err), 'error');
    try { await writeClientDebugEvent('update_check_frontend_error', { error: err.message || String(err) }); } catch (_) {}
  } finally {
    updateCheckInProgress = false;
  }
}

function startUpdateChecks() {
  if (updateCheckTimer) clearInterval(updateCheckTimer);
  setTimeout(() => checkForAppUpdates(false), 3500);
  updateCheckTimer = setInterval(() => checkForAppUpdates(false), 60 * 60 * 1000);
}

function setTextareaValue(id, value) {
  const el = $('#' + id);
  if (el) el.value = value || '';
}

function currentOutputTabName() {
  const tab = characterOutputTabs[activeOutputTabIndex];
  return tab?.name || tab?.focusName || 'Character';
}

function isPlaceholderQaText(value) {
  const text = String(value || '').trim();
  if (!text) return true;
  return /^(Q&A was disabled or returned no answers for this generation\.?|No Q&A answers yet\.?|Q&A was skipped\.?|No answers generated\.?)$/i.test(text);
}

function cleanQaAnswersForStorage(value, outputText = '') {
  const text = String(value || '').trim();
  if (!text) return '';
  if (!String(outputText || '').trim() && isPlaceholderQaText(text)) return '';
  return text;
}

function firstNonEmptyString(...values) {
  for (const value of values) {
    const text = String(value ?? '').trim();
    if (text) return text;
  }
  return '';
}

function loadedOutputTextFromTab(tab = {}) {
  if (!tab || typeof tab !== 'object') return '';
  return firstNonEmptyString(
    tab.output,
    tab.fullTextOutput,
    tab.fullText,
    tab.fullTextOutputText,
    tab.outputText,
    tab.cardText,
    tab.cardOutput,
    tab.raw_card,
    tab.rawCard,
    tab.text,
    tab.content
  );
}

function loadedQaTextFromTab(tab = {}) {
  if (!tab || typeof tab !== 'object') return '';
  return firstNonEmptyString(tab.qaAnswers, tab.qnaAnswers, tab.qa, tab.qna, tab.answers, tab.qAndA);
}

function loadedOutputTextFromState(state = {}, fallbackTab = {}) {
  const workspace = (state && typeof state.workspace === 'object') ? state.workspace : {};
  return firstNonEmptyString(
    state.output,
    state.fullTextOutput,
    state.fullText,
    state.outputText,
    state.cardText,
    state.cardOutput,
    state.raw_card,
    state.rawCard,
    workspace.output,
    workspace.fullTextOutput,
    workspace.fullText,
    workspace.outputText,
    workspace.cardText,
    workspace.cardOutput,
    workspace.raw_card,
    workspace.rawCard,
    loadedOutputTextFromTab(fallbackTab)
  );
}

function loadedQaTextFromState(state = {}, fallbackTab = {}) {
  const workspace = (state && typeof state.workspace === 'object') ? state.workspace : {};
  return firstNonEmptyString(
    state.qnaAnswers,
    state.qaAnswers,
    state.qna,
    state.qa,
    workspace.qnaAnswers,
    workspace.qaAnswers,
    workspace.qna,
    workspace.qa,
    loadedQaTextFromTab(fallbackTab)
  );
}

function loadedImageListFromState(state = {}, key, fallbackTab = {}) {
  const workspace = (state && typeof state.workspace === 'object') ? state.workspace : {};
  const direct = state[key];
  if (Array.isArray(direct) && direct.length) return direct;
  const nested = workspace[key];
  if (Array.isArray(nested) && nested.length) return nested;
  const tabList = fallbackTab && typeof fallbackTab === 'object' ? fallbackTab[key] : null;
  if (Array.isArray(tabList) && tabList.length) return tabList;
  return Array.isArray(direct) ? direct : (Array.isArray(nested) ? nested : (Array.isArray(tabList) ? tabList : []));
}

function captureActiveOutputTab() {
  if (!characterOutputTabs.length) return;
  const tab = characterOutputTabs[activeOutputTabIndex];
  if (!tab) return;
  const outputText = $('#outputText')?.value || '';
  const qaText = $('#qaAnswersText')?.value || lastQnaAnswers || '';
  tab.output = outputText;
  tab.qaAnswers = cleanQaAnswersForStorage(qaText, outputText);
  tab.emotionImages = emotionImageState.map(img => ({...img}));
  tab.cardImagePath = $('#cardImagePath')?.value || '';
}

function applyActiveOutputTab() {
  const tab = characterOutputTabs[activeOutputTabIndex] || characterOutputTabs[0];
  if (!tab) return;
  setTextareaValue('outputText', tab.output || '');
  lastQnaAnswers = tab.qaAnswers || '';
  setTextareaValue('qaAnswersText', lastQnaAnswers || 'Q&A was disabled or returned no answers for this generation.');
  emotionImageState = Array.isArray(tab.emotionImages) ? tab.emotionImages.map(img => ({...img})) : [];
  renderEmotionImageResults(emotionImageState);
  renderGeneratedImages(Array.isArray(tab.generatedImages) ? tab.generatedImages : []);
  const cardImage = $('#cardImagePath');
  if (cardImage) cardImage.value = tab.cardImagePath || '';
  if (settings) settings.cardImagePath = tab.cardImagePath || '';
  updateCardImagePreview();
  updateAvailability();
}


function workspaceTabNameForIndex(index) {
  const outputName = characterOutputTabs[index]?.name || characterOutputTabs[index]?.focusName;
  const conceptName = conceptWorkspaceTabs[index]?.name;
  const manualName = manualGuideTabs[index]?.name;
  return cleanOutputTabName(outputName || conceptName || manualName || `Character ${Number(index || 0) + 1}`) || `Character ${Number(index || 0) + 1}`;
}

function canonicalWorkspaceProjectPath(value) {
  let text = String(value || '').trim();
  if (!text) return '';
  try {
    if (/^file:\/\//i.test(text)) text = decodeURIComponent(text.replace(/^file:\/\//i, ''));
  } catch (_) {
    text = text.replace(/^file:\/\//i, '');
  }
  return text.replace(/\\/g, '/').replace(/\/+$/g, '');
}

function workspaceTabProjectPath(index) {
  const outputTab = characterOutputTabs[index] || {};
  const conceptTab = conceptWorkspaceTabs[index] || {};
  const manualTab = manualGuideTabs[index] || {};
  return canonicalWorkspaceProjectPath(
    outputTab.projectPath || outputTab.workspaceProjectPath || outputTab.sourcePath
    || conceptTab.projectPath || conceptTab.workspaceProjectPath
    || manualTab.projectPath || manualTab.workspaceProjectPath
  );
}

function findOpenWorkspaceTabByProjectPath(projectPath) {
  const target = canonicalWorkspaceProjectPath(projectPath);
  if (!target) return -1;
  ensureLinkedWorkspaceTabs();
  return characterOutputTabs.findIndex((_, idx) => workspaceTabProjectPath(idx) === target);
}

function workspaceProjectPathDuplicateCount(projectPath) {
  const target = canonicalWorkspaceProjectPath(projectPath);
  if (!target) return 0;
  ensureLinkedWorkspaceTabs();
  return characterOutputTabs.reduce((count, _, idx) => count + (workspaceTabProjectPath(idx) === target ? 1 : 0), 0);
}

function tabHasSavedWorkspaceIdentity(index) {
  return !!workspaceTabProjectPath(index);
}

function normaliseConceptTab(tab = {}, fallbackName = '') {
  const base = makeBlankConceptTab(fallbackName || tab.name || 'Concept');
  const merged = { ...base, ...(tab || {}) };
  merged.name = cleanOutputTabName(merged.name || fallbackName || 'Concept') || fallbackName || 'Concept';
  merged.concept = String(merged.concept ?? '');
  merged.visionDescription = String(merged.visionDescription ?? '');
  merged.visionImagePath = String(merged.visionImagePath ?? merged.imagePath ?? '');
  merged.conceptAttachments = Array.isArray(merged.conceptAttachments) ? merged.conceptAttachments.map(a => ({...a})) : [];
  merged.builderState = merged.builderState || { mode: 'single', selectedIndex: 0, states: [{}] };
  return merged;
}

function normaliseManualTab(tab = {}, fallbackName = '') {
  const base = makeBlankManualTab(fallbackName || tab.name || 'Manual');
  const merged = { ...base, ...(tab || {}) };
  merged.name = cleanOutputTabName(merged.name || fallbackName || 'Manual') || fallbackName || 'Manual';
  merged.state = JSON.parse(JSON.stringify(merged.state || {}));
  merged.pageIndex = Number(merged.pageIndex || 0);
  return merged;
}

function makeConceptTabFromWorkspaceState(state = {}, tabIndex = 0, fallbackName = '', options = {}) {
  const sourceTabs = (!options.singleProject && Array.isArray(state?.conceptTabs)) ? state.conceptTabs : [];
  const selected = sourceTabs[tabIndex] || sourceTabs[Number(state?.activeConceptTabIndex || 0)] || sourceTabs[0] || {};
  const merged = normaliseConceptTab(selected, fallbackName || selected.name || state.name || `Concept ${tabIndex + 1}`);
  if (!String(merged.concept || '').trim() && typeof state?.concept === 'string') merged.concept = state.concept;
  if (!String(merged.visionDescription || '').trim() && typeof state?.visionDescription === 'string') merged.visionDescription = state.visionDescription;
  if (!String(merged.visionImagePath || '').trim()) merged.visionImagePath = String(state?.visionImagePath || state?.settings?.visionImagePath || '');
  if (!merged.conceptAttachments.length && Array.isArray(state?.conceptAttachments)) merged.conceptAttachments = state.conceptAttachments.map(a => ({...a}));
  if ((!merged.builderState || !Object.keys(merged.builderState || {}).length) && state?.builderState) merged.builderState = state.builderState;
  return merged;
}

function makeManualTabFromWorkspaceState(state = {}, tabIndex = 0, fallbackName = '', options = {}) {
  const sourceTabs = (!options.singleProject && Array.isArray(state?.manualTabs)) ? state.manualTabs : [];
  const selected = sourceTabs[tabIndex] || sourceTabs[Number(state?.activeManualGuideTabIndex || 0)] || sourceTabs[0] || {};
  return normaliseManualTab(selected, fallbackName || selected.name || state.name || `Manual ${tabIndex + 1}`);
}

function bestLoadedCharacterTabForSingleProject(state = {}) {
  const tabs = Array.isArray(state?.characterTabs) ? state.characterTabs.filter(tab => tab && typeof tab === 'object') : [];
  if (!tabs.length) return {};
  const stateOutput = String(state?.output || state?.workspace?.output || '').trim();
  const stateName = cleanOutputTabName(state?.name || extractOutputNameForTab(stateOutput) || '');
  const stateProject = canonicalWorkspaceProjectPath(state?.projectPath || state?.sourcePath || '');
  const matchByProject = tabs.find(tab => canonicalWorkspaceProjectPath(tab.projectPath || tab.workspaceProjectPath || tab.sourcePath || '') === stateProject);
  if (matchByProject) return matchByProject;
  const matchByOutput = stateOutput ? tabs.find(tab => loadedOutputTextFromTab(tab) === stateOutput) : null;
  if (matchByOutput) return matchByOutput;
  const matchByName = stateName ? tabs.find(tab => cleanOutputTabName(tab.name || tab.focusName || extractOutputNameForTab(tab.output || '')) === stateName) : null;
  if (matchByName) return matchByName;
  return tabs.find(tab => loadedOutputTextFromTab(tab)) || tabs[0] || {};
}

function ensureLinkedWorkspaceTabs() {
  const maxLen = Math.max(1, characterOutputTabs.length || 0, conceptWorkspaceTabs.length || 0, manualGuideTabs.length || 0);
  while (characterOutputTabs.length < maxLen) characterOutputTabs.push(makeBlankOutputTab(`Character ${characterOutputTabs.length + 1}`));
  while (conceptWorkspaceTabs.length < maxLen) conceptWorkspaceTabs.push(makeBlankConceptTab(workspaceTabNameForIndex(conceptWorkspaceTabs.length) || `Concept ${conceptWorkspaceTabs.length + 1}`));
  while (manualGuideTabs.length < maxLen) manualGuideTabs.push(makeBlankManualTab(workspaceTabNameForIndex(manualGuideTabs.length) || `Manual ${manualGuideTabs.length + 1}`));
  characterOutputTabs = characterOutputTabs.slice(0, maxLen);
  conceptWorkspaceTabs = conceptWorkspaceTabs.slice(0, maxLen);
  manualGuideTabs = manualGuideTabs.slice(0, maxLen);
  activeOutputTabIndex = Math.max(0, Math.min(maxLen - 1, Number(activeOutputTabIndex || 0)));
  activeConceptTabIndex = Math.max(0, Math.min(maxLen - 1, Number(activeConceptTabIndex || activeOutputTabIndex || 0)));
  activeManualGuideTabIndex = Math.max(0, Math.min(maxLen - 1, Number(activeManualGuideTabIndex || activeOutputTabIndex || 0)));
}

function renderAllWorkspaceTabRails() {
  renderCharacterOutputTabs();
  renderConceptWorkspaceTabs();
  renderManualWorkspaceTabs();
  refreshRelationshipMatrixOpenCharacterList();
}

function switchLinkedWorkspaceTab(index, source = '') {
  ensureLinkedWorkspaceTabs();
  const target = Math.max(0, Math.min(characterOutputTabs.length - 1, Number(index || 0)));
  if (target === activeOutputTabIndex && target === activeConceptTabIndex && target === activeManualGuideTabIndex) return;
  captureActiveOutputTab();
  captureActiveConceptTab();
  captureActiveManualTab();
  activeOutputTabIndex = target;
  activeConceptTabIndex = target;
  activeManualGuideTabIndex = target;
  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  applyActiveConceptTab();
  applyActiveManualTab();
  const name = workspaceTabNameForIndex(target);
  setStatus(`Switched to ${name}.`, '');
}

function addLinkedWorkspaceTab({ outputTab = null, conceptTab = null, manualTab = null, activate = true } = {}) {
  captureActiveOutputTab();
  captureActiveConceptTab();
  captureActiveManualTab();
  const idx = characterOutputTabs.length;
  const output = outputTab ? { ...makeBlankOutputTab(outputTab.name || outputTab.focusName || `Character ${idx + 1}`), ...(outputTab || {}) } : makeBlankOutputTab(`Character ${idx + 1}`);
  output.output = loadedOutputTextFromTab(output);
  const name = cleanOutputTabName(output.name || output.focusName || extractOutputNameForTab(output.output || '') || `Character ${idx + 1}`) || `Character ${idx + 1}`;
  output.name = name;
  output.focusName = output.focusName || name;
  output.projectPath = canonicalWorkspaceProjectPath(output.projectPath || output.workspaceProjectPath || output.sourcePath || '');
  output.workspaceProjectPath = output.projectPath || output.workspaceProjectPath || '';
  output.qaAnswers = loadedQaTextFromTab(output);
  output.qnaAnswers = output.qaAnswers;
  output.emotionImages = Array.isArray(output.emotionImages) ? output.emotionImages : [];
  output.generatedImages = Array.isArray(output.generatedImages) ? output.generatedImages : [];
  output.cardImagePath = output.cardImagePath || output.imagePath || '';
  const normalisedConcept = normaliseConceptTab(conceptTab || {}, name);
  const normalisedManual = normaliseManualTab(manualTab || {}, name);
  if (output.projectPath) {
    normalisedConcept.projectPath = output.projectPath;
    normalisedConcept.workspaceProjectPath = output.projectPath;
    normalisedManual.projectPath = output.projectPath;
    normalisedManual.workspaceProjectPath = output.projectPath;
  }
  characterOutputTabs.push(output);
  conceptWorkspaceTabs.push(normalisedConcept);
  manualGuideTabs.push(normalisedManual);
  ensureLinkedWorkspaceTabs();
  if (activate) {
    activeOutputTabIndex = idx;
    activeConceptTabIndex = idx;
    activeManualGuideTabIndex = idx;
  }
  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  applyActiveConceptTab();
  applyActiveManualTab();
  return idx;
}

function manualGuideStateHasUserContent(value, path = '') {
  // Blank Guided Manual tabs create lots of default state while rendering:
  // { include: true, fields: { Name: "" }, expandedFields: {...}, pageIndex: 0 }
  // The old close test treated the existence of a fields object as real content,
  // which kept sending never-generated tabs through the heavy close/render path.
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return !!value.trim();
  if (typeof value === 'number') {
    // Default slider values are normally 0. Non-zero means the user likely changed it.
    return Number.isFinite(value) && value !== 0;
  }
  if (typeof value === 'boolean') {
    // include/expanded/default flags are UI state, not card content.
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item, idx) => manualGuideStateHasUserContent(item, `${path}[${idx}]`));
  }
  if (typeof value === 'object') {
    return Object.entries(value).some(([key, child]) => {
      const lower = String(key || '').toLowerCase();
      if (['include', 'expanded', 'expandedfields', 'collapsed', 'pageindex', 'currentpage'].includes(lower)) return false;
      if (lower === 'fields' || lower === 'alternates' || lower === 'state' || lower === 'sections') {
        return manualGuideStateHasUserContent(child, `${path}.${key}`);
      }
      return manualGuideStateHasUserContent(child, `${path}.${key}`);
    });
  }
  return false;
}

function linkedWorkspaceTabHasContent(index) {
  const outputTab = characterOutputTabs[index] || {};
  const conceptTab = conceptWorkspaceTabs[index] || {};
  const manualTab = manualGuideTabs[index] || {};
  const outputText = loadedOutputTextFromTab(outputTab);
  const rawQaText = String(outputTab.qaAnswers || outputTab.qnaAnswers || '').trim();
  const qaText = isPlaceholderQaText(rawQaText) ? '' : rawQaText;
  const conceptText = String(conceptTab.concept || '').trim();
  const visionText = String(conceptTab.visionDescription || conceptTab.visionImagePath || '').trim();
  const hasConceptAttachments = Array.isArray(conceptTab.conceptAttachments) && conceptTab.conceptAttachments.length > 0;
  const hasOutputImages = (Array.isArray(outputTab.emotionImages) && outputTab.emotionImages.length > 0)
    || (Array.isArray(outputTab.generatedImages) && outputTab.generatedImages.length > 0)
    || !!String(outputTab.cardImagePath || outputTab.imagePath || '').trim();
  const manualState = manualTab.state && typeof manualTab.state === 'object' ? manualTab.state : {};
  const hasManualContent = manualGuideStateHasUserContent(manualState);
  return !!(outputText || qaText || conceptText || visionText || hasConceptAttachments || hasOutputImages || hasManualContent);
}

function safeCaptureLinkedWorkspaceStateForClose(closingIndex) {
  // Closing a never-generated blank tab used to run the full capture/preview/autosave path.
  // In WebKit/PyWebView that could lock the UI because Manual preview rendering can re-enter
  // while the tab arrays are being spliced. Only capture when there is actual state worth saving.
  const activeIndex = activeOutputTabIndex;
  const closingActive = Number(closingIndex) === Number(activeIndex);
  const activeHasContent = linkedWorkspaceTabHasContent(activeIndex);
  if (closingActive && !activeHasContent) return;
  try { captureActiveOutputTab(); } catch (err) { console.warn('captureActiveOutputTab during close failed', err); }
  try { captureActiveConceptTab(); } catch (err) { console.warn('captureActiveConceptTab during close failed', err); }
  try { captureActiveManualTab({ lightweight: true }); } catch (err) { console.warn('captureActiveManualTab during close failed', err); }
}

function resetLinkedWorkspaceTabsToBlank() {
  characterOutputTabs = [makeBlankOutputTab('Character')];
  conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
  manualGuideTabs = [makeBlankManualTab('Manual 1')];
  activeOutputTabIndex = 0;
  activeConceptTabIndex = 0;
  activeManualGuideTabIndex = 0;
}

function closeLinkedWorkspaceTab(index) {
  if (workspaceTabCloseInProgress) return;
  ensureLinkedWorkspaceTabs();
  workspaceTabCloseInProgress = true;
  workspaceTabRenderSuspendAutoScroll = true;
  // Do not splice/render tab DOM during the close button click event. Some WebKit/PyWebView
  // builds can lock up if the clicked tab is removed while the event is still bubbling through
  // the old DOM tree. Queue the real close to the next tick instead.
  const tabCount = Math.max(1, characterOutputTabs.length || 0);
  if (tabCount <= 1) {
    setTimeout(() => performLastLinkedWorkspaceTabReset(index), 0);
    return;
  }
  setTimeout(() => performLinkedWorkspaceTabClose(index), 0);
}

function performLastLinkedWorkspaceTabReset(index) {
  try {
    ensureLinkedWorkspaceTabs();
    const hadContent = linkedWorkspaceTabHasContent(0);

    // The final linked tab must never be physically removed. Deleting the last tab leaves
    // several panels with no active index to bind to, which can lock up PyWebView/WebKit.
    // Treat close-on-last-tab as "replace this workspace with a fresh blank card".
    resetLinkedWorkspaceTabsToBlank();
    workspaceTabRenderSuspendAutoScroll = false;
    renderAllWorkspaceTabRails();

    // If the tab was already blank, avoid the heavier apply/manual-render path entirely.
    // The visible fields are already blank and this sidesteps the freeze path users hit
    // when clicking close on an empty final tab.
    if (hadContent) {
      setTimeout(() => {
        try {
          applyActiveOutputTab();
          applyActiveConceptTab();
          applyActiveManualTab({ skipPreview: true });
          refreshWorkspaceTabScrollButtons();
          setStatus('Closed last tab and opened a new blank tab.', 'ok');
        } catch (err) {
          console.error('last linked tab reset apply failed', err);
          setStatus(`Opened a new blank tab, but refresh hit an error: ${err.message || err}`, 'warn');
        } finally {
          workspaceTabCloseInProgress = false;
        }
      }, 0);
    } else {
      refreshWorkspaceTabScrollButtons();
      setStatus('Kept one blank tab open.', 'ok');
      workspaceTabCloseInProgress = false;
    }
  } catch (err) {
    workspaceTabRenderSuspendAutoScroll = false;
    workspaceTabCloseInProgress = false;
    console.error('performLastLinkedWorkspaceTabReset failed', err);
    setStatus(`Could not reset final tab: ${err.message || err}`, 'error');
  }
}

function performLinkedWorkspaceTabClose(index) {
  let closedHadContent = false;
  let closingActive = false;
  try {
    ensureLinkedWorkspaceTabs();
    const idx = Math.max(0, Math.min(characterOutputTabs.length - 1, Number(index || 0)));
    closedHadContent = linkedWorkspaceTabHasContent(idx);
    closingActive = idx === activeOutputTabIndex || idx === activeConceptTabIndex || idx === activeManualGuideTabIndex;

    // Only capture the active tab if it has real content. Empty tabs often contain generated UI
    // placeholder state; treating that as content sends blank tabs through expensive save/render code.
    if (closedHadContent) safeCaptureLinkedWorkspaceStateForClose(idx);

    if (characterOutputTabs.length <= 1) {
      // Defensive fallback. Normal last-tab closes are routed to performLastLinkedWorkspaceTabReset(),
      // but keep this safe if arrays changed between click and close execution.
      workspaceTabCloseInProgress = false;
      performLastLinkedWorkspaceTabReset(idx);
      return;
    }

    characterOutputTabs.splice(idx, 1);
    conceptWorkspaceTabs.splice(idx, 1);
    manualGuideTabs.splice(idx, 1);
    const next = Math.max(0, Math.min(idx, characterOutputTabs.length - 1));
    activeOutputTabIndex = next;
    activeConceptTabIndex = next;
    activeManualGuideTabIndex = next;

    ensureLinkedWorkspaceTabs();
    renderAllWorkspaceTabRails();

    setTimeout(() => {
      try {
        workspaceTabRenderSuspendAutoScroll = false;
        applyActiveOutputTab();
        applyActiveConceptTab();
        applyActiveManualTab({ skipPreview: true });
        // Only rebuild manual preview for genuinely populated tabs, not blank/default section state.
        if (linkedWorkspaceTabHasContent(activeOutputTabIndex)) updateManualPreview();
        refreshWorkspaceTabScrollButtons();
        const closedProjectPath = workspaceTabProjectPath(idx);
        const closedWasDuplicateProject = closedProjectPath && workspaceProjectPathDuplicateCount(closedProjectPath) > 0;
        // If the closed tab was one of multiple tabs opened from the same saved workspace,
        // do not autosave during the close. Duplicate project tabs can race the browser refresh
        // and lock PyWebView/WebKit. The remaining tab still contains the workspace state.
        if (closedHadContent && hasOutput() && !closedWasDuplicateProject) scheduleOutputEditorAutosave();
        if (!closedHadContent && closingActive) setStatus('Closed empty tab.', 'ok');
        else if (closedWasDuplicateProject) setStatus('Closed duplicate workspace tab.', 'ok');
      } catch (err) {
        console.error('deferred linked tab apply failed', err);
        setStatus(`Closed tab, but refresh hit an error: ${err.message || err}`, 'warn');
      } finally {
        workspaceTabCloseInProgress = false;
      }
    }, 0);
  } catch (err) {
    workspaceTabRenderSuspendAutoScroll = false;
    workspaceTabCloseInProgress = false;
    console.error('closeLinkedWorkspaceTab failed', err);
    setStatus(`Could not close tab: ${err.message || err}`, 'error');
  }
}

function renderCharacterOutputTabs() {
  const holder = $('#characterOutputTabs');
  if (!holder) return;
  if (!characterOutputTabs.length) {
    characterOutputTabs = [makeBlankOutputTab('Character')];
    activeOutputTabIndex = 0;
  }
  ensureLinkedWorkspaceTabs();
  holder.innerHTML = '';
  characterOutputTabs.forEach((tab, idx) => {
    const item = document.createElement('div');
    item.className = 'workspace-tab character-output-tab' + (idx === activeOutputTabIndex ? ' active' : '');
    item.dataset.index = String(idx);
    item.setAttribute('role', 'button');
    item.tabIndex = 0;
    const title = document.createElement('span');
    title.className = 'workspace-tab-title';
    title.textContent = tab.name || tab.focusName || `Character ${idx + 1}`;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'workspace-tab-close';
    close.textContent = '×';
    close.title = 'Close linked card tab';
    close.addEventListener('click', (event) => { event.stopPropagation(); closeOutputTab(idx); });
    item.appendChild(title);
    item.appendChild(close);
    item.addEventListener('click', () => switchLinkedWorkspaceTab(idx, 'output'));
    item.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        item.click();
      }
    });
    holder.appendChild(item);
  });
  if (!workspaceTabRenderSuspendAutoScroll) scrollWorkspaceTabIntoView('characterOutputTabs', activeOutputTabIndex);
  else refreshWorkspaceTabScrollButtons('characterOutputTabs');
}

function setCharacterOutputTabs(cards) {
  const previousConcept = conceptWorkspaceTabs[activeConceptTabIndex] ? JSON.parse(JSON.stringify(conceptWorkspaceTabs[activeConceptTabIndex])) : null;
  const previousManual = manualGuideTabs[activeManualGuideTabIndex] ? JSON.parse(JSON.stringify(manualGuideTabs[activeManualGuideTabIndex])) : null;
  characterOutputTabs = (cards || []).map((card, idx) => {
    const cardOutput = loadedOutputTextFromTab(card);
    const extractedName = extractOutputNameForTab(cardOutput || '');
    const originalName = card.name || card.focusName || `Character ${idx + 1}`;
    const finalName = isGenericOutputName(originalName) && extractedName ? extractedName : cleanOutputTabName(originalName) || extractedName || `Character ${idx + 1}`;
    return {
      name: finalName,
      focusName: card.focusName || finalName,
      output: cardOutput || '',
      qaAnswers: loadedQaTextFromTab(card),
      emotionImages: Array.isArray(card.emotionImages) ? card.emotionImages : [],
      generatedImages: Array.isArray(card.generatedImages) ? card.generatedImages : [],
      cardImagePath: card.cardImagePath || card.imagePath || '',
      splitMode: card.splitMode || card.splitCard || (String(settings?.cardMode || $('#cardMode')?.value || '').toLowerCase() === 'split_cards' ? 'split_cards' : ''),
    };
  });
  if (!characterOutputTabs.length) characterOutputTabs = [makeBlankOutputTab('Character')];
  conceptWorkspaceTabs = characterOutputTabs.map((tab, idx) => normaliseConceptTab((cards || [])[idx]?.conceptTab || previousConcept || {}, tab.name || `Concept ${idx + 1}`));
  manualGuideTabs = characterOutputTabs.map((tab, idx) => normaliseManualTab((cards || [])[idx]?.manualTab || previousManual || {}, tab.name || `Manual ${idx + 1}`));
  activeOutputTabIndex = 0;
  activeConceptTabIndex = 0;
  activeManualGuideTabIndex = 0;
  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  applyActiveConceptTab();
  applyActiveManualTab();
}


function makeBlankOutputTab(name = 'Character') {
  return { name, focusName: name, output: '', qaAnswers: '', emotionImages: [], generatedImages: [], cardImagePath: '' };
}

function refreshWorkspaceTabScrollButtons(targetId = '') {
  const targets = targetId ? [$('#' + targetId)] : $$('.workspace-tabs');
  targets.forEach(group => {
    if (!group) return;
    const shell = group.closest('.workspace-tab-shell');
    const overflow = group.scrollWidth > group.clientWidth + 4;
    if (shell) shell.classList.toggle('has-overflow', overflow);
    const left = shell?.querySelector('[data-scroll-dir="-1"]');
    const right = shell?.querySelector('[data-scroll-dir="1"]');
    if (left) left.disabled = !overflow || group.scrollLeft <= 2;
    if (right) right.disabled = !overflow || group.scrollLeft + group.clientWidth >= group.scrollWidth - 2;
  });
}

function bindWorkspaceTabScrollers() {
  document.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-scroll-tabs]');
    if (!btn) return;
    const group = $('#' + btn.dataset.scrollTabs);
    if (!group) return;
    const dir = Number(btn.dataset.scrollDir || 1);
    group.scrollBy({ left: dir * Math.max(180, Math.floor(group.clientWidth * 0.75)), behavior: 'smooth' });
    setTimeout(() => refreshWorkspaceTabScrollButtons(group.id), 180);
  });
  $$('.workspace-tabs').forEach(group => group.addEventListener('scroll', () => refreshWorkspaceTabScrollButtons(group.id), { passive: true }));
  window.addEventListener('resize', () => refreshWorkspaceTabScrollButtons());
}

function scrollWorkspaceTabIntoView(holderId, idx) {
  const holder = $('#' + holderId);
  const btn = holder?.querySelector(`[data-index="${idx}"]`);
  if (btn) setTimeout(() => btn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }), 0);
  setTimeout(() => refreshWorkspaceTabScrollButtons(holderId), 0);
  setTimeout(() => refreshWorkspaceTabScrollButtons(holderId), 150);
}

function closeOutputTab(index) {
  closeLinkedWorkspaceTab(index);
}

function addOutputTab(card = {}, activate = true) {
  const idx = characterOutputTabs.length;
  const conceptTab = card.conceptTab || makeBlankConceptTab(card.name || card.focusName || `Concept ${idx + 1}`);
  const manualTab = card.manualTab || makeBlankManualTab(card.name || card.focusName || `Manual ${idx + 1}`);
  addLinkedWorkspaceTab({ outputTab: card, conceptTab, manualTab, activate });
  if (!workspaceTabRenderSuspendAutoScroll) scrollWorkspaceTabIntoView('characterOutputTabs', activeOutputTabIndex);
  else refreshWorkspaceTabScrollButtons('characterOutputTabs');
}

function addBlankOutputTab() {
  addOutputTab(makeBlankOutputTab(`Character ${characterOutputTabs.length + 1}`), true);
  switchToOutputTab();
  setStatus('New Output / Editor tab opened.', 'ok');
}

function switchToOutputTab(subtab = 'output-fulltext') {
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="output"]')?.classList.add('active');
  $('#output')?.classList.add('active');
  if (subtab) switchSubTab('output', subtab);
}

function makeBlankConceptTab(name = '') {
  const idx = conceptWorkspaceTabs.length + 1;
  const tabName = name || `Concept ${idx}`;
  return {
    name: tabName,
    concept: '',
    visionDescription: '',
    visionImagePath: '',
    conceptAttachments: [],
    builderState: { mode: 'single', selectedIndex: 0, states: [{}] },
  };
}

function captureActiveConceptTab() {
  if (!conceptWorkspaceTabs.length) conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
  const tab = conceptWorkspaceTabs[activeConceptTabIndex];
  if (!tab) return;
  tab.concept = $('#conceptText')?.value || '';
  tab.visionDescription = $('#visionDescription')?.value || '';
  tab.visionImagePath = $('#visionImagePath')?.value || '';
  tab.conceptAttachments = Array.isArray(conceptAttachments) ? conceptAttachments.map(a => ({...a})) : [];
  try { tab.builderState = collectBuilderWorkspaceState(); } catch (_) {}
  const nameFromConcept = extractOutputNameForTab(tab.concept || '') || '';
  if (nameFromConcept && /^Concept\s+\d+$/i.test(tab.name || '')) tab.name = nameFromConcept;
}

function applyActiveConceptTab() {
  if (!conceptWorkspaceTabs.length) conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
  const tab = conceptWorkspaceTabs[activeConceptTabIndex] || conceptWorkspaceTabs[0];
  if (!tab) return;
  if ($('#conceptText')) $('#conceptText').value = tab.concept || '';
  if ($('#visionDescription')) $('#visionDescription').value = tab.visionDescription || '';
  setVisionImagePath(tab.visionImagePath || '');
  conceptAttachments = Array.isArray(tab.conceptAttachments) ? tab.conceptAttachments.map(a => ({...a})) : [];
  renderConceptAttachments();
  if (tab.builderState) restoreBuilderWorkspaceState(tab.builderState);
  updateAvailability();
}

function renderConceptWorkspaceTabs() {
  const holder = $('#conceptWorkspaceTabs');
  if (!holder) return;
  if (!conceptWorkspaceTabs.length) {
    conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
    activeConceptTabIndex = 0;
  }
  ensureLinkedWorkspaceTabs();
  holder.innerHTML = '';
  conceptWorkspaceTabs.forEach((tab, idx) => {
    const item = document.createElement('div');
    item.className = 'workspace-tab concept-workspace-tab' + (idx === activeConceptTabIndex ? ' active' : '');
    item.dataset.index = String(idx);
    item.setAttribute('role', 'button');
    item.tabIndex = 0;
    const title = document.createElement('span');
    title.className = 'workspace-tab-title';
    title.textContent = tab.name || workspaceTabNameForIndex(idx) || `Concept ${idx + 1}`;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'workspace-tab-close';
    close.textContent = '×';
    close.title = 'Close linked card tab';
    close.addEventListener('click', (event) => { event.stopPropagation(); closeConceptWorkspaceTab(idx); });
    item.appendChild(title);
    item.appendChild(close);
    item.addEventListener('click', () => switchConceptWorkspaceTab(idx));
    item.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); switchConceptWorkspaceTab(idx); } });
    holder.appendChild(item);
  });
  if (!workspaceTabRenderSuspendAutoScroll) scrollWorkspaceTabIntoView('conceptWorkspaceTabs', activeConceptTabIndex);
  else refreshWorkspaceTabScrollButtons('conceptWorkspaceTabs');
}

function switchConceptWorkspaceTab(index) {
  switchLinkedWorkspaceTab(index, 'concept');
  switchSubTab('concept', 'concept-main');
}

function addConceptWorkspaceTab() {
  const idx = characterOutputTabs.length;
  addLinkedWorkspaceTab({
    outputTab: makeBlankOutputTab(`Character ${idx + 1}`),
    conceptTab: makeBlankConceptTab(`Concept ${idx + 1}`),
    manualTab: makeBlankManualTab(`Manual ${idx + 1}`),
    activate: true,
  });
  switchSubTab('concept', 'concept-main');
  setStatus('New linked card tab opened.', 'ok');
}

function closeConceptWorkspaceTab(index) {
  closeLinkedWorkspaceTab(index);
}

function makeBlankManualTab(name = '') {
  const idx = manualGuideTabs.length + 1;
  return { name: name || `Manual ${idx}`, state: {}, pageIndex: 0 };
}

function captureActiveManualTab(options = {}) {
  if (!manualGuideTabs.length) manualGuideTabs = [makeBlankManualTab('Manual 1')];
  const tab = manualGuideTabs[activeManualGuideTabIndex];
  if (!tab) return;
  if (!options.lightweight) captureManualGuideInputs();
  tab.state = JSON.parse(JSON.stringify(manualGuideState || {}));
  tab.pageIndex = manualGuidePageIndex || 0;
  if (options.lightweight) return;
  const built = buildManualGuideOutput ? buildManualGuideOutput() : '';
  const nameFromOutput = extractOutputNameForTab(built || '') || '';
  if (nameFromOutput && /^Manual\s+\d+$/i.test(tab.name || '')) tab.name = nameFromOutput;
}

function applyActiveManualTab(options = {}) {
  if (!manualGuideTabs.length) manualGuideTabs = [makeBlankManualTab('Manual 1')];
  const tab = manualGuideTabs[activeManualGuideTabIndex] || manualGuideTabs[0];
  manualGuideState = JSON.parse(JSON.stringify(tab?.state || {}));
  manualGuidePageIndex = Number(tab?.pageIndex || 0);
  renderManualGuide({ skipPreview: !!options.skipPreview });
}

function renderManualWorkspaceTabs() {
  const holder = $('#manualWorkspaceTabs');
  if (!holder) return;
  if (!manualGuideTabs.length) {
    manualGuideTabs = [makeBlankManualTab('Manual 1')];
    activeManualGuideTabIndex = 0;
  }
  ensureLinkedWorkspaceTabs();
  holder.innerHTML = '';
  manualGuideTabs.forEach((tab, idx) => {
    const item = document.createElement('div');
    item.className = 'workspace-tab manual-workspace-tab' + (idx === activeManualGuideTabIndex ? ' active' : '');
    item.dataset.index = String(idx);
    item.setAttribute('role', 'button');
    item.tabIndex = 0;
    const title = document.createElement('span');
    title.className = 'workspace-tab-title';
    title.textContent = tab.name || workspaceTabNameForIndex(idx) || `Manual ${idx + 1}`;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'workspace-tab-close';
    close.textContent = '×';
    close.title = 'Close linked card tab';
    close.addEventListener('click', (event) => { event.stopPropagation(); closeManualWorkspaceTab(idx); });
    item.appendChild(title);
    item.appendChild(close);
    item.addEventListener('click', () => switchManualWorkspaceTab(idx));
    item.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); switchManualWorkspaceTab(idx); } });
    holder.appendChild(item);
  });
  if (!workspaceTabRenderSuspendAutoScroll) scrollWorkspaceTabIntoView('manualWorkspaceTabs', activeManualGuideTabIndex);
  else refreshWorkspaceTabScrollButtons('manualWorkspaceTabs');
}

function switchManualWorkspaceTab(index) {
  switchLinkedWorkspaceTab(index, 'manual');
}

function addManualWorkspaceTab() {
  const idx = characterOutputTabs.length;
  addLinkedWorkspaceTab({
    outputTab: makeBlankOutputTab(`Character ${idx + 1}`),
    conceptTab: makeBlankConceptTab(`Concept ${idx + 1}`),
    manualTab: makeBlankManualTab(`Manual ${idx + 1}`),
    activate: true,
  });
  setStatus('New linked Guided Manual tab opened.', 'ok');
}

function closeManualWorkspaceTab(index) {
  closeLinkedWorkspaceTab(index);
}

function clearCurrentManualGuideDraft() {
  manualGuideState = {};
  manualGuidePageIndex = 0;
  if (!manualGuideTabs.length) manualGuideTabs = [makeBlankManualTab('Manual 1')];
  manualGuideTabs[activeManualGuideTabIndex] = makeBlankManualTab(`Manual ${activeManualGuideTabIndex + 1}`);
  renderManualWorkspaceTabs();
  renderManualGuide();
  setStatus('Cleared current Guided Manual draft.', 'ok');
}

function buildLinkedWorkspaceTabsFromLoadedState(state = {}, options = {}) {
  const projectPath = canonicalWorkspaceProjectPath(state?.projectPath || state?.sourcePath || '');
  const forceSingleProject = !!options.singleProject;
  const savedTabs = (!forceSingleProject && Array.isArray(state?.characterTabs))
    ? state.characterTabs.filter(tab => tab && typeof tab === 'object' && loadedOutputTextFromTab(tab))
    : [];
  const rows = [];
  if (savedTabs.length) {
    savedTabs.forEach((tab, idx) => {
      const name = tab.name || tab.focusName || extractOutputNameForTab(loadedOutputTextFromTab(tab) || '') || `Loaded ${idx + 1}`;
      const outputTab = {
        ...tab,
        name,
        focusName: tab.focusName || name,
        projectPath: canonicalWorkspaceProjectPath(tab.projectPath || tab.workspaceProjectPath || projectPath),
        workspaceProjectPath: canonicalWorkspaceProjectPath(tab.projectPath || tab.workspaceProjectPath || projectPath),
        output: loadedOutputTextFromTab(tab),
        fullTextOutput: loadedOutputTextFromTab(tab),
        cardImagePath: tab.cardImagePath || tab.imagePath || state.imagePath || state.cardImagePath || '',
        qaAnswers: loadedQaTextFromTab(tab),
        qnaAnswers: loadedQaTextFromTab(tab),
        emotionImages: Array.isArray(tab.emotionImages) ? tab.emotionImages : [],
        generatedImages: Array.isArray(tab.generatedImages) ? tab.generatedImages : [],
      };
      const conceptTab = makeConceptTabFromWorkspaceState(state, idx, name);
      const manualTab = makeManualTabFromWorkspaceState(state, idx, name);
      if (outputTab.projectPath) {
        conceptTab.projectPath = outputTab.projectPath;
        conceptTab.workspaceProjectPath = outputTab.projectPath;
        manualTab.projectPath = outputTab.projectPath;
        manualTab.workspaceProjectPath = outputTab.projectPath;
      }
      rows.push({ outputTab, conceptTab, manualTab });
    });
  } else {
    const fallbackTab = forceSingleProject ? bestLoadedCharacterTabForSingleProject(state) : {};
    const outputText = loadedOutputTextFromState(state, fallbackTab);
    if (!outputText) return rows;
    const name = state.name || fallbackTab.name || fallbackTab.focusName || extractOutputNameForTab(outputText) || 'Loaded Character';
    const outputTab = {
      ...fallbackTab,
      name,
      focusName: fallbackTab.focusName || name,
      projectPath,
      workspaceProjectPath: projectPath,
      output: outputText,
      qaAnswers: loadedQaTextFromState(state, fallbackTab),
      qnaAnswers: loadedQaTextFromState(state, fallbackTab),
      emotionImages: loadedImageListFromState(state, 'emotionImages', fallbackTab),
      generatedImages: loadedImageListFromState(state, 'generatedImages', fallbackTab),
      cardImagePath: state.imagePath || state.cardImagePath || state?.workspace?.cardImagePath || state?.workspace?.imagePath || fallbackTab.cardImagePath || fallbackTab.imagePath || '',
    };
    const conceptTab = makeConceptTabFromWorkspaceState(state, 0, name, { singleProject: forceSingleProject });
    const manualTab = makeManualTabFromWorkspaceState(state, 0, name, { singleProject: forceSingleProject });
    if (projectPath) {
      conceptTab.projectPath = projectPath;
      conceptTab.workspaceProjectPath = projectPath;
      manualTab.projectPath = projectPath;
      manualTab.workspaceProjectPath = projectPath;
    }
    rows.push({ outputTab, conceptTab, manualTab });
  }
  return rows;
}

function applyLoadedStateToExistingWorkspaceTab(index, row, state = {}) {
  ensureLinkedWorkspaceTabs();
  const idx = Math.max(0, Math.min(characterOutputTabs.length - 1, Number(index || 0)));
  if (!row || !row.outputTab) return idx;
  characterOutputTabs[idx] = {
    ...makeBlankOutputTab(row.outputTab.name || row.outputTab.focusName || `Character ${idx + 1}`),
    ...row.outputTab,
  };
  conceptWorkspaceTabs[idx] = normaliseConceptTab(row.conceptTab || {}, row.outputTab.name || `Concept ${idx + 1}`);
  manualGuideTabs[idx] = normaliseManualTab(row.manualTab || {}, row.outputTab.name || `Manual ${idx + 1}`);
  const projectPath = canonicalWorkspaceProjectPath(row.outputTab.projectPath || state?.projectPath || '');
  if (projectPath) {
    characterOutputTabs[idx].projectPath = projectPath;
    characterOutputTabs[idx].workspaceProjectPath = projectPath;
    conceptWorkspaceTabs[idx].projectPath = projectPath;
    conceptWorkspaceTabs[idx].workspaceProjectPath = projectPath;
    manualGuideTabs[idx].projectPath = projectPath;
    manualGuideTabs[idx].workspaceProjectPath = projectPath;
  }
  activeOutputTabIndex = idx;
  activeConceptTabIndex = idx;
  activeManualGuideTabIndex = idx;
  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  applyActiveConceptTab();
  applyActiveManualTab({ skipPreview: true });
  setTimeout(() => { try { updateManualPreview(); } catch (_) {} }, 0);
  return idx;
}

function appendLoadedStateToOutputTabs(state, options = {}) {
  const loadedRows = buildLinkedWorkspaceTabsFromLoadedState(state, options);
  const projectPath = canonicalWorkspaceProjectPath(state?.projectPath || '');
  if (!loadedRows.length) {
    setStatus('Loaded the project file, but no saved Full Text Output was found to restore.', 'error');
    try { writeClientDebugEvent('browser_load_empty_output_rows', { projectPath, hasOutput: !!loadedOutputTextFromState(state, {}), tabCount: Array.isArray(state?.characterTabs) ? state.characterTabs.length : 0 }); } catch (_) {}
    return;
  }

  if (projectPath) {
    const existingIndex = findOpenWorkspaceTabByProjectPath(projectPath);
    if (existingIndex >= 0) {
      // Opening the same saved workspace twice used to create duplicate linked tabs.
      // Closing one of those duplicates could then race autosave/browser refresh and freeze.
      // Treat the second open as "focus/refresh existing tab" instead.
      if (loadedRows.length) applyLoadedStateToExistingWorkspaceTab(existingIndex, loadedRows[0], state);
      else switchLinkedWorkspaceTab(existingIndex, 'browser-load-existing');
      currentBrowserDescription = state?.browserDescription || state?.libraryDescription || '';
      currentCardRating = state?.cardRating || '';
      currentCardRatingReasoning = state?.cardRatingReasoning || '';
      currentCardRatingDetails = Array.isArray(state?.cardRatingDetails) ? state.cardRatingDetails : [];
      currentCardRatingSourceHash = state?.cardRatingSourceHash || '';
      switchToOutputTab('output-fulltext');
      setStatus('That workspace is already open, so the existing tab was focused instead of opening a duplicate.', 'ok');
      return;
    }
  }

  const before = characterOutputTabs.length;
  loadedRows.forEach((row, idx) => {
    const fallback = `Loaded ${before + idx + 1}`;
    if (!row.outputTab.name) row.outputTab.name = fallback;
    addLinkedWorkspaceTab({ ...row, activate: true });
  });

  currentBrowserDescription = state?.browserDescription || state?.libraryDescription || '';
  currentCardRating = state?.cardRating || '';
  currentCardRatingReasoning = state?.cardRatingReasoning || '';
  currentCardRatingDetails = Array.isArray(state?.cardRatingDetails) ? state.cardRatingDetails : [];
  currentCardRatingSourceHash = state?.cardRatingSourceHash || '';
  switchToOutputTab('output-fulltext');
}

function clearGenerationArtifacts(options = {}) {
  const preserveWorkspaceInputs = !!options.preserveWorkspaceInputs;
  const activeIndex = Math.max(0, Number(activeOutputTabIndex || 0));

  if (preserveWorkspaceInputs) {
    captureActiveConceptTab();
    captureActiveManualTab();
    ensureLinkedWorkspaceTabs();
  }

  lastQnaAnswers = '';
  currentBrowserDescription = '';
  currentCardRating = '';
  currentCardRatingReasoning = '';
  currentCardRatingDetails = [];
  currentCardRatingSourceHash = '';
  emotionImageState = [];

  if (preserveWorkspaceInputs) {
    ensureLinkedWorkspaceTabs();
    const current = characterOutputTabs[activeIndex] || makeBlankOutputTab(`Character ${activeIndex + 1}`);
    characterOutputTabs[activeIndex] = {
      ...makeBlankOutputTab(current.name || current.focusName || `Character ${activeIndex + 1}`),
      projectPath: current.projectPath || current.workspaceProjectPath || '',
      workspaceProjectPath: current.workspaceProjectPath || current.projectPath || '',
    };
    activeOutputTabIndex = activeIndex;
    activeConceptTabIndex = activeIndex;
    activeManualGuideTabIndex = activeIndex;
  } else {
    characterOutputTabs = [makeBlankOutputTab('Character')];
    conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
    manualGuideTabs = [makeBlankManualTab('Manual 1')];
    activeOutputTabIndex = 0;
    activeConceptTabIndex = 0;
    activeManualGuideTabIndex = 0;
    setTextareaValue('conceptText', '');
    setTextareaValue('visionDescription', '');
    setVisionImagePath('');
    conceptAttachments = [];
    manualGuideState = {};
    manualGuidePageIndex = 0;
  }

  setTextareaValue('qaAnswersText', '');
  setTextareaValue('outputText', '');
  setTextareaValue('followupText', '');
  const emotions = $('#emotionImages');
  if (emotions) emotions.innerHTML = '';
  const generated = $('#generatedImages');
  if (generated) generated.innerHTML = '';
  const cardImage = $('#cardImagePath');
  if (cardImage) cardImage.value = '';
  if (settings) settings.cardImagePath = '';
  renderAllWorkspaceTabRails();
  if (!preserveWorkspaceInputs) {
    renderConceptAttachments();
    renderManualGuide();
  }
}

window.ccfStreamUpdate = function(payload) {
  try {
    const target = String(payload?.target || '').toLowerCase();
    // Emotion prompt generation is an internal JSON request. It should never
    // replace the main generated card text, even if an older backend emits
    // a stray output stream event.
    if (target === 'output' && /emotion/i.test(String(currentTask || ''))) return;
    const text = String(payload?.text || '');
    const chunk = String(payload?.chunk || '');
    const id = target === 'qa' ? 'qaAnswersText' : target === 'output' ? 'outputText' : '';
    if (!id) return;
    const el = $('#' + id);
    if (!el) return;
    el.value = text || (el.value + chunk);
    el.scrollTop = el.scrollHeight;
    updateAvailability();
  } catch (_) {}
};

window.ccfEmotionProgress = function(payload) {
  try {
    const msg = payload?.message || '';
    if (msg) setStatus(msg, '');
    if (payload?.phase === 'prompts') setBusy('GENERATING EMOTION PROMPTS — AI is preparing image prompts…');
    if (payload?.phase === 'images') setBusy('GENERATING EMOTION IMAGES — SD Forge / Automatic1111 is working…');
  } catch (_) {}
};

window.ccfEmotionImageGenerated = function(image) {
  try {
    if (!image || !image.emotion) return;
    const idx = emotionImageState.findIndex(x => x.emotion === image.emotion);
    if (idx >= 0) emotionImageState[idx] = {...image};
    else emotionImageState.push({...image});
    renderEmotionImageResults([], false);
    setStatus(`Generated ${image.emotion}.png (${emotionImageState.length} so far)…`, 'ok');
  } catch (_) {}
};

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

function updateImportedCardToolsHint() {
  const hint = $('#importedCardToolsHint');
  if (!hint) return;
  if (!hasOutput()) {
    hint.textContent = 'Load or import a card first. If it does not already include a Stable Diffusion Prompt, use one of the buttons above to generate and save it.';
    return;
  }
  if (hasStableDiffusionPrompt()) {
    hint.textContent = 'This card already has a Stable Diffusion Prompt. You can still regenerate it from the current card image or full text output if you want a new one.';
    return;
  }
  const hasImage = !!($('#cardImagePath')?.value || '').trim();
  hint.textContent = hasImage
    ? 'This card does not currently have a Stable Diffusion Prompt. Use Vision → SD Prompt to infer one from the current card image, or Full Text → SD Prompt to build one from the loaded metadata.'
    : 'This card does not currently have a Stable Diffusion Prompt. Use Full Text → SD Prompt to build one from the loaded metadata, or choose a card image first and then use Vision → SD Prompt.';
}
function setBusy(task) {
  isBusy = !!task;
  currentTask = task || '';
  const banner = $('#busyBanner');
  const busyText = $('#busyText');
  if (banner) {
    if (busyText) busyText.textContent = task || '';
    banner.classList.toggle('hidden', !task);
    banner.classList.toggle('ai-only-busy', isAiGenerationBusy());
  }
  updateAvailability();
}

function isAiGenerationBusy() {
  if (!isBusy) return false;
  const task = String(currentTask || '').toLowerCase();
  return /\b(ai|generation|generating|q&a|vision|stable diffusion|sd forge|sd images|emotion image|tag cleanup|description|revision|revise|suggestion|random theme|transfer to builders|backup text model|model)\b/.test(task);
}

function isInterfaceLocked() {
  // AI work should only lock other AI actions. Non-AI file/browser/editor controls stay usable.
  return isBusy && !isAiGenerationBusy();
}

function isAiActionElement(el) {
  if (!el) return false;
  const id = String(el.id || '');
  if (el.closest && (el.closest('.ai-suggest-field') || el.closest('.ai-tag-cleanup-card'))) return true;
  if (el.classList && el.classList.contains('regen-emotion-btn')) return true;
  const aiIds = new Set([
    'generateBtn','generateIdeaBtn','reviseBtn','transferToBuildersBtn','transferToBuildersMainBtn','analyzeVisionBtn','startVisionAnalyzeOptionsBtn',
    'builderGenerateBtn','personalityBuilderGenerateBtn','sceneBuilderGenerateBtn','aiRandomPresetBtn','aiRandomPresetBuildBtn',
    'generateImagesBtn','generateEmotionImagesBtn','generateSdPromptFromVisionBtn','generateSdPromptFromOutputBtn','aiTagCleanupBtn','aiTagMergeAllBtn','aiTagRenameAllBtn','browserAiDescriptionBtn'
  ]);
  if (aiIds.has(id)) return true;
  return /(?:^|)(ai|suggest|analyze|generate|revise|random)(?:|$)/i.test(id) && !/export|copy|load|select|clear|save|delete|folder|refresh|zip/i.test(id);
}

function isAiDropZoneId(id) {
  return ['visionDropZone','builderCardDropZoneMain','builderCardDropZoneMode'].includes(String(id || ''));
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
    analyze.disabled = isInterfaceLocked() || isAiGenerationBusy() ? true : !value;
    analyze.title = value ? '' : 'Select a vision image first.';
  }
  const fullCardAnalyze = $('#analyzeFullCardBtn');
  if (fullCardAnalyze) {
    fullCardAnalyze.dataset.visionPath = value;
    fullCardAnalyze.disabled = isInterfaceLocked() || isAiGenerationBusy() ? true : !value;
    fullCardAnalyze.title = value ? '' : 'Select a vision image first.';
  }
}

function preventDragDefaults(event) {
  event.preventDefault();
  event.stopPropagation();
}

function decodeDroppedFileUri(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  // KDE/GNOME sometimes prepend clipboard action lines before file:// URIs.
  if (/^(copy|cut|move|link)$/i.test(raw)) return '';
  if (/^file:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      return decodeURIComponent(url.pathname || '').replace(/^\/([A-Za-z]:\/)/, '$1');
    } catch (_) {
      return decodeURIComponent(raw.replace(/^file:\/\/+/, '/'));
    }
  }
  return raw;
}

function getDroppedFilePaths(dataTransfer) {
  const dt = dataTransfer;
  if (!dt || typeof dt.getData !== 'function') return [];
  const seen = new Set();
  const paths = [];
  const add = (value) => {
    const path = decodeDroppedFileUri(value);
    if (!path || /^https?:\/\//i.test(path)) return;
    if (/^(copy|cut|move|link)$/i.test(path)) return;
    if (!seen.has(path)) {
      seen.add(path);
      paths.push(path);
    }
  };
  // Different Linux desktops/WebKit builds expose file drops through different text payloads.
  // Import Card/Image worked because browser File objects were present there; these extra
  // payloads cover AppImage/KDE/GNOME cases where dataTransfer.files is empty.
  [
    'text/uri-list',
    'text/plain',
    'text/x-moz-url',
    'text/x-moz-url-data',
    'application/x-kde-cutselection',
    'x-special/gnome-copied-files',
  ].forEach(type => {
    let text = '';
    try { text = dt.getData(type) || ''; } catch (_) { text = ''; }
    String(text || '').split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#')).forEach(add);
  });
  return paths;
}

function getDroppedFiles(dataTransfer) {
  const dt = dataTransfer;
  const files = [...(dt?.files || [])].filter(Boolean);
  if (files.length) return files;
  const itemFiles = [];
  try {
    for (const item of [...(dt?.items || [])]) {
      if (item?.kind === 'file' && typeof item.getAsFile === 'function') {
        const file = item.getAsFile();
        if (file) itemFiles.push(file);
      }
    }
  } catch (_) {}
  return itemFiles;
}

function bindDropZone(id, options = {}) {
  const zone = $('#' + id);
  if (!zone) return;
  if (zone.__ccfDropZoneBound) return;
  zone.__ccfDropZoneBound = true;
  zone.dataset.ccfDropZoneId = id;
  const input = options.inputId ? $('#' + options.inputId) : null;
  const isBlocked = () => isInterfaceLocked() || (isAiGenerationBusy() && isAiDropZoneId(id));
  const setActive = (active) => zone.classList.toggle('drag-over', !!active && !isBlocked());
  const describeDropPayload = (dt) => {
    try {
      const types = [...(dt?.types || [])].join(', ');
      return types ? ` Detected payload types: ${types}.` : '';
    } catch (_) { return ''; }
  };
  const handleDrop = async (e) => {
    preventDragDefaults(e);
    setActive(false);
    if (isBlocked()) {
      setStatus(isAiGenerationBusy() ? 'An AI task is running. AI-assisted drop zones are paused, but other controls are still usable.' : 'Please wait until the current task finishes before dropping files.', 'error');
      return;
    }
    const files = getDroppedFiles(e.dataTransfer);
    if (files.length && options.onFiles) {
      await options.onFiles(files);
      return;
    }
    const paths = getDroppedFilePaths(e.dataTransfer);
    if (paths.length && options.onPaths) {
      await options.onPaths(paths);
      return;
    }
    setStatus('No dropped file was detected. Try the Select/Attach button instead.' + describeDropPayload(e.dataTransfer), 'error');
  };
  ['dragenter', 'dragover'].forEach(evt => zone.addEventListener(evt, (e) => {
    preventDragDefaults(e);
    if (isBlocked()) return;
    setActive(true);
  }));
  ['dragleave', 'dragend'].forEach(evt => zone.addEventListener(evt, (e) => {
    preventDragDefaults(e);
    setActive(false);
  }));
  zone.addEventListener('drop', handleDrop);
  zone.addEventListener('click', async (e) => {
    if (isBlocked()) return;
    try {
      // For Vision and Concept Attachments the most reliable Linux/WebView path is the
      // same browser file input used by Import Card/Image. Keep this synchronous inside
      // the user click; delayed input.click() after an awaited native dialog can be blocked.
      if (options.preferInputOnClick && input) {
        input.value = '';
        input.click();
        return;
      }
      if (options.onClick) await options.onClick();
      else if (input) {
        input.value = '';
        input.click();
      }
    } catch (err) {
      if (input) {
        try { input.value = ''; input.click(); return; } catch (_) {}
      }
      setStatus(err?.message || String(err), 'error');
    }
  });
  zone.tabIndex = zone.tabIndex >= 0 ? zone.tabIndex : 0;
  zone.setAttribute('role', zone.getAttribute('role') || 'button');
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      preventDragDefaults(e);
      zone.click();
    }
  });
}

function openBrowserFileInput(inputId, label = 'file') {
  const input = $('#' + inputId);
  if (!input) {
    setStatus(`File input missing for ${label}.`, 'error');
    return false;
  }
  try {
    input.value = '';
    input.click();
    return true;
  } catch (err) {
    setStatus(`Could not open ${label} picker: ${err?.message || err}`, 'error');
    return false;
  }
}

function promptForUrl(label = 'URL') {
  const url = window.prompt(`Paste ${label}:`);
  if (url === null) return '';
  return String(url || '').trim();
}

function isProbablyUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

function updateAvailability() {
  const output = hasOutput();
  const sdReady = hasStableDiffusionPrompt();
  const aiBusy = isAiGenerationBusy();
  const hardLocked = isInterfaceLocked();

  $$('button, select, input, textarea').forEach(el => {
    if (el.id === 'status') return;
    if (hardLocked) {
      el.disabled = true;
    } else if (aiBusy) {
      el.disabled = isAiActionElement(el);
    } else {
      el.disabled = false;
    }
  });

  const stopBtn = $('#stopTaskBtn');
  if (stopBtn) stopBtn.disabled = !isBusy;

  ['conceptAttachmentDropZone','visionDropZone','savedFileDropZone','cardImageDropZone','builderCardDropZoneMain','builderCardDropZoneMode','conceptCardDropZoneMain','conceptCardDropZoneMode'].forEach(id => {
    const z = $('#'+id);
    if (z) z.classList.toggle('disabled', hardLocked || (aiBusy && isAiDropZoneId(id)));
  });

  if (!hardLocked) {
    ['copyBtn','exportBtn','zipEmotionImagesBtn'].forEach(id => { const el = $('#'+id); if (el) el.disabled = !output; });
    ['reviseBtn','generateEmotionImagesBtn'].forEach(id => { const el = $('#'+id); if (el) el.disabled = !output || aiBusy; });
    const genCard = $('#generateBtn');
    if (genCard) genCard.disabled = aiBusy;
    const genImg = $('#generateImagesBtn');
    if (genImg) genImg.disabled = !sdReady || aiBusy;
    const path = getVisionImagePath();
    const analyze = $('#analyzeVisionBtn');
    if (analyze) {
      analyze.dataset.visionPath = path;
      analyze.disabled = !path || aiBusy;
      analyze.title = path ? (aiBusy ? 'An AI task is already running.' : 'Open vision analysis options.') : 'Select a vision image first.';
    }
    const fullCardAnalyze = $('#analyzeFullCardBtn');
    if (fullCardAnalyze) {
      fullCardAnalyze.dataset.visionPath = path;
      fullCardAnalyze.disabled = !path || aiBusy;
      fullCardAnalyze.title = path ? (aiBusy ? 'An AI task is already running.' : 'Analyze the full card image into Main Concept.') : 'Select a vision image first.';
    }
    const follow = $('#followupText');
    if (follow) follow.disabled = !output;
  }
}

function showBrowserLoadingModal(message = 'Scanning saved cards and refreshing the browser cache. Large libraries can take a moment.') {
  const modal = $('#browserLoadingModal');
  if (!modal) return;
  const text = $('#browserLoadingText');
  if (text) text.textContent = message;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function hideBrowserLoadingModal() {
  const modal = $('#browserLoadingModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function waitForNextFrame() {
  return new Promise(resolve => requestAnimationFrame(() => resolve()));
}

function bindTabs() {
  $$('.nav').forEach(btn => btn.addEventListener('click', async () => {
    $$('.nav').forEach(b => b.classList.remove('active'));
    $$('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    $('#' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'browser') {
      showBrowserLoadingModal();
      await waitForNextFrame();
      await refreshCharacterBrowser(false, { modal: true, keepModalVisible: true });
    }
    if (btn.dataset.tab === 'manual') {
      renderManualGuide();
    }
    refreshSubtabScrollControls();
    updateAvailability();
  }));
}

function enhanceScrollableSubtabs() {
  $$('.subtabs').forEach(group => {
    if (group.parentElement?.classList.contains('subtabs-scroll-shell')) return;
    const shell = document.createElement('div');
    shell.className = 'subtabs-scroll-shell';
    const left = document.createElement('button');
    left.type = 'button';
    left.className = 'subtabs-scroll-btn subtabs-scroll-left';
    left.textContent = '‹';
    left.setAttribute('aria-label', 'Scroll tabs left');
    const right = document.createElement('button');
    right.type = 'button';
    right.className = 'subtabs-scroll-btn subtabs-scroll-right';
    right.textContent = '›';
    right.setAttribute('aria-label', 'Scroll tabs right');
    group.parentNode.insertBefore(shell, group);
    shell.appendChild(left);
    shell.appendChild(group);
    shell.appendChild(right);
    const update = () => {
      const overflow = group.scrollWidth > group.clientWidth + 4;
      shell.classList.toggle('has-overflow', overflow);
      left.disabled = !overflow || group.scrollLeft <= 2;
      right.disabled = !overflow || group.scrollLeft + group.clientWidth >= group.scrollWidth - 2;
    };
    left.addEventListener('click', () => group.scrollBy({ left: -Math.max(180, Math.floor(group.clientWidth * 0.7)), behavior: 'smooth' }));
    right.addEventListener('click', () => group.scrollBy({ left: Math.max(180, Math.floor(group.clientWidth * 0.7)), behavior: 'smooth' }));
    group.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    setTimeout(update, 0);
    shell.__ccfUpdateSubtabs = update;
    setTimeout(update, 250);
  });
}

function refreshSubtabScrollControls() {
  $$('.subtabs-scroll-shell').forEach(shell => {
    if (typeof shell.__ccfUpdateSubtabs === 'function') {
      setTimeout(shell.__ccfUpdateSubtabs, 0);
      setTimeout(shell.__ccfUpdateSubtabs, 120);
    }
  });
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
      setTimeout(() => btn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }), 0);
      if (btn.dataset.subtab === 'output-debug') refreshDebugLog(true);
      if (btn.dataset.subtab === 'output-relationships') refreshRelationshipMatrixOpenCharacterList();
      refreshSubtabScrollControls();
      updateAvailability();
    }));
  });
}

async function init() {
  installConceptImportModalDelegatedHandlers();
  installConceptVisionAttachmentDelegatedHandlers();
  bindTabs();
  enhanceScrollableSubtabs();
  bindWorkspaceTabScrollers();
  bindSubTabs();
  const state = await window.pywebview.api.get_state();
  template = state.template;
  settings = state.settings;
  appVersion = (state.version || 'unknown').toString().trim() || 'unknown';
  updateAppVersionDisplay();
  recentModels = normalizeRecentModels(settings.recentModels || []);
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
  if (!conceptWorkspaceTabs.length) conceptWorkspaceTabs = [makeBlankConceptTab('Concept 1')];
  if (!manualGuideTabs.length) manualGuideTabs = [makeBlankManualTab('Manual 1')];
  renderConceptWorkspaceTabs();
  applyActiveConceptTab();
  renderManualWorkspaceTabs();
  renderManualGuide();
  renderConceptAttachments();
  showRandomTip();
  bindActions();
  setTimeout(() => { populateBuilderPresets(); populateAiRandomThemes(); ensureBuilderPresetDropdowns(); updateAiRandomThemeCustom(); }, 0);
  setTimeout(ensureBuilderPresetDropdowns, 250);
  setTimeout(ensureBuilderPresetDropdowns, 1000);
  updateAvailability();
  startDebugLogAutoRefresh();
  try { await writeClientDebugEvent('client_bridge_ready', { availableApiMethods: Object.keys(window.pywebview?.api || {}).sort().slice(0, 120) }); } catch (_) {}
  startUpdateChecks();
}

function hydrateSettings() {
  $('#apiBaseUrl').value = settings.apiBaseUrl || '';
  $('#apiKey').value = settings.apiKey || '';
  $('#model').value = settings.model || '';
  recentModels = normalizeRecentModels(settings.recentModels || recentModels || []);
  renderRecentModelDropdown('', false);
  updateModelTokenHint();
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
  const streamAi = $('#streamAi'); if (streamAi) streamAi.checked = !!settings.streamAi;
  const frontPorchTarget = $('#frontPorchExportTarget'); if (frontPorchTarget) frontPorchTarget.value = (settings.frontPorchExportTarget === 'beta' ? 'beta' : 'stable');
  const legacyFrontPorchFolder = settings.frontPorchDataFolder || '';
  const frontPorchStableDataFolder = $('#frontPorchStableDataFolder'); if (frontPorchStableDataFolder) frontPorchStableDataFolder.value = settings.frontPorchStableDataFolder || ((settings.frontPorchExportTarget !== 'beta') ? legacyFrontPorchFolder : '');
  const frontPorchBetaDataFolder = $('#frontPorchBetaDataFolder'); if (frontPorchBetaDataFolder) frontPorchBetaDataFolder.value = settings.frontPorchBetaDataFolder || ((settings.frontPorchExportTarget === 'beta') ? legacyFrontPorchFolder : '');
  const dataFilesFolder = $('#dataFilesFolder'); if (dataFilesFolder) dataFilesFolder.value = settings.dataFilesFolder || settings?.paths?.userDataRoot || '';
  const restrictTags = $('#restrictTags'); if (restrictTags) restrictTags.checked = !!settings.restrictTags;
  const allowedTags = $('#allowedTags'); if (allowedTags) allowedTags.value = settings.allowedTags || '';
  const nsfwBrowserMode = $('#nsfwBrowserMode'); if (nsfwBrowserMode) nsfwBrowserMode.value = settings.nsfwBrowserMode || 'show';
  const nsfwTags = $('#nsfwTags'); if (nsfwTags) nsfwTags.value = settings.nsfwTags || 'NSFW';
  const mobileServerEnabled = $('#mobileServerEnabled'); if (mobileServerEnabled) mobileServerEnabled.checked = !!settings.mobileServerEnabled;
  const mobileServerHost = $('#mobileServerHost'); if (mobileServerHost) mobileServerHost.value = settings.mobileServerHost || '0.0.0.0';
  const mobileServerPort = $('#mobileServerPort'); if (mobileServerPort) mobileServerPort.value = settings.mobileServerPort || 8787;
  const mobileServerAccessCode = $('#mobileServerAccessCode'); if (mobileServerAccessCode) mobileServerAccessCode.value = settings.mobileServerAccessCode || '';
  refreshMobileServerStatus(false);
  const ideaRandomMax = $('#ideaGeneratorRandomMaxChoices'); if (ideaRandomMax) ideaRandomMax.value = Math.max(1, Math.min(20, Number(settings.ideaGeneratorRandomMaxChoices || DEFAULT_IDEA_RANDOM_MAX_CHOICES)));
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
  if ($('#sdImageCount')) $('#sdImageCount').value = settings.sdImageCount || 4;
  if ($('#exportDestinationFolder')) $('#exportDestinationFolder').value = settings.exportDestinationFolder || '';
  updateCardImagePreview();
  $('#altCount').value = settings.alternateFirstMessages ?? 2;
  const firstCustomStyle = $('#firstCustomStyle'); if (firstCustomStyle) firstCustomStyle.value = settings.firstMessageCustomStyle || '';
  const firstCustomInstructions = $('#firstCustomInstructions'); if (firstCustomInstructions) firstCustomInstructions.value = settings.firstMessageCustomInstructions || '';
  browserTagMerges = cleanBrowserTagMerges(settings.browserTagMerges || {});
  browserVirtualFolders = Array.isArray(settings.browserVirtualFolders) ? settings.browserVirtualFolders : [];
  browserShowSubfolders = !!settings.browserShowSubfolders;
  const showSubfolders = $('#browserShowSubfolders'); if (showSubfolders) showSubfolders.checked = browserShowSubfolders;
  initIdeaSettingsEditor();
  populateIdeaGeneratorOptions();
  updateImportedCardToolsHint();
}


function cleanOutputTabName(value) {
  let name = String(value || '').trim().replace(/^[-*•\s]+/, '').replace(/^["“”]+|["“”]+$/g, '');
  if (!name) return '';
  const beforeParen = name.split(/\s*\(/)[0].trim();
  if (beforeParen && beforeParen.length <= 80) name = beforeParen;
  name = name.split(/\s+(?:often|usually|sometimes|also|aka|a\.k\.a\.|known as|who )\b/i)[0].trim();
  name = name.split(/\s*[,;]\s*/)[0].trim();
  return name.slice(0, 80);
}

function isDividerLine(value) {
  const raw = String(value || '').trim();
  return !!raw && /^[-_=*~]{3,}$/.test(raw);
}

function isGenericOutputName(value) {
  const cleaned = cleanOutputTabName(value).toLowerCase();
  return !cleaned || ['character', 'characters', 'character card', 'new character', 'untitled', 'unknown'].includes(cleaned);
}

function extractOutputNameForTab(output) {
  const text = String(output || '');
  const lines = text.split(/\r?\n/);
  const stopHeadings = /^(description|personality|scenario|first message|alternative first messages|example dialogues|lorebook entries|tags|state tracking|stable diffusion prompt)$/i;

  for (let i = 0; i < lines.length; i += 1) {
    const raw = String(lines[i] || '').trim();
    if (!raw || isDividerLine(raw)) continue;
    const inline = raw.match(/^name\s*[:：-]\s*(.+)$/i);
    if (inline) {
      const name = cleanOutputTabName(inline[1]);
      if (name && !isGenericOutputName(name)) return name;
    }
    const heading = raw.replace(/^[#*`\s]+|[#*`\s]+$/g, '').trim();
    if (/^name$/i.test(heading)) {
      for (let j = i + 1; j < lines.length; j += 1) {
        const cand = String(lines[j] || '').trim();
        if (!cand || isDividerLine(cand)) continue;
        const nextHeading = cand.replace(/^[#*`\s]+|[#*`\s]+$/g, '').trim();
        if (stopHeadings.test(nextHeading)) break;
        const name = cleanOutputTabName(cand);
        if (name && !isGenericOutputName(name)) return name;
        break;
      }
    }
  }

  const inline = text.match(/^\s*Name\s*[:：-]\s*(.+)$/im);
  if (inline) return cleanOutputTabName(inline[1]);
  return '';
}

function applyLoadedState(state, options = {}) {
  currentLoadedType = String(state?.loadedType || "");
  if (options && options.appendOutputTab) {
    appendLoadedStateToOutputTabs(state, options);
    updateImportedCardToolsHint();
    updateAvailability();
    return;
  }
  if (!settings) settings = collectSettings();

  const savedTabs = Array.isArray(state.characterTabs)
    ? state.characterTabs.filter(tab => tab && typeof tab === 'object' && loadedOutputTextFromTab(tab))
    : [];

  if (savedTabs.length) {
    characterOutputTabs = savedTabs.map((tab, idx) => ({
      ...makeBlankOutputTab(tab.name || tab.focusName || `Character ${idx + 1}`),
      ...tab,
      output: loadedOutputTextFromTab(tab),
      fullTextOutput: loadedOutputTextFromTab(tab),
      name: tab.name || tab.focusName || extractOutputNameForTab(loadedOutputTextFromTab(tab) || '') || `Character ${idx + 1}`,
      focusName: tab.focusName || tab.name || `Character ${idx + 1}`,
      qaAnswers: loadedQaTextFromTab(tab),
      qnaAnswers: loadedQaTextFromTab(tab),
      cardImagePath: tab.cardImagePath || tab.imagePath || '',
      projectPath: canonicalWorkspaceProjectPath(tab.projectPath || tab.workspaceProjectPath || state.projectPath || ''),
      workspaceProjectPath: canonicalWorkspaceProjectPath(tab.projectPath || tab.workspaceProjectPath || state.projectPath || ''),
    }));
  } else {
    characterOutputTabs = [{
      ...makeBlankOutputTab(state.name || extractOutputNameForTab(state.output || '') || 'Character'),
      output: loadedOutputTextFromState(state, {}),
      qaAnswers: loadedQaTextFromState(state, {}),
      qnaAnswers: loadedQaTextFromState(state, {}),
      emotionImages: loadedImageListFromState(state, 'emotionImages', {}),
      generatedImages: loadedImageListFromState(state, 'generatedImages', {}),
      cardImagePath: state.imagePath || state.cardImagePath || '',
      projectPath: canonicalWorkspaceProjectPath(state.projectPath || ''),
      workspaceProjectPath: canonicalWorkspaceProjectPath(state.projectPath || ''),
    }];
  }

  conceptWorkspaceTabs = characterOutputTabs.map((tab, idx) => makeConceptTabFromWorkspaceState(state, idx, tab.name || `Concept ${idx + 1}`));
  manualGuideTabs = characterOutputTabs.map((tab, idx) => makeManualTabFromWorkspaceState(state, idx, tab.name || `Manual ${idx + 1}`));

  const loadedIdx = Math.max(0, characterOutputTabs.findIndex(tab => loadedOutputTextFromTab(tab) === loadedOutputTextFromState(state, tab)));
  activeOutputTabIndex = loadedIdx >= 0 ? loadedIdx : 0;
  activeConceptTabIndex = activeOutputTabIndex;
  activeManualGuideTabIndex = activeOutputTabIndex;
  ensureLinkedWorkspaceTabs();

  currentBrowserDescription = state.browserDescription || state.libraryDescription || '';
  currentCardRating = state.cardRating || '';
  currentCardRatingReasoning = state.cardRatingReasoning || '';
  currentCardRatingDetails = Array.isArray(state.cardRatingDetails) ? state.cardRatingDetails : [];
  currentCardRatingSourceHash = state.cardRatingSourceHash || '';

  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  applyActiveConceptTab();
  applyActiveManualTab();
  updateImportedCardToolsHint();
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

function normalizeRecentModels(list = []) {
  const out = [];
  const seen = new Set();
  (Array.isArray(list) ? list : []).forEach(item => {
    const name = cleanModelName(typeof item === 'string' ? item : (item?.name || item?.model || item?.id || ''));
    if (!name) return;
    const key = name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    const entry = { name, lastUsed: Number(item?.lastUsed || item?.last_used || 0) || 0 };
    const inTok = Number(item?.maxInputTokens || item?.max_input_tokens || 0);
    const outTok = Number(item?.maxOutputTokens || item?.max_output_tokens || 0);
    if (inTok > 0) entry.maxInputTokens = inTok;
    if (outTok > 0) entry.maxOutputTokens = outTok;
    out.push(entry);
  });
  out.sort((a,b) => (Number(b.lastUsed||0) - Number(a.lastUsed||0)) || a.name.localeCompare(b.name));
  return out.slice(0, 30);
}

function touchRecentModel(name, tokenInfo = {}) {
  name = cleanModelName(name);
  if (!name) return;
  const key = name.toLowerCase();
  const now = Date.now() / 1000;
  const existingItems = normalizeRecentModels(recentModels);
  const previous = existingItems.find(item => item.name.toLowerCase() === key) || {};
  const existing = existingItems.filter(item => item.name.toLowerCase() !== key);
  const entry = { name, lastUsed: now };
  const inTok = Number(tokenInfo.maxInputTokens || tokenInfo.max_input_tokens || previous.maxInputTokens || 0);
  const outTok = Number(tokenInfo.maxOutputTokens || tokenInfo.max_output_tokens || previous.maxOutputTokens || 0);
  if (inTok > 0) entry.maxInputTokens = inTok;
  if (outTok > 0) entry.maxOutputTokens = outTok;
  recentModels = normalizeRecentModels([entry, ...existing]);
  renderRecentModelDropdown($('#model')?.value || '', false);
}

function currentModelTokenInfoFromFields() {
  return {
    maxInputTokens: Number($('#maxInputTokens')?.value || 0),
    maxOutputTokens: Number($('#maxOutputTokens')?.value || 0),
  };
}

async function rememberCurrentModel(saveNow = false) {
  const name = cleanModelName($('#model')?.value || '');
  if (!name) return;
  const tokenInfo = currentModelTokenInfoFromFields();
  touchRecentModel(name, tokenInfo);
  const api = window.pywebview?.api || {};
  if (saveNow && (api.remember_recent_model || api.rememberRecentModel || api.save_settings)) {
    try {
      settings = collectSettings();
      const rememberFn = api.remember_recent_model || api.rememberRecentModel;
      const res = rememberFn
        ? await rememberFn(settings, name, tokenInfo)
        : await api.save_settings(settings);
      if (res?.settings) settings = res.settings;
      recentModels = normalizeRecentModels(res?.recentModels || settings.recentModels || recentModels);
      renderRecentModelDropdown($('#model')?.value || '', false);
      updateModelTokenHint();
    } catch (_) {}
  }
}

function recentModelTokenInfo(name) {
  const key = cleanModelName(name).toLowerCase();
  return normalizeRecentModels(recentModels).find(item => item.name.toLowerCase() === key) || null;
}

function renderRecentModelDropdown(filter = '', show = true) {
  const panel = $('#recentModelDropdown');
  if (!panel) return;
  const term = cleanModelName(filter).toLowerCase();
  const items = normalizeRecentModels(recentModels)
    .filter(item => !term || item.name.toLowerCase().includes(term))
    .slice(0, 25);
  panel.innerHTML = '';
  if (!items.length || !show) {
    panel.classList.add('hidden');
    return;
  }
  items.forEach(item => {
    const div = document.createElement('div');
    div.className = 'model-suggestion-item';
    div.innerHTML = `<div class="model-name">${escapeHtml(item.name)}</div><div class="model-meta">${item.maxInputTokens ? `Input ${item.maxInputTokens.toLocaleString()} tokens` : 'No token metadata yet'}${item.maxOutputTokens ? ` · Output ${item.maxOutputTokens.toLocaleString()}` : ''}</div>`;
    div.addEventListener('mousedown', e => {
      e.preventDefault();
      $('#model').value = item.name;
      if (item.maxInputTokens) $('#maxInputTokens').value = item.maxInputTokens;
      if (item.maxOutputTokens) $('#maxOutputTokens').value = item.maxOutputTokens;
      updateModelTokenHint(`Using recent model: ${item.name}`);
      panel.classList.add('hidden');
      settings = collectSettings();
      try { window.pywebview.api.save_settings(settings); } catch (_) {}
    });
    panel.appendChild(div);
  });
  panel.classList.remove('hidden');
}

function updateModelTokenHint(text = '') {
  const hint = $('#modelTokenHint');
  if (!hint) return;
  if (text) { hint.textContent = text; return; }
  const info = recentModelTokenInfo($('#model')?.value || '');
  if (info?.maxInputTokens || info?.maxOutputTokens) {
    hint.textContent = `Remembered limits: ${info.maxInputTokens ? `${info.maxInputTokens.toLocaleString()} input` : 'unknown input'}${info.maxOutputTokens ? ` / ${info.maxOutputTokens.toLocaleString()} output` : ''} tokens.`;
  } else {
    hint.textContent = 'Recent models appear as you type. Nano-GPT token limits can be fetched automatically.';
  }
}

function setModelTokenResult(text = '', kind = '') {
  const box = $('#modelTokenResultBox');
  if (!box) return;
  box.textContent = text || 'No token fetch run in this window yet.';
  box.classList.remove('ok', 'error', 'warning');
  if (kind) box.classList.add(kind);
}

async function copyTokenDebugSummary() {
  const logText = $('#debugLogText')?.value || '';
  const boxText = $('#modelTokenResultBox')?.textContent || '';
  const summary = [boxText, '', logText].filter(Boolean).join('\n');
  try {
    await navigator.clipboard.writeText(summary || 'No token debug text loaded yet.');
    setStatus('Token debug copied to clipboard.', 'ok');
  } catch (err) {
    setStatus('Could not copy token debug: ' + (err?.message || String(err)), 'error');
  }
}

async function showTokenDebugLog() {
  // Switch visibly to Output / Editor → Debug Log, then force-read the backend log.
  $$('.nav').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === 'output'));
  $$('.tab').forEach(panel => panel.classList.toggle('active', panel.id === 'output'));
  const group = $('.subtabs[data-subtab-group="output"]');
  if (group) $$('.subtab', group).forEach(btn => btn.classList.toggle('active', btn.dataset.subtab === 'output-debug'));
  $$('[data-subtab-panel="output"]').forEach(panel => panel.classList.toggle('active', panel.id === 'output-debug'));
  await refreshDebugLog(true);
  const log = $('#debugLogText');
  if (log) log.scrollTop = log.scrollHeight;
  setStatus('Debug Log loaded. Latest token fetch entries are at the bottom.', 'ok');
}

function isNanoGptBaseUrl(value) {
  return /nano[-.]?gpt/i.test(String(value || ''));
}

async function writeClientDebugEvent(event, payload = {}) {
  try {
    const api = window.pywebview?.api || {};
    const fn = api.append_debug_event || api.appendDebugEvent;
    if (!fn) return;
    await fn(event, {
      page: 'frontend',
      version: appVersion,
      ...(payload || {}),
    });
  } catch (_) {
    // Debug logging must never break the user's action.
  }
}

async function fetchModelTokenLimits(auto = false) {
  const modelValue = ($('#model')?.value || '').trim();
  const baseValue = ($('#apiBaseUrl')?.value || '').trim();
  setModelTokenResult(auto ? `Auto-checking token limits for ${modelValue || '(blank model)'}…` : `Fetching token limits for ${modelValue || '(blank model)'}…`, 'warning');
  await writeClientDebugEvent('client_model_token_fetch_invoked', {
    auto,
    hasModel: !!modelValue,
    model: modelValue,
    hasApiBaseUrl: !!baseValue,
    apiBaseUrl: baseValue,
    isNanoGptBaseUrl: isNanoGptBaseUrl(baseValue),
  });
  if (!modelValue || !baseValue) {
    const reason = !modelValue && !baseValue ? 'missing model and API base URL' : (!modelValue ? 'missing model' : 'missing API base URL');
    await writeClientDebugEvent('client_model_token_fetch_skipped', { auto, reason });
    setModelTokenResult(`Cannot fetch token limits: ${reason}.`, 'error');
    if (!auto) setStatus(`Cannot fetch token limits: ${reason}.`, 'error');
    try { refreshDebugLog(true); } catch (_) {}
    return;
  }
  if (auto && !isNanoGptBaseUrl(baseValue)) {
    await writeClientDebugEvent('client_model_token_fetch_skipped', { auto, reason: 'auto fetch only runs for Nano-GPT base URLs', apiBaseUrl: baseValue });
    setModelTokenResult('Auto token fetch skipped: API Base URL is not Nano-GPT.', 'warning');
    try { refreshDebugLog(true); } catch (_) {}
    return;
  }
  try {
    await rememberCurrentModel(!auto);
    if (!auto) setStatus('Fetching model token limits…', '');
    const localSettings = { ...collectSettings(), model: modelValue };
    const api = window.pywebview?.api || {};
    const fn = api.fetch_model_token_limits || api.fetchModelTokenLimits;
    if (!fn) {
      await writeClientDebugEvent('client_model_token_fetch_backend_missing', {
        availableApiMethods: Object.keys(api).sort().slice(0, 120),
      });
      setModelTokenResult('Backend token fetch method is missing. This usually means the running app/AppImage is still old.', 'error');
      throw new Error('Model metadata fetch backend is not available. Restart the app after updating.');
    }
    await writeClientDebugEvent('client_model_token_fetch_backend_call_start', { auto, model: modelValue, apiBaseUrl: baseValue });
    const res = await fn(localSettings);
    await writeClientDebugEvent('client_model_token_fetch_backend_result', {
      ok: !!res?.ok,
      error: res?.error || '',
      model: res?.model || '',
      maxInputTokens: res?.maxInputTokens || 0,
      maxOutputTokens: res?.maxOutputTokens || 0,
      sourceEndpoint: res?.sourceEndpoint || '',
      fetchMethod: res?.fetchMethod || '',
      searchedEndpoints: Array.isArray(res?.searchedEndpoints) ? res.searchedEndpoints : [],
      endpointErrors: Array.isArray(res?.endpointErrors) ? res.endpointErrors.slice(0, 8) : [],
      fetchAttempts: Array.isArray(res?.fetchAttempts) ? res.fetchAttempts : [],
      debugLogPath: res?.debugLogPath || '',
    });
    if (!res.ok) {
      if (!auto) throw new Error(res.error || 'Could not fetch token limits.');
      updateModelTokenHint(res.error || 'Could not fetch token limits automatically.');
      return;
    }
    if (res.maxInputTokens) {
      const inputEl = $('#maxInputTokens');
      if (inputEl) {
        inputEl.value = String(res.maxInputTokens);
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        inputEl.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    if (res.maxOutputTokens) {
      const outputEl = $('#maxOutputTokens');
      if (outputEl) {
        outputEl.value = String(res.maxOutputTokens);
        outputEl.dispatchEvent(new Event('input', { bubbles: true }));
        outputEl.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    touchRecentModel(res.model || modelValue, res);
    settings = collectSettings();
    try {
      const saveRes = await window.pywebview.api.save_settings(settings);
      if (saveRes?.settings) settings = saveRes.settings;
    } catch (_) {}
    recentModels = normalizeRecentModels(res.recentModels || settings.recentModels || recentModels);
    const resultText = `Fetched limits for ${res.model || modelValue}: ${res.maxInputTokens ? res.maxInputTokens.toLocaleString() + ' input' : 'unknown input'}${res.maxOutputTokens ? ' / ' + res.maxOutputTokens.toLocaleString() + ' output' : ''} tokens.`;
    updateModelTokenHint(resultText);
    setModelTokenResult(resultText, 'ok');
    const resultBox = $('#modelTokenResultBox');
    if (resultBox) resultBox.title = res.debugLogPath ? `Debug log: ${res.debugLogPath}` : '';
    await refreshDebugLog(true);
    if (!auto) setStatus('Fetched model token limits and wrote diagnostics.', 'ok');
  } catch (err) {
    await writeClientDebugEvent('client_model_token_fetch_exception', {
      auto,
      message: err?.message || String(err),
      stack: String(err?.stack || '').slice(0, 4000),
    });
    setModelTokenResult(err?.message || String(err), 'error');
    if (!auto) setStatus(err.message || String(err), 'error');
  } finally {
    try { refreshDebugLog(true); } catch (_) {}
  }
}

function scheduleAutoModelTokenFetch() {
  clearTimeout(modelTokenFetchTimer);
  modelTokenFetchTimer = setTimeout(() => fetchModelTokenLimits(true), 900);
}

function collectSettings() {
  // v1.0.6 critical fix: the Card Mode dropdown is the source of truth.
  // Previously a stale hidden/shared-scene value of "split_cards" could force
  // cardMode back to split even after the user changed Card Mode to Single.
  // That caused normal single-card generations to split into multiple cards.
  const rawCardMode = ($('#cardMode') ? $('#cardMode').value : 'single');
  let selectedCardMode = ['single', 'multi', 'split_cards'].includes(rawCardMode) ? rawCardMode : 'single';
  let selectedSharedScenePolicy = ($('#sharedScenePolicy') ? $('#sharedScenePolicy').value : 'ai_reconcile');
  if (selectedCardMode === 'single') {
    selectedSharedScenePolicy = 'ai_reconcile';
  } else if (selectedCardMode === 'split_cards') {
    selectedSharedScenePolicy = 'split_cards';
  } else if (selectedSharedScenePolicy === 'split_cards') {
    // Split is now represented by Card Mode itself. If the user changes back
    // to multi-card-single-output, clear the stale split scene policy.
    selectedSharedScenePolicy = 'ai_reconcile';
  }
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
    streamAi: !!($('#streamAi') && $('#streamAi').checked),
    frontPorchExportTarget: ($('#frontPorchExportTarget') ? $('#frontPorchExportTarget').value : 'stable'),
    frontPorchStableDataFolder: ($('#frontPorchStableDataFolder') ? $('#frontPorchStableDataFolder').value.trim() : ''),
    frontPorchBetaDataFolder: ($('#frontPorchBetaDataFolder') ? $('#frontPorchBetaDataFolder').value.trim() : ''),
    frontPorchDataFolder: (($('#frontPorchExportTarget') && $('#frontPorchExportTarget').value === 'beta') ? ($('#frontPorchBetaDataFolder') ? $('#frontPorchBetaDataFolder').value.trim() : '') : ($('#frontPorchStableDataFolder') ? $('#frontPorchStableDataFolder').value.trim() : '')),
    dataFilesFolder: ($('#dataFilesFolder') ? $('#dataFilesFolder').value.trim() : ''),
    restrictTags: !!($('#restrictTags') && $('#restrictTags').checked),
    allowedTags: ($('#allowedTags') ? $('#allowedTags').value.trim() : ''),
    nsfwBrowserMode: ($('#nsfwBrowserMode') ? $('#nsfwBrowserMode').value : 'show'),
    nsfwTags: ($('#nsfwTags') ? $('#nsfwTags').value.trim() : 'NSFW'),
    ideaGeneratorRandomMaxChoices: Math.max(1, Math.min(20, Number(($('#ideaGeneratorRandomMaxChoices') ? $('#ideaGeneratorRandomMaxChoices').value : DEFAULT_IDEA_RANDOM_MAX_CHOICES) || DEFAULT_IDEA_RANDOM_MAX_CHOICES))),
    sdBaseUrl: $('#sdBaseUrl').value.trim() || 'http://127.0.0.1:7860',
    sdModel: ($('#sdModel') ? $('#sdModel').value.trim() : ''),
    sdSteps: Number($('#sdSteps').value || 28),
    sdCfgScale: Number($('#sdCfgScale').value || 7),
    sdSampler: $('#sdSampler').value.trim() || 'Euler a',
    sdImageCount: Math.max(1, Math.min(16, Number(($('#sdImageCount') ? $('#sdImageCount').value : 4) || 4))),
    mode: $('#modeSelect').value,
    cardMode: selectedCardMode,
    multiCharacterCount: Number($('#multiCharacterCount').value || 2),
    sharedScenePolicy: selectedSharedScenePolicy,
    frontend: 'front_porch',
    exportFormat: ($('#exportFormat') ? $('#exportFormat').value : 'chara_v2_png') || 'chara_v2_png',
    exportDestinationFolder: ($('#exportDestinationFolder') ? $('#exportDestinationFolder').value.trim() : ''),
    cardImagePath: $('#cardImagePath').value.trim(),
    firstMessageStyle: $('#firstStyle').value,
    firstMessageCustomStyle: ($('#firstCustomStyle') ? $('#firstCustomStyle').value.trim() : ''),
    firstMessageCustomInstructions: ($('#firstCustomInstructions') ? $('#firstCustomInstructions').value.trim() : ''),
    alternateFirstMessages: Number($('#altCount').value || 0),
    alternateFirstMessageStyles: $$(`[data-alt-style-index]`).map(el => el.value),
    alternateFirstMessageCustomStyles: $$(`[data-alt-custom-style-index]`).map(el => el.value.trim()),
    alternateFirstMessageInstructions: $$(`[data-alt-instructions-index]`).map(el => el.value.trim()),
    emotionImageEmotions: $$('#emotionOptions input:checked').map(el => el.value),
    browserTagMerges: browserTagMerges || {},
    browserVirtualFolders: browserVirtualFolders || [],
    browserShowSubfolders: !!browserShowSubfolders,
    mobileServerEnabled: !!($('#mobileServerEnabled') && $('#mobileServerEnabled').checked),
    mobileServerHost: ($('#mobileServerHost') ? $('#mobileServerHost').value.trim() : '0.0.0.0') || '0.0.0.0',
    mobileServerPort: Number(($('#mobileServerPort') ? $('#mobileServerPort').value : 8787) || 8787),
    mobileServerAccessCode: ($('#mobileServerAccessCode') ? $('#mobileServerAccessCode').value.trim() : ''),
    recentModels: normalizeRecentModels(recentModels),
    ...collectIdeaSettingsEditorState(settings || {}),
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
    return `AI settings are incomplete: ${missing.join(', ')}. Open Settings and re-enter your endpoint/model/key before generating or revising.`;
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
    return `Vision settings are incomplete: ${missing.join(', ')}. Open Settings and re-enter your vision model/key before analyzing an image.`;
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

function firstMessageStyleLabel(key, label) {
  if (key === 'custom') return 'Custom style…';
  return key.replaceAll('_', ' ') + ' — ' + String(label || '').split(':')[0];
}

function updateFirstMessageCustomVisibility() {
  const panel = $('#firstMessageOptionsPanel');
  if (!panel) return;
  const isCustom = ($('#firstStyle')?.value || '') === 'custom';
  panel.classList.toggle('custom-style-active', isCustom);
}

function renderStyles() {
  const select = $('#firstStyle');
  if (!select) return;
  select.innerHTML = '';
  for (const [key, label] of Object.entries(styles || {})) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = firstMessageStyleLabel(key, label);
    select.appendChild(opt);
  }
  const custom = document.createElement('option');
  custom.value = 'custom';
  custom.textContent = 'Custom style…';
  select.appendChild(custom);
  select.value = settings.firstMessageStyle || 'cinematic';
  if (!select.value) select.value = 'cinematic';
  updateFirstMessageCustomVisibility();
  renderAltStyleRows();
}

function renderAltStyleRows() {
  const holder = $('#altStyleRows');
  if (!holder) return;
  holder.innerHTML = '';
  const count = Number($('#altCount')?.value || settings.alternateFirstMessages || 0);
  const selected = settings.alternateFirstMessageStyles || [];
  const customStyles = settings.alternateFirstMessageCustomStyles || [];
  const instructions = settings.alternateFirstMessageInstructions || [];
  for (let i = 0; i < count; i++) {
    const row = document.createElement('div');
    row.className = 'alt-style-row alt-style-grid';
    const label = document.createElement('label');
    label.textContent = `Alternative First Message ${i + 1} Style`;
    const select = document.createElement('select');
    select.dataset.altStyleIndex = String(i);
    const same = document.createElement('option');
    same.value = '';
    same.textContent = `Same as main`;
    select.appendChild(same);
    for (const [key, value] of Object.entries(styles || {})) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = firstMessageStyleLabel(key, value);
      select.appendChild(opt);
    }
    const custom = document.createElement('option');
    custom.value = 'custom';
    custom.textContent = 'Custom style…';
    select.appendChild(custom);
    select.value = selected[i] || '';
    label.appendChild(select);
    row.appendChild(label);

    const customLabel = document.createElement('label');
    customLabel.textContent = 'Custom Style Name';
    const customInput = document.createElement('input');
    customInput.dataset.altCustomStyleIndex = String(i);
    customInput.placeholder = 'Cold, time skip, jealous...';
    customInput.value = customStyles[i] || '';
    customLabel.appendChild(customInput);
    row.appendChild(customLabel);

    const instLabel = document.createElement('label');
    instLabel.textContent = 'Custom Instructions';
    const inst = document.createElement('textarea');
    inst.dataset.altInstructionsIndex = String(i);
    inst.placeholder = 'Example: This greeting happens two months later after the first greeting.';
    inst.value = instructions[i] || '';
    instLabel.appendChild(inst);
    row.appendChild(instLabel);
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
  renderManualGuide();
}


function manualGuidePages() {
  return [
    { id: 'description', title: 'Description', hint: 'Name plus visual/description sections from the active prompt template.', panels: ['sectionsDescription'], sectionIds: ['name', 'description'] },
    { id: 'personality', title: 'Personality', hint: 'Personality, behavior, relationship, backstory, and any custom Personality template sections.', panels: ['sectionsPersonality'], sectionIds: ['personality'] },
    { id: 'scenario', title: 'Scenario', hint: 'The starting situation and immediate roleplay context.', panels: ['sectionsScenario'], sectionIds: ['scenario'] },
    { id: 'first', title: 'First Message(s)', hint: 'Main first message plus optional alternative openings.', panels: ['sectionsFirst'], sectionIds: ['first_message', 'alternate_first_messages'] },
    { id: 'examples', title: 'Example Dialogues', hint: 'Example dialogue and lorebook-style supporting entries if your template has them.', panels: ['sectionsExamples'], sectionIds: ['example_dialogues', 'lorebook'] },
    { id: 'tagsSystem', title: 'Tags and System Prompt', hint: 'Tags plus optional custom system prompt / behavior rules.', panels: ['sectionsTagsSystem'], sectionIds: ['tags', 'system_prompt'] },
    { id: 'stateSd', title: 'State Tracking and Stable Diffusion Prompt', hint: 'Optional Front Porch state values and image-generation prompt fields.', panels: ['sectionsStateSd'], sectionIds: ['state_tracking', 'stable_diffusion'] },
  ];
}

function manualGuideSectionKey(section) {
  return String(section?.id || section?.title || uid()).trim() || uid();
}

function ensureManualGuideSectionState(section) {
  const key = manualGuideSectionKey(section);
  if (!manualGuideState[key]) manualGuideState[key] = { include: section?.enabled !== false, body: '', fields: {} };
  if (typeof manualGuideState[key].include !== 'boolean') manualGuideState[key].include = section?.enabled !== false;
  if (!manualGuideState[key].fields || typeof manualGuideState[key].fields !== 'object') manualGuideState[key].fields = {};
  (section?.fields || []).forEach(field => {
    const fid = String(field?.id || field?.label || uid());
    if (manualGuideState[key].fields[fid] === undefined) manualGuideState[key].fields[fid] = '';
  });
  if (isManualAlternateFirstMessagesSection(section)) ensureManualAlternateMessagesState(section, manualGuideState[key]);
  return manualGuideState[key];
}

function manualGuideSectionsForPage(page) {
  if (!template || !Array.isArray(template.sections)) return [];
  const used = new Set();
  const wantedPanels = new Set(page.panels || []);
  const wantedIds = new Set(page.sectionIds || []);
  const sections = [];
  (template.sections || []).forEach(section => {
    const sid = String(section.id || '');
    const panel = sectionTemplatePanel(section);
    if (wantedIds.has(sid) || wantedPanels.has(panel)) {
      const key = manualGuideSectionKey(section);
      if (!used.has(key)) {
        used.add(key);
        sections.push(section);
      }
    }
  });
  return sections;
}

function manualGuideUsesLargeText(page) {
  return ['scenario', 'first', 'examples'].includes(String(page?.id || ''));
}

function isManualSystemPromptSection(section) {
  const sid = String(section?.id || '').toLowerCase();
  const title = String(section?.title || '').toLowerCase();
  return sid === 'system_prompt' || title.includes('system prompt');
}

function isManualStateTrackingSection(section) {
  const sid = String(section?.id || '').toLowerCase();
  const title = String(section?.title || '').toLowerCase();
  return sid === 'state_tracking' || title.includes('state tracking');
}

function manualGuideFieldIdentity(field) {
  const id = String(field?.id || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const label = String(field?.label || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return { id, label, combined: `${id} ${label}`.trim() };
}

function manualGuideSpecialControlForField(section, field) {
  if (!isManualStateTrackingSection(section)) return null;
  const ident = manualGuideFieldIdentity(field);
  const name = ident.combined;
  if (ident.id === 'short_term_bond' || name.includes('short_term_bond')) {
    return { type: 'range', min: -300, max: 300, step: 1, defaultValue: 0 };
  }
  if (ident.id === 'long_term_bond' || name.includes('long_term_bond')) {
    return { type: 'range', min: -300, max: 300, step: 1, defaultValue: 0 };
  }
  if (ident.id === 'trust_level' || name.includes('trust_level')) {
    return { type: 'range', min: -100, max: 100, step: 1, defaultValue: 0 };
  }
  if (ident.id === 'time_of_day' || name.includes('time_of_day')) {
    return { type: 'select', options: [
      { value: '', label: 'Unset' },
      { value: 'morning', label: 'Morning' },
      { value: 'noon', label: 'Noon' },
      { value: 'afternoon', label: 'Afternoon' },
      { value: 'late afternoon', label: 'Late Afternoon' },
      { value: 'evening', label: 'Evening' },
      { value: 'night', label: 'Night' },
    ]};
  }
  if (ident.id === 'day_of_week' || name.includes('day_of_week')) {
    return { type: 'select', options: [
      { value: '', label: 'Unset / legacy' },
      { value: '1', label: 'Monday (1)' },
      { value: '2', label: 'Tuesday (2)' },
      { value: '3', label: 'Wednesday (3)' },
      { value: '4', label: 'Thursday (4)' },
      { value: '5', label: 'Friday (5)' },
      { value: '6', label: 'Saturday (6)' },
      { value: '7', label: 'Sunday (7)' },
    ]};
  }
  return null;
}

function manualGuideDisplayValueForField(section, field, value) {
  const control = manualGuideSpecialControlForField(section, field);
  const raw = String(value || '').trim();
  if (!raw || !control) return raw;
  if (control.type === 'select') {
    const match = (control.options || []).find(opt => String(opt.value) === raw);
    return match && match.value ? match.label : raw;
  }
  return raw;
}

function manualGuideSectionUsesLargeText(section, page) {
  return manualGuideUsesLargeText(page) || isManualSystemPromptSection(section);
}

function manualGuideSectionUsesFullWidth(section, page) {
  return manualGuideSectionUsesLargeText(section, page);
}

function isManualAlternateFirstMessagesSection(section) {
  const sid = String(section?.id || '').toLowerCase();
  const title = String(section?.title || '').toLowerCase();
  return sid === 'alternate_first_messages' || sid === 'alternative_first_messages' || title.includes('alternative first message') || title.includes('alternate first message');
}

function ensureManualAlternateMessagesState(section, state = null) {
  const key = manualGuideSectionKey(section);
  const target = state || (manualGuideState[key] || (manualGuideState[key] = { include: section?.enabled !== false, body: '', fields: {} }));
  if (!Array.isArray(target.alternates)) {
    target.alternates = [];
    const oldBody = String(target.body || '').trim();
    if (oldBody) target.alternates.push(oldBody);
  }
  target.alternates = target.alternates.map(value => String(value || ''));
  return target.alternates;
}

function manualGuideAlternateMessagesMarkup(section, state) {
  const key = manualGuideSectionKey(section);
  const alternates = ensureManualAlternateMessagesState(section, state);
  const rows = alternates.map((value, index) => `
    <div class="manual-alt-message-card" data-manual-alt-card="${escapeAttr(index)}">
      <div class="manual-alt-message-head">
        <strong>Alternative First Message ${index + 1}</strong>
        <button type="button" class="danger-ghost small manual-alt-remove" data-manual-section="${escapeAttr(key)}" data-manual-alt-index="${escapeAttr(index)}">Remove</button>
      </div>
      <textarea class="manual-guide-input manual-guide-large manual-alt-message-input" data-manual-section="${escapeAttr(key)}" data-manual-alt-index="${escapeAttr(index)}" rows="8" placeholder="Write alternative first message ${index + 1}...">${escapeText(value || '')}</textarea>
    </div>
  `).join('');
  const empty = alternates.length ? '' : '<div class="empty manual-alt-empty">No alternative first messages added yet. Use the button below to add one.</div>';
  return `
    <div class="manual-alt-message-list">
      ${rows || empty}
    </div>
    <div class="manual-alt-actions">
      <button type="button" class="ghost manual-alt-add" data-manual-section="${escapeAttr(key)}">+ Add Alternative First Message</button>
    </div>
  `;
}

function manualGuideSpecialInputMarkup({ key, fieldId = '', field = null, section = null, value = '', label = '', hint = '', placeholder = '', control = null, extraClass = '' }) {
  if (!control) return '';
  const safeValue = String(value ?? '');
  if (control.type === 'range') {
    const currentValue = safeValue.trim() === '' ? String(control.defaultValue ?? 0) : safeValue;
    const displayValue = safeValue.trim() === '' ? currentValue : safeValue;
    return `
      <div class="manual-field-label manual-slider-field ${extraClass}">
        <div class="manual-field-title-row">
          <span>${escapeText(label)}</span>
          <span class="manual-slider-value" data-manual-slider-value-for="${escapeAttr(key)}:${escapeAttr(fieldId)}">${escapeText(displayValue)}</span>
        </div>
        ${hint ? `<span class="manual-field-hint">${escapeText(hint)}</span>` : ''}
        <input type="range" class="manual-guide-input manual-guide-slider" data-manual-section="${escapeAttr(key)}" data-manual-field="${escapeAttr(fieldId)}" data-manual-slider="1" min="${escapeAttr(control.min)}" max="${escapeAttr(control.max)}" step="${escapeAttr(control.step || 1)}" value="${escapeAttr(currentValue)}" />
        <div class="manual-slider-scale"><span>${escapeText(control.min)}</span><span>${escapeText(control.max)}</span></div>
      </div>
    `;
  }
  if (control.type === 'select') {
    const options = (control.options || []).map(opt => `<option value="${escapeAttr(opt.value)}" ${String(opt.value) === safeValue ? 'selected' : ''}>${escapeText(opt.label)}</option>`).join('');
    return `
      <label class="manual-field-label manual-select-field ${extraClass}">
        <div class="manual-field-title-row"><span>${escapeText(label)}</span></div>
        ${hint ? `<span class="manual-field-hint">${escapeText(hint)}</span>` : ''}
        <select class="manual-guide-input manual-guide-select" data-manual-section="${escapeAttr(key)}" data-manual-field="${escapeAttr(fieldId)}" aria-label="${escapeAttr(label)}">
          ${options}
        </select>
      </label>
    `;
  }
  return '';
}

function manualGuideInputMarkup({ key, fieldId = '', body = false, value = '', label = '', hint = '', placeholder = '', large = false, expanded = false, extraClass = '' }) {
  const isExpanded = large || expanded;
  const rows = large ? 8 : (expanded ? 5 : 1);
  const compactClass = large ? 'manual-guide-large' : 'manual-guide-compact';
  const expandButton = large ? '' : `<button type="button" class="ghost small manual-expand-toggle" data-manual-section="${escapeAttr(key)}" ${body ? 'data-manual-body-expand="1"' : `data-manual-field-expand="${escapeAttr(fieldId)}"`}>${isExpanded ? 'Collapse' : 'Expand'}</button>`;
  return `
    <div class="manual-field-label ${extraClass}">
      <div class="manual-field-title-row">
        <span>${escapeText(label)}</span>
        ${expandButton}
      </div>
      ${hint ? `<span class="manual-field-hint">${escapeText(hint)}</span>` : ''}
      <textarea class="manual-guide-input ${compactClass} ${isExpanded ? 'expanded' : ''}" data-manual-section="${escapeAttr(key)}" ${body ? 'data-manual-body="1"' : `data-manual-field="${escapeAttr(fieldId)}"`} rows="${rows}" placeholder="${escapeAttr(placeholder)}">${escapeText(value || '')}</textarea>
    </div>
  `;
}

function manualGuideInputRowsForSection(section, state, page) {
  const key = manualGuideSectionKey(section);
  const fields = (section.fields || []).filter(field => field && field.enabled !== false);
  const rows = [];
  const large = manualGuideSectionUsesLargeText(section, page);
  const fullWidth = manualGuideSectionUsesFullWidth(section, page);
  state.expandedFields = state.expandedFields && typeof state.expandedFields === 'object' ? state.expandedFields : {};
  if (isManualAlternateFirstMessagesSection(section)) {
    return manualGuideAlternateMessagesMarkup(section, state);
  }
  if (fields.length) {
    fields.forEach(field => {
      const fid = String(field.id || field.label || uid());
      const control = manualGuideSpecialControlForField(section, field);
      if (control) {
        rows.push(manualGuideSpecialInputMarkup({
          key,
          fieldId: fid,
          field,
          section,
          value: state.fields[fid] || '',
          label: field.label || fid.replace(/_/g, ' '),
          hint: field.hint || '',
          control,
          extraClass: fullWidth ? 'manual-full-width' : '',
        }));
        return;
      }
      rows.push(manualGuideInputMarkup({
        key,
        fieldId: fid,
        value: state.fields[fid] || '',
        label: field.label || fid.replace(/_/g, ' '),
        hint: field.hint || '',
        placeholder: `Fill ${field.label || fid}...`,
        large,
        expanded: !!state.expandedFields[fid],
        extraClass: fullWidth ? 'manual-full-width' : '',
      }));
    });
    rows.push(manualGuideInputMarkup({
      key,
      body: true,
      value: state.body || '',
      label: 'Extra Section Notes',
      hint: 'Optional free text appended to this section after the structured fields.',
      placeholder: `Optional extra notes for ${section.title || 'this section'}...`,
      large,
      expanded: !!state.bodyExpanded,
      extraClass: `manual-extra-notes ${fullWidth ? 'manual-full-width' : ''}`.trim(),
    }));
  } else {
    rows.push(manualGuideInputMarkup({
      key,
      body: true,
      value: state.body || '',
      label: section.title || 'Section Text',
      placeholder: `Write ${section.title || 'this section'} manually...`,
      large,
      expanded: !!state.bodyExpanded,
      extraClass: fullWidth ? 'manual-full-width' : '',
    }));
  }
  return rows.join('');
}

function manualGuideSectionHasContent(section, state) {
  if (!state) return false;
  if (isManualAlternateFirstMessagesSection(section)) {
    return Array.isArray(state.alternates) && state.alternates.some(v => String(v || '').trim());
  }
  if (String(state.body || '').trim()) return true;
  return Object.values(state.fields || {}).some(v => String(v || '').trim());
}

function renderManualGuide(options = {}) {
  const holder = $('#manualGuideContent');
  if (!holder) return;
  const pages = manualGuidePages();
  manualGuidePageIndex = Math.max(0, Math.min(manualGuidePageIndex, pages.length - 1));
  const page = pages[manualGuidePageIndex];
  const title = $('#manualGuidePageTitle');
  const hint = $('#manualGuidePageHint');
  const progress = $('#manualGuideProgress');
  if (title) title.textContent = `Page ${manualGuidePageIndex + 1}: ${page.title}`;
  if (hint) hint.textContent = page.hint || '';
  if (progress) progress.textContent = `Page ${manualGuidePageIndex + 1} / ${pages.length}`;

  const chips = $('#manualGuideChips');
  if (chips) {
    chips.innerHTML = pages.map((p, idx) => `<button type="button" class="manual-guide-chip ${idx === manualGuidePageIndex ? 'active' : ''}" data-manual-page="${idx}">${idx + 1}. ${escapeText(p.title)}</button>`).join('');
    $$('.manual-guide-chip', chips).forEach(btn => btn.addEventListener('click', () => {
      captureManualGuideInputs();
      manualGuidePageIndex = Number(btn.dataset.manualPage || 0);
      renderManualGuide();
    }));
  }

  const sections = manualGuideSectionsForPage(page);
  if (!sections.length) {
    holder.innerHTML = '<div class="empty">No template sections are assigned to this page yet. Add or enable sections in Prompt Template.</div>';
  } else {
    holder.innerHTML = sections.map(section => {
      const key = manualGuideSectionKey(section);
      const state = ensureManualGuideSectionState(section);
      const disabledNote = section.enabled === false ? '<span class="manual-section-badge disabled">disabled in template</span>' : '<span class="manual-section-badge">enabled</span>';
      return `
        <div class="manual-section-card" data-manual-section-card="${escapeAttr(key)}">
          <div class="manual-section-head">
            <div>
              <h3>${escapeText(section.title || key)}</h3>
              ${section.description ? `<p>${escapeText(section.description)}</p>` : ''}
            </div>
            <label class="toggle-inline manual-include-toggle"><input type="checkbox" class="manual-guide-include" data-manual-section="${escapeAttr(key)}" ${state.include ? 'checked' : ''} /> Include</label>
          </div>
          <div class="manual-section-meta">${disabledNote}<span class="manual-section-badge">${escapeText(sectionTemplatePanel(section).replace('sections', '') || 'section')}</span></div>
          <div class="manual-field-grid">
            ${manualGuideInputRowsForSection(section, state, page)}
          </div>
        </div>
      `;
    }).join('');
  }

  bindManualGuideInputs();
  updateManualGuideButtons();
  if (!options.skipPreview) updateManualPreview();
  if (manualGuideTabs[activeManualGuideTabIndex]) {
    manualGuideTabs[activeManualGuideTabIndex].pageIndex = manualGuidePageIndex || 0;
  }
  setTimeout(() => refreshWorkspaceTabScrollButtons('manualWorkspaceTabs'), 0);
}

function bindManualGuideInputs() {
  const commitManualGuideInput = (input) => {
    const key = input.dataset.manualSection;
    if (!key) return;
    const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {} });
    if (input.dataset.manualAltIndex !== undefined) {
      state.alternates = Array.isArray(state.alternates) ? state.alternates : [];
      state.alternates[Number(input.dataset.manualAltIndex || 0)] = input.value;
    } else if (input.dataset.manualBody) state.body = input.value;
    else if (input.dataset.manualField) {
      state.fields[input.dataset.manualField] = input.value;
      if (input.dataset.manualSlider) {
        const valueEl = document.querySelector(`[data-manual-slider-value-for="${CSS.escape(`${key}:${input.dataset.manualField}`)}"]`);
        if (valueEl) valueEl.textContent = input.value;
      }
    }
    updateManualPreview();
  };
  $$('.manual-guide-input').forEach(input => {
    input.addEventListener('input', () => commitManualGuideInput(input));
    input.addEventListener('change', () => commitManualGuideInput(input));
  });
  $$('.manual-guide-include').forEach(input => {
    input.addEventListener('change', () => {
      const key = input.dataset.manualSection;
      if (!key) return;
      const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {} });
      state.include = !!input.checked;
      updateManualPreview();
    });
  });
  $$('.manual-expand-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      captureManualGuideInputs();
      const key = btn.dataset.manualSection;
      if (!key) return;
      const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {}, expandedFields: {} });
      state.expandedFields = state.expandedFields && typeof state.expandedFields === 'object' ? state.expandedFields : {};
      if (btn.dataset.manualBodyExpand) {
        state.bodyExpanded = !state.bodyExpanded;
      } else if (btn.dataset.manualFieldExpand) {
        const fid = btn.dataset.manualFieldExpand;
        state.expandedFields[fid] = !state.expandedFields[fid];
      }
      renderManualGuide();
    });
  });
  $$('.manual-alt-add').forEach(btn => {
    btn.addEventListener('click', () => {
      captureManualGuideInputs();
      const key = btn.dataset.manualSection;
      if (!key) return;
      const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {}, alternates: [] });
      state.alternates = Array.isArray(state.alternates) ? state.alternates : [];
      state.alternates.push('');
      state.include = true;
      renderManualGuide();
      const inputs = $$('.manual-alt-message-input');
      const last = inputs[inputs.length - 1];
      if (last) last.focus();
    });
  });
  $$('.manual-alt-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      captureManualGuideInputs();
      const key = btn.dataset.manualSection;
      const index = Number(btn.dataset.manualAltIndex || 0);
      if (!key) return;
      const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {}, alternates: [] });
      state.alternates = Array.isArray(state.alternates) ? state.alternates : [];
      state.alternates.splice(index, 1);
      renderManualGuide();
    });
  });
}

function captureManualGuideInputs() {
  $$('.manual-guide-input').forEach(input => {
    const key = input.dataset.manualSection;
    if (!key) return;
    const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {} });
    if (input.dataset.manualAltIndex !== undefined) {
      state.alternates = Array.isArray(state.alternates) ? state.alternates : [];
      state.alternates[Number(input.dataset.manualAltIndex || 0)] = input.value;
    } else if (input.dataset.manualBody) state.body = input.value;
    else if (input.dataset.manualField) state.fields[input.dataset.manualField] = input.value;
  });
  $$('.manual-guide-include').forEach(input => {
    const key = input.dataset.manualSection;
    if (!key) return;
    const state = manualGuideState[key] || (manualGuideState[key] = { include: true, body: '', fields: {} });
    state.include = !!input.checked;
  });
  if (manualGuideTabs[activeManualGuideTabIndex]) {
    manualGuideTabs[activeManualGuideTabIndex].state = JSON.parse(JSON.stringify(manualGuideState || {}));
    manualGuideTabs[activeManualGuideTabIndex].pageIndex = manualGuidePageIndex || 0;
  }
}

function updateManualGuideButtons() {
  const pages = manualGuidePages();
  const back = $('#manualBackBtn');
  const next = $('#manualNextBtn');
  if (back) back.disabled = manualGuidePageIndex <= 0;
  if (next) {
    next.disabled = manualGuidePageIndex >= pages.length - 1;
    next.textContent = manualGuidePageIndex >= pages.length - 1 ? 'Last Page' : 'Next';
  }
}

function manualGuideFormatSection(section, state) {
  if (isManualAlternateFirstMessagesSection(section)) {
    const alternates = Array.isArray(state.alternates) ? state.alternates : [];
    return alternates
      .map((value, index) => ({ value: String(value || '').trim(), index }))
      .filter(item => item.value)
      .map(item => `Alternative First Message ${item.index + 1}:\n${item.value}`)
      .join('\n\n')
      .trim();
  }
  const fields = (section.fields || []).filter(field => field && field.enabled !== false);
  const lines = [];
  if (fields.length) {
    fields.forEach(field => {
      const fid = String(field.id || field.label || 'field');
      const value = String(state.fields?.[fid] || '').trim();
      const displayValue = manualGuideDisplayValueForField(section, field, value);
      if (displayValue) lines.push(`- ${field.label || fid}: ${displayValue}`);
    });
    const body = String(state.body || '').trim();
    if (body) lines.push(body);
  } else {
    const body = String(state.body || '').trim();
    if (body) lines.push(body);
  }
  return lines.join('\n').trim();
}

function buildManualGuideOutput() {
  captureManualGuideInputs();
  if (!template || !Array.isArray(template.sections)) return '';
  const out = [];
  (template.sections || []).forEach(section => {
    const key = manualGuideSectionKey(section);
    const state = ensureManualGuideSectionState(section);
    const body = manualGuideFormatSection(section, state);
    const hasContent = !!body.trim();
    if (!hasContent) return;
    if (state.include === false) return;
    const title = String(section.title || key).trim() || key;
    out.push('------------------------------------------------');
    out.push(title);
    out.push('');
    out.push(body);
    out.push('');
  });
  return out.join('\n').trim();
}

function updateManualPreview() {
  const preview = $('#manualPreviewText');
  if (!preview) return;
  const output = buildManualGuideOutput();
  preview.value = output || '';
}

function manualGuideNextPage() {
  captureManualGuideInputs();
  const pages = manualGuidePages();
  manualGuidePageIndex = Math.min(pages.length - 1, manualGuidePageIndex + 1);
  renderManualGuide();
}

function manualGuidePreviousPage() {
  captureManualGuideInputs();
  manualGuidePageIndex = Math.max(0, manualGuidePageIndex - 1);
  renderManualGuide();
}

function clearManualGuideDraft() {
  if (!confirm('Clear every field in the current Guided Manual draft?')) return;
  clearCurrentManualGuideDraft();
}


async function buildManualGuideIntoOutput() {
  if (isInterfaceLocked()) return;
  const output = buildManualGuideOutput();
  if (!output.trim()) {
    setStatus('Fill at least one Guided Manual field before building the output.', 'error');
    return;
  }
  lastQnaAnswers = 'Guided Manual Mode was used. Q&A was skipped and no AI generation was run.';
  currentBrowserDescription = '';
  currentCardRating = '';
  currentCardRatingReasoning = '';
  currentCardRatingDetails = [];
  currentCardRatingSourceHash = '';
  const manualName = extractOutputNameForTab(output) || (manualGuideTabs[activeManualGuideTabIndex]?.name || `Manual ${activeManualGuideTabIndex + 1}`);
  ensureLinkedWorkspaceTabs();
  const targetIdx = activeManualGuideTabIndex;
  if (!characterOutputTabs[targetIdx]) characterOutputTabs[targetIdx] = makeBlankOutputTab(manualName);
  characterOutputTabs[targetIdx] = {
    ...characterOutputTabs[targetIdx],
    name: manualName,
    focusName: manualName,
    output,
    qaAnswers: lastQnaAnswers,
    emotionImages: [],
    generatedImages: [],
    cardImagePath: characterOutputTabs[targetIdx]?.cardImagePath || '',
  };
  activeOutputTabIndex = targetIdx;
  activeConceptTabIndex = targetIdx;
  activeManualGuideTabIndex = targetIdx;
  renderAllWorkspaceTabRails();
  applyActiveOutputTab();
  const qaBox = $('#qaAnswersText');
  if (qaBox) qaBox.value = lastQnaAnswers;
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="output"]')?.classList.add('active');
  $('#output')?.classList.add('active');
  switchSubTab('output', 'output-fulltext');
  updateAvailability();
  await saveCurrentWorkspace('silent');
  setStatus('Guided Manual output built, Q&A skipped, and workspace autosaved.', 'ok');
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
  $$('.subtab', group).forEach(btn => {
    const active = btn.dataset.subtab === panelId;
    btn.classList.toggle('active', active);
    if (active) setTimeout(() => btn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' }), 0);
  });
  $$(`[data-subtab-panel="${groupName}"]`).forEach(panel => panel.classList.toggle('active', panel.id === panelId));
  if (panelId === 'output-debug') refreshDebugLog(true);
  refreshSubtabScrollControls();
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
  return ['multi','split_cards'].includes($('#cardMode')?.value);
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
  $('#newCardBtn').addEventListener('click', addConceptWorkspaceTab);
  $('#nextTipBtn')?.addEventListener('click', () => showRandomTip(true));
  $('#closeUpdateAvailableModalBtn')?.addEventListener('click', closeUpdateAvailableModal);
  $('#remindLaterUpdateBtn')?.addEventListener('click', closeUpdateAvailableModal);
  $('#openUpdateReleaseBtn')?.addEventListener('click', openUpdateReleasePage);
  $('#openUpdateRepoBtn')?.addEventListener('click', openUpdateRepositoryPage);
  $('#updateAvailableModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'updateAvailableModal') closeUpdateAvailableModal(); });
  $('#newCardOutputBtn').addEventListener('click', addBlankOutputTab);
  $('#checkUpdatesBtn')?.addEventListener('click', () => checkForAppUpdates(true));
  $('#generateRelationshipMatrixBtn')?.addEventListener('click', generateRelationshipMatrixForOpenCharacters);
  $('#refreshRelationshipMatrixCharactersBtn')?.addEventListener('click', refreshRelationshipMatrixOpenCharacterList);
  $('#copyRelationshipMatrixBtn')?.addEventListener('click', copyRelationshipMatrixToClipboard);
  $('#relationshipMatrixText')?.addEventListener('input', () => { relationshipMatrixText = $('#relationshipMatrixText').value || ''; });
  $('#manualBackBtn')?.addEventListener('click', manualGuidePreviousPage);
  $('#manualNextBtn')?.addEventListener('click', manualGuideNextPage);
  $('#manualBuildOutputBtn')?.addEventListener('click', buildManualGuideIntoOutput);
  $('#manualBuildOutputTopBtn')?.addEventListener('click', buildManualGuideIntoOutput);
  $('#manualNewTabBtn')?.addEventListener('click', addManualWorkspaceTab);
  $('#manualResetBtn')?.addEventListener('click', clearCurrentManualGuideDraft);
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
    touchRecentModel($('#model')?.value || '', currentModelTokenInfoFromFields());
    settings = collectSettings();
    const res = await window.pywebview.api.save_settings(settings);
    if (res?.settings) settings = res.settings;
    hydrateSettings();
    renderMobileServerStatus(res?.mobileServer || await window.pywebview.api.mobile_server_status());
    renderCharacterBrowser();
    if (res?.dataFolder && !res.dataFolder.ok) {
      alert('Settings saved, but data folder was not changed: ' + (res.dataFolder.error || 'Unknown error'));
    } else if (res?.restartRequired) {
      alert('Settings saved. Data folder changed and existing data was copied. Restart the app to use the new data folder.');
    } else {
      alert('Settings saved.');
    }
  });
  $('#fetchModelTokensBtn')?.addEventListener('click', () => fetchModelTokenLimits(false));
  $('#showTokenDebugBtn')?.addEventListener('click', showTokenDebugLog);
  $('#copyTokenDebugBtn')?.addEventListener('click', copyTokenDebugSummary);
  $('#model')?.addEventListener('focus', () => renderRecentModelDropdown($('#model').value, true));
  $('#model')?.addEventListener('input', () => { renderRecentModelDropdown($('#model').value, true); updateModelTokenHint(); scheduleAutoModelTokenFetch(); });
  $('#model')?.addEventListener('blur', () => { setTimeout(() => $('#recentModelDropdown')?.classList.add('hidden'), 180); touchRecentModel($('#model')?.value || '', currentModelTokenInfoFromFields()); settings = collectSettings(); try { window.pywebview.api.save_settings(settings); } catch (_) {} });
  $('#apiBaseUrl')?.addEventListener('input', scheduleAutoModelTokenFetch);

  $('#selectDataFolderBtn')?.addEventListener('click', async () => {
    try {
      const res = await window.pywebview.api.select_data_folder();
      if (res?.ok && res.path && $('#dataFilesFolder')) $('#dataFilesFolder').value = res.path;
      else if (res && !res.cancelled) setStatus(res.error || 'Could not select data folder.', 'error');
    } catch (err) {
      setStatus(err.message || String(err), 'error');
    }
  });
  $('#mobileServerStatusBtn')?.addEventListener('click', () => refreshMobileServerStatus(true));
  $('#mobileServerOpenBtn')?.addEventListener('click', openMobileServerPage);
  $('#mobileServerEnabled')?.addEventListener('change', async () => { settings = collectSettings(); const res = await window.pywebview.api.save_settings(settings); if (res?.settings) settings = res.settings; renderMobileServerStatus(res?.mobileServer || await window.pywebview.api.mobile_server_status()); });
  ['mobileServerHost','mobileServerPort','mobileServerAccessCode'].forEach(id => $('#'+id)?.addEventListener('input', () => { settings = collectSettings(); }));
  $('#scanFrontPorchBtn')?.addEventListener('click', () => scanFrontPorchFolder());
  $('#scanFrontPorchStableBtn')?.addEventListener('click', () => scanFrontPorchFolder('stable'));
  $('#scanFrontPorchBetaBtn')?.addEventListener('click', () => scanFrontPorchFolder('beta'));
  $('#auditFrontPorchBtn')?.addEventListener('click', () => auditFrontPorchDatabase());
  $('#auditFrontPorchStableBtn')?.addEventListener('click', () => auditFrontPorchDatabase('stable'));
  $('#auditFrontPorchBetaBtn')?.addEventListener('click', () => auditFrontPorchDatabase('beta'));
  $('#fetchSdModelsBtn')?.addEventListener('click', fetchStableDiffusionModels);
  $('#firstStyle')?.addEventListener('change', () => { settings = collectSettings(); updateFirstMessageCustomVisibility(); updateAvailability(); });
  $('#firstCustomStyle')?.addEventListener('input', () => { settings = collectSettings(); updateAvailability(); });
  $('#firstCustomInstructions')?.addEventListener('input', () => { settings = collectSettings(); updateAvailability(); });
  $('#altStyleRows')?.addEventListener('input', () => { settings = collectSettings(); updateAvailability(); });
  $('#altStyleRows')?.addEventListener('change', () => { settings = collectSettings(); updateAvailability(); });
  $('#altCount').addEventListener('input', () => { settings = collectSettings(); renderAltStyleRows(); updateAvailability(); });
  $('#cardMode').addEventListener('change', () => {
    const mode = $('#cardMode')?.value || 'single';
    if ($('#sharedScenePolicy')) {
      if (mode === 'single') $('#sharedScenePolicy').value = 'ai_reconcile';
      else if (mode === 'split_cards') $('#sharedScenePolicy').value = 'split_cards';
      else if ($('#sharedScenePolicy').value === 'split_cards') $('#sharedScenePolicy').value = 'ai_reconcile';
    }
    settings = collectSettings();
    if (mode === 'multi') { ensureMultiBuilderStates(); multiBuilderStates[multiBuilderSelectedIndex] = readBuilderDomState(); }
    updateCardModeHint();
    updateAvailability();
  });
  $('#multiCharacterCount').addEventListener('input', () => { settings = collectSettings(); captureCurrentMultiBuilderState(); ensureMultiBuilderStates(); updateMultiBuilderSelectors(true); updateAvailability(); });
  $('#sharedScenePolicy')?.addEventListener('change', () => { if ($('#sharedScenePolicy')?.value === 'split_cards' && $('#cardMode')) $('#cardMode').value = 'split_cards'; settings = collectSettings(); updateAvailability(); updateMultiBuilderSelectors(false); });
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
  $('#selectVisionImageBtn')?.addEventListener('click', openVisionImagePicker);
  $('#visionImageUrlBtn')?.addEventListener('click', () => selectVisionImageUrl({ analyze: false }));
  $('#visionImagePath').addEventListener('input', () => { currentVisionImagePath = $('#visionImagePath').value.trim(); if (settings) settings.visionImagePath = currentVisionImagePath; updateAvailability(); });
  $('#analyzeVisionBtn').addEventListener('click', openVisionAnalyzeOptionsModal);
  $('#analyzeFullCardBtn')?.addEventListener('click', analyzeFullCardToMainConcept);
  $('#closeVisionAnalyzeOptionsModalBtn')?.addEventListener('click', closeVisionAnalyzeOptionsModal);
  $('#cancelVisionAnalyzeOptionsBtn')?.addEventListener('click', closeVisionAnalyzeOptionsModal);
  $('#startVisionAnalyzeOptionsBtn')?.addEventListener('click', startVisionAnalyzeFromModal);
  $('#visionAnalyzeOptionsModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'visionAnalyzeOptionsModal') closeVisionAnalyzeOptionsModal(); });
  $('#clearVisionBtn').addEventListener('click', clearVisionDescription);
  $('#outputText').addEventListener('input', () => { updateAvailability(); scheduleOutputEditorAutosave(); updateImportedCardToolsHint(); });
  $('#stopTaskBtn').addEventListener('click', stopCurrentTask);
  $('#generateBtn').addEventListener('click', openGenerationOptionsModal);
  $('#openIdeaGeneratorModalBtn')?.addEventListener('click', openIdeaGeneratorModal);
  $('#closeGenerationOptionsModalBtn')?.addEventListener('click', closeGenerationOptionsModal);
  $('#cancelGenerationOptionsBtn')?.addEventListener('click', closeGenerationOptionsModal);
  $('#startGenerationWithOptionsBtn')?.addEventListener('click', startGenerationFromModal);
  $('#generationOptionsModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'generationOptionsModal') closeGenerationOptionsModal(); });
  $('#closeFrontPorchExportTargetModalBtn')?.addEventListener('click', () => closeFrontPorchExportTargetModal(null));
  $('#cancelFrontPorchExportTargetBtn')?.addEventListener('click', () => closeFrontPorchExportTargetModal(null));
  $('#frontPorchExportStableBtn')?.addEventListener('click', () => closeFrontPorchExportTargetModal(['stable']));
  $('#frontPorchExportBetaBtn')?.addEventListener('click', () => closeFrontPorchExportTargetModal(['beta']));
  $('#frontPorchExportBothBtn')?.addEventListener('click', () => closeFrontPorchExportTargetModal(['stable', 'beta']));
  $('#frontPorchExportTargetModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'frontPorchExportTargetModal') closeFrontPorchExportTargetModal(null); });
  $('#ideaGender')?.addEventListener('change', populateIdeaGeneratorOptions);
  $('#closeIdeaGeneratorModalBtn')?.addEventListener('click', closeIdeaGeneratorModal);
  $('#clearIdeaGeneratorBtn')?.addEventListener('click', clearIdeaGenerator);
  $('#randomiseIdeaGeneratorBtn')?.addEventListener('click', randomiseIdeaGenerator);
  $('#generateIdeaBtn')?.addEventListener('click', generateIdeaIntoMainConcept);
  $('#ideaSettingsField')?.addEventListener('change', (e) => switchIdeaSettingsField(e.target.value));
  $('#ideaSettingsApplyBtn')?.addEventListener('click', () => applyIdeaSettingsField(true));
  $('#ideaSettingsResetFieldBtn')?.addEventListener('click', resetIdeaSettingsField);
  $('#ideaSettingsResetAllBtn')?.addEventListener('click', resetAllIdeaSettings);
  $('#ideaSettingsMulti')?.addEventListener('change', () => applyIdeaSettingsField(false));
  $('#ideaGeneratorModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'ideaGeneratorModal') closeIdeaGeneratorModal(); });
  initIdeaSettingsEditor();
  populateIdeaGeneratorOptions();
  $('#refreshCharactersBtn')?.addEventListener('click', () => refreshCharacterBrowser(true, { modal: true }));
  $('#browserMultiDeleteBtn')?.addEventListener('click', deleteSelectedCharacterDirectories);
  $('#browserMultiExportPngBtn')?.addEventListener('click', () => exportSelectedCharactersBatch('chara_v2_png'));
  $('#browserMultiExportJsonBtn')?.addEventListener('click', () => exportSelectedCharactersBatch('chara_v2_json'));
  $('#browserMultiFrontPorchBtn')?.addEventListener('click', exportSelectedCharactersToFrontPorchBatch);
  $('#browserCreateFolderBtn')?.addEventListener('click', createBrowserVirtualFolder);
  $('#browserRenameFolderBtn')?.addEventListener('click', renameCurrentBrowserFolder);
  $('#browserDeleteFolderBtn')?.addEventListener('click', deleteCurrentBrowserFolder);
  $('#browserMoveToFolderBtn')?.addEventListener('click', moveSelectedCharactersToFolder);
  $('#browserShowSubfolders')?.addEventListener('change', (e) => { browserShowSubfolders = !!e.currentTarget.checked; settings = { ...(settings || {}), browserShowSubfolders }; try { window.pywebview.api.save_settings(settings); } catch (_) {} renderCharacterBrowser(); });
  $('#browserFolderSelect')?.addEventListener('change', (e) => { setBrowserCurrentFolder(e.target.value || '', `Opened ${browserFolderPathLabel(e.target.value || '')}.`); });
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
  $('#browserImproveFromRatingBtn')?.addEventListener('click', generateRatingImprovementPreview);
  $('#browserRatingDetailsBtn')?.addEventListener('click', showSelectedRatingDetailsModal);
  $('#closeRatingDetailsModalBtn')?.addEventListener('click', closeRatingDetailsModal);
  $('#ratingDetailsModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'ratingDetailsModal') closeRatingDetailsModal(); });
  $('#closeRatingImproveModalBtn')?.addEventListener('click', closeRatingImproveModal);
  $('#cancelRatingImproveBtn')?.addEventListener('click', closeRatingImproveModal);
  $('#commitRatingImproveBtn')?.addEventListener('click', commitRatingImprovementPreview);
  $('#copyRatingImprovePreviewBtn')?.addEventListener('click', copyRatingImprovementPreview);
  $('#ratingImproveModal')?.addEventListener('click', (e) => { if (e.target && e.target.id === 'ratingImproveModal') closeRatingImproveModal(); });
  $('#browserLoadBtn')?.addEventListener('click', loadSelectedCharacterWorkspace);
  $('#browserDeleteSelectedBtn')?.addEventListener('click', deleteSelectedCharacterCard);
  $('#browserExportPngBtn')?.addEventListener('click', () => exportSelectedCharacter('chara_v2_png'));
  $('#browserExportJsonBtn')?.addEventListener('click', () => exportSelectedCharacter('chara_v2_json'));
  $('#browserEmotionZipBtn')?.addEventListener('click', zipSelectedCharacterEmotions);
  $('#browserFrontPorchExportBtn')?.addEventListener('click', exportSelectedCharacterToFrontPorch);
  $('#saveWorkspaceBtn')?.addEventListener('click', () => saveCurrentWorkspace('manual'));
  $('#importLoadedCardBtn')?.addEventListener('click', () => importCurrentOutputToBrowser(true));
  $('#analyzeImageToBuildersMainBtn')?.addEventListener('click', analyzeSelectedImageToBuilders);
  $('#analyzeVisionToBuildersBtn')?.addEventListener('click', analyzeSelectedImageToBuilders);
  $('#transferToBuildersBtn')?.addEventListener('click', transferConceptToBuilders);
  $('#transferToBuildersMainBtn')?.addEventListener('click', transferConceptToBuilders);
  $('#loadCardToBuildersMainBtn')?.addEventListener('click', loadCardToBuildersNative);
  $('#loadCardToBuildersModeBtn')?.addEventListener('click', loadCardToBuildersNative);
  $('#loadCardToBuildersUrlMainBtn')?.addEventListener('click', loadCardToBuildersUrl);
  $('#loadCardToBuildersUrlModeBtn')?.addEventListener('click', loadCardToBuildersUrl);
  $('#loadCardToConceptMainBtn')?.addEventListener('click', loadCardToMainConceptNative);
  $('#loadCardToConceptModeBtn')?.addEventListener('click', loadCardToMainConceptNative);
  $('#loadCardToConceptUrlMainBtn')?.addEventListener('click', loadCardToMainConceptUrl);
  $('#loadCardToConceptUrlModeBtn')?.addEventListener('click', loadCardToMainConceptUrl);
  $('#reviseBtn').addEventListener('click', reviseCard);
  $('#loadSavedBtn')?.addEventListener('click', loadSavedCardOrProject);
  $('#loadSavedUrlBtn')?.addEventListener('click', loadSavedCardOrProjectFromUrl);
  const viewLogBtn = $('#viewLogBtn'); if (viewLogBtn) viewLogBtn.addEventListener('click', viewDebugLog);
  $('#clearLogBtn').addEventListener('click', clearDebugLog);
  $('#copyBtn').addEventListener('click', copyOutput);
  $('#exportBtn')?.addEventListener('click', openExportModal);
  $('#openExportModalBtn')?.addEventListener('click', openExportModal);
  $('#closeExportModalBtn')?.addEventListener('click', closeExportModal);
  $('#runExportCardBtn')?.addEventListener('click', exportCard);
  $('#selectExportFolderBtn')?.addEventListener('click', selectExportFolder);
  $('#openQuickImportModalBtn')?.addEventListener('click', openQuickImportModal);
  $('#closeQuickImportModalBtn')?.addEventListener('click', closeQuickImportModal);
  $('#runQuickImportBtn')?.addEventListener('click', runQuickImport);
  $('#clearQuickImportSourceBtn')?.addEventListener('click', clearQuickImportSource);
  $('#quickImportFileInput')?.addEventListener('change', handleQuickImportFileSelected);
  $('#openCardImageModalBtn')?.addEventListener('click', openCardImageModal);
  $('#closeCardImageModalBtn')?.addEventListener('click', closeCardImageModal);
  $('#applyCardImagePathBtn')?.addEventListener('click', applyCardImageModalPath);
  $('#selectImageBtn')?.addEventListener('click', selectCardImage);
  $('#cardImageUrlBtn')?.addEventListener('click', importCardImageUrl);
  $('#generateImagesBtn')?.addEventListener('click', generateSdImages);
  $('#generateSdPromptFromVisionBtn')?.addEventListener('click', generateSdPromptFromLoadedVision);
  $('#generateSdPromptFromOutputBtn')?.addEventListener('click', generateSdPromptFromLoadedOutput);
  $('#generateEmotionImagesBtn').addEventListener('click', generateEmotionImages);
  $('#zipEmotionImagesBtn').addEventListener('click', createEmotionZip);
  $('#selectAllEmotionsBtn').addEventListener('click', () => { $$('#emotionOptions input').forEach(el => el.checked = true); });
  $('#clearEmotionsBtn').addEventListener('click', () => { $$('#emotionOptions input').forEach(el => el.checked = false); });
  $('#clearImageBtn')?.addEventListener('click', () => { $('#cardImagePath').value = ''; if ($('#cardImageModalPath')) $('#cardImageModalPath').value = ''; settings = collectSettings(); window.pywebview.api.save_settings(settings); updateCardImagePreview(); updateImportedCardToolsHint(); setStatus('Card image cleared. PNG export will use the built-in blank image.', 'ok'); });
  $('#cardImagePath')?.addEventListener('input', () => { settings = collectSettings(); if (characterOutputTabs[activeOutputTabIndex]) characterOutputTabs[activeOutputTabIndex].cardImagePath = $('#cardImagePath').value.trim(); updateCardImagePreview(); updateAvailability(); });
  $('#quickImportPath')?.addEventListener('input', () => { syncQuickImportUrlFromInput(); updateQuickImportSelected(); });
  $('#quickImportPath')?.addEventListener('paste', () => { setTimeout(() => { syncQuickImportUrlFromInput(); updateQuickImportSelected(); }, 0); });
  $('#sdImageCount')?.addEventListener('input', () => { settings = collectSettings(); window.pywebview?.api?.save_settings(settings); });
  $('#modeSelect')?.addEventListener('change', () => { if ($('#modeSelect').value === 'compact_lite') { if (Number($('#maxInputTokens').value || 0) > 8192) $('#maxInputTokens').value = 8000; if (Number($('#maxOutputTokens').value || 0) > 4096) $('#maxOutputTokens').value = 2500; setStatus('Compact Lite selected: token budgets adjusted for an ~8k context model.', 'ok'); } });
  $('#attachConceptFilesBtn').addEventListener('click', attachConceptFiles);
  $('#attachConceptUrlBtn')?.addEventListener('click', attachConceptUrl);
  $('#clearConceptAttachmentsBtn').addEventListener('click', clearConceptAttachments);
  // Hidden file inputs remain as an emergency browser fallback, but normal flow uses KDE/Zenity native dialogs from the backend.
  $('#conceptAttachmentInput').addEventListener('change', handleConceptAttachmentFiles);
  $('#visionFileInput').addEventListener('change', handleVisionFileSelected);
  $('#cardImageFileInput')?.addEventListener('change', handleCardImageFileSelected);
  $('#savedFileInput').addEventListener('change', handleSavedFileSelected);
  $('#builderCardFileInput')?.addEventListener('change', handleBuilderCardFileSelected);
  $('#conceptCardFileInput')?.addEventListener('change', handleConceptCardFileSelected);
  $('#conceptImportFileInput')?.addEventListener('change', handleConceptImportFileSelected);
  $('#openConceptImportModalBtn')?.addEventListener('click', openConceptImportModal);
  $('#closeConceptImportModalBtn')?.addEventListener('click', closeConceptImportModal);
  $('#clearConceptImportSourceBtn')?.addEventListener('click', clearConceptImportSource);
  $('#conceptImportAsMainBtn')?.addEventListener('click', () => runConceptImport('main'));
  $('#conceptImportAsBuildersBtn')?.addEventListener('click', () => runConceptImport('builders'));

  bindDropZone('conceptAttachmentDropZone', { inputId: 'conceptAttachmentInput', onFiles: importConceptAttachmentFiles, onPaths: importConceptAttachmentPaths, onClick: attachConceptFiles, preferInputOnClick: true });
  bindDropZone('visionDropZone', { inputId: 'visionFileInput', onFiles: importVisionFiles, onPaths: importVisionPaths, onClick: openVisionImagePicker, preferInputOnClick: true });
  bindDropZone('savedFileDropZone', { inputId: 'savedFileInput', onFiles: importSavedFiles, onClick: loadSavedCardOrProject });
  bindDropZone('builderCardDropZoneMode', { inputId: 'builderCardFileInput', onFiles: importBuilderCardFiles, onClick: loadCardToBuildersNative });
  bindDropZone('conceptCardDropZoneMode', { inputId: 'conceptCardFileInput', onFiles: importCardToMainConceptFiles, onClick: loadCardToMainConceptNative });
  bindDropZone('cardImageDropZone', { inputId: 'cardImageFileInput', onFiles: importCardImageFiles, onPaths: importCardImagePaths, onClick: () => openBrowserFileInput('cardImageFileInput', 'card image'), preferInputOnClick: true });
  bindDropZone('quickImportDropZone', { inputId: 'quickImportFileInput', onFiles: importQuickImportFiles, onPaths: importQuickImportPaths, onClick: () => openBrowserFileInput('quickImportFileInput', 'card or project'), preferInputOnClick: true });
  bindConceptImportDropZone();
  enhanceBuilderAiButtons();
  populateBuilderPresets();
  populateAiRandomThemes();
  ensureBuilderPresetDropdowns();
  setTimeout(ensureBuilderPresetDropdowns, 100);
  setTimeout(ensureBuilderPresetDropdowns, 500);
  $('#aiRandomThemeSelect')?.addEventListener('change', updateAiRandomThemeCustom);
  $('#aiRandomThemeSelect')?.addEventListener('focus', ensureBuilderPresetDropdowns);
  $('#aiRandomThemeSelect')?.addEventListener('click', ensureBuilderPresetDropdowns);
  $('#builderPresetSelect')?.addEventListener('focus', ensureBuilderPresetDropdowns);
  $('#builderPresetSelect')?.addEventListener('click', ensureBuilderPresetDropdowns);
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
  const previous = select.value || 'wildcard';
  let themes = {
    ntr: { name: 'NTR / Forbidden Temptation', prompt: 'Create a random adult NTR or forbidden-temptation route.', tags: ['ntr'] },
    slutty: { name: 'Slutty / Promiscuous Character', prompt: 'Create a random adult sexually confident or promiscuous character.', tags: ['slutty'] },
    romance: { name: 'Romance / Slow Burn', prompt: 'Create a random adult romance or slow-burn character.', tags: ['romance'] },
    workplace: { name: 'Workplace / Office Drama', prompt: 'Create a random adult workplace scenario.', tags: ['workplace'] },
    sharehouse: { name: 'Share House / Group Chaos', prompt: 'Create a random adult share-house, roommate, or multi-character setup.', tags: ['sharehouse'] },
    gyaru: { name: 'Gyaru / Social Butterfly', prompt: 'Create a random adult gyaru-inspired character.', tags: ['gyaru'] },
    dark: { name: 'Dark Romance / Corruption', prompt: 'Create a random adult dark-romance or corruption-focused route.', tags: ['dark'] },
    wildcard: { name: 'Wildcard Mix', prompt: 'Create a coherent random adult character-card setup.', tags: ['random'] },
    custom: { name: 'Custom…', prompt: '', tags: ['custom'] }
  };
  try {
    if (typeof AI_RANDOM_THEMES !== 'undefined' && Object.keys(AI_RANDOM_THEMES || {}).length) themes = AI_RANDOM_THEMES;
  } catch (_) {}
  select.innerHTML = '';
  Object.entries(themes).forEach(([key, theme]) => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = theme.name || key;
    select.appendChild(opt);
  });
  if ([...select.options].some(o => o.value === previous)) select.value = previous;
  else if ([...select.options].some(o => o.value === 'wildcard')) select.value = 'wildcard';
}

function updateAiRandomThemeCustom() {
  const wrap = $('#aiRandomCustomThemeWrap');
  const isCustom = ($('#aiRandomThemeSelect')?.value || '') === 'custom';
  if (wrap) wrap.classList.toggle('hidden', !isCustom);
}

function selectLooksFallbackOnly(select, fallbackValues = []) {
  if (!select) return true;
  const values = [...select.options].map(o => o.value);
  if (!values.length) return true;
  if (values.length <= fallbackValues.length && values.every(v => fallbackValues.includes(v))) return true;
  return false;
}

function ensureBuilderPresetDropdowns() {
  const presetSelect = $('#builderPresetSelect');
  if (presetSelect && selectLooksFallbackOnly(presetSelect, ['custom_blank'])) {
    try { populateBuilderPresets(); } catch (e) { console.warn('Could not populate builder presets', e); }
    if (selectLooksFallbackOnly(presetSelect, ['custom_blank'])) {
      presetSelect.innerHTML = `
        <option value="ntr_gyaru">NTR Gyaru Temptation</option>
        <option value="slutty_roommate">Shameless Slutty Roommate</option>
        <option value="wholesome_childhood_friend">Wholesome Childhood Friend Romance</option>
        <option value="office_affair">Office Affair / Forbidden Workplace</option>
        <option value="share_house_harem">Share House / Multi-Girl Chaos</option>
        <option value="tsundere_rival">Tsundere Rival / Bratty Slow Burn</option>
      `;
    }
  }
  const themeSelect = $('#aiRandomThemeSelect');
  if (themeSelect && selectLooksFallbackOnly(themeSelect, ['wildcard', 'custom'])) {
    try { populateAiRandomThemes(); } catch (e) { console.warn('Could not populate AI random themes', e); }
    if (selectLooksFallbackOnly(themeSelect, ['wildcard', 'custom'])) {
      themeSelect.innerHTML = `
        <option value="ntr">NTR / Forbidden Temptation</option>
        <option value="slutty">Slutty / Promiscuous Character</option>
        <option value="romance">Romance / Slow Burn</option>
        <option value="workplace">Workplace / Office Drama</option>
        <option value="sharehouse">Share House / Group Chaos</option>
        <option value="gyaru">Gyaru / Social Butterfly</option>
        <option value="dark">Dark Romance / Corruption</option>
        <option value="wildcard">Wildcard Mix</option>
        <option value="custom">Custom…</option>
      `;
      themeSelect.value = 'wildcard';
    }
  }
  try { updateBuilderPresetPreview(); } catch (e) {}
  try { updateAiRandomThemeCustom(); } catch (e) {}
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
  const themes = (typeof AI_RANDOM_THEMES !== 'undefined' && Object.keys(AI_RANDOM_THEMES || {}).length) ? AI_RANDOM_THEMES : { wildcard: { name: 'Wildcard / Surprise Me', prompt: 'Create a coherent random adult character-card setup.', tags: ['random'] } };
  return { key, preset: themes[key] || themes.wildcard };
}

function populateBuilderPresets() {
  const select = $('#builderPresetSelect');
  if (!select) return;
  const previous = select.value || 'custom_blank';
  let presets = { custom_blank: { name: 'Blank / Manual', description: 'Start from blank builder fields.', tags: [], fields: {} } };
  try {
    if (typeof BUILDER_PRESETS !== 'undefined' && Object.keys(BUILDER_PRESETS || {}).length) presets = BUILDER_PRESETS;
  } catch (_) {}
  select.innerHTML = '';
  Object.entries(presets).forEach(([key, preset]) => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = preset.name || key;
    select.appendChild(opt);
  });
  if ([...select.options].some(o => o.value === previous)) select.value = previous;
  updateBuilderPresetPreview();
}

function updateBuilderPresetPreview() {
  const key = $('#builderPresetSelect')?.value;
  const presets = (typeof BUILDER_PRESETS !== 'undefined' && Object.keys(BUILDER_PRESETS || {}).length) ? BUILDER_PRESETS : { custom_blank: { name: 'Blank / Manual', description: 'Start from blank builder fields.', tags: [], fields: {} } };
  const preset = presets[key] || presets[Object.keys(presets)[0]];
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
  const presets = (typeof BUILDER_PRESETS !== 'undefined' && Object.keys(BUILDER_PRESETS || {}).length) ? BUILDER_PRESETS : { custom_blank: { name: 'Blank / Manual', description: 'Start from blank builder fields.', tags: [], fields: {} } };
  const key = $('#builderPresetSelect')?.value || Object.keys(presets)[0];
  const preset = presets[key];
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
    settings.cardMode = $('#cardMode')?.value || 'multi';
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
  const mainConcept = ($('#conceptText')?.value || '').trim();
  const characterDescription = ($('#visionDescription')?.value || '').trim();
  return transferTextToBuilders(mainConcept, characterDescription, {
    busyMessage: 'TRANSFER TO BUILDERS — reading concept and filling builder fields…',
    statusMessage: 'Transferring concept into Character, Personality, and Scene Builders…'
  });
}

async function aiRandomizeBuilderPreset({ build = false } = {}) {
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
  addConceptWorkspaceTab();
  $('#cardMode').value = 'single';
  $('#multiCharacterCount').value = 2;
  if ($('#sharedScenePolicy')) $('#sharedScenePolicy').value = 'ai_reconcile';
  settings = collectSettings();
  settings.cardMode = 'single';
  settings.multiCharacterCount = 2;
  settings.visionImagePath = '';
  settings.cardImagePath = '';
  await window.pywebview.api.save_settings(settings);
  updateCardModeHint();
  updateAvailability();
  setStatus('New linked card tab opened. Card Mode reset to Single Character.', 'ok');
}

async function loadSelectedTemplate() {
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
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

async function selectVisionImage(options = {}) {
  if (isInterfaceLocked()) return;
  const fallbackToBrowserInput = !!options.fallbackToBrowserInput;
  if (!window.pywebview?.api?.pick_image_file) {
    openBrowserFileInput('visionFileInput', 'vision image');
    return;
  }
  setBusy('SELECTING VISION IMAGE…');
  let shouldOpenBrowserFallback = false;
  try {
    const res = await window.pywebview.api.pick_image_file('vision');
    if (!res.ok) {
      if (res.cancelled) {
        shouldOpenBrowserFallback = fallbackToBrowserInput;
        return;
      }
      throw new Error(res.error || 'Vision image selection failed.');
    }
    setVisionImagePath(res.path);
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    setStatus('Selected vision image: ' + res.path, 'ok');
  } catch (err) {
    if (fallbackToBrowserInput) {
      shouldOpenBrowserFallback = true;
      setStatus('Native vision image picker failed; opening browser picker fallback.', 'error');
    } else {
      setStatus(err.message || String(err), 'error');
    }
  } finally {
    setBusy('');
    setVisionImagePath(getVisionImagePath());
    updateAvailability();
    if (shouldOpenBrowserFallback) openBrowserFileInput('visionFileInput', 'vision image');
  }
}

async function openVisionImagePicker() {
  if (isInterfaceLocked()) return;
  if (openBrowserFileInput('visionFileInput', 'vision image')) return;
  await selectVisionImage({ fallbackToBrowserInput: false });
}

async function importVisionPaths(paths) {
  const path = [...(paths || [])].find(Boolean);
  if (!path) return;
  if (!window.pywebview?.api?.import_image_path) {
    setStatus('This build cannot import dropped file paths. Click the drop area to browse instead.', 'error');
    return;
  }
  setBusy('IMPORTING VISION IMAGE…');
  try {
    const res = await window.pywebview.api.import_image_path(path, 'vision');
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

async function selectVisionImageUrl({ analyze = false } = {}) {
  if (isInterfaceLocked()) return;
  const url = promptForUrl('image URL');
  if (!url) return;
  if (!isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// image URL.', 'error'); return; }
  setVisionImagePath(url);
  settings = collectSettings();
  settings.visionImagePath = url;
  await window.pywebview.api.save_settings(settings);
  if (analyze) {
    await analyzeVisionImage();
  } else {
    setStatus('Vision image URL set. Click Analyze when ready.', 'ok');
  }
}

function getCheckedRadioValue(name, fallback = '') {
  const checked = document.querySelector(`input[name="${name}"]:checked`);
  return String(checked?.value || fallback || '').trim();
}

function openVisionAnalyzeOptionsModal() {
  if (isInterfaceLocked()) return;
  const visionPath = getVisionImagePath();
  if (!visionPath) {
    setStatus('Select a vision image, drop one onto the Vision area, or paste an image path/URL first.', 'error');
    updateAvailability();
    return;
  }
  const modal = $('#visionAnalyzeOptionsModal');
  if (!modal) {
    analyzeVisionImage();
    return;
  }
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  $('#visionAnalyzeCustomInstructions')?.focus();
}

function closeVisionAnalyzeOptionsModal() {
  const modal = $('#visionAnalyzeOptionsModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function startVisionAnalyzeFromModal() {
  const analysisType = getCheckedRadioValue('visionAnalysisType', 'character');
  const target = getCheckedRadioValue('visionAnalysisTarget', 'concept');
  const customInstructions = String($('#visionAnalyzeCustomInstructions')?.value || '').trim();
  closeVisionAnalyzeOptionsModal();
  await runVisionAnalysisWithOptions({ analysisType, target, customInstructions });
}

function writeVisionAnalysisToConcept(text, { analysisType = 'character' } = {}) {
  const conceptBox = $('#conceptText');
  if (!conceptBox) throw new Error('Main Concept box was not found.');
  const cleanText = String(text || '').trim();
  if (!cleanText) throw new Error('Vision model returned an empty result.');
  const block = analysisType === 'full_card'
    ? cleanText
    : `Character Visual Description:\n${cleanText}`;
  const existing = String(conceptBox.value || '').trim();
  let finalText = block;
  if (existing) {
    const replace = window.confirm('Replace the current Main Concept with this vision analysis?\n\nOK = Replace\nCancel = Append below the existing concept');
    finalText = replace ? block : `${existing}\n\n---\n\n${block}`;
  }
  conceptBox.value = finalText;
  conceptBox.dispatchEvent(new Event('input', { bubbles: true }));
}

async function transferTextToBuilders(mainConcept, characterDescription, options = {}) {
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return false;
  }
  const mainText = String(mainConcept || '').trim();
  const characterText = String(characterDescription || '').trim();
  if (!mainText && !characterText) {
    setStatus('Provide a Main Concept or vision description before transferring to Builders.', 'error');
    return false;
  }
  setBusy(options.busyMessage || 'TRANSFER TO BUILDERS — reading analysis and filling builder fields…');
  setStatus(options.statusMessage || 'Transferring analysis into Character, Personality, and Scene Builders…', '');
  try {
    const catalog = collectCompactBuilderFieldCatalog();
    const res = await window.pywebview.api.ai_transfer_to_builders(mainText, characterText, catalog, settings);
    if (!res.ok) throw new Error(res.error || 'Transfer to Builders failed.');
    const applied = applyBuilderTransferResult(res);
    const multiMsg = applied.characterCount >= 2 ? ` Detected ${applied.characterCount} main characters and switched to Multi-Character Single Card. Side characters remain in concept/lore context, not builder slots.` : '';
    setStatus(`Transferred analysis to builders: filled ${applied.count} field(s). Builder guidance now takes priority during generation.${multiMsg}${res.notes ? ' ' + res.notes : ''}`, 'ok');
    if (options.switchToBuilders !== false) switchSubTab('concept', 'concept-builder');
    return true;
  } catch (err) {
    setStatus(err.message || String(err), 'error');
    return false;
  } finally {
    setBusy('');
    updateAvailability();
  }
}

async function runVisionAnalysisWithOptions({ analysisType = 'character', target = 'concept', customInstructions = '' } = {}) {
  const visionPath = getVisionImagePath();
  if (!visionPath) {
    setStatus('Select a vision image before analyzing.', 'error');
    updateAvailability();
    return;
  }
  const fullCard = analysisType === 'full_card';
  const sendToBuilders = target === 'builders';
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
  setBusy(fullCard ? 'ANALYZING FULL CARD WITH VISION MODEL…' : 'ANALYZING IMAGE WITH VISION MODEL…');
  try {
    const mode = fullCard ? 'full_card' : 'character';
    const res = await window.pywebview.api.analyze_vision_image(visionPath, settings, mode, customInstructions || '');
    if (!res.ok) throw new Error(res.error || 'Vision analysis failed.');
    const resultText = String(res.concept || res.description || '').trim();
    if (!resultText) throw new Error('Vision model returned an empty result. Try a different vision model or add custom instructions.');
    if (res.imagePath) setVisionImagePath(res.imagePath);
    if ($('#visionDescription')) $('#visionDescription').value = resultText;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);

    if (sendToBuilders) {
      setBusy('');
      await transferTextToBuilders(fullCard ? resultText : '', fullCard ? '' : resultText, {
        busyMessage: fullCard ? 'TRANSFER TO BUILDERS — reading full-card analysis…' : 'TRANSFER TO BUILDERS — reading character description…',
        statusMessage: fullCard ? 'Transferring full-card analysis into Builders…' : 'Transferring character description into Builders…'
      });
    } else {
      writeVisionAnalysisToConcept(resultText, { analysisType: fullCard ? 'full_card' : 'character' });
      updateAvailability();
      setStatus(res.retryUsed ? 'Vision analysis succeeded after a SFW retry. Main Concept updated.' : 'Vision analysis complete. Main Concept updated.', 'ok');
    }
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
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

async function analyzeFullCardToMainConcept() {
  const visionPath = getVisionImagePath();
  if (!visionPath) {
    setStatus('Select a vision image before analyzing the full card.', 'error');
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
  setBusy('ANALYZING FULL CARD WITH VISION MODEL — building Main Concept…');
  try {
    const res = await window.pywebview.api.analyze_vision_image(visionPath, settings, 'full_card');
    if (!res.ok) throw new Error(res.error || 'Full card analysis failed.');
    const concept = String(res.concept || res.description || '').trim();
    if (!concept) throw new Error('Vision model returned an empty concept. Try a different vision model or enter the concept manually.');
    const conceptBox = $('#conceptText');
    if (!conceptBox) throw new Error('Main Concept box was not found.');
    const existing = String(conceptBox.value || '').trim();
    let finalText = concept;
    if (existing) {
      const replace = window.confirm('Replace the current Main Concept with the full-card analysis?\n\nOK = Replace\nCancel = Append below the existing concept');
      finalText = replace ? concept : `${existing}\n\n---\n\nFull Card Image Analysis:\n${concept}`;
    }
    conceptBox.value = finalText;
    conceptBox.dispatchEvent(new Event('input', { bubbles: true }));
    if (res.imagePath) setVisionImagePath(res.imagePath);
    if ($('#visionDescription') && concept.length <= 12000) $('#visionDescription').value = concept;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    updateAvailability();
    setStatus(res.retryUsed ? 'Full-card analysis succeeded after a SFW retry. Main Concept updated.' : 'Full-card analysis complete. Main Concept updated.', 'ok');
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
  if (isInterfaceLocked()) return;
  // Use the browser file input first. This matches the Import Card/Image modal path,
  // which works reliably in Linux AppImage/WebView builds.
  if (openBrowserFileInput('conceptAttachmentInput', 'concept attachment files')) return;
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

async function importConceptAttachmentPaths(paths) {
  paths = [...(paths || [])].filter(Boolean);
  if (!paths.length) return;
  if (!window.pywebview?.api?.import_concept_attachment_paths) {
    setStatus('This build cannot import dropped concept file paths. Click Attach Files instead.', 'error');
    return;
  }
  setBusy('IMPORTING CONCEPT ATTACHMENT(S)…');
  try {
    const res = await window.pywebview.api.import_concept_attachment_paths(paths);
    if (!res.ok) throw new Error(res.error || 'Could not import dropped concept attachment(s).');
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
  if (concept) {
    parts.push([
      'MAIN CONCEPT — AUTHORITATIVE USER SOURCE. Preserve these named characters, relationships, premise, scenario hook, visual details, clothing/props, captions/messages, and any explicit First Message/Greeting beats.',
      'Clean up and expand the idea, but do not replace it with another character, different relationship, unrelated scenario, or stale builder/workspace content.',
      concept
    ].join('\n'));
  }
  if (hasBuilder) {
    parts.push(concept
      ? 'BUILDER SUPPLEMENT RULE — builder guidance below may fill in missing details or refine compatible fields, but it must never override explicit Main Concept facts, names, relationships, outfit, scenario, First Message, or temporary generation notes. If it conflicts, ignore the builder detail.'
      : 'BUILDER PRIORITY RULE — no Main Concept was entered, so builder guidance is the primary source for this generation.');
  }
  if (attachmentText) parts.push(attachmentText);
  if (visual) {
    parts.push([
      'VISION REFERENCE — use this as physical appearance/clothing reference only when it does not conflict with Character Builder Visual Description. Builder visual fields take priority:',
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
    settings.cardMode = $('#cardMode')?.value || 'multi';
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

function collectWorkspacePayloadForTab(tabIndex = activeOutputTabIndex, baseSettings = null) {
  captureActiveOutputTab();
  captureActiveConceptTab();
  captureActiveManualTab();
  ensureLinkedWorkspaceTabs();
  const tabs = Array.isArray(characterOutputTabs) ? characterOutputTabs : [];
  const tab = tabs[tabIndex] || tabs[activeOutputTabIndex] || null;
  const conceptTab = conceptWorkspaceTabs[tabIndex] || conceptWorkspaceTabs[activeConceptTabIndex] || makeBlankConceptTab(`Concept ${tabIndex + 1}`);
  const isActiveOutput = tabIndex === activeOutputTabIndex;
  const isActiveConcept = tabIndex === activeConceptTabIndex;
  const tabOutput = isActiveOutput ? ($('#outputText')?.value || '') : loadedOutputTextFromTab(tab || {});
  const tabQa = isActiveOutput ? (($('#qaAnswersText')?.value || lastQnaAnswers || '')) : loadedQaTextFromTab(tab || {});
  const tabEmotions = isActiveOutput ? (emotionImageState || []) : (Array.isArray(tab?.emotionImages) ? tab.emotionImages : []);
  const tabGenerated = Array.isArray(tab?.generatedImages) ? tab.generatedImages : [];
  const tabImage = String(isActiveOutput ? ($('#cardImagePath')?.value || tab?.cardImagePath || '') : (tab?.cardImagePath || '')).trim();
  const tabName = cleanOutputTabName(tab?.name || tab?.focusName || extractOutputNameForTab(tabOutput) || `Character ${tabIndex + 1}`);
  const conceptValue = isActiveConcept ? ($('#conceptText')?.value || '') : (conceptTab?.concept || '');
  const visionDescriptionValue = isActiveConcept ? ($('#visionDescription')?.value || '') : (conceptTab?.visionDescription || '');
  const conceptAttachmentsValue = isActiveConcept ? (conceptAttachments || []) : (Array.isArray(conceptTab?.conceptAttachments) ? conceptTab.conceptAttachments : []);
  let builderStateValue = conceptTab?.builderState || { mode: 'single', selectedIndex: 0, states: [{}] };
  if (isActiveConcept) {
    try { builderStateValue = collectBuilderWorkspaceState(); } catch (_) {}
  }
  const payloadSettings = { ...(baseSettings || settings || {}) };
  payloadSettings.cardImagePath = tabImage;
  payloadSettings.visionImagePath = isActiveConcept ? ($('#visionImagePath')?.value || '') : (conceptTab?.visionImagePath || '');
  const outputTabForProject = {
    ...(tab || {}),
    name: tabName || `Character ${tabIndex + 1}`,
    focusName: tab?.focusName || tabName || `Character ${tabIndex + 1}`,
    output: tabOutput,
    qaAnswers: cleanQaAnswersForStorage(tabQa, tabOutput),
    qnaAnswers: cleanQaAnswersForStorage(tabQa, tabOutput),
    emotionImages: tabEmotions,
    generatedImages: tabGenerated,
    cardImagePath: tabImage,
    imagePath: tabImage,
    projectPath: canonicalWorkspaceProjectPath(tab?.projectPath || tab?.workspaceProjectPath || ''),
    workspaceProjectPath: canonicalWorkspaceProjectPath(tab?.workspaceProjectPath || tab?.projectPath || ''),
  };
  const conceptTabForProject = normaliseConceptTab({
    ...(conceptTab || {}),
    name: tabName || conceptTab?.name || `Concept ${tabIndex + 1}`,
    concept: conceptValue,
    visionDescription: visionDescriptionValue,
    visionImagePath: payloadSettings.visionImagePath || '',
    conceptAttachments: conceptAttachmentsValue,
    builderState: builderStateValue,
  }, tabName || `Concept ${tabIndex + 1}`);
  const manualTabForProject = normaliseManualTab(manualGuideTabs[tabIndex] || {}, tabName || `Manual ${tabIndex + 1}`);
  return {
    concept: conceptValue,
    output: tabOutput,
    template,
    settings: payloadSettings,
    builderState: builderStateValue,
    qnaAnswers: tabQa,
    emotionImages: tabEmotions,
    generatedImages: tabGenerated,
    visionDescription: visionDescriptionValue,
    visionImagePath: payloadSettings.visionImagePath || '',
    conceptAttachments: conceptAttachmentsValue,
    cardImagePath: tabImage,
    imagePath: tabImage,
    _disableSettingsCardImageFallback: !tabImage,
    browserDescription: isActiveOutput ? (currentBrowserDescription || '') : '',
    cardRating: isActiveOutput ? (currentCardRating || '') : '',
    cardRatingReasoning: isActiveOutput ? (currentCardRatingReasoning || '') : '',
    cardRatingDetails: isActiveOutput && Array.isArray(currentCardRatingDetails) ? currentCardRatingDetails : [],
    cardRatingSourceHash: isActiveOutput ? (currentCardRatingSourceHash || '') : '',
    name: tabName || `Character ${tabIndex + 1}`,
    projectPath: canonicalWorkspaceProjectPath(tab?.projectPath || tab?.workspaceProjectPath || ''),
    characterTabs: [outputTabForProject],
    conceptTabs: [conceptTabForProject],
    activeConceptTabIndex: 0,
    manualTabs: [manualTabForProject],
    activeManualGuideTabIndex: 0,
    splitTabIndex: tabIndex,
    splitTabCount: tabs.length,
  };
}

function collectWorkspacePayload() {
  settings = collectSettings();
  return collectWorkspacePayloadForTab(activeOutputTabIndex, settings);
}

function shouldSaveAllSplitOutputTabs(reason = '') {
  const tabs = Array.isArray(characterOutputTabs) ? characterOutputTabs : [];
  if (tabs.length <= 1) return false;
  const mode = String(settings?.cardMode || $('#cardMode')?.value || '').toLowerCase();
  if (mode === 'split_cards') return true;
  return tabs.some(tab => String(tab?.splitCard || tab?.splitMode || '').toLowerCase() === 'split_cards');
}

function scheduleOutputEditorAutosave() {
  if (outputEditorSaveTimer) clearTimeout(outputEditorSaveTimer);
  outputEditorSaveTimer = setTimeout(() => {
    outputEditorSaveTimer = null;
    if (!isBusy && hasOutput()) saveCurrentWorkspace('silent');
  }, 1500);
}

async function importCurrentOutputToBrowser(showStatus = true) {
  if (!hasOutput()) {
    setStatus('Load or generate a card first.', 'error');
    return null;
  }
  const res = await saveCurrentWorkspace('silent');
  if (res && showStatus) setStatus(`Imported current card into Character Browser: ${res.folder}`, 'ok');
  return res;
}

async function generateSdPromptFromLoadedOutput() {
  if (isInterfaceLocked()) return;
  if (!hasOutput()) { setStatus('Load or generate a card first.', 'error'); return; }
  settings = collectSettings();
  const missing = validateTextApiSettings(settings);
  if (missing) { setStatus(missing, 'error'); switchToSettingsTab(); return; }
  setBusy('GENERATING STABLE DIFFUSION PROMPT FROM FULL TEXT OUTPUT…');
  try {
    const res = await window.pywebview.api.generate_sd_prompt_from_output($('#outputText').value, settings);
    if (!res.ok) throw new Error(res.error || 'Could not generate Stable Diffusion Prompt.');
    $('#outputText').value = res.output || $('#outputText').value;
    updateImportedCardToolsHint();
    await saveCurrentWorkspace('silent');
    setStatus('Generated Stable Diffusion Prompt from Full Text Output and saved it to the current card.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function generateSdPromptFromLoadedVision() {
  if (isInterfaceLocked()) return;
  if (!hasOutput()) { setStatus('Load or generate a card first.', 'error'); return; }
  const imagePath = ($('#cardImagePath')?.value || '').trim();
  if (!imagePath) { setStatus('Select or load a card image first.', 'error'); return; }
  settings = collectSettings();
  const textMissing = validateTextApiSettings(settings);
  if (textMissing) { setStatus(textMissing, 'error'); switchToSettingsTab(); return; }
  const visionMissing = validateVisionApiSettings(settings);
  if (visionMissing) { setStatus(visionMissing, 'error'); switchToSettingsTab(); return; }
  setBusy('GENERATING STABLE DIFFUSION PROMPT FROM VISION…');
  try {
    const res = await window.pywebview.api.generate_sd_prompt_from_vision(imagePath, $('#outputText').value, settings);
    if (!res.ok) throw new Error(res.error || 'Could not generate Stable Diffusion Prompt from vision.');
    $('#outputText').value = res.output || $('#outputText').value;
    if (typeof res.visionDescription === 'string' && $('#visionDescription')) $('#visionDescription').value = res.visionDescription;
    updateImportedCardToolsHint();
    await saveCurrentWorkspace('silent');
    setStatus('Generated Stable Diffusion Prompt from the current card image and saved it to the current card.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}


function collectOpenCharactersForRelationshipMatrix(options = {}) {
  // Relationship Matrix must be read-only during normal tab rendering/load.
  // Beta7 accidentally captured the active editor DOM while the loaded tab rail
  // was being rendered, before the loaded output was applied to the textarea.
  // That overwrote freshly loaded tabs with the previous/blank editor state.
  // Only capture on an explicit Generate/Copy-style action where the user may
  // have unsaved edits in the visible Output textarea.
  if (options.captureCurrent) captureActiveOutputTab();
  if (options.ensureTabs) ensureLinkedWorkspaceTabs();
  return (characterOutputTabs || [])
    .map((tab, idx) => ({
      name: cleanOutputTabName(tab?.name || tab?.focusName || extractOutputNameForTab(tab?.output || '') || `Character ${idx + 1}`),
      output: String(tab?.output || '').trim(),
      index: idx + 1,
    }))
    .filter(item => item.output);
}

function refreshRelationshipMatrixOpenCharacterList() {
  const holder = $('#relationshipMatrixOpenCharacters');
  if (!holder) return;
  const chars = collectOpenCharactersForRelationshipMatrix();
  if (!chars.length) {
    holder.innerHTML = '<div class="empty small">No generated characters are open yet.</div>';
    return;
  }
  holder.innerHTML = chars.map(c => `<span class="tag-pill">${escapeHtml(c.name)}</span>`).join('');
}

function applyRelationshipMatrixText(value) {
  relationshipMatrixText = String(value || '');
  const box = $('#relationshipMatrixText');
  if (box) box.value = relationshipMatrixText;
}

async function generateRelationshipMatrixForOpenCharacters() {
  if (isInterfaceLocked()) return;
  const chars = collectOpenCharactersForRelationshipMatrix({ captureCurrent: true, ensureTabs: true });
  refreshRelationshipMatrixOpenCharacterList();
  if (chars.length < 2) {
    setStatus('Open or generate at least two characters before generating a relationship matrix.', 'error');
    return;
  }
  settings = collectSettings();
  const missing = validateTextApiSettings(settings);
  if (missing) { setStatus(missing, 'error'); switchToSettingsTab(); return; }
  setBusy('RELATIONSHIP MATRIX — analyzing open characters…');
  try {
    const res = await window.pywebview.api.generate_relationship_matrix(chars, settings);
    if (!res.ok) throw new Error(res.error || 'Relationship matrix generation failed.');
    applyRelationshipMatrixText(res.matrix || '');
    setStatus(`Generated relationship matrix for ${chars.length} open character${chars.length === 1 ? '' : 's'}.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function copyRelationshipMatrixToClipboard() {
  const text = ($('#relationshipMatrixText')?.value || relationshipMatrixText || '').trim();
  if (!text) { setStatus('No relationship matrix to copy yet.', 'error'); return; }
  try {
    await navigator.clipboard.writeText(text);
    setStatus('Relationship matrix copied to clipboard.', 'ok');
  } catch (_) {
    setStatus('Could not access clipboard. Select the matrix text and copy manually.', 'warn');
  }
}

async function saveCurrentWorkspace(reason='autosave') {
  captureActiveOutputTab();
  if (!hasOutput()) return null;
  try {
    settings = collectSettings();
    if (shouldSaveAllSplitOutputTabs(reason)) {
      const tabs = Array.isArray(characterOutputTabs) ? characterOutputTabs : [];
      const saved = [];
      const failed = [];
      for (let idx = 0; idx < tabs.length; idx += 1) {
        const payload = collectWorkspacePayloadForTab(idx, settings);
        if (!String(payload.output || '').trim()) continue;
        const res = await window.pywebview.api.save_character_workspace(payload);
        if (res && res.ok) saved.push(res);
        else failed.push({ index: idx, name: payload.name || `Character ${idx + 1}`, error: res?.error || 'Workspace save failed.' });
      }
      if (failed.length) {
        const msg = failed.map(f => `${f.name}: ${f.error}`).join('; ');
        throw new Error(`Saved ${saved.length} split card(s), but ${failed.length} failed. ${msg}`);
      }
      if (reason !== 'silent') {
        const activeSaved = saved[activeOutputTabIndex] || saved[0];
        setStatus(`Saved ${saved.length} split character workspace${saved.length === 1 ? '' : 's'} to the Character Browser${activeSaved?.folder ? `, including ${activeSaved.folder}` : ''}.`, 'ok');
      }
      await refreshCharacterBrowser(false);
      return saved[activeOutputTabIndex] || saved[0] || null;
    }

    const payload = collectWorkspacePayload();
    const res = await window.pywebview.api.save_character_workspace(payload);
    if (!res.ok) throw new Error(res.error || 'Workspace save failed.');
    if (reason !== 'silent') setStatus(`Workspace saved to ${res.folder}`, 'ok');
    await refreshCharacterBrowser(false);
    return res;
  } catch (err) {
    setStatus(`Workspace autosave failed: ${err.message || err}`, 'error');
    return null;
  }
}

async function refreshCharacterBrowser(showStatus=true, options={}) {
  const useModal = !!(options && options.modal);
  if (useModal && !options.keepModalVisible) {
    showBrowserLoadingModal();
    await waitForNextFrame();
  }
  try {
    const res = await window.pywebview.api.list_character_library();
    if (!res.ok) throw new Error(res.error || 'Could not load character browser.');
    characterBrowserCards = res.cards || [];
    if (Array.isArray(res.folders)) {
      browserVirtualFolders = res.folders;
      if (settings) settings.browserVirtualFolders = res.folders;
    }
    if (selectedCharacterProjectPath && !characterBrowserCards.some(c => c.projectPath === selectedCharacterProjectPath)) {
      selectedCharacterProjectPath = '';
    }
    browserSelectedProjects = new Set([...browserSelectedProjects].filter(path => characterBrowserCards.some(c => c.projectPath === path)));
    renderCharacterBrowser();
    if (selectedCharacterProjectPath && characterBrowserCards.some(c => c.projectPath === selectedCharacterProjectPath)) {
      selectCharacterBrowserCard(selectedCharacterProjectPath);
    } else {
      renderSelectedCharacterTags(null);
      updateBrowserRatingPanel(null);
    }
    if (showStatus) setStatus(`Character Browser refreshed: ${characterBrowserCards.length} character(s).`, 'ok');
  } catch (err) {
    if (showStatus) setStatus(err.message || String(err), 'error');
  } finally {
    if (useModal) hideBrowserLoadingModal();
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

function browserFolderIdsForView(mode = 'view') {
  const current = normaliseFolderId(browserCurrentFolderId);
  if (current === '__all__') return null; // null means every folder/card is in scope.
  const includeSubfolders = mode === 'current_subfolders' || (mode === 'view' && browserShowSubfolders);
  const ids = new Set([current]);
  if (includeSubfolders) {
    browserFolderDescendantIds(current).forEach(id => ids.add(id));
  }
  return ids;
}

function browserCardMatchesFolderView(card) {
  const ids = browserFolderIdsForView('view');
  if (ids === null) return true;
  return ids.has(browserCardFolderId(card));
}

function browserCardsForSearchAndFilter() {
  // Folder dropdown controls the normal view. When search/filter is active,
  // this dropdown decides how far the search/filter should reach.
  if (browserFolderScope === 'global') return characterBrowserCards.slice();
  if (browserCurrentFolderId === '__all__') return characterBrowserCards.slice();
  const ids = browserFolderIdsForView(browserFolderScope === 'current_subfolders' ? 'current_subfolders' : 'current');
  if (ids === null) return characterBrowserCards.slice();
  return characterBrowserCards.filter(card => ids.has(browserCardFolderId(card)));
}

function browserViewCards() {
  return characterBrowserCards.filter(browserCardMatchesFolderView);
}

function browserSearchOrFilterActive() {
  return !!browserSearchTerm.trim() || browserIncludeTags.size > 0 || browserExcludeTags.size > 0;
}

function browserScopeCards() {
  return browserSearchOrFilterActive() ? browserCardsForSearchAndFilter() : browserViewCards();
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

function browserFolderPathParts(folderId) {
  const id = normaliseFolderId(folderId);
  if (id === '__all__') return [{ id: '__all__', name: 'All folders' }];
  const parts = [{ id: '', name: 'Root / Unfiled' }];
  if (!id) return parts;
  let current = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === id);
  const chain = [];
  const guard = new Set();
  while (current && !guard.has(current.id)) {
    guard.add(current.id);
    chain.unshift({ id: current.id, name: current.name || 'Folder' });
    current = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === normaliseFolderId(current.parentId));
  }
  return parts.concat(chain);
}

function setBrowserCurrentFolder(folderId, message = '') {
  browserCurrentFolderId = normaliseFolderId(folderId);
  const folderSelect = $('#browserFolderSelect');
  if (folderSelect) folderSelect.value = browserCurrentFolderId;
  renderCharacterBrowser();
  if (message) setStatus(message, 'ok');
}

function renderBrowserBreadcrumb() {
  const holder = $('#browserBreadcrumb');
  if (!holder) return;
  const parts = browserFolderPathParts(browserCurrentFolderId);
  const current = normaliseFolderId(browserCurrentFolderId);
  const parentId = (() => {
    if (!current || current === '__all__') return '';
    const folder = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === current);
    return normaliseFolderId(folder?.parentId || '');
  })();
  const upButton = current && current !== '__all__'
    ? `<button type="button" class="breadcrumb-up" data-folder="${escapeAttr(parentId)}">↑ Up</button>`
    : '';
  holder.innerHTML = `${upButton}<span class="breadcrumb-label">Location:</span> ` + parts.map((part, index) => {
    const isLast = index === parts.length - 1;
    const cls = isLast ? 'breadcrumb-part current' : 'breadcrumb-part';
    return `<button type="button" class="${cls}" data-folder="${escapeAttr(part.id)}" ${isLast ? 'disabled' : ''}>${escapeHtml(part.name)}</button>`;
  }).join('<span class="breadcrumb-sep">›</span>');
  $$('.breadcrumb-part:not(.current), .breadcrumb-up', holder).forEach(btn => {
    btn.addEventListener('click', () => setBrowserCurrentFolder(btn.dataset.folder || '', `Opened ${browserFolderPathLabel(btn.dataset.folder || '')}.`));
  });
}

function renderBrowserFolderControls() {
  const folderSelect = $('#browserFolderSelect');
  const moveSelect = $('#browserMoveFolderSelect');
  const scopeSelect = $('#browserFolderScope');
  const options = ['<option value="">Root / Unfiled</option>', '<option value="__all__">All folders</option>']
    .concat((browserVirtualFolders || [])
      .slice()
      .sort((a,b) => browserFolderPathLabel(a.id).localeCompare(browserFolderPathLabel(b.id), undefined, { sensitivity: 'base' }))
      .map(f => `<option value="${escapeAttr(f.id)}">${escapeHtml(browserFolderPathLabel(f.id))}</option>`));
  if (folderSelect) {
    folderSelect.innerHTML = options.join('');
    if (![...folderSelect.options].some(o => o.value === browserCurrentFolderId)) browserCurrentFolderId = '';
    folderSelect.value = browserCurrentFolderId;
  }
  if (moveSelect) {
    const moveOptions = ['<option value="">Root / Unfiled</option>'].concat((browserVirtualFolders || [])
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
  const bulk = $('.browser-bulk-toolbar');
  if (bulk && count) bulk.open = true;
}

async function saveBrowserVirtualFolders() {
  settings = { ...(settings || {}), browserVirtualFolders: browserVirtualFolders || [], browserShowSubfolders: !!browserShowSubfolders };
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

async function renameCurrentBrowserFolder() {
  const folderId = normaliseFolderId(browserCurrentFolderId);
  if (!folderId || folderId === '__all__') {
    setStatus('Select a virtual folder first. Root / All folders cannot be renamed.', 'error');
    return;
  }
  const folder = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === folderId);
  if (!folder) { setStatus('Selected virtual folder was not found.', 'error'); return; }
  const name = prompt('Rename virtual folder:', folder.name || '');
  const clean = String(name || '').trim();
  if (!clean) return;
  folder.name = clean;
  await saveBrowserVirtualFolders();
  renderCharacterBrowser();
  setStatus(`Renamed virtual folder to: ${clean}`, 'ok');
}

async function deleteCurrentBrowserFolder() {
  const folderId = normaliseFolderId(browserCurrentFolderId);
  if (!folderId || folderId === '__all__') {
    setStatus('Select a virtual folder first. Root / All folders cannot be deleted.', 'error');
    return;
  }
  const folder = (browserVirtualFolders || []).find(f => normaliseFolderId(f.id) === folderId);
  if (!folder) { setStatus('Selected virtual folder was not found.', 'error'); return; }
  const deleteIds = folderDescendantOrSelfIds(folderId);
  const affectedCards = (characterBrowserCards || []).filter(card => deleteIds.has(browserCardFolderId(card)));
  const childFolderCount = Math.max(0, deleteIds.size - 1);
  const ok = confirm(`Delete virtual folder "${folder.name}"${childFolderCount ? ` and ${childFolderCount} subfolder${childFolderCount === 1 ? '' : 's'}` : ''}?

${affectedCards.length} character${affectedCards.length === 1 ? '' : 's'} will be moved back to Root / Unfiled. Physical saved card folders and Front Porch entries are not deleted.`);
  if (!ok) return;
  setBusy('DELETING VIRTUAL FOLDER…');
  try {
    const paths = affectedCards.map(card => card.projectPath).filter(Boolean);
    if (paths.length) {
      const res = await window.pywebview.api.move_character_projects_to_folder(paths, '');
      if (!res.ok) throw new Error(res.error || 'Could not move characters back to root.');
    }
    browserVirtualFolders = (browserVirtualFolders || []).filter(f => !deleteIds.has(normaliseFolderId(f.id)));
    browserCurrentFolderId = '';
    await saveBrowserVirtualFolders();
    await refreshCharacterBrowser(false);
    setStatus(`Deleted virtual folder. Moved ${affectedCards.length} character${affectedCards.length === 1 ? '' : 's'} back to Root / Unfiled.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
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

async function deleteSelectedCharacterCard() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  const card = characterBrowserCards.find(c => c.projectPath === selectedCharacterProjectPath);
  const name = card?.name || 'this character';
  const ok = confirm(`Delete saved card "${name}" from Character Card Forge?\n\nThis deletes the physical saved/export folder for this card only. It does not delete virtual folders and does not touch Front Porch AI database entries.`);
  if (!ok) return;
  setBusy('DELETING SAVED CHARACTER CARD…');
  try {
    const res = await window.pywebview.api.delete_character_project_directories([selectedCharacterProjectPath]);
    if (!res.ok) throw new Error(res.error || 'Delete failed.');
    browserSelectedProjects.delete(selectedCharacterProjectPath);
    selectedCharacterProjectPath = '';
    await refreshCharacterBrowser(false);
    setStatus(`Deleted saved card folder for ${name}. Front Porch was not touched.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function deleteSelectedCharacterDirectories() {
  const paths = selectedBrowserProjectPaths();
  if (!paths.length) { setStatus('Select one or more characters first.', 'error'); return; }
  const ok = confirm(`Delete ${paths.length} physical saved Character Card Forge folder${paths.length === 1 ? '' : 's'} from disk?\n\nThis removes the real saved/export folder inside Character Card Forge. It does not delete virtual folders and does not touch Front Porch AI database entries.`);
  if (!ok) return;
  setBusy('DELETING PHYSICAL SAVED CHARACTER FOLDERS…');
  try {
    const res = await window.pywebview.api.delete_character_project_directories(paths);
    if (!res.ok) throw new Error(res.error || 'Delete failed.');
    browserSelectedProjects.clear();
    selectedCharacterProjectPath = '';
    await refreshCharacterBrowser(false);
    setStatus(`Deleted ${res.deleted || 0} physical saved character folder${res.deleted === 1 ? '' : 's'}. Virtual folders and Front Porch were not touched.`, 'ok');
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
  const targets = await chooseFrontPorchExportTargets({ count: paths.length, mode: 'batch' });
  if (!targets || !targets.length) return;

  if (!frontPorchBothFoldersConfigured(settings)) {
    const label = frontPorchTargetInfo(targets[0], settings).label;
    const okConfirm = confirm(`Export ${paths.length} selected character(s) to ${label}?

A database backup is created by the exporter. Close Front Porch before exporting if possible.`);
    if (!okConfirm) return;
  }

  const originalSettings = { ...settings };
  setBusy('BATCH EXPORTING TO FRONT PORCH AI…');
  let ok = 0;
  let failed = 0;
  const targetTotals = [];
  try {
    for (const target of targets) {
      const info = frontPorchTargetInfo(target, originalSettings);
      let targetOk = 0;
      let targetFailed = 0;
      setBusy(`BATCH EXPORTING TO ${info.label.toUpperCase()}…`);
      for (const path of paths) {
        try {
          const res = await exportFrontPorchProjectToTarget(path, target, originalSettings);
          if (res.ok) { ok += 1; targetOk += 1; }
          else { failed += 1; targetFailed += 1; }
        } catch (_) { failed += 1; targetFailed += 1; }
      }
      targetTotals.push(`${info.label}: ${targetOk} succeeded${targetFailed ? `, ${targetFailed} failed` : ''}`);
    }
  } finally {
    try { await window.pywebview.api.save_settings(originalSettings); } catch (_) {}
    settings = originalSettings;
    setBusy('');
  }
  setStatus(`Front Porch batch export complete — ${targetTotals.join(' | ')}.`, failed ? 'error' : 'ok');
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
    .filter(card => browserCardMatchesTagFilters(card) && browserCardMatchesSearch(card) && browserCardAllowedByPrivacy(card))
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

function configuredNsfwTagValues() {
  const raw = (settings && settings.nsfwTags) || 'NSFW';
  const values = Array.isArray(raw) ? raw : String(raw || '').split(/[,\n]+/);
  const cleaned = [];
  const seen = new Set();
  values.forEach(value => {
    const tag = normaliseBrowserTag(value).replace(/^[-•*]+\s*/, '');
    const key = browserTagKey(tag);
    if (key && !seen.has(key)) {
      seen.add(key);
      cleaned.push(tag);
    }
  });
  return cleaned.length ? cleaned : ['NSFW'];
}

function primaryNsfwTagValue() {
  return configuredNsfwTagValues()[0] || 'NSFW';
}

function browserNsfwTags() {
  return new Set(configuredNsfwTagValues().map(browserTagKey).filter(Boolean));
}

function browserCardIsNsfw(card) {
  const nsfw = browserNsfwTags();
  return cardEffectiveTags(card).some(tag => nsfw.has(browserTagKey(tag)));
}

function browserPrivacyMode() {
  return (settings && settings.nsfwBrowserMode) || 'show';
}

function browserCardAllowedByPrivacy(card) {
  return !(browserPrivacyMode() === 'hide' && browserCardIsNsfw(card));
}

function getVisibleBrowserCards() {
  const cards = browserScopeCards().filter(card => browserCardMatches(card) && browserCardAllowedByPrivacy(card));
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
  setBusy('AI BROWSER ANALYSIS — READING CHARACTER CARD…');
  try {
    const res = await window.pywebview.api.regenerate_browser_description_for_project(selectedCharacterProjectPath, settings || {});
    if (!res.ok) throw new Error(res.error || 'Could not run AI browser analysis.');
    const card = getSelectedBrowserCard();
    let returnedDetails = ratingDetailsFromApiResult(res, card?.cardRatingDetails || []);
    let detailSource = String(res.cardRatingDetailSource || res.detailSource || '').trim();
    if (!returnedDetails.length) {
      setBusy('AI BROWSER ANALYSIS — repairing missing rating details…');
      const ensured = await ensureRatingDetailsForSelectedCard(card, 'regenerate-description');
      if (ensured.length) {
        returnedDetails = ensured;
        detailSource = detailSource || 'ensured';
      }
    }
    if (card) {
      card.browserDescription = res.browserDescription || card.browserDescription || '';
      card.browserDescriptionSource = res.browserDescriptionSource || 'ai';
      card.cardRating = res.cardRating || res.rating || card.cardRating || '';
      card.cardRatingReasoning = res.cardRatingReasoning || res.reasoning || card.cardRatingReasoning || '';
      card.cardRatingDetails = returnedDetails;
      card.cardRatingDetailSource = detailSource;
      card.cardRatingSourceHash = res.cardRatingSourceHash || res.sourceHash || res.source_hash || card.cardRatingSourceHash || '';
      if (Array.isArray(res.tags) && res.tags.length) card.tags = res.tags;
    }
    currentBrowserDescription = res.browserDescription || '';
    currentCardRating = res.cardRating || res.rating || '';
    currentCardRatingReasoning = res.cardRatingReasoning || res.reasoning || '';
    currentCardRatingDetails = returnedDetails;
    currentCardRatingSourceHash = res.cardRatingSourceHash || res.sourceHash || res.source_hash || '';
    const preview = $('#browserPreview');
    if (preview) preview.value = res.browserDescription || '';
    updateBrowserRatingPanel(card || { cardRating: res.cardRating || res.rating || '', cardRatingReasoning: res.cardRatingReasoning || res.reasoning || '', cardRatingDetails: returnedDetails });
    const sourceBadge = $('#browserDescriptionSource');
    if (sourceBadge) {
      const source = res.browserDescriptionSource || 'ai';
      sourceBadge.textContent = descriptionSourceLabel(source);
      sourceBadge.classList.remove('hidden');
      sourceBadge.classList.toggle('ai-source', String(source).toLowerCase() === 'ai');
      sourceBadge.classList.toggle('extracted-source', String(source).toLowerCase() !== 'ai');
    }
    await refreshCharacterBrowser(false);
    // If the SQLite browser cache ever lags behind the just-saved project, keep
    // the visible selected card hydrated with the fresh response so the Details
    // modal cannot fall back to an empty/stale array.
    const refreshedCard = getSelectedBrowserCard();
    if (refreshedCard && selectedCharacterProjectPath === (res.projectPath || selectedCharacterProjectPath)) {
      refreshedCard.cardRating = refreshedCard.cardRating || currentCardRating;
      refreshedCard.cardRatingReasoning = refreshedCard.cardRatingReasoning || currentCardRatingReasoning;
      if (Array.isArray(res.tags) && res.tags.length) refreshedCard.tags = res.tags;
      if (!normaliseRatingDetails(refreshedCard.cardRatingDetails || []).length && currentCardRatingDetails.length) {
        refreshedCard.cardRatingDetails = currentCardRatingDetails;
        updateBrowserRatingPanel(refreshedCard);
      }
    }
    const detailCount = normaliseRatingDetails(currentCardRatingDetails || []).length;
    const detailHint = detailCount ? ` with ${detailCount} detail ratings${detailSource ? ` (${detailSource})` : ''}` : '';
    const ratingMsg = currentCardRating ? ` Rating: ${currentCardRating}/10${detailHint}.` : '';
    const nsfwMsg = res.nsfwTagAdded ? ` Added ${primaryNsfwTagValue()} tag.` : '';
    setStatus(`AI browser analysis updated.${ratingMsg}${nsfwMsg}`, 'ok');
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
        <button id="browserMarkNsfwBtn" type="button" title="Add the first configured NSFW marker tag to this card">Mark NSFW</button>
        <button id="browserSaveTagsBtn" type="button" class="primary">Save Tags</button>
        <button id="browserCancelTagsBtn" type="button">Cancel</button>
      </div>
      <div id="browserEditableTagList" class="editable-tag-list">${tags.map(tag => `<button type="button" class="editable-tag" data-tag="${escapeAttr(tag)}" title="Remove tag">${escapeHtml(tag)} ×</button>`).join('')}</div>
      <div class="tag-editor-hint">Click a character tag to filter. In edit mode, click a tag to remove it. NSFW privacy uses the tags configured in Settings → Tags.</div>
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
  $('#browserMarkNsfwBtn')?.addEventListener('click', () => addEditorTag(primaryNsfwTagValue()));
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


function folderDescendantOrSelfIds(folderId) {
  const id = normaliseFolderId(folderId);
  const ids = browserFolderDescendantIds(id);
  ids.add(id);
  return ids;
}

function browserFolderVisibleInGrid(folder) {
  const fid = normaliseFolderId(folder?.id);
  if (!fid) return false;
  const parent = normaliseFolderId(folder?.parentId);
  const current = normaliseFolderId(browserCurrentFolderId);
  if (current === '__all__') {
    return browserShowSubfolders ? true : parent === '';
  }
  if (browserShowSubfolders) {
    if (parent === current) return true;
    return browserFolderDescendantIds(current).has(fid);
  }
  return parent === current;
}

function browserFolderCardCards(folderId, sourceCards = null) {
  const ids = folderDescendantOrSelfIds(folderId);
  const pool = sourceCards || characterBrowserCards || [];
  return pool.filter(card => ids.has(browserCardFolderId(card)));
}

function getVisibleBrowserFolders(visibleCards) {
  const folders = (browserVirtualFolders || []).filter(browserFolderVisibleInGrid);
  // When searching/filtering, hide folder tiles that contain no matching character
  // within the active search/filter result set. Otherwise keep empty folders visible.
  const searchActive = browserSearchOrFilterActive();
  const filtered = searchActive
    ? folders.filter(folder => browserFolderCardCards(folder.id, visibleCards).length > 0)
    : folders;
  return filtered.slice().sort((a,b) => browserFolderPathLabel(a.id).localeCompare(browserFolderPathLabel(b.id), undefined, { sensitivity: 'base' }));
}

function renderFolderPreviewThumbs(folder, visibleCards) {
  const source = browserSearchOrFilterActive() ? visibleCards : characterBrowserCards;
  const cards = browserFolderCardCards(folder.id, source)
    .filter(card => card.thumbnail)
    .slice(0, 4);
  if (!cards.length) return '<div class="folder-empty-icon">📁</div>';
  return cards.map(card => `<img src="${card.thumbnail}" alt="${escapeAttr(card.name || '')}" />`).join('');
}

function folderCardCount(folderId) {
  return browserFolderCardCards(folderId, characterBrowserCards).length;
}

function cardRatingValue(card) {
  const raw = card ? (card.cardRating ?? card.rating ?? '') : '';
  const text = String(raw || '').trim();
  if (!text) return '';
  const match = text.match(/\d+(?:\.\d+)?/);
  if (!match) return '';
  let num = Number(match[0]);
  if (!Number.isFinite(num)) return '';
  num = Math.max(0, Math.min(10, num));
  return Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : String(Math.round(num * 10) / 10);
}

function cardRatingBadgeHtml(card) {
  const rating = cardRatingValue(card);
  if (!rating) return '';
  const reason = String(card?.cardRatingReasoning || '').trim();
  const detailCount = normaliseRatingDetails(card?.cardRatingDetails || []).length;
  const title = reason ? `Card Rating: ${rating}/10${detailCount ? ` (${detailCount} details)` : ''} — ${reason}` : `Card Rating: ${rating}/10${detailCount ? ` (${detailCount} details)` : ''}`;
  return `<div class="character-rating-badge" title="${escapeAttr(title)}">★ ${escapeHtml(rating)}/10</div>`;
}

function normaliseTextForDiff(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function sectionKeyFromTitle(title) {
  return String(title || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function parseCardSectionsForDiff(text) {
  const knownTitles = (template?.sections || [])
    .map(sec => String(sec?.title || '').trim())
    .filter(Boolean);
  const knownKeys = new Map(knownTitles.map(title => [sectionKeyFromTitle(title), title]));
  const sections = new Map();
  let currentKey = 'full_card';
  let currentTitle = 'Full Card';
  const ensure = () => {
    if (!sections.has(currentKey)) sections.set(currentKey, { key: currentKey, name: currentTitle, lines: [] });
  };
  ensure();
  String(text || '').split(/\r?\n/).forEach(rawLine => {
    const line = rawLine.trim();
    const headingRaw = line.replace(/^[-#*\s]+/, '').replace(/[:：]\s*$/, '').trim();
    const headingKey = sectionKeyFromTitle(headingRaw);
    const looksLikeKnown = knownKeys.has(headingKey);
    const looksLikeHeading = looksLikeKnown || (/^[A-Za-z][A-Za-z0-9 /&(){}'’-]{1,70}$/.test(headingRaw) && /[:：]\s*$/.test(line));
    if (looksLikeHeading && headingRaw.length <= 90) {
      currentKey = headingKey || headingRaw.toLowerCase();
      currentTitle = knownKeys.get(headingKey) || headingRaw;
      ensure();
      return;
    }
    ensure();
    sections.get(currentKey).lines.push(rawLine);
  });
  return [...sections.values()].reduce((acc, item) => {
    const body = item.lines.join('\n').trim();
    if (body || item.key !== 'full_card') acc[item.key] = { name: item.name, body };
    return acc;
  }, {});
}

function computeFieldDiffsForPreview(original, revised) {
  const oldSections = parseCardSectionsForDiff(original || '');
  const newSections = parseCardSectionsForDiff(revised || '');
  const ordered = [];
  (template?.sections || []).forEach(sec => {
    const title = String(sec?.title || '').trim();
    const key = sectionKeyFromTitle(title);
    if (key && !ordered.includes(key)) ordered.push(key);
  });
  Object.keys(oldSections).concat(Object.keys(newSections)).forEach(key => {
    if (!ordered.includes(key)) ordered.push(key);
  });
  return ordered.map(key => {
    const oldBody = oldSections[key]?.body || '';
    const newBody = newSections[key]?.body || '';
    if (!oldBody && !newBody) return null;
    let status = 'changed';
    if (normaliseTextForDiff(oldBody) === normaliseTextForDiff(newBody)) status = 'unchanged';
    else if (oldBody && !newBody) status = 'removed';
    else if (!oldBody && newBody) status = 'added';
    return {
      name: oldSections[key]?.name || newSections[key]?.name || key.replace(/_/g, ' '),
      key,
      status,
      oldLength: oldBody.length,
      newLength: newBody.length,
      delta: newBody.length - oldBody.length
    };
  }).filter(Boolean).slice(0, 40);
}

function normaliseImprovementFieldDiffs(value, original='', revised='') {
  if (Array.isArray(value) && value.length) {
    return value.map(item => ({
      name: String(item?.name || item?.field || item?.section || 'Section').trim(),
      status: String(item?.status || (item?.changed === false ? 'unchanged' : 'changed')).toLowerCase(),
      oldLength: Number(item?.oldLength || 0),
      newLength: Number(item?.newLength || 0),
      delta: Number(item?.delta || 0)
    })).filter(item => item.name).slice(0, 40);
  }
  return computeFieldDiffsForPreview(original, revised);
}

function renderRatingImproveFieldDiffs(diffs) {
  const box = $('#ratingImproveFieldDiffs');
  if (!box) return;
  const list = Array.isArray(diffs) ? diffs : [];
  if (!list.length) {
    box.innerHTML = '<div class="empty small">Field-by-field preview will appear after the improved card is generated.</div>';
    return;
  }
  box.innerHTML = list.map(item => {
    const status = ['changed','unchanged','added','removed'].includes(item.status) ? item.status : 'changed';
    const label = status.charAt(0).toUpperCase() + status.slice(1);
    const delta = Number.isFinite(Number(item.delta)) && Number(item.delta) !== 0 ? ` · ${Number(item.delta) > 0 ? '+' : ''}${Number(item.delta)} chars` : '';
    return `<div class="rating-field-diff-row ${escapeAttr(status)}"><span class="rating-field-name">${escapeHtml(item.name)}</span><span class="rating-field-status">${escapeHtml(label)}${escapeHtml(delta)}</span></div>`;
  }).join('');
}

function renderRatingImproveLostDetails(items, summary='') {
  const box = $('#ratingImproveLostDetails');
  if (!box) return;
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  const summaryText = String(summary || '').trim();
  if (!list.length && !summaryText) {
    box.innerHTML = '<div class="empty small">Lost-detail check will appear after the improved card is generated.</div>';
    return;
  }
  const summaryHtml = summaryText ? `<p class="rating-lost-summary">${escapeHtml(summaryText)}</p>` : '';
  const listHtml = list.length
    ? `<ul>${list.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
    : '<div class="ok small">No obvious removed details were flagged. Still review the preview manually.</div>';
  box.innerHTML = summaryHtml + listHtml;
}

function closeRatingImproveModal() {
  const modal = $('#ratingImproveModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function showRatingImproveModal({ card=null, output='', loading=false, fieldDiffs=null, lostDetails=null, lostDetailSummary='' } = {}) {
  const modal = $('#ratingImproveModal');
  if (!modal) return;
  const summary = $('#ratingImproveSummary');
  const notes = $('#ratingImproveNotes');
  const preview = $('#ratingImprovePreview');
  const commit = $('#commitRatingImproveBtn');
  const copy = $('#copyRatingImprovePreviewBtn');
  const rating = cardRatingValue(card);
  const name = card?.name || 'selected card';
  if (summary) summary.textContent = loading
    ? `Generating an improved preview for ${name}${rating ? ` (${rating}/10)` : ''}…`
    : `Previewing AI improvements for ${name}${rating ? ` (${rating}/10)` : ''}.`;
  if (notes) notes.value = card?.cardRatingReasoning || 'No rating reasoning was saved for this card.';
  if (preview) preview.value = output || (loading ? 'Generating improved card preview…' : '');
  ratingImproveFieldDiffs = loading ? [] : normaliseImprovementFieldDiffs(fieldDiffs || [], '', output || '');
  ratingImproveLostDetails = Array.isArray(lostDetails) ? lostDetails : [];
  ratingImproveLostSummary = String(lostDetailSummary || '').trim();
  renderRatingImproveFieldDiffs(ratingImproveFieldDiffs);
  renderRatingImproveLostDetails(ratingImproveLostDetails, ratingImproveLostSummary);
  if (commit) commit.disabled = !!loading || !String(output || '').trim();
  if (copy) copy.disabled = !!loading || !String(output || '').trim();
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function availableApiMethodNames(pattern = /./) {
  const api = window.pywebview?.api;
  if (!api) return '';
  try { return Object.keys(api).filter(k => pattern.test(k)).sort().join(', '); }
  catch (_) { return ''; }
}

async function callCardImprovementPreviewBackend(projectPath, activeSettings) {
  const api = window.pywebview?.api;
  if (!api) return { ok: false, error: 'Backend API is not available yet.' };

  const directFn = api.generate_card_improvement_from_rating
    || api.generateCardImprovementFromRating
    || api.improveCardFromRating
    || api.revise_card_from_rating_project
    || api.reviseCardFromRatingProject;
  if (directFn) return await directFn.call(api, projectPath, activeSettings || {});

  // Compatibility fallback for AppImage/pywebview builds whose method table was
  // generated before the dedicated rating-improvement backend method existed.
  // It uses older, already-exposed bridge methods: load_character_project + revise_card.
  const loadFn = api.load_character_project;
  const reviseFn = api.revise_card;
  if (!loadFn || !reviseFn) {
    const available = availableApiMethodNames(/improve|rating|card|character|revise|load/i);
    return {
      ok: false,
      error: 'Card improvement backend is not available in this build, and the compatibility fallback is missing required methods.' + (available ? ` Available related API methods: ${available}` : '')
    };
  }

  const loaded = await loadFn.call(api, projectPath);
  if (!loaded || !loaded.ok) return loaded || { ok: false, error: 'Could not load selected character project.' };

  const rating = String(loaded.cardRating || getSelectedBrowserCard()?.cardRating || '').trim();
  const reasoning = String(loaded.cardRatingReasoning || getSelectedBrowserCard()?.cardRatingReasoning || '').trim();
  if (!reasoning) {
    return { ok: false, error: 'Generate an AI Card Rating first so the model has improvement notes to apply.' };
  }

  const followup = [
    'Apply the AI Card Rating suggestions to improve this character card.',
    'Return the COMPLETE revised card only, not a diff and not commentary.',
    'PRESERVE CORE FACTS: do not remove or contradict existing facts.',
    'Do not change names, ages, relationships, setting, backstory, kinks, boundaries, or roleplay premise unless explicitly instructed.',
    'Improve wording, clarity, specificity, and roleplay usefulness while preserving the card\'s intent.',
    'Preserve the character name, premise, tone, relationship dynamic with {{user}}, and enabled section order.',
    'Do not simplify the card by deleting unique hooks, jobs, locations, history, or first-meeting setup.',
    'Improve craft/usability: make the concept clearer, deepen personality consistency, sharpen the scenario hook, improve {{user}} involvement, strengthen the first message, and clean formatting where needed.',
    rating ? `Current AI Card Rating: ${rating}/10` : '',
    '',
    'AI CARD RATING REASONING / IMPROVEMENT NOTES:',
    reasoning
  ].filter(Boolean).join('\n');

  const volatileImageKeys = ['cardImagePath', 'imagePath', 'imageDataUrl', 'cardImageDataUrl'];
  const cleanedActiveSettings = { ...(activeSettings || {}) };
  volatileImageKeys.forEach((key) => { delete cleanedActiveSettings[key]; });
  const mergedSettings = { ...(loaded.settings || {}), ...cleanedActiveSettings, streamAi: false, _streamTarget: '' };
  const originalImage = loaded.cardImagePath || loaded.imagePath || loaded.imageDataUrl || getSelectedBrowserCard()?.cardImagePath || getSelectedBrowserCard()?.imagePath || '';
  if (originalImage) mergedSettings.cardImagePath = originalImage;
  const res = await reviseFn.call(api, loaded.output || '', followup, loaded.concept || '', loaded.template || {}, mergedSettings);
  if (!res || !res.ok) return res || { ok: false, error: 'The revision backend did not return a result.' };
  const revisedOutput = res.output || '';
  return {
    ok: true,
    projectPath,
    name: loaded.name || getSelectedBrowserCard()?.name || '',
    rating,
    reasoning,
    output: revisedOutput,
    validation: res.validation || null,
    fieldDiffs: computeFieldDiffsForPreview(loaded.output || '', revisedOutput),
    lostDetails: [],
    lostDetailSummary: 'Lost-detail audit requires the newer rating-improvement backend. Review the field changes and full preview carefully.',
    fallbackMode: 'revise_card'
  };
}

async function callApplyCardImprovementBackend(projectPath, revisedOutput, activeSettings) {
  const api = window.pywebview?.api;
  if (!api) return { ok: false, error: 'Backend API is not available yet.' };

  const directFn = api.apply_card_improvement_preview
    || api.applyCardImprovementPreview
    || api.commitCardImprovementPreview;
  if (directFn) return await directFn.call(api, projectPath, revisedOutput, activeSettings || {});

  // Compatibility fallback: load the original project, replace only the output,
  // then save through the existing workspace save endpoint.
  const loadFn = api.load_character_project;
  const saveFn = api.save_character_workspace;
  if (!loadFn || !saveFn) {
    const available = availableApiMethodNames(/improve|rating|card|character|apply|commit|save|load/i);
    return {
      ok: false,
      error: 'Card improvement commit backend is not available in this build, and the compatibility fallback is missing required methods.' + (available ? ` Available related API methods: ${available}` : '')
    };
  }

  const loaded = await loadFn.call(api, projectPath);
  if (!loaded || !loaded.ok) return loaded || { ok: false, error: 'Could not load selected character project.' };

  const volatileImageKeys = ['cardImagePath', 'imagePath', 'imageDataUrl', 'cardImageDataUrl'];
  const cleanedActiveSettings = { ...(activeSettings || {}) };
  volatileImageKeys.forEach((key) => { delete cleanedActiveSettings[key]; });
  const originalImage = loaded.cardImagePath
    || loaded.imagePath
    || loaded.imageDataUrl
    || getSelectedBrowserCard()?.cardImagePath
    || getSelectedBrowserCard()?.imagePath
    || '';
  const savedSettings = { ...(loaded.settings || {}), ...cleanedActiveSettings };
  if (originalImage) savedSettings.cardImagePath = originalImage;

  const workspace = {
    ...(loaded.workspace || {}),
    name: loaded.name || getSelectedBrowserCard()?.name || '',
    concept: loaded.concept || '',
    output: revisedOutput || '',
    template: loaded.template || {},
    settings: savedSettings,
    cardImagePath: originalImage,
    imagePath: originalImage,
    imageDataUrl: loaded.imageDataUrl || '',
    _disableSettingsCardImageFallback: true,
    browserDescription: loaded.browserDescription || getSelectedBrowserCard()?.browserDescription || '',
    browserDescriptionSource: loaded.browserDescriptionSource || getSelectedBrowserCard()?.browserDescriptionSource || '',
    cardRating: '',
    cardRatingReasoning: '',
    cardRatingDetails: [],
    cardRatingSourceHash: '',
    tags: loaded.tags || getSelectedBrowserCard()?.tags || [],
    virtualFolderId: loaded.virtualFolderId || getSelectedBrowserCard()?.virtualFolderId || '',
    qnaAnswers: loaded.qnaAnswers || '',
    builderState: loaded.builderState || {},
    emotionImages: loaded.emotionImages || [],
    generatedImages: loaded.generatedImages || [],
    characterTabs: loaded.characterTabs || [],
    emotionManifest: loaded.emotionManifest || '',
    visionDescription: loaded.visionDescription || '',
    conceptAttachments: loaded.conceptAttachments || []
  };

  const res = await saveFn.call(api, workspace);
  if (!res || !res.ok) return res || { ok: false, error: 'Workspace save did not return a result.' };
  return { ...res, ok: true, fallbackMode: 'save_character_workspace' };
}

async function generateRatingImprovementPreview() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  const card = getSelectedBrowserCard();
  if (!cardRatingValue(card) && !String(card?.cardRatingReasoning || '').trim()) {
    setStatus('Generate an AI Card Rating first, then use Improve.', 'error');
    return;
  }
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  const okToImprove = window.confirm(
    'Lower-quality models may remove details, alter character intent, or simplify the card. Review all changes before committing.\n\nContinue and generate an improved preview?'
  );
  if (!okToImprove) return;
  ratingImprovementProjectPath = selectedCharacterProjectPath;
  showRatingImproveModal({ card, loading: true });
  setBusy('AI CARD IMPROVEMENT — GENERATING PREVIEW…');
  try {
    const res = await callCardImprovementPreviewBackend(selectedCharacterProjectPath, settings || {});
    if (!res.ok) throw new Error(res.error || 'Could not generate improved preview.');
    ratingImprovementProjectPath = res.projectPath || selectedCharacterProjectPath;
    showRatingImproveModal({
      card,
      output: res.output || '',
      fieldDiffs: res.fieldDiffs || [],
      lostDetails: res.lostDetails || [],
      lostDetailSummary: res.lostDetailSummary || ''
    });
    if (res.validation && res.validation.ok === false) {
      setStatus(`Improved preview generated, but structure check found ${res.validation.missing?.length || 0} missing item(s). Review before committing.`, 'error');
    } else {
      setStatus('Improved card preview generated. Review it before committing.', 'ok');
    }
  } catch (err) {
    closeRatingImproveModal();
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function commitRatingImprovementPreview() {
  const projectPath = ratingImprovementProjectPath || selectedCharacterProjectPath;
  const preview = $('#ratingImprovePreview')?.value || '';
  if (!projectPath) { setStatus('No selected project to update.', 'error'); return; }
  if (!preview.trim()) { setStatus('Preview is empty. Nothing to commit.', 'error'); return; }
  settings = collectSettings();
  setBusy('COMMITTING AI CARD IMPROVEMENT…');
  try {
    const res = await callApplyCardImprovementBackend(projectPath, preview, settings || {});
    if (!res.ok) throw new Error(res.error || 'Could not commit improved card.');
    closeRatingImproveModal();
    ratingImprovementProjectPath = '';
    const newPath = res.projectPath || projectPath;
    selectedCharacterProjectPath = newPath;
    await refreshCharacterBrowser(false);
    if (newPath) selectCharacterBrowserCard(newPath);
    setStatus(`Improved card committed and saved to ${res.folder || 'Character Browser'}.`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function copyRatingImprovementPreview() {
  const text = $('#ratingImprovePreview')?.value || '';
  if (!text.trim()) { setStatus('No preview to copy.', 'error'); return; }
  navigator.clipboard?.writeText(text).then(
    () => setStatus('Improved card preview copied.', 'ok'),
    () => setStatus('Could not copy preview.', 'error')
  );
}

const RATING_DETAIL_KEYS = [
  'cardRatingDetails', 'details', 'detailRatings', 'detail_ratings', 'detailedRatings', 'detailed_ratings',
  'elementRatings', 'element_ratings', 'elements', 'elementScores', 'element_scores',
  'criteria', 'criteriaRatings', 'criteria_ratings', 'criteriaScores', 'criteria_scores',
  'breakdown', 'breakdownByElement', 'breakdown_by_element', 'categoryBreakdown', 'category_breakdown',
  'categories', 'categoryRatings', 'category_ratings', 'scores', 'ratings', 'ratingDetails', 'rating_details',
  'perElementRatings', 'per_element_ratings', 'aspectRatings', 'aspect_ratings', 'sectionRatings', 'section_ratings'
];

const RATING_DETAIL_INTERNAL_KEYS = new Set([
  'ok', 'success', 'error', 'errors', 'projectpath', 'project_path', 'path', 'filepath', 'file_path',
  'browserdescription', 'browser_description', 'browserdescriptionsource', 'browser_description_source',
  'browserdescriptionsourcehash', 'browser_description_source_hash',
  'cardrating', 'card_rating', 'cardratingreasoning', 'card_rating_reasoning',
  'cardratingsourcehash', 'card_rating_source_hash', 'sourcehash', 'source_hash',
  'source', 'hash', 'updated_at', 'created_at', 'workspace', 'settings', 'output', 'concept'
]);

function firstRatingDetailValue(obj, keys) {
  if (!obj || typeof obj !== 'object') return '';
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = obj[key];
      if (value !== undefined && value !== null && String(value).trim() !== '') return value;
    }
  }
  return '';
}

function ratingDetailHasRowShape(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false;
  const rowName = firstRatingDetailValue(obj, ['name', 'category', 'element', 'criteria', 'criterion', 'field', 'section', 'title', 'aspect', 'label']);
  const rowScore = firstRatingDetailValue(obj, ['rating', 'score', 'value', 'points', 'grade', 'status']);
  return !!(rowName && rowScore !== '');
}

function ratingDetailPrimitiveLooksLikeScore(value) {
  if (value === undefined || value === null) return false;
  const text = String(value).trim();
  if (!text || text.length > 24) return false;
  if (/^(?:verified|changed|missing|present|weak|ok|good|great|excellent|needs work)$/i.test(text)) return true;
  const m = text.match(/^\s*(\d+(?:\.\d+)?)\s*(?:\/\s*10)?\s*$/);
  if (m) {
    const n = Number(m[1]);
    return Number.isFinite(n) && n >= 0 && n <= 10;
  }
  return /^[ABCDF][+-]?$/i.test(text);
}

function ratingDetailsPayloadFrom(value, depth = 0, allowObjectMap = false) {
  if (!value || depth > 4) return [];
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return ratingDetailsPayloadFrom(parsed, depth + 1, allowObjectMap);
    } catch (_) {
      return [];
    }
  }
  if (Array.isArray(value)) return value;
  if (typeof value !== 'object') return [];

  if (ratingDetailHasRowShape(value)) return [value];

  // Only descend into known detail container keys. This avoids treating the whole
  // character/project object as a fake rating map, which caused rows like
  // cardRatingReasoning, cardRatingSourceHash and projectPath to appear as scores.
  for (const key of RATING_DETAIL_KEYS) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      const nested = ratingDetailsPayloadFrom(value[key], depth + 1, true);
      if (nested.length) return nested;
    }
  }

  for (const key of ['result', 'evaluation', 'analysis', 'ratingResult', 'rating_result']) {
    if (value[key] && typeof value[key] === 'object') {
      const nested = ratingDetailsPayloadFrom(value[key], depth + 1, false);
      if (nested.length) return nested;
    }
  }

  if (!allowObjectMap) return [];

  const rows = [];
  for (const [key, val] of Object.entries(value)) {
    const lowered = String(key || '').toLowerCase();
    if (RATING_DETAIL_INTERNAL_KEYS.has(lowered)) continue;
    if (RATING_DETAIL_KEYS.includes(key)) continue;
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      const item = { name: key, ...val };
      if (ratingDetailHasRowShape(item)) rows.push(item);
    } else if (ratingDetailPrimitiveLooksLikeScore(val)) {
      rows.push({ name: key, rating: val, reason: '' });
    }
  }
  return rows;
}

function normaliseRatingDetails(details) {
  const payload = ratingDetailsPayloadFrom(details, 0, false);
  if (!Array.isArray(payload)) return [];
  const seen = new Set();
  return payload.map(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
    const name = String(firstRatingDetailValue(item, ['name', 'category', 'element', 'criteria', 'criterion', 'field', 'section', 'title', 'aspect', 'label']) || '').trim();
    if (!name) return null;
    const lowered = name.toLowerCase();
    if (RATING_DETAIL_INTERNAL_KEYS.has(lowered)) return null;
    const key = lowered.replace(/\s+/g, ' ').trim();
    if (seen.has(key)) return null;

    const rawRating = firstRatingDetailValue(item, ['rating', 'score', 'value', 'points', 'grade']);
    const status = String(firstRatingDetailValue(item, ['status', 'state']) || '').trim();
    const rating = String(rawRating ?? '').trim();
    // A row needs either a sane score/grade or a short status. Long free-text
    // values are probably reasoning that accidentally got bound as a score.
    if (rating && !ratingDetailPrimitiveLooksLikeScore(rating)) return null;
    if (!rating && status && !ratingDetailPrimitiveLooksLikeScore(status)) return null;
    if (!rating && !status) return null;

    seen.add(key);
    const reason = String(firstRatingDetailValue(item, ['reason', 'reasoning', 'comment', 'comments', 'note', 'notes', 'feedback', 'explanation', 'rationale']) || status || '').trim();
    return { name: name.slice(0, 80), rating, reason, status };
  }).filter(Boolean).slice(0, 12);
}

function ratingDetailsFromApiResult(res, fallback = []) {
  const direct = normaliseRatingDetails(res?.cardRatingDetails);
  if (direct.length) return direct;
  const aliases = normaliseRatingDetails(res);
  if (aliases.length) return aliases;
  return normaliseRatingDetails(fallback);
}

async function ensureRatingDetailsForSelectedCard(card = null, reason = 'manual') {
  const target = card || getSelectedBrowserCard();
  const projectPath = target?.projectPath || selectedCharacterProjectPath || '';
  if (!projectPath || !window.pywebview?.api?.ensure_card_rating_details_for_project) return [];
  try {
    const res = await window.pywebview.api.ensure_card_rating_details_for_project(projectPath, settings || {});
    if (!res || !res.ok) return [];
    const details = ratingDetailsFromApiResult(res, []);

    // Important: bind the repaired details back to the card that was requested,
    // not whichever browser card happens to be selected when the async call
    // finishes. Otherwise Details can leak rows from the previous/next card.
    const matchedCard = characterBrowserCards.find(c => c.projectPath === projectPath) || target;
    if (matchedCard) {
      matchedCard.cardRating = res.cardRating || res.rating || matchedCard.cardRating || '';
      matchedCard.cardRatingReasoning = res.cardRatingReasoning || res.reasoning || matchedCard.cardRatingReasoning || '';
      matchedCard.cardRatingDetails = details;
      matchedCard.cardRatingDetailSource = res.cardRatingDetailSource || res.detailSource || matchedCard.cardRatingDetailSource || '';
      matchedCard.cardRatingSourceHash = res.cardRatingSourceHash || res.sourceHash || res.source_hash || matchedCard.cardRatingSourceHash || '';
    }
    if (projectPath === selectedCharacterProjectPath) {
      currentCardRating = res.cardRating || res.rating || currentCardRating || '';
      currentCardRatingReasoning = res.cardRatingReasoning || res.reasoning || currentCardRatingReasoning || '';
      currentCardRatingDetails = details;
      currentCardRatingSourceHash = res.cardRatingSourceHash || res.sourceHash || res.source_hash || currentCardRatingSourceHash || '';
      updateBrowserRatingPanel(matchedCard || { cardRating: currentCardRating, cardRatingReasoning: currentCardRatingReasoning, cardRatingDetails: details });
    }
    return details;
  } catch (err) {
    console.warn('Could not ensure rating details:', err);
    return [];
  }
}

const RATING_EXPECTED_DETAIL_NAMES = [
  'Concept Clarity', 'Character Identity', 'Personality Depth', 'Scenario Hook',
  'Relationship to {{user}}', 'First Message', 'Formatting', 'Specificity',
  'Roleplay Usability', 'Continuity/Lore'
];

function fallbackRatingDetailsForCard(card) {
  const rating = cardRatingValue(card);
  if (!rating) return [];
  const reason = String(card?.cardRatingReasoning || '').trim();
  const reasonHint = reason
    ? 'Fallback display from the saved overall rating; run AI Browser Analysis to save true per-element reasoning.'
    : 'Fallback display from the saved overall rating; no per-element reasoning was saved.';
  return RATING_EXPECTED_DETAIL_NAMES.map(name => ({
    name,
    rating,
    reason: reasonHint,
    status: 'fallback'
  }));
}

function renderRatingDetailsHtml(details) {
  const rows = normaliseRatingDetails(details);
  if (!rows.length) {
    return '<div class="empty small">No detailed element ratings were saved for this card yet. Run AI Browser Analysis to create the new breakdown.</div>';
  }
  return rows.map(item => {
    const score = item.rating ? `${escapeHtml(item.rating)}/10` : escapeHtml(item.status || '—');
    return `
      <div class="rating-detail-row">
        <div class="rating-detail-score">${score}</div>
        <div class="rating-detail-body">
          <div class="rating-detail-name">${escapeHtml(item.name)}</div>
          <div class="rating-detail-reason">${escapeHtml(item.reason || 'No short reasoning saved for this element.')}</div>
        </div>
      </div>
    `;
  }).join('');
}

function closeRatingDetailsModal() {
  const modal = $('#ratingDetailsModal');
  if (modal) modal.classList.add('hidden');
}

async function showRatingDetailsModal(card) {
  const chosen = card || getSelectedBrowserCard();
  if (!chosen) { setStatus('Select a character first.', 'error'); return; }
  const modal = $('#ratingDetailsModal');
  if (!modal) return;
  const modalProjectPath = chosen.projectPath || '';
  modal.dataset.ratingProjectPath = modalProjectPath;
  const name = $('#ratingDetailsName');
  const overall = $('#ratingDetailsOverall');
  const summary = $('#ratingDetailsSummary');
  const list = $('#ratingDetailsList');

  function paint(activeCard, rows) {
    // Do not let a slower repair from a previous Details click overwrite the
    // modal after the user has opened Details for another card.
    if ((modal.dataset.ratingProjectPath || '') !== modalProjectPath) return;
    const rating = cardRatingValue(activeCard);
    if (name) name.textContent = activeCard.name || 'Selected character';
    if (overall) overall.textContent = rating ? `${rating}/10 overall` : 'No overall score';
    if (summary) summary.textContent = activeCard.cardRatingReasoning || 'No overall reasoning was saved for this card.';
    if (list) list.innerHTML = renderRatingDetailsHtml(rows || []);
  }

  // Only use detail rows stored on the card that was clicked. Do not fall back
  // to currentCardRatingDetails here; that global belongs to the previously
  // loaded/generated workspace and can contain another card's breakdown.
  let rows = normaliseRatingDetails(chosen.cardRatingDetails || []);
  paint(chosen, rows);
  modal.classList.remove('hidden');

  // If the browser cache/state has the overall score but no per-element rows,
  // repair from the backend when the user opens Details. This checks the saved
  // project on disk, saves repaired details, and updates only the requested card.
  if (!rows.length && (cardRatingValue(chosen) || String(chosen.cardRatingReasoning || '').trim())) {
    if (list) list.innerHTML = '<div class="empty small">No saved breakdown found. Repairing rating details now…</div>';
    const ensured = await ensureRatingDetailsForSelectedCard(chosen, 'details-modal');
    if ((modal.dataset.ratingProjectPath || '') !== modalProjectPath) return;
    const refreshed = characterBrowserCards.find(c => c.projectPath === modalProjectPath) || chosen;
    rows = ensured.length ? ensured : normaliseRatingDetails(refreshed.cardRatingDetails || []);
    paint(refreshed, rows);
    if (rows.length) setStatus(`Rating details repaired and saved (${rows.length} rows).`, 'ok');
  }
}

async function showSelectedRatingDetailsModal() {
  await showRatingDetailsModal(getSelectedBrowserCard());
}

function updateBrowserRatingPanel(card) {
  const panel = $('#browserRatingPanel');
  const score = $('#browserRatingScore');
  const box = $('#browserRatingReasoning');
  const improveBtn = $('#browserImproveFromRatingBtn');
  const detailsBtn = $('#browserRatingDetailsBtn');
  if (!panel || !score || !box) return;
  const rating = cardRatingValue(card);
  const reasoning = String(card?.cardRatingReasoning || '').trim();
  const details = normaliseRatingDetails(card?.cardRatingDetails || []);
  const hasRating = !!(rating || reasoning || details.length);
  panel.classList.toggle('hidden', !hasRating);
  score.textContent = rating ? `${rating}/10` : 'No score';
  box.value = reasoning || (rating ? 'No rating reasoning was saved for this card.' : '');
  if (detailsBtn) {
    detailsBtn.disabled = !hasRating;
    detailsBtn.title = details.length ? 'Show detailed per-element rating breakdown.' : 'No detailed breakdown saved yet. Run AI Browser Analysis to create one.';
  }
  if (improveBtn) {
    improveBtn.disabled = !hasRating || !selectedCharacterProjectPath;
    improveBtn.title = hasRating
      ? 'Let the AI apply the rating suggestions and preview the improved card before saving.'
      : 'Generate an AI Card Rating first.';
  }
}

function renderCharacterBrowser() {
  const grid = $('#characterGrid');
  if (!grid) return;
  renderBrowserFolderControls();
  renderBrowserBreadcrumb();
  renderBrowserFilterPanel();
  const visibleCards = getVisibleBrowserCards();
  renderBrowserLetterStrip(visibleCards);
  const countEl = $('#browserResultCount');
  const scopedTotal = browserScopeCards().length;
  if (countEl) countEl.textContent = `${visibleCards.length} / ${scopedTotal} in scope (${characterBrowserCards.length} total)`;
  const visibleFolders = getVisibleBrowserFolders(visibleCards);
  if (!characterBrowserCards.length && !visibleFolders.length) {
    grid.innerHTML = '<div class="empty">No saved characters yet. Generate a card first.</div>';
    return;
  }
  if (!visibleCards.length && !visibleFolders.length) {
    grid.innerHTML = '<div class="empty">No characters or folders match the current search/filter.</div>';
    return;
  }
  updateBrowserMultiActionState();
  const folderHtml = visibleFolders.map(folder => {
    const count = folderCardCount(folder.id);
    return `
    <div class="browser-folder-tile" data-folder="${escapeAttr(folder.id)}">
      <div class="folder-thumb-grid">${renderFolderPreviewThumbs(folder, visibleCards)}</div>
      <div class="folder-tile-name">📁 ${escapeHtml(folder.name || 'Folder')}</div>
      <div class="folder-tile-path">${escapeHtml(browserFolderPathLabel(folder.id))}</div>
      <div class="folder-tile-count">${count} character${count === 1 ? '' : 's'}</div>
      <div class="folder-tile-actions"><button type="button" class="folder-rename-btn" data-folder="${escapeAttr(folder.id)}">Rename</button><button type="button" class="folder-delete-btn danger-ghost" data-folder="${escapeAttr(folder.id)}">Delete</button></div>
    </div>`;
  }).join('');
  const cardHtml = visibleCards.map(card => {
    const name = card.name || 'Unnamed';
    const ch = String(name).trim().charAt(0).toUpperCase();
    const letter = /^[A-Z]$/.test(ch) ? ch : '#';
    const multiSelected = browserSelectedProjects.has(card.projectPath);
    const isNsfw = browserCardIsNsfw(card);
    const privacyClass = isNsfw && browserPrivacyMode() === 'blur' ? 'nsfw-blurred' : '';
    return `
    <div class="character-card-tile ${card.projectPath === selectedCharacterProjectPath ? 'selected' : ''} ${multiSelected ? 'multi-selected' : ''} ${privacyClass}" data-project="${escapeAttr(card.projectPath)}" data-letter="${escapeAttr(letter)}">
      <label class="character-multi-check"><input type="checkbox" class="browser-card-checkbox" data-project="${escapeAttr(card.projectPath)}" ${multiSelected ? 'checked' : ''} /> Select</label>
      <div class="character-thumb">${card.thumbnail ? `<img src="${card.thumbnail}" alt="${escapeAttr(name)}" />` : '<div class="no-thumb">No Image</div>'}${cardRatingBadgeHtml(card)}${isNsfw && browserPrivacyMode() === 'blur' ? '<div class="nsfw-overlay">NSFW</div>' : ''}</div>
      <div class="character-tile-name">${escapeHtml(name)}</div>
      <div class="character-tile-summary-source ${String(card.browserDescriptionSource || '').toLowerCase() === 'ai' ? 'ai-source' : 'extracted-source'}">${escapeHtml(descriptionSourceLabel(card.browserDescriptionSource))}</div>
      <div class="character-tile-summary">${escapeHtml(card.browserDescription || card.outputPreview || '')}</div>
      <div class="character-tile-tags">${cardEffectiveTags(card).slice(0, 5).map(t => `<button type="button" class="character-tag-chip ${isMergedBrowserTag(t) ? 'merged-display' : ''}" data-tag="${escapeAttr(t)}">${escapeHtml(t)}</button>`).join('')}</div>
      <div class="character-tile-folder">${escapeHtml(browserFolderPathLabel(card.virtualFolderId || ''))}</div>
      <div class="character-tile-date">${escapeHtml(card.updated || '')}</div>
    </div>
  `}).join('');
  grid.innerHTML = folderHtml + cardHtml;
  $$('.folder-rename-btn', grid).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      browserCurrentFolderId = btn.dataset.folder || '';
      renameCurrentBrowserFolder();
    });
  });
  $$('.folder-delete-btn', grid).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      browserCurrentFolderId = btn.dataset.folder || '';
      deleteCurrentBrowserFolder();
    });
  });
  $$('.browser-folder-tile', grid).forEach(tile => {
    tile.addEventListener('click', () => {
      const id = tile.dataset.folder || '';
      setBrowserCurrentFolder(id, `Opened virtual folder: ${browserFolderPathLabel(id)}`);
    });
  });
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

function descriptionSourceLabel(source) {
  const s = String(source || '').toLowerCase();
  if (s === 'ai') return 'AI generated description';
  return 'Extracted from card';
}

function selectCharacterBrowserCard(projectPath) {
  selectedCharacterProjectPath = projectPath || '';
  const card = characterBrowserCards.find(c => c.projectPath === selectedCharacterProjectPath);
  $$('.character-card-tile').forEach(el => el.classList.toggle('selected', el.dataset.project === selectedCharacterProjectPath));
  $('#selectedCharacterInfo').textContent = card ? `${card.name} — ${browserFolderPathLabel(card.virtualFolderId || '')} — ${card.folder}` : 'Select a character card.';
  const sourceBadge = $('#browserDescriptionSource');
  if (sourceBadge) {
    sourceBadge.textContent = card ? descriptionSourceLabel(card.browserDescriptionSource) : '';
    sourceBadge.classList.toggle('hidden', !card);
    sourceBadge.classList.toggle('ai-source', !!card && String(card.browserDescriptionSource || '').toLowerCase() === 'ai');
    sourceBadge.classList.toggle('extracted-source', !!card && String(card.browserDescriptionSource || '').toLowerCase() !== 'ai');
  }
  $('#browserPreview').value = card ? (card.browserDescription || card.outputPreview || '') : '';
  updateBrowserRatingPanel(card);
  renderSelectedCharacterTags(card);
}

async function loadSelectedCharacterWorkspace() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  setBusy('LOADING CHARACTER WORKSPACE…');
  try {
    const res = await window.pywebview.api.load_character_project(selectedCharacterProjectPath);
    if (!res.ok) throw new Error(res.error || 'Could not load character project.');
    applyLoadedState(res, { appendOutputTab: true, singleProject: true });
    updateAvailability();
    setStatus(res.message || 'Character workspace loaded into a new Output / Editor tab.', 'ok');
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


function renderMobileServerStatus(res) {
  const el = $('#mobileServerStatusText');
  if (!el) return;
  if (!res || res.ok === false) {
    el.textContent = `Mobile server status unavailable${res?.error ? ': ' + res.error : '.'}`;
    return;
  }
  if (!res.running) {
    el.textContent = 'Mobile server is not running. Enable it and save settings to start it.';
    return;
  }
  const urls = Array.isArray(res.urls) && res.urls.length ? res.urls : [`http://${res.host || '127.0.0.1'}:${res.port || 8787}/mobile.html`];
  el.innerHTML = `Running at ${urls.map(url => `<code>${escapeHtml(url)}</code>`).join(' or ')}${res.authRequired ? '<br><span class="muted">Access code is required for mobile generation.</span>' : ''}`;
}

async function refreshMobileServerStatus(showToast = true) {
  try {
    if (!window.pywebview?.api?.mobile_server_status) return;
    const res = await window.pywebview.api.mobile_server_status();
    renderMobileServerStatus(res);
    if (showToast) setStatus(res.running ? 'Mobile server is running.' : 'Mobile server is stopped.', res.running ? 'ok' : '');
  } catch (err) {
    renderMobileServerStatus({ ok: false, error: err.message || String(err) });
  }
}

async function openMobileServerPage() {
  try {
    settings = collectSettings();
    let res = await window.pywebview.api.mobile_server_status();
    if (!res?.running) {
      res = await window.pywebview.api.start_mobile_server(settings);
      if (res?.ok === false) throw new Error(res.error || 'Could not start mobile server.');
      if (settings) settings.mobileServerEnabled = true;
      const enabled = $('#mobileServerEnabled'); if (enabled) enabled.checked = true;
    }
    renderMobileServerStatus(res);
    const url = (Array.isArray(res.urls) && res.urls[0]) ? res.urls[0] : `http://127.0.0.1:${res.port || settings.mobileServerPort || 8787}/mobile.html`;
    await window.pywebview.api.open_external_url(url);
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  }
}

async function scanFrontPorchFolder(targetOverride = null) {
  settings = collectSettings();
  const target = targetOverride || settings.frontPorchExportTarget || 'stable';
  const scanSettings = { ...settings, frontPorchExportTarget: target };
  scanSettings.frontPorchDataFolder = target === 'beta' ? (settings.frontPorchBetaDataFolder || '') : (settings.frontPorchStableDataFolder || '');
  const label = target === 'beta' ? 'Beta Front Porch' : 'Stable Front Porch';
  setBusy(`SCANNING ${label.toUpperCase()} FOLDER…`);
  try {
    await window.pywebview.api.save_settings(settings);
    // Pass a single object through the PyWebView bridge. Older bridge builds can
    // throw "takes 1 to 2 positional arguments but 3 were given" when a second
    // positional target argument is supplied, so the target rides inside settings.
    const res = await window.pywebview.api.scan_front_porch_folder(scanSettings);
    if (!res.ok) throw new Error(res.error || 'Could not find Front Porch database.');
    setStatus(`${res.targetLabel || label} found: ${res.databaseName} — Characters folder: ${res.charactersDir}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function formatFrontPorchAuditReport(res) {
  const lines = [];
  const target = res?.targetLabel || res?.target || 'Front Porch';
  lines.push(`${target} Front Porch database audit`);
  lines.push('');
  lines.push(`Database: ${res?.database || 'Unknown'}`);
  lines.push(`KoboldManager: ${res?.koboldManager || 'Unknown'}`);
  lines.push(`Characters folder: ${res?.charactersDir || 'Unknown'}`);
  if (Number.isFinite(res?.characterCount)) lines.push(`Existing characters: ${res.characterCount}`);
  lines.push('');
  lines.push(`Errors: ${res?.errorCount || 0}`);
  lines.push(`Warnings: ${res?.warningCount || 0}`);
  if (res?.insertRollbackTest) {
    const test = res.insertRollbackTest;
    lines.push(`Rollback insert test: ${test.ok ? 'PASSED' : 'FAILED'}${test.cleaned ? ' / temporary rows verified deleted' : ''}`);
  }

  const addItems = (title, items) => {
    if (!items || !items.length) return;
    lines.push('');
    lines.push(title);
    for (const item of items.slice(0, 20)) {
      const table = item.table ? `[${item.table}] ` : '';
      lines.push(`- ${table}${item.message || String(item)}`);
    }
    if (items.length > 20) lines.push(`- ...and ${items.length - 20} more.`);
  };

  addItems('Errors', res?.errors || []);
  addItems('Warnings', res?.warnings || []);
  addItems('Info', res?.info || []);

  if (res?.tables && Object.keys(res.tables).length) {
    lines.push('');
    lines.push('Tables checked');
    for (const [table, info] of Object.entries(res.tables)) {
      lines.push(`- ${table}: ${info.columnCount || (info.columns || []).length} columns`);
    }
  }
  return lines.join('\n');
}

async function auditFrontPorchDatabase(targetOverride = null) {
  settings = collectSettings();
  const target = targetOverride || settings.frontPorchExportTarget || 'stable';
  const auditSettings = { ...settings, frontPorchExportTarget: target };
  auditSettings.frontPorchDataFolder = target === 'beta' ? (settings.frontPorchBetaDataFolder || '') : (settings.frontPorchStableDataFolder || '');
  const label = target === 'beta' ? 'Beta Front Porch' : 'Stable Front Porch';
  setBusy(`AUDITING ${label.toUpperCase()} DATABASE…`);
  try {
    await window.pywebview.api.save_settings(settings);
    const res = await window.pywebview.api.audit_front_porch_database(auditSettings);
    if (!res.ok && res.error) throw new Error(res.error);
    const report = formatFrontPorchAuditReport(res);
    alert(report);
    if (res.ok) {
      setStatus(`${label} database audit passed: ${res.errorCount || 0} errors, ${res.warningCount || 0} warnings.`, 'ok');
    } else {
      setStatus(`${label} database audit found ${res.errorCount || 0} error(s) and ${res.warningCount || 0} warning(s).`, 'error');
    }
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function frontPorchTargetInfo(targetOverride = null, baseSettings = null) {
  const current = baseSettings || collectSettings();
  const target = targetOverride ? (targetOverride === 'beta' ? 'beta' : 'stable') : (current.frontPorchExportTarget === 'beta' ? 'beta' : 'stable');
  const folder = target === 'beta' ? current.frontPorchBetaDataFolder : current.frontPorchStableDataFolder;
  return {
    target,
    folder: (folder || '').trim(),
    label: target === 'beta' ? 'Beta Front Porch' : 'Stable Front Porch',
  };
}

function currentFrontPorchTargetInfo() {
  return frontPorchTargetInfo();
}

function frontPorchBothFoldersConfigured(baseSettings = null) {
  const current = baseSettings || collectSettings();
  return !!String(current.frontPorchStableDataFolder || '').trim() && !!String(current.frontPorchBetaDataFolder || '').trim();
}

function frontPorchSettingsForTarget(target, baseSettings = null) {
  const current = { ...(baseSettings || collectSettings()) };
  const selectedTarget = target === 'beta' ? 'beta' : 'stable';
  current.frontPorchExportTarget = selectedTarget;
  current.frontPorchDataFolder = selectedTarget === 'beta'
    ? String(current.frontPorchBetaDataFolder || '').trim()
    : String(current.frontPorchStableDataFolder || '').trim();
  return current;
}

function openFrontPorchExportTargetModal({ count = 1, mode = 'single' } = {}) {
  const modal = $('#frontPorchExportTargetModal');
  if (!modal) return Promise.resolve(null);
  const summary = $('#frontPorchExportTargetSummary');
  if (summary) {
    const itemLabel = count === 1 ? 'this character' : `${count} selected characters`;
    summary.textContent = `Both Stable and Beta Front Porch data folders are configured. Choose where to export ${itemLabel}.`;
  }
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  return new Promise(resolve => {
    frontPorchExportTargetModalResolve = resolve;
  });
}

function closeFrontPorchExportTargetModal(result = null) {
  const modal = $('#frontPorchExportTargetModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
  if (frontPorchExportTargetModalResolve) {
    const resolve = frontPorchExportTargetModalResolve;
    frontPorchExportTargetModalResolve = null;
    resolve(result);
  }
}

function showFrontPorchSettingsError() {
  setStatus('Set at least one Front Porch Data Folder in Settings first. Stable uses front_porch.db; Beta uses front_porch_beta.db.', 'error');
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="settings"]')?.classList.add('active');
  $('#settings')?.classList.add('active');
}

async function chooseFrontPorchExportTargets({ count = 1, mode = 'single' } = {}) {
  settings = collectSettings();
  const hasStable = !!String(settings.frontPorchStableDataFolder || '').trim();
  const hasBeta = !!String(settings.frontPorchBetaDataFolder || '').trim();
  if (hasStable && hasBeta) {
    return await openFrontPorchExportTargetModal({ count, mode });
  }
  if (hasStable) return ['stable'];
  if (hasBeta) return ['beta'];
  showFrontPorchSettingsError();
  return null;
}

async function exportFrontPorchProjectToTarget(projectPath, target, baseSettings = null) {
  const targetSettings = frontPorchSettingsForTarget(target, baseSettings);
  await window.pywebview.api.save_settings(targetSettings);
  // Keep the bridge call one-argument for AppImage/stale frontend compatibility.
  // The backend is beta7-tolerant of optional target/settings arguments, but does
  // not require them because save_settings updates the active export target first.
  return await window.pywebview.api.export_front_porch_from_project(projectPath);
}

async function exportSelectedCharacterToFrontPorch() {
  if (!selectedCharacterProjectPath) { setStatus('Select a character first.', 'error'); return; }
  settings = collectSettings();
  const targets = await chooseFrontPorchExportTargets({ count: 1, mode: 'single' });
  if (!targets || !targets.length) return;

  if (!frontPorchBothFoldersConfigured(settings)) {
    const label = frontPorchTargetInfo(targets[0], settings).label;
    const ok = confirm(`Export this saved character directly into ${label}?

This will write to the selected Front Porch SQLite database and copy the character card/emotion images into KoboldManager/Characters. A timestamped database backup will be created first. Close Front Porch before exporting if possible.`);
    if (!ok) return;
  }

  const originalSettings = { ...settings };
  setBusy('EXPORTING TO FRONT PORCH AI…');
  const results = [];
  try {
    for (const target of targets) {
      const info = frontPorchTargetInfo(target, originalSettings);
      setBusy(`EXPORTING TO ${info.label.toUpperCase()}…`);
      const res = await exportFrontPorchProjectToTarget(selectedCharacterProjectPath, target, originalSettings);
      if (!res.ok) throw new Error(res.error || `${info.label} export failed.`);
      results.push(`${res.targetLabel || info.label}: ${res.name} — DB: ${res.database} — emotions: ${res.emotionImages}. Backup: ${res.backup}`);
    }
    setStatus(`Exported to Front Porch AI. ${results.join(' | ')}`, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    try { await window.pywebview.api.save_settings(originalSettings); } catch (_) {}
    settings = originalSettings;
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


const IDEA_OPTIONS = {
  archetype: [
    'gyaru','childhood friend','rich girl','older woman','shy nerd','tomboy','villainess','office lady','idol','cosplayer','delinquent','teacher','supernatural girl','online content creator','student','artist','model','beautician','cheerleader','adventurer','detective','magician','housewife','hostess','single parent','NEET','freelancer'
  ],
  conflict: [
    'hiding a secret','fake confidence','forbidden attraction','jealousy','double life','debt/favor','rival becoming lover','public mask vs private self','loyalty tested','ambition vs love','corrupted innocence','obsession','cheating','taboo relationship','NTR tension','family pressure','identity reveal','dangerous rumor','blackmail','unspoken confession','career risk','class difference','supernatural curse','pregnancy'
  ],
  setting: [
    'university','share house','high school','cafe','train trip','beach villa','convention','apartment neighbours','clubroom','classroom','family homestay','band tour','workplace','fantasy city','red light district','mystery cruise','love hotel','apartment','resort villa','office','train museum','dormitory','shopping district','small town','royal court','detective agency','hospital','bar','restaurant','live house','futuristic','sci-fi','space ship','space colony','another world'
  ],
  tone: [
    'sweet romance','spicy comedy','dark drama','NTR tension','mystery','slow burn','corruption','taboo psychological','cozy domestic','angst','romantic comedy','melodrama','thriller','slice of life','forbidden romance','chaotic comedy','bittersweet','seductive noir','fantasy adventure','emotional healing'
  ],
  occupation: [
    'artist','teacher','warrior','white-collar worker','healthcare professional','sex industry worker','student','religious role','blue collar worker','criminal','pink-collar worker','politician','royalty','scientist','psychic','writer','driver','model','noble','beautician','cheerleader','tailor','vendor','adventurer','archeologist','astronaut','barista','bartender','blacksmith','bounty hunter','captain','communications officer','cook','croupier','delivery worker','detective','dormitory manager','elevator operator','executioner','firefighter','fisherman','flight attendant','florist','fortune teller','freelancer','guide','hacker','hermit','historian','hostess','housewife','journalist','judge','landlord','lawyer','lifeguard','mages organization member','magician','mail carrier','massage therapist','merchant','NEET','news presenter','orphanage director','parent-teacher association member','part-time worker','peasant','professional athlete','professional matchmaker','receptionist','sailor','shopkeeper','single parent','television host','toymaker','unemployed','video game developer','volunteer worker','waitstaff','office lady','idol','cosplayer','online content creator'
  ],
  relationship: [
    'grandchild','grandparent','offspring','parent','sibling','spouse','cousin','aunt','nephew','niece','uncle','friend','schoolmate','coworker','neighbor','boyfriend','girlfriend','ex-boyfriend','ex-girlfriend','secret boyfriend','secret girlfriend','domestic partner','employee','employer','betrothed','concubine','divorcee','kouhai','legal guardian','mistress','roommate','senpai','sex friend','childhood friend','rival','client','customer','landlord','tenant','classmate','clubmate','online friend','affair partner','personal slut','fucktoy','slave','step-sibling','bully'
  ],
  status: [
    'homeless','ojousama','poor','wealthy','middle class','new money','old money','fallen noble','celebrity','local celebrity','outsider','transfer student','foreign exchange student','single parent','widow','divorcee','secretly rich','secretly poor','high-status family','disgraced family','underground celebrity','public figure'
  ],
  personality: [
    'Immature','Confident','Smart','Dishonest','Otaku','Absentminded','Ambitious','Cautious','Emotional','Jealous','Kind','Lazy','Outgoing','Pervert','Pretending','Protective','Reserved','Secretive','Serious','Stoic','Stubborn','Uneducated','Violent','Wise','Adaptable','Airhead','Antisocial','Apathetic','Bookworm','Brave','Charismatic','Cinephile','Clumsy','Competitive','Coward','Creative','Cruel','Curious','Cynic','Docile','Dogmatic','Donkan','Effeminate','Energetic','Envious','Family Oriented','Fear of Commitment','Feminist','Flustered','Funny','Genre Savvy','Gloomy','Gossipy','Grumbler','Henpecked','Hetare','Homophobe','Honorable','Idealist','Idiot','Ignorant','Incorruptible','Insightful','Japanophile','Jock','Loner','Loyal','Lucky','Mature','Misandrist','Misanthrope','Mischievous','Misogynist','Money Lover','Naive','Nihilist','No Sense of Direction','Obedient','Observant','Obsessive','Old-fashioned','Optimist','Pacifist','Patriotic','Perfectionist','Pessimist','Primitive','Proactive','Promiscuous','Racist','Rebellious','Refined','Resilient','Romantic','Romantically Indecisive','Rude','Sensitive','Sharp-tongued','Short-tempered','Sleepyhead','Sociopath','Stylish','Superficial','Superstitious','Taciturn','Talkative','Thrifty','Timid','Tomboy','Transphobe','Unlucky','Vindictive','Whimsical','Womanizer'
  ],
  subjectOf: [
    'Health Issues','Crime','Breakup','Flirting','Infidelity','Netorare','Mind Control','Confinement','Sexual Corruption','Porn Acting','Guilt','Grief','Teasing','Bullying','Arranged Marriage','Manipulation','Massage','Possession','Accident','Apotheosis','Arrest','Being in Heat','Betrayal','Blessing','Bounty','Bridal Carry','Catheter','Child Abandonment','Curse','Debt','Disappearance','Disaster','Discrimination','Disownment','Erotic Photography','Exile','Exorcism','Fixation with Former Lover','Forgotten','Human Subject Research','Impersonation','Inheritance','Interrogation','Memory Alteration','Nightmares','Petrification','Slavery','Stage Fright','Stalking','Survival','Tentacle Restraint','Termination of Employment','Time Loop','Turndown','Tutoring','Uncontrollable Superpowers','Unhealthy Relationship'
  ],
  engagesIn: [
    'Sports','Crime','Breakup','Fake Relationship','Flirting','Infidelity','Discrimination','Performing Arts','Cosplay','Fighting','Filming','Mind Control','Drug Use','Bullying','Teasing','Betrayal','Childbirth','Cooking','Drinking','Vomiting on Others','Astral Projection','Blessing','Body Swap','Bondage','Bridal Carry','Child Abandonment','Cleaning','Coming Out','Competition','Computering','Confinement','Cursing','Daydreaming','Demonic Contract','Dimensional Travel','Disownment','Driving','Duel','Elopement','Escape From Confinement','Flying','Gambling','Gardening','Genetic Research','Graduation','Human Subject Research','Infiltration','Interrogation','Investigation','Invisibility','Job Hunting','Knitting','Learning of a Foreign Language','Letter Writing','Lock Picking','Medication','Meditation','Memory Alteration','Moving','Necrophilia','Nude Modeling','Online Chatting','Parachuting','Photography','Piloting','Planning','Reading','Redemption','Revenge','Riding','Sarcasm','Self-harm','Self-sacrifice','Sewing','Sexual Abstinence','Shopping','Sign Language','Skipping School','Sleepwalking','Smoking','Stalking','Stargazing','Summoning','Supernatural Cloning','Surgery','Symbolic Hair Cutting','Treason','Turndown','Ventriloquism','Voodoo','Yoga'
  ],
  sexualEngagesIn: [
    'Group Sex','Masturbation','Location-based Sex','Pornography','Molesting','Oral Sex','Incest','Defloration','Fingering','Sex With Others','Cum Play','Discreet Sex','Sexual Roleplay','Sexual Cosplay','Sexual Fantasy','Comfort Sex','Condom Sex','Phone Sex','Drunk Sex','Erotic Spitting','French Kiss','Genderbent Sex','Impregnation','Leg Locking During Sex','Live Sex Chat','Paraphilic Infantilism','Rough Sex','Sex in a Wedding Dress','Sex Involving Menstruation','Sex Involving Prostitution','Sex Involving Smegma','Sexting','Sexual Hair Eating','Sexual Sadism','Sex while Being Pregnant','Sleep Sex','Spit Drinking','Striptease','Sweat Licking','Voyeurism','Wake-up Sex'
  ]
};

const IDEA_FIELD_LABELS = {
  archetype: 'Archetype',
  conflict: 'Core Conflict',
  setting: 'Setting',
  tone: 'Tone',
  occupation: 'Occupation / Role',
  relationship: 'Relationship to {{user}}',
  status: 'Status / Social Position',
  personality: 'Personality',
  subjectOf: 'Subject Of',
  engagesIn: 'Engages In',
  sexualEngagesIn: 'Engages In (Sexual)'
};

const DEFAULT_IDEA_MULTI_FIELDS = ['personality', 'subjectOf', 'engagesIn', 'sexualEngagesIn'];
const DEFAULT_IDEA_RANDOM_MAX_CHOICES = 3;
const IDEA_OPTION_LIMIT = 80;
let ideaSettingsEditorLoadedField = 'personality';

function ideaRandomLockableFieldIds() {
  return ['ideaGender', ...Object.keys(IDEA_FIELD_TO_LIST)];
}

function ideaLockSvg(locked = false) {
  if (locked) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V8a5 5 0 0 1 10 0v2h1.2c.99 0 1.8.81 1.8 1.8v7.4c0 .99-.81 1.8-1.8 1.8H5.8A1.8 1.8 0 0 1 4 19.2v-7.4c0-.99.81-1.8 1.8-1.8H7Zm2 0h6V8a3 3 0 1 0-6 0v2Zm3 3.25a1.5 1.5 0 0 0-.75 2.8V18h1.5v-1.95a1.5 1.5 0 0 0-.75-2.8Z"/></svg>';
  }
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 10h2.2c.99 0 1.8.81 1.8 1.8v7.4c0 .99-.81 1.8-1.8 1.8H5.8A1.8 1.8 0 0 1 4 19.2v-7.4c0-.99.81-1.8 1.8-1.8H14V8a3 3 0 0 0-5.68-1.34L6.58 5.67A5 5 0 0 1 16 8v2Zm-4 3.25a1.5 1.5 0 0 0-.75 2.8V18h1.5v-1.95a1.5 1.5 0 0 0-.75-2.8Z"/></svg>';
}

function isIdeaFieldLocked(id) {
  const el = $('#' + id);
  return !!(el && el.dataset.ideaRandomLocked === '1');
}

function setIdeaFieldLocked(id, locked) {
  const el = $('#' + id);
  if (!el) return;
  const isLocked = !!locked;
  el.dataset.ideaRandomLocked = isLocked ? '1' : '0';
  const label = el.closest('label');
  if (label) label.classList.toggle('idea-field-locked', isLocked);
  const btn = label ? label.querySelector(`.idea-random-lock-btn[data-idea-lock-for="${id}"]`) : null;
  if (btn) {
    btn.classList.toggle('locked', isLocked);
    btn.setAttribute('aria-pressed', isLocked ? 'true' : 'false');
    btn.title = isLocked ? 'Locked: Randomise will not change this field' : 'Unlocked: Randomise can change this field';
    btn.setAttribute('aria-label', btn.title);
    btn.innerHTML = ideaLockSvg(isLocked);
  }
}

function toggleIdeaFieldLock(id) {
  setIdeaFieldLocked(id, !isIdeaFieldLocked(id));
}

function ensureIdeaLockControls() {
  ideaRandomLockableFieldIds().forEach(id => {
    const el = $('#' + id);
    if (!el) return;
    const label = el.closest('label');
    if (!label) return;
    label.classList.add('idea-lockable-field');
    let btn = label.querySelector(`.idea-random-lock-btn[data-idea-lock-for="${id}"]`);
    if (!btn) {
      btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'idea-random-lock-btn';
      btn.dataset.ideaLockFor = id;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleIdeaFieldLock(id);
      });
      label.appendChild(btn);
    }
    setIdeaFieldLocked(id, isIdeaFieldLocked(id));
  });
}


function cleanIdeaOptionValue(value) {
  return String(value || '').trim().replace(/\s+/g, ' ').slice(0, 120);
}

function dedupeIdeaOptions(values = []) {
  const out = [];
  const seen = new Set();
  (Array.isArray(values) ? values : []).forEach(value => {
    const cleaned = cleanIdeaOptionValue(value);
    if (!cleaned) return;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(cleaned);
  });
  return out;
}

function parseIdeaOptionText(text) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  const parts = raw.includes('\n') ? raw.split(/\r?\n/) : raw.split(',');
  return dedupeIdeaOptions(parts);
}

function formatIdeaOptionText(values = []) {
  return dedupeIdeaOptions(values).join('\n');
}

function normaliseIdeaGeneratorOptionsMap(map = {}) {
  const cleaned = {};
  Object.keys(IDEA_OPTIONS).forEach(field => {
    const values = map?.[field];
    if (Array.isArray(values)) {
      const list = dedupeIdeaOptions(values);
      if (list.length) cleaned[field] = list;
    }
  });
  return cleaned;
}

function collectIdeaGeneratorMultiFieldsFromSettings(baseSettings = settings) {
  const raw = baseSettings?.ideaGeneratorMultiFields;
  const list = Array.isArray(raw) ? raw : DEFAULT_IDEA_MULTI_FIELDS;
  const valid = new Set(Object.keys(IDEA_OPTIONS));
  const out = [];
  list.forEach(field => {
    const key = String(field || '').trim();
    if (valid.has(key) && !out.includes(key)) out.push(key);
  });
  return out.length ? out : [...DEFAULT_IDEA_MULTI_FIELDS];
}

function getIdeaGeneratorOptionsFromSettings(baseSettings = settings) {
  return normaliseIdeaGeneratorOptionsMap(baseSettings?.ideaGeneratorOptions || {});
}

function collectIdeaSettingsEditorState(baseSettings = settings, targetField = ideaSettingsEditorLoadedField || $('#ideaSettingsField')?.value || '') {
  const optionsMap = getIdeaGeneratorOptionsFromSettings(baseSettings);
  let multiFields = collectIdeaGeneratorMultiFieldsFromSettings(baseSettings);
  const field = String(targetField || '').trim();
  if (field && IDEA_OPTIONS[field]) {
    const edited = parseIdeaOptionText($('#ideaSettingsOptions')?.value || '');
    const defaults = dedupeIdeaOptions(IDEA_OPTIONS[field] || []);
    const editedKey = edited.join('\n').toLowerCase();
    const defaultKey = defaults.join('\n').toLowerCase();
    if (edited.length && editedKey !== defaultKey) optionsMap[field] = edited;
    else delete optionsMap[field];

    const allowMulti = !!$('#ideaSettingsMulti')?.checked;
    multiFields = multiFields.filter(x => x !== field);
    if (allowMulti) multiFields.push(field);
  }
  return {
    ideaGeneratorOptions: normaliseIdeaGeneratorOptionsMap(optionsMap),
    ideaGeneratorMultiFields: collectIdeaGeneratorMultiFieldsFromSettings({ ideaGeneratorMultiFields: multiFields })
  };
}

function applyIdeaSettingsFieldToSettings(field, showStatus = false) {
  const targetField = String(field || '').trim();
  if (!targetField || !IDEA_OPTIONS[targetField]) return false;
  const collected = collectIdeaSettingsEditorState(settings || {}, targetField);
  settings = { ...(settings || {}), ...collected };
  populateIdeaGeneratorOptions();
  if (showStatus) setStatus(`Updated Idea Generator options for ${IDEA_FIELD_LABELS[targetField] || targetField}. Save Settings to keep it.`, 'ok');
  return true;
}

function ideaBaseOptions(listName) {
  const custom = getIdeaGeneratorOptionsFromSettings(settings)[listName];
  return dedupeIdeaOptions(custom && custom.length ? custom : (IDEA_OPTIONS[listName] || []));
}

function ideaIsMultiField(listName) {
  return collectIdeaGeneratorMultiFieldsFromSettings(settings).includes(listName);
}

function fillIdeaDatalist(id, values) {
  const list = $('#' + id);
  if (!list) return;
  list.innerHTML = (values || []).map(v => `<option value="${escapeHtml(v)}"></option>`).join('');
}

const IDEA_FIELD_TO_LIST = {
  ideaArchetype: 'archetype',
  ideaConflict: 'conflict',
  ideaSetting: 'setting',
  ideaTone: 'tone',
  ideaOccupation: 'occupation',
  ideaRelationship: 'relationship',
  ideaStatus: 'status',
  ideaPersonality: 'personality',
  ideaSubjectOf: 'subjectOf',
  ideaEngagesIn: 'engagesIn',
  ideaSexualEngagesIn: 'sexualEngagesIn'
};

function ideaInputValues(input) {
  if (!input) return [];
  const listName = IDEA_FIELD_TO_LIST[input.id];
  if (listName && ideaIsMultiField(listName)) {
    try {
      const parsed = JSON.parse(input.dataset.ideaSelectedValues || '[]');
      return dedupeIdeaOptions(Array.isArray(parsed) ? parsed : []);
    } catch (_) {
      return [];
    }
  }
  return dedupeIdeaOptions(String(input?.value || '').split(','));
}

function setIdeaInputValues(input, values) {
  if (!input) return;
  const listName = IDEA_FIELD_TO_LIST[input.id];
  const cleaned = dedupeIdeaOptions(values);
  if (listName && ideaIsMultiField(listName)) {
    input.dataset.ideaSelectedValues = JSON.stringify(cleaned);
    input.value = '';
    renderIdeaSelectedChips(input);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }
  input.value = cleaned.join(', ');
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function normaliseIdeaMultiInputState(input) {
  if (!input) return;
  const listName = IDEA_FIELD_TO_LIST[input.id];
  if (!listName) return;
  if (ideaIsMultiField(listName)) {
    if (input.dataset.ideaSelectedValues === undefined) {
      const migrated = String(input.value || '').includes(',') ? dedupeIdeaOptions(String(input.value || '').split(',')) : [];
      input.dataset.ideaSelectedValues = JSON.stringify(migrated);
      if (migrated.length) input.value = '';
    }
    input.placeholder = input.dataset.multiPlaceholder || input.placeholder || 'Search/select; picked chips stay below...';
  } else {
    delete input.dataset.ideaSelectedValues;
    if (input.dataset.singlePlaceholder) input.placeholder = input.dataset.singlePlaceholder;
  }
}

function ideaPayloadValue(id) {
  const input = $('#' + id);
  if (!input) return '';
  const listName = IDEA_FIELD_TO_LIST[id];
  if (listName && ideaIsMultiField(listName)) {
    const values = ideaInputValues(input);
    const pending = cleanIdeaOptionValue(input.value || '');
    if (pending && !values.some(v => v.toLowerCase() === pending.toLowerCase())) values.push(pending);
    return dedupeIdeaOptions(values).join(', ');
  }
  return input.value || '';
}

function ideaActiveSearchQuery(input) {
  const raw = String(input?.value || '');
  return raw.trim().toLowerCase();
}

function renderIdeaSelectedChips(input) {
  if (!input) return;
  normaliseIdeaMultiInputState(input);
  const listName = IDEA_FIELD_TO_LIST[input.id];
  const parent = input.parentElement;
  if (!parent) return;
  let holder = parent.querySelector(`.idea-selected-chips[data-for-input="${input.id}"]`);
  if (!listName || !ideaIsMultiField(listName)) {
    if (holder) holder.remove();
    return;
  }
  const values = ideaInputValues(input);
  if (!holder) {
    holder = document.createElement('div');
    holder.className = 'idea-selected-chips';
    holder.dataset.forInput = input.id;
    input.insertAdjacentElement('afterend', holder);
  }
  if (!values.length) {
    holder.innerHTML = '<span class="idea-chip-placeholder">Search/select options above. Picked chips stay here; use × to remove them.</span>';
    return;
  }
  holder.innerHTML = values.map(v => `<span class="idea-chip"><span>${escapeHtml(v)}</span><button type="button" class="idea-chip-remove" data-input="${escapeHtml(input.id)}" data-value="${escapeHtml(v)}" title="Remove ${escapeHtml(v)}">×</button></span>`).join('');
}

function closeIdeaSuggestionBoxes(exceptInput = null) {
  $$('.idea-suggestion-box').forEach(box => {
    if (exceptInput && box.dataset.forInput === exceptInput.id) return;
    box.remove();
  });
}

function ensureIdeaSuggestionBox(input) {
  if (!input) return null;
  const parent = input.parentElement;
  if (!parent) return null;
  parent.classList.add('idea-combo-wrap');
  let box = parent.querySelector(`.idea-suggestion-box[data-for-input="${input.id}"]`);
  if (!box) {
    box = document.createElement('div');
    box.className = 'idea-suggestion-box hidden';
    box.dataset.forInput = input.id;
    parent.appendChild(box);
  }
  return box;
}

function renderIdeaSuggestionBox(input) {
  if (!input) return;
  const listName = IDEA_FIELD_TO_LIST[input.id];
  if (!listName) return;
  const box = ensureIdeaSuggestionBox(input);
  if (!box) return;
  const query = ideaActiveSearchQuery(input);
  const selected = new Set(ideaInputValues(input).map(v => v.toLowerCase()));
  const allValues = ideaOptionsForGender(listName);
  let values = allValues;
  if (query) values = allValues.filter(v => String(v).toLowerCase().includes(query));
  if (ideaIsMultiField(listName)) values = values.filter(v => !selected.has(String(v).toLowerCase()));
  values = values.slice(0, IDEA_OPTION_LIMIT);
  if (!values.length) {
    box.innerHTML = '<div class="idea-suggestion-empty">No matching options. You can still type a custom value.</div>';
  } else {
    box.innerHTML = values.map(v => `<button type="button" class="idea-suggestion-item" data-value="${escapeHtml(v)}">${escapeHtml(v)}</button>`).join('');
  }
  box.classList.remove('hidden');
  renderIdeaSelectedChips(input);
}

function setupIdeaAutocompleteFields() {
  Object.keys(IDEA_FIELD_TO_LIST).forEach(id => {
    const input = $('#' + id);
    if (!input) return;
    if (!input.dataset.singlePlaceholder) input.dataset.singlePlaceholder = input.getAttribute('placeholder') || '';
    if (!input.dataset.multiPlaceholder) input.dataset.multiPlaceholder = 'Search/select; picked chips stay below...';
    input.removeAttribute('list');
    normaliseIdeaMultiInputState(input);
    ensureIdeaSuggestionBox(input);
    renderIdeaSelectedChips(input);
    if (input.dataset.ideaAutocompleteReady === '1') return;
    input.dataset.ideaAutocompleteReady = '1';
    // Native datalist popups cannot be size-limited consistently in WebView,
    // so use a themed scrollable suggestion panel instead.
    input.addEventListener('focus', () => { closeIdeaSuggestionBoxes(input); renderIdeaSuggestionBox(input); });
    input.addEventListener('click', () => { closeIdeaSuggestionBoxes(input); renderIdeaSuggestionBox(input); });
    input.addEventListener('input', () => { renderIdeaSelectedChips(input); renderIdeaSuggestionBox(input); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeIdeaSuggestionBoxes();
      if (e.key === 'Enter') {
        const listName = IDEA_FIELD_TO_LIST[input.id];
        if (listName && ideaIsMultiField(listName)) {
          e.preventDefault();
          const last = cleanIdeaOptionValue(input.value || '');
          const existing = ideaInputValues(input);
          if (last && !existing.some(v => v.toLowerCase() === last.toLowerCase())) setIdeaInputValues(input, [...existing, last]);
          else input.value = '';
        }
      }
    });
  });
  ensureIdeaLockControls();
  if (!document.body.dataset.ideaAutocompleteGlobalReady) {
    document.body.dataset.ideaAutocompleteGlobalReady = '1';
    document.addEventListener('click', (e) => {
      const remove = e.target?.closest?.('.idea-chip-remove');
      if (remove) {
        e.preventDefault();
        const input = $('#' + remove.dataset.input);
        if (input) {
          const removeKey = String(remove.dataset.value || '').toLowerCase();
          setIdeaInputValues(input, ideaInputValues(input).filter(v => v.toLowerCase() !== removeKey));
          closeIdeaSuggestionBoxes(input);
          renderIdeaSuggestionBox(input);
        }
        return;
      }
      const item = e.target?.closest?.('.idea-suggestion-item');
      if (item) {
        const box = item.closest('.idea-suggestion-box');
        const input = box ? $('#' + box.dataset.forInput) : null;
        if (input) {
          const value = item.dataset.value || item.textContent || '';
          const listName = IDEA_FIELD_TO_LIST[input.id];
          if (listName && ideaIsMultiField(listName)) {
            const current = ideaInputValues(input);
            const key = String(value).toLowerCase();
            if (!current.some(v => v.toLowerCase() === key)) setIdeaInputValues(input, [...current, value]);
            closeIdeaSuggestionBoxes(input);
            renderIdeaSuggestionBox(input);
            input.focus();
          } else {
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            closeIdeaSuggestionBoxes();
            input.focus();
          }
        }
        return;
      }
      if (!e.target?.closest?.('.idea-combo-wrap')) closeIdeaSuggestionBoxes();
    }, { capture: true });
  }
}

function ideaOptionsForGender(listName) {
  const gender = $('#ideaGender')?.value || '';
  let values = [...ideaBaseOptions(listName)];
  if (gender === 'female') {
    if (listName === 'relationship') values = values.filter(v => !['boyfriend','ex-boyfriend','secret boyfriend','uncle','nephew'].includes(v));
    if (listName === 'archetype') values = values.filter(v => !['warrior'].includes(v)).concat(['wife','mistress','mature beauty']).filter((v,i,a)=>a.indexOf(v)===i);
  } else if (gender === 'male') {
    if (listName === 'relationship') values = values.filter(v => !['girlfriend','ex-girlfriend','secret girlfriend','aunt','niece','mistress'].includes(v)).concat(['husband']).filter((v,i,a)=>a.indexOf(v)===i);
    if (listName === 'archetype') values = values.filter(v => !['gyaru','rich girl','older woman','office lady','idol','cosplayer','villainess','housewife','hostess'].includes(v)).concat(['salaryman','older man','prince','delinquent guy']).filter((v,i,a)=>a.indexOf(v)===i);
  } else if (gender === 'nonbinary') {
    if (listName === 'relationship') values = values.filter(v => !['boyfriend','girlfriend','ex-boyfriend','ex-girlfriend','secret boyfriend','secret girlfriend','aunt','uncle','niece','nephew','mistress'].includes(v)).concat(['partner','ex-partner','secret partner']).filter((v,i,a)=>a.indexOf(v)===i);
    if (listName === 'archetype') values = values.filter(v => !['gyaru','rich girl','older woman','office lady','housewife','hostess'].includes(v)).concat(['androgynous beauty','mysterious outsider']).filter((v,i,a)=>a.indexOf(v)===i);
  }
  return dedupeIdeaOptions(values).sort((a,b)=>String(a).localeCompare(String(b)));
}

function populateIdeaGeneratorOptions() {
  fillIdeaDatalist('ideaArchetypeList', ideaOptionsForGender('archetype'));
  fillIdeaDatalist('ideaConflictList', ideaOptionsForGender('conflict'));
  fillIdeaDatalist('ideaSettingList', ideaOptionsForGender('setting'));
  fillIdeaDatalist('ideaToneList', ideaOptionsForGender('tone'));
  fillIdeaDatalist('ideaOccupationList', ideaOptionsForGender('occupation'));
  fillIdeaDatalist('ideaRelationshipList', ideaOptionsForGender('relationship'));
  fillIdeaDatalist('ideaStatusList', ideaOptionsForGender('status'));
  fillIdeaDatalist('ideaPersonalityList', ideaOptionsForGender('personality'));
  fillIdeaDatalist('ideaSubjectOfList', ideaOptionsForGender('subjectOf'));
  fillIdeaDatalist('ideaEngagesInList', ideaOptionsForGender('engagesIn'));
  fillIdeaDatalist('ideaSexualEngagesInList', ideaOptionsForGender('sexualEngagesIn'));
  setupIdeaAutocompleteFields();
  const active = document.activeElement;
  if (active && IDEA_FIELD_TO_LIST[active.id]) renderIdeaSuggestionBox(active);
}

function populateIdeaSettingsFieldSelect() {
  const select = $('#ideaSettingsField');
  if (!select) return;
  const prev = select.value || ideaSettingsEditorLoadedField || 'personality';
  select.innerHTML = Object.entries(IDEA_FIELD_LABELS).map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join('');
  select.value = IDEA_OPTIONS[prev] ? prev : 'personality';
}

function loadIdeaSettingsField(field = $('#ideaSettingsField')?.value || ideaSettingsEditorLoadedField || 'personality') {
  const select = $('#ideaSettingsField');
  if (!select || !IDEA_OPTIONS[field]) return;
  select.value = field;
  ideaSettingsEditorLoadedField = field;
  const custom = getIdeaGeneratorOptionsFromSettings(settings)[field];
  const values = custom && custom.length ? custom : (IDEA_OPTIONS[field] || []);
  const textarea = $('#ideaSettingsOptions');
  if (textarea) textarea.value = formatIdeaOptionText(values);
  const multi = $('#ideaSettingsMulti');
  if (multi) multi.checked = ideaIsMultiField(field);
}

function switchIdeaSettingsField(nextField) {
  const next = String(nextField || '').trim();
  const current = ideaSettingsEditorLoadedField || $('#ideaSettingsField')?.value || 'personality';
  if (!next || !IDEA_OPTIONS[next]) return;
  if (current && IDEA_OPTIONS[current] && current !== next) {
    applyIdeaSettingsFieldToSettings(current, false);
    setStatus(`Auto-applied ${IDEA_FIELD_LABELS[current] || current} edits. Save Settings to keep them.`, 'ok');
  }
  loadIdeaSettingsField(next);
}

function applyIdeaSettingsField(showStatus = true) {
  const field = ideaSettingsEditorLoadedField || $('#ideaSettingsField')?.value || '';
  if (!field || !IDEA_OPTIONS[field]) return;
  applyIdeaSettingsFieldToSettings(field, showStatus);
  loadIdeaSettingsField(field);
}

function resetIdeaSettingsField() {
  const field = ideaSettingsEditorLoadedField || $('#ideaSettingsField')?.value || '';
  if (!field || !IDEA_OPTIONS[field]) return;
  const map = getIdeaGeneratorOptionsFromSettings(settings);
  delete map[field];
  settings = { ...(settings || {}), ideaGeneratorOptions: map };
  loadIdeaSettingsField(field);
  populateIdeaGeneratorOptions();
  setStatus(`Reset ${IDEA_FIELD_LABELS[field] || field} options to defaults. Save Settings to keep it.`, 'ok');
}

function resetAllIdeaSettings() {
  if (!confirm('Reset all Idea Generator option lists to their built-in defaults?')) return;
  settings = { ...(settings || {}), ideaGeneratorOptions: {}, ideaGeneratorMultiFields: [...DEFAULT_IDEA_MULTI_FIELDS] };
  loadIdeaSettingsField($('#ideaSettingsField')?.value || ideaSettingsEditorLoadedField || 'personality');
  populateIdeaGeneratorOptions();
  setStatus('Reset all Idea Generator options to defaults. Save Settings to keep it.', 'ok');
}

function initIdeaSettingsEditor() {
  populateIdeaSettingsFieldSelect();
  loadIdeaSettingsField($('#ideaSettingsField')?.value || ideaSettingsEditorLoadedField || 'personality');
}

function openIdeaGeneratorModal() {
  populateIdeaGeneratorOptions();
  ensureIdeaLockControls();
  closeIdeaSuggestionBoxes();
  const modal = $('#ideaGeneratorModal');
  if (!modal) { setStatus('Idea Generator popup could not be found.', 'error'); return; }
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeIdeaGeneratorModal() {
  closeIdeaSuggestionBoxes();
  const modal = $('#ideaGeneratorModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
}

function clearIdeaGenerator() {
  closeIdeaSuggestionBoxes();
  ['ideaGender','ideaArchetype','ideaConflict','ideaSetting','ideaTone','ideaOccupation','ideaRelationship','ideaStatus','ideaPersonality','ideaSubjectOf','ideaEngagesIn','ideaSexualEngagesIn','ideaCustomInstructions'].forEach(id => {
    const el = $('#' + id);
    if (el) {
      el.value = '';
      if (IDEA_FIELD_TO_LIST[id]) {
        delete el.dataset.ideaSelectedValues;
        normaliseIdeaMultiInputState(el);
        renderIdeaSelectedChips(el);
      }
    }
  });
}

function ideaGeneratorRandomMaxChoices() {
  const raw = $('#ideaGeneratorRandomMaxChoices')?.value ?? settings?.ideaGeneratorRandomMaxChoices ?? DEFAULT_IDEA_RANDOM_MAX_CHOICES;
  return Math.max(1, Math.min(20, Number(raw || DEFAULT_IDEA_RANDOM_MAX_CHOICES)));
}

function randomChoice(values = []) {
  const list = dedupeIdeaOptions(values);
  if (!list.length) return '';
  return list[Math.floor(Math.random() * list.length)] || '';
}

function randomSample(values = [], count = 1) {
  const pool = dedupeIdeaOptions(values);
  const wanted = Math.max(0, Math.min(pool.length, Number(count || 0)));
  const out = [];
  while (out.length < wanted && pool.length) {
    const idx = Math.floor(Math.random() * pool.length);
    out.push(pool.splice(idx, 1)[0]);
  }
  return out;
}

function randomiseIdeaGenerator() {
  closeIdeaSuggestionBoxes();
  ensureIdeaLockControls();
  let lockedCount = 0;
  let changedCount = 0;
  const genderSelect = $('#ideaGender');
  if (genderSelect) {
    if (isIdeaFieldLocked('ideaGender')) {
      lockedCount += 1;
    } else {
      const genderOptions = Array.from(genderSelect.options || []).map(o => o.value).filter(v => v !== '');
      genderSelect.value = randomChoice(genderOptions);
      changedCount += 1;
    }
  }
  const maxChoices = ideaGeneratorRandomMaxChoices();
  Object.entries(IDEA_FIELD_TO_LIST).forEach(([id, listName]) => {
    const input = $('#' + id);
    if (!input) return;
    if (isIdeaFieldLocked(id)) {
      lockedCount += 1;
      return;
    }
    const options = dedupeIdeaOptions(ideaOptionsForGender(listName));
    if (!options.length) return;
    if (ideaIsMultiField(listName)) {
      const maxForField = Math.min(maxChoices, options.length);
      const count = 1 + Math.floor(Math.random() * maxForField);
      setIdeaInputValues(input, randomSample(options, count));
    } else {
      input.value = randomChoice(options);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    changedCount += 1;
    renderIdeaSelectedChips(input);
  });
  const lockNote = lockedCount ? ` ${lockedCount} locked field${lockedCount === 1 ? '' : 's'} kept unchanged.` : '';
  const changeNote = changedCount ? `Randomised ${changedCount} field${changedCount === 1 ? '' : 's'} from your lists.` : 'No unlocked fields were available to randomise.';
  setStatus(`${changeNote}${lockNote} This did not call AI.`, changedCount ? 'ok' : 'error');
}

function collectIdeaGeneratorPayload() {
  return {
    gender: $('#ideaGender')?.value || '',
    archetype: ideaPayloadValue('ideaArchetype'),
    coreConflict: ideaPayloadValue('ideaConflict'),
    setting: ideaPayloadValue('ideaSetting'),
    tone: ideaPayloadValue('ideaTone'),
    occupation: ideaPayloadValue('ideaOccupation'),
    relationship: ideaPayloadValue('ideaRelationship'),
    status: ideaPayloadValue('ideaStatus'),
    personality: ideaPayloadValue('ideaPersonality'),
    subjectOf: ideaPayloadValue('ideaSubjectOf'),
    engagesIn: ideaPayloadValue('ideaEngagesIn'),
    sexualEngagesIn: ideaPayloadValue('ideaSexualEngagesIn'),
    customInstructions: $('#ideaCustomInstructions')?.value || ''
  };
}

function buildIdeaFallbackConcept(payload) {
  const labels = {
    gender: 'Gender', archetype: 'Archetype', coreConflict: 'Core Conflict', setting: 'Setting', tone: 'Tone',
    occupation: 'Occupation / Role', relationship: 'Relationship to {{user}}', status: 'Status / Social Position',
    personality: 'Personality', subjectOf: 'Subject Of', engagesIn: 'Engages In', sexualEngagesIn: 'Engages In (Sexual)', customInstructions: 'Custom Instructions'
  };
  const lines = [
    'You are generating an IDEA SEED for the Main Concept box, not a full character card.',
    'Create compact editable concept notes only. Do not write a finished card.',
    'Use these exact sections: Core Idea, Main Character, Relationship to {{user}}, Conflict, Setting, Tone, First Scene Hook, Tags.',
    'Keep it concise and playable. All romance/sexual participants must be 18+.',
    '',
    'SELECTED IDEA INGREDIENTS'
  ];
  Object.entries(labels).forEach(([key, label]) => {
    const value = String(payload?.[key] || '').trim();
    if (value) lines.push(`- ${label}: ${value}`);
  });
  return lines.join('\n');
}

function buildIdeaFallbackTemplate() {
  const makeSection = (id, title, description) => ({ id, title, enabled: true, category: 'idea', description, fields: [] });
  return {
    globalRules: [
      'This is an idea generator pass only.',
      'Return concise Main Concept notes, not a complete card.',
      'Do not include First Message, Example Dialogues, State Tracking, or Stable Diffusion Prompt unless the user explicitly asked for them in custom instructions.'
    ],
    sections: [
      makeSection('core_idea', 'Core Idea', 'One paragraph summarizing the card concept.'),
      makeSection('main_character', 'Main Character', 'Who the central character is, including the selected archetype/role.'),
      makeSection('relationship', 'Relationship to {{user}}', 'How the character knows or relates to {{user}}.'),
      makeSection('conflict', 'Conflict', 'The main tension, secret, problem, or emotional hook.'),
      makeSection('setting', 'Setting', 'Where the concept begins and why it is playable.'),
      makeSection('tone', 'Tone', 'The mood and genre direction.'),
      makeSection('first_scene_hook', 'First Scene Hook', 'A short setup for where the chat could begin.'),
      makeSection('tags', 'Tags', '6-10 lowercase comma-separated tags.')
    ],
    qa: { enabled: false, sections: [] }
  };
}

async function callIdeaGeneratorBackend(api, payload, settings) {
  const direct = api?.generate_idea || api?.generateIdea || api?.generateIdeaFromOptions || api?.ideaGenerator || api?.createIdea;
  if (direct) return await direct.call(api, payload, settings);

  // Packaged builds may lag behind the frontend method table. Fallback through
  // the long-standing generate() API so Idea Generator still works without a
  // dedicated backend method. Restore the user's real template afterwards.
  if (api?.generate) {
    const fallbackSettings = { ...(settings || {}), streamAi: false, alternateFirstMessages: 0, mode: (settings?.mode || 'full') };
    const res = await api.generate(buildIdeaFallbackConcept(payload), buildIdeaFallbackTemplate(), fallbackSettings);
    try { if (api.save_template && template) await api.save_template(template); } catch (_) {}
    if (!res.ok) return res;
    return { ok: true, idea: (res.output || '').trim(), fallback: true };
  }

  const available = api ? Object.keys(api).filter(k => /idea|generate/i.test(k)).join(', ') : '';
  return { ok: false, error: 'Idea Generator backend is not available. Restart the app after updating.' + (available ? ` Available related methods: ${available}` : '') };
}

async function generateIdeaIntoMainConcept() {
  if (isInterfaceLocked()) return;
  settings = collectSettings();
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  const payload = collectIdeaGeneratorPayload();
  const hasAny = Object.values(payload).some(v => String(v || '').trim());
  if (!hasAny) { setStatus('Choose at least one idea option or enter custom instructions first.', 'error'); return; }
  // Close the modal before the AI call starts so the user can keep using the
  // rest of the app while the floating busy banner tracks generation progress.
  closeIdeaGeneratorModal();
  setBusy('IDEA GENERATOR — creating main concept seed…');
  setStatus('Generating a compact idea seed for Main Concept…', '');
  try {
    const api = window.pywebview?.api;
    const res = await callIdeaGeneratorBackend(api, payload, settings);
    if (!res.ok) throw new Error(res.error || 'Idea generation failed.');
    $('#conceptText').value = res.idea || '';
    closeIdeaGeneratorModal();
    updateAvailability();
    setStatus('Idea generated into Main Concept. Review/tweak it, then generate the card when ready.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function openGenerationOptionsModal() {
  if (isInterfaceLocked()) return;
  const modal = $('#generationOptionsModal');
  if (!modal) { generateCard({}); return; }
  const runQa = $('#generationRunQa');
  if (runQa) runQa.checked = !!template?.qa?.enabled;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  setTimeout(() => $('#generationTemporaryNotes')?.focus(), 40);
}

function closeGenerationOptionsModal() {
  const modal = $('#generationOptionsModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
}

function collectGenerationRunOptions() {
  const tempNotes = ($('#generationTemporaryNotes')?.value || '').trim();
  const customQaText = ($('#generationCustomQa')?.value || '').trim();
  const customQaQuestions = customQaText.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const includeTempNotes = $('#generationIncludeTemporaryNotes') ? $('#generationIncludeTemporaryNotes').checked : true;
  return {
    runQa: $('#generationRunQa') ? $('#generationRunQa').checked : !!template?.qa?.enabled,
    temporaryNotes: includeTempNotes ? tempNotes : '',
    customQaQuestions,
  };
}

async function startGenerationFromModal() {
  const options = collectGenerationRunOptions();
  if (options.customQaQuestions.length) options.runQa = true;
  closeGenerationOptionsModal();
  await generateCard(options);
}

function applyGenerationOptionsToConcept(concept, options={}) {
  const parts = [String(concept || '').trim()].filter(Boolean);
  const notes = String(options.temporaryNotes || '').trim();
  if (notes) {
    parts.push(['TEMPORARY GENERATION NOTES FOR THIS CARD ONLY — MANDATORY. These notes clarify the current card and must be preserved. They override generic assumptions and stale builder/workspace context. Do not create a separate section for them unless the template already asks for it:', notes].join('\n'));
  }
  return parts.join('\n\n');
}

function buildGenerationQaTemplate(baseTemplate, options = {}) {
  // Build a temporary Q&A template in the frontend so generate_qa_context can
  // keep its original 3-argument bridge call. This avoids PyWebView/AppImage
  // mismatch errors when a newly packed frontend is accidentally paired with
  // an older backend signature.
  let temp = {};
  try {
    temp = JSON.parse(JSON.stringify(baseTemplate || {}));
  } catch (err) {
    temp = { ...(baseTemplate || {}) };
  }
  const questions = Array.isArray(options.customQaQuestions)
    ? options.customQaQuestions.map(q => String(q || '').trim()).filter(Boolean)
    : [];
  const qa = temp.qa || {};
  if (options.runQa || questions.length) qa.enabled = true;
  if (questions.length) {
    const sections = Array.isArray(qa.sections) ? qa.sections.slice() : [];
    sections.push({
      id: 'temporary_card_qa',
      title: 'Card-specific Q&A',
      enabled: true,
      collapsed: false,
      questions: questions.map(q => ({ enabled: true, text: q })),
    });
    qa.sections = sections;
  }
  temp.qa = qa;
  return temp;
}

async function generateCard(options = {}) {
  options = { runQa: !!template?.qa?.enabled, temporaryNotes: '', customQaQuestions: [], ...(options || {}) };
  if ((options.customQaQuestions || []).length) options.runQa = true;
  if (!handleUnbuiltBuilderWarning()) return;
  captureActiveConceptTab();
  const conceptForModel = applyGenerationOptionsToConcept(buildConceptForModel(), options);
  if (!String(conceptForModel || '').trim()) {
    setStatus('Enter a character concept first.', 'error');
    return;
  }
  clearGenerationArtifacts({ preserveWorkspaceInputs: true });
  setStatus('Starting generation…', '');
  $$('.nav').forEach(b => b.classList.remove('active'));
  $$('.tab').forEach(t => t.classList.remove('active'));
  $('[data-tab="output"]')?.classList.add('active');
  $('#output')?.classList.add('active');
  switchSubTab('output', 'output-fulltext');
  await rememberCurrentModel(true);
  settings = collectSettings();
  const liveCardMode = ($('#cardMode') ? $('#cardMode').value : settings.cardMode || 'single');
  if (['single', 'multi', 'split_cards'].includes(liveCardMode) && settings.cardMode !== liveCardMode) {
    // Last-line defence against stale saved/shared-scene state changing the
    // generation route. The visible Card Mode control wins.
    settings.cardMode = liveCardMode;
    if (liveCardMode === 'single') settings.sharedScenePolicy = 'ai_reconcile';
    if (liveCardMode === 'split_cards') settings.sharedScenePolicy = 'split_cards';
  }
  const settingsError = validateTextApiSettings(settings);
  if (settingsError) {
    setBusy('');
    await window.pywebview.api.save_settings(settings);
    setStatus(settingsError, 'error');
    switchToSettingsTab();
    updateAvailability();
    return;
  }
  try {
    if (settings.cardMode === 'split_cards') {
      const runSplitQa = !!(options.runQa || (options.customQaQuestions || []).length);
      setBusy(runSplitQa ? 'SPLIT-CARD GENERATION — identifying characters and running focused Q&A per card…' : 'SPLIT-CARD GENERATION — identifying characters and generating separate cards…');
      setStatus(runSplitQa
        ? 'Generating one card per main character. Each card will get its own focused Q&A/Output/Emotion/Image tab.'
        : 'Generating one card per main character. Each card will get its own Output/Emotion/Image tab.', '');
      const res = await window.pywebview.api.generate_split_cards(conceptForModel, template, settings, '', !runSplitQa, options.customQaQuestions || []);
      if (!res.ok) throw new Error(res.error || 'Split-card generation failed.');
      setCharacterOutputTabs(res.cards || []);
      currentBrowserDescription = '';
  currentCardRating = '';
  currentCardRatingReasoning = '';
  currentCardRatingDetails = [];
  currentCardRatingSourceHash = '';
      updateAvailability();
      const count = characterOutputTabs.length;
      const foundNames = Array.isArray(res.characters) && res.characters.length ? ` Identified: ${res.characters.join(', ')}.` : '';
      setStatus(`Split-card generation complete: ${count} card${count === 1 ? '' : 's'} generated.${foundNames} Current tab autosaving…`, 'ok');
      await saveCurrentWorkspace('silent');
      return;
    }

    let qaAnswers = '';
    if (options.runQa || (options.customQaQuestions || []).length) {
      setBusy('PRE-GENERATION Q&A — interviewing the character(s)…');
      setStatus(settings.streamAi ? 'Running Q&A interview pass with streaming enabled…' : 'Running Q&A interview pass before card generation…', '');
      const qaBoxStream = $('#qaAnswersText');
      if (qaBoxStream && settings.streamAi) qaBoxStream.value = '';
      const qaRes = await window.pywebview.api.generate_qa_context(conceptForModel, buildGenerationQaTemplate(template, options), settings);
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
    setBusy(settings.streamAi ? 'CHARACTER GENERATION — streaming the final card…' : 'CHARACTER GENERATION — writing the final card…');
    const outBoxStream = $('#outputText');
    if (outBoxStream && settings.streamAi) outBoxStream.value = '';
    const res = await window.pywebview.api.generate_with_qa_answers(conceptForModel, template, settings, qaAnswers);
    if (!res.ok) throw new Error(res.error || 'Generation failed.');
    $('#outputText').value = res.output;
    currentBrowserDescription = '';
  currentCardRating = '';
  currentCardRatingReasoning = '';
  currentCardRatingDetails = [];
  currentCardRatingSourceHash = '';
    lastQnaAnswers = res.qaAnswers || qaAnswers || '';
    const qaBox = $('#qaAnswersText');
    if (qaBox) qaBox.value = lastQnaAnswers || 'Q&A was disabled or returned no answers for this generation.';
    setCharacterOutputTabs([{ name: extractOutputNameForTab(res.output) || (settings.cardMode === 'multi' ? 'Characters' : 'Character'), output: res.output, qaAnswers: lastQnaAnswers, emotionImages: [], generatedImages: [], cardImagePath: '' }]);
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
  currentCardRating = '';
  currentCardRatingReasoning = '';
  currentCardRatingDetails = [];
  currentCardRatingSourceHash = '';
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
  if (isInterfaceLocked()) return;
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
    updateCardImagePreview();
    updateImportedCardToolsHint();
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
    updateCardImagePreview();
    updateImportedCardToolsHint();
    setStatus('Selected card image: ' + res.path + (hasOutput() ? ' and updated the saved workspace.' : ''), 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function importCardImagePaths(paths) {
  const path = String([...(paths || [])][0] || '').trim();
  if (!path) return;
  if (isProbablyUrl(path)) {
    if ($('#cardImageModalPath')) $('#cardImageModalPath').value = path;
    await applyCardImageModalPath();
    return;
  }
  setBusy('IMPORTING CARD IMAGE…');
  try {
    const res = await window.pywebview.api.import_image_path(path, 'card');
    if (!res.ok) throw new Error(res.error || 'Card image import failed.');
    $('#cardImagePath').value = res.path;
    if ($('#cardImageModalPath')) $('#cardImageModalPath').value = res.path;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    if (hasOutput()) await saveCurrentWorkspace('silent');
    updateCardImagePreview();
    updateImportedCardToolsHint();
    setStatus('Selected card image: ' + res.path + (hasOutput() ? ' and updated the saved workspace.' : ''), 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

async function importCardImageUrl() {
  if (isInterfaceLocked()) return;
  const url = promptForUrl('card image URL');
  if (!url) return;
  if (!isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// image URL.', 'error'); return; }
  setBusy('IMPORTING CARD IMAGE FROM URL…');
  try {
    const res = await window.pywebview.api.save_image_from_url(url, 'card');
    if (!res.ok) throw new Error(res.error || 'Card image URL import failed.');
    $('#cardImagePath').value = res.path;
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    if (hasOutput()) await saveCurrentWorkspace('silent');
    updateCardImagePreview();
    updateImportedCardToolsHint();
    setStatus('Selected card image from URL: ' + res.path + (hasOutput() ? ' and updated the saved workspace.' : ''), 'ok');
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
  const imageCount = Math.max(1, Math.min(16, Number(settings.sdImageCount || 4)));
  setBusy(`GENERATING ${imageCount} SD IMAGE${imageCount === 1 ? '' : 'S'} — SD Forge / Automatic1111 is working…`);
  setStatus(`Generating ${imageCount} image${imageCount === 1 ? '' : 's'} in SD Forge / Automatic1111 at 1024×1024…`, '');
  try {
    const res = await window.pywebview.api.generate_sd_images($('#outputText').value, settings);
    if (!res.ok) throw new Error(res.error || 'Image generation failed.');
    if (characterOutputTabs[activeOutputTabIndex]) characterOutputTabs[activeOutputTabIndex].generatedImages = res.images || [];
    renderGeneratedImages(res.images || []);
    setStatus(`Generated ${res.images?.length || imageCount} image candidate${(res.images?.length || imageCount) === 1 ? '' : 's'}. Select the one you like, delete rejects, or regenerate.`, 'ok');
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
      if (characterOutputTabs[activeOutputTabIndex]) characterOutputTabs[activeOutputTabIndex].cardImagePath = img.path;
      if (hasOutput()) await saveCurrentWorkspace('silent');
      updateCardImagePreview();
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
        updateCardImagePreview();
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
      if (isInterfaceLocked()) return;
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
  emotionImageState = [];
  renderEmotionImageResults([], false);
  setBusy('GENERATING EMOTION PROMPTS — AI is preparing image prompts…');
  setStatus('Generating emotion prompts with the AI model…', '');
  try {
    const res = await window.pywebview.api.generate_emotion_images($('#outputText').value, settings.emotionImageEmotions, settings);
    if (res.cancelled) {
      if (Array.isArray(res.images) && res.images.length) renderEmotionImageResults(res.images || []);
      setStatus(`Emotion generation stopped. Kept ${emotionImageState.length || res.images?.length || 0} generated image(s).`, 'error');
      if ((emotionImageState.length || res.images?.length || 0) > 0) await saveCurrentWorkspace('silent');
      return;
    }
    if (!res.ok) {
      if (Array.isArray(res.images) && res.images.length) renderEmotionImageResults(res.images || []);
      throw new Error(res.error || 'Emotion image generation failed.');
    }
    renderEmotionImageResults(res.images || emotionImageState || []);
    if (characterOutputTabs[activeOutputTabIndex]) characterOutputTabs[activeOutputTabIndex].emotionImages = emotionImageState.map(img => ({...img}));
    setStatus(`Generated ${res.images?.length || emotionImageState.length || 0} emotion image(s) in ${res.folder}. Autosaving workspace…`, 'ok');
    await saveCurrentWorkspace('silent');
  } catch (err) {
    setStatus((err.message || String(err)) + (emotionImageState.length ? ` Kept ${emotionImageState.length} generated image(s).` : ''), 'error');
  } finally {
    setBusy('');
  }
}

async function createEmotionZip() {
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
  setBusy('LOADING SAVED CARD / PROJECT…');
  setStatus('Loading saved character card or project…', '');
  try {
    const res = await window.pywebview.api.pick_saved_file();
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Load failed.');
      return;
    }
    applyLoadedState(res, { appendOutputTab: true, singleProject: true });
    updateAvailability();
    let statusMessage = res.message || 'Loaded saved card/project into a new Output / Editor tab.';
    if (!/project/i.test(String(res.loadedType || ''))) {
      const imported = await importCurrentOutputToBrowser(false);
      if (imported?.ok) statusMessage += ' Imported into Character Browser.';
    }
    setStatus(statusMessage, 'ok');
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
    applyLoadedState(res, { appendOutputTab: true, singleProject: true });
    updateAvailability();
    let statusMessage = res.message || 'Loaded saved card/project into a new Output / Editor tab.';
    if (!/project/i.test(String(res.loadedType || ''))) {
      const imported = await importCurrentOutputToBrowser(false);
      if (imported?.ok) statusMessage += ' Imported into Character Browser.';
    }
    setStatus(statusMessage, 'ok');
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


async function loadSavedCardOrProjectFromUrl() {
  if (isInterfaceLocked()) return;
  const url = promptForUrl('character card / project URL');
  if (!url) return;
  if (!isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// card URL.', 'error'); return; }
  setBusy('LOADING SAVED CARD / PROJECT FROM URL…');
  setStatus('Downloading saved character card or project from URL…', '');
  try {
    const res = await window.pywebview.api.load_import_url(url);
    if (!res.ok) throw new Error(res.error || 'Load URL failed.');
    applyLoadedState(res, { appendOutputTab: true, singleProject: true });
    updateAvailability();
    let statusMessage = res.message || 'Loaded saved card/project from URL into a new Output / Editor tab.';
    if (!/project/i.test(String(res.loadedType || ''))) {
      const imported = await importCurrentOutputToBrowser(false);
      if (imported?.ok) statusMessage += ' Imported into Character Browser.';
    }
    setStatus(statusMessage, 'ok');
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


function openQuickImportModal() {
  if (isInterfaceLocked()) return;
  const modal = $('#quickImportModal');
  if (!modal) { loadSavedCardOrProject(); return; }
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  updateQuickImportSelected();
}

function closeQuickImportModal() {
  const modal = $('#quickImportModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function syncQuickImportUrlFromInput(value = null) {
  const input = $('#quickImportPath');
  const raw = value !== null ? value : (input ? input.value : '');
  quickImportUrlValue = String(raw || '').trim();
  if (input && value !== null) input.value = String(raw || '');
  return quickImportUrlValue;
}

function updateQuickImportSelected() {
  const holder = $('#quickImportSelected');
  if (!holder) return;
  const value = syncQuickImportUrlFromInput();
  if (quickImportFile) holder.textContent = `Selected file: ${quickImportFile.name || 'file'}${value && isProbablyUrl(value) ? ' + URL also entered; URL will be used first.' : ''}`;
  else if (value) holder.textContent = isProbablyUrl(value) ? `Selected URL: ${value}` : `Selected path/text: ${value}`;
  else holder.textContent = 'No file or URL selected.';
}

function clearQuickImportSource() {
  quickImportFile = null;
  quickImportUrlValue = '';
  const input = $('#quickImportPath');
  if (input) input.value = '';
  const fileInput = $('#quickImportFileInput');
  if (fileInput) fileInput.value = '';
  updateQuickImportSelected();
}

function setQuickImportFile(file) {
  if (!file) return;
  quickImportFile = file;
  const input = $('#quickImportPath');
  if (input && !isProbablyUrl(input.value || '')) input.value = file.name || '';
  quickImportUrlValue = '';
  updateQuickImportSelected();
}

async function importQuickImportFiles(files) {
  const file = [...(files || [])][0];
  if (!file) return;
  setQuickImportFile(file);
}

async function importQuickImportPaths(paths) {
  const path = String([...(paths || [])][0] || '').trim();
  if (!path) return;
  quickImportFile = null;
  const input = $('#quickImportPath');
  if (input) input.value = path;
  quickImportUrlValue = path;
  updateQuickImportSelected();
}

function handleQuickImportFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  setQuickImportFile(file);
}

function quickImportSdMode() {
  return getCheckedRadioValue('quickImportSdMode', 'none');
}

function ensureEmptyStableDiffusionPromptSection() {
  const out = $('#outputText');
  if (!out) return;
  const text = String(out.value || '').trimEnd();
  if (/^\s*Stable Diffusion Prompt\s*$/im.test(text) || /Positive Prompt\s*:/i.test(text)) return;
  const block = '------------------------------------------------\nStable Diffusion Prompt\n\nPositive Prompt:\nNegative Prompt:';
  out.value = text ? `${text}\n\n${block}` : block;
}

async function runQuickImport() {
  if (isInterfaceLocked()) return;
  syncQuickImportUrlFromInput();
  updateQuickImportSelected();
  const sourceText = String(quickImportUrlValue || '').trim();
  const url = sourceText && isProbablyUrl(sourceText) ? sourceText : '';
  const localPath = sourceText && !url ? sourceText : '';
  const file = quickImportFile;
  if (!url && !localPath && !file) { setStatus('Choose a file or enter a card path/URL first.', 'error'); return; }
  settings = collectSettings();
  setBusy(url ? 'IMPORTING CARD FROM URL…' : (localPath ? 'IMPORTING CARD FROM PATH…' : 'IMPORTING CARD FROM FILE…'));
  try {
    let res;
    if (url) {
      res = await window.pywebview.api.load_import_url(url);
    } else if (localPath) {
      res = await window.pywebview.api.load_import_path(localPath);
    } else {
      const dataUrl = await fileToDataUrl(file);
      res = await window.pywebview.api.load_import_upload(file.name, dataUrl);
    }
    if (!res.ok) throw new Error(res.error || 'Import failed.');
    applyLoadedState(res, { appendOutputTab: true, singleProject: true });
    updateAvailability();
    let statusMessage = res.message || 'Imported card/project into a new Output / Editor tab.';
    if (!/project/i.test(String(res.loadedType || ''))) {
      const imported = await importCurrentOutputToBrowser(false);
      if (imported?.ok) statusMessage += ' Imported into Character Browser.';
    }

    const mode = quickImportSdMode();
    if (mode === 'vision') {
      setBusy('IMPORT CARD — generating Stable Diffusion Prompt from image…');
      await generateSdPromptFromLoadedVision();
      statusMessage += ' Stable Diffusion Prompt generated from image.';
    } else if (mode === 'full_text') {
      setBusy('IMPORT CARD — generating Stable Diffusion Prompt from full text…');
      await generateSdPromptFromLoadedOutput();
      statusMessage += ' Stable Diffusion Prompt generated from full text.';
    } else {
      ensureEmptyStableDiffusionPromptSection();
      await saveCurrentWorkspace('silent');
      statusMessage += ' Stable Diffusion Prompt section left empty for manual editing.';
    }
    closeQuickImportModal();
    setStatus(statusMessage, 'ok');
    switchSubTab('output', 'output-export');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateCardImagePreview();
    updateImportedCardToolsHint();
  }
}

function openExportModal() {
  if (isInterfaceLocked()) return;
  const modal = $('#exportCardModal');
  if (!modal) { exportCard(); return; }
  if ($('#exportDestinationFolder')) $('#exportDestinationFolder').value = settings?.exportDestinationFolder || '';
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeExportModal() {
  const modal = $('#exportCardModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function selectExportFolder() {
  if (isInterfaceLocked()) return;
  if (!window.pywebview?.api?.select_export_folder) {
    setStatus('This build does not expose an export-folder picker. Paste a folder path instead.', 'error');
    return;
  }
  setBusy('SELECTING EXPORT FOLDER…');
  try {
    const res = await window.pywebview.api.select_export_folder();
    if (!res.ok) {
      if (!res.cancelled) throw new Error(res.error || 'Could not select export folder.');
      return;
    }
    if ($('#exportDestinationFolder')) $('#exportDestinationFolder').value = res.path || '';
    settings = collectSettings();
    await window.pywebview.api.save_settings(settings);
    setStatus('Export folder selected: ' + res.path, 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
  }
}

function openCardImageModal() {
  if (isInterfaceLocked()) return;
  const modal = $('#cardImageModal');
  if (!modal) { selectCardImage(); return; }
  if ($('#cardImageModalPath')) $('#cardImageModalPath').value = $('#cardImagePath')?.value || '';
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeCardImageModal() {
  const modal = $('#cardImageModal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

async function applyCardImageModalPath() {
  const value = String($('#cardImageModalPath')?.value || '').trim();
  if (!value) { setStatus('Enter an image path/URL or drop/select an image first.', 'error'); return; }
  if (isProbablyUrl(value)) {
    setBusy('IMPORTING CARD IMAGE FROM URL…');
    try {
      const res = await window.pywebview.api.save_image_from_url(value, 'card');
      if (!res.ok) throw new Error(res.error || 'Card image URL import failed.');
      $('#cardImagePath').value = res.path;
      closeCardImageModal();
    } catch (err) {
      setStatus(err.message || String(err), 'error');
      return;
    } finally {
      setBusy('');
    }
  } else {
    $('#cardImagePath').value = value;
    closeCardImageModal();
  }
  settings = collectSettings();
  await window.pywebview.api.save_settings(settings);
  if (characterOutputTabs[activeOutputTabIndex]) characterOutputTabs[activeOutputTabIndex].cardImagePath = $('#cardImagePath').value;
  if (hasOutput()) await saveCurrentWorkspace('silent');
  updateCardImagePreview();
  updateImportedCardToolsHint();
  setStatus('Card image updated.', 'ok');
}

function cardImagePreviewSrc(path) {
  const value = String(path || '').trim();
  if (!value) return '';
  if (/^data:image\//i.test(value)) return value;
  if (/^https?:\/\//i.test(value)) return value;
  if (/^file:\/\//i.test(value)) return value;
  const prefix = value.startsWith('/') ? 'file://' : 'file:///';
  return prefix + value.split('/').map(part => encodeURIComponent(part)).join('/').replaceAll('%3A', ':');
}

function shortImageLabel(path) {
  const value = String(path || '').trim();
  if (!value) return '';
  try {
    if (/^https?:\/\//i.test(value)) {
      const url = new URL(value);
      return url.pathname.split('/').filter(Boolean).pop() || url.hostname;
    }
  } catch (_) {}
  return value.split(/[\/]/).filter(Boolean).pop() || value;
}

async function updateCardImagePreview() {
  const input = $('#cardImagePath');
  const img = $('#cardImagePreview');
  const hint = $('#cardImagePreviewHint');
  const path = String(input?.value || '').trim();
  const token = ++cardImagePreviewToken;
  if ($('#cardImageModalPath') && !$('#cardImageModal')?.classList.contains('hidden')) $('#cardImageModalPath').value = path;
  if (img) {
    img.alt = 'Current card image preview';
    if (!path) {
      img.removeAttribute('src');
      img.classList.add('hidden');
    } else {
      img.classList.remove('hidden');
      img.src = cardImagePreviewSrc(path);
      if (window.pywebview?.api?.image_preview_data_url && !/^https?:\/\//i.test(path) && !/^data:image\//i.test(path)) {
        try {
          const res = await window.pywebview.api.image_preview_data_url(path);
          if (token === cardImagePreviewToken && res?.ok && res.dataUrl) img.src = res.dataUrl;
        } catch (_) {}
      }
    }
  }
  if (hint) hint.textContent = path ? `Current image set: ${shortImageLabel(path)}` : 'No custom image selected. PNG export will use the built-in blank image.';
}


function syncConceptImportUrlFromInput(value = null) {
  const input = $('#conceptImportUrl');
  const raw = value !== null ? value : (input ? input.value : '');
  conceptImportUrlValue = String(raw || '').trim();
  if (input && value !== null) input.value = String(raw || '');
  return conceptImportUrlValue;
}

function updateConceptImportSelected() {
  const holder = $('#conceptImportSelected');
  if (!holder) return;
  const url = syncConceptImportUrlFromInput();
  const file = conceptImportFile;
  if (file) {
    holder.textContent = `Selected file: ${file.name || 'file'}${url && isProbablyUrl(url) ? ' + URL also entered; URL will be used first.' : ''}`;
  } else if (url) {
    holder.textContent = isProbablyUrl(url) ? `Selected URL: ${url}` : `Selected file/path text: ${url}`;
  } else {
    holder.textContent = 'No file or URL selected.';
  }
}

function openConceptImportModal() {
  const modal = $('#conceptImportModal');
  if (modal) {
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  } else {
    setStatus('Import Card/Image popup could not be found in the page.', 'error');
  }
  syncConceptImportUrlFromInput();
  updateConceptImportSelected();
}

function closeConceptImportModal() {
  const modal = $('#conceptImportModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
}

function clearConceptImportSource() {
  conceptImportFile = null;
  conceptImportUrlValue = '';
  const fileInput = $('#conceptImportFileInput');
  if (fileInput) fileInput.value = '';
  const urlInput = $('#conceptImportUrl');
  if (urlInput) urlInput.value = '';
  updateConceptImportSelected();
}

// Backwards-compatible names for older bindings.
function clearConceptImportFile() { clearConceptImportSource(); }
function clearConceptImportUrl() { clearConceptImportSource(); }

function setConceptImportFile(file) {
  if (!file) return;
  conceptImportFile = file;
  // File inputs do not expose full paths in WebView, so show the filename in the shared source box.
  // The actual File object remains the source of truth for import.
  const input = $('#conceptImportUrl');
  if (input && !isProbablyUrl(input.value || '')) input.value = file.name || '';
  conceptImportUrlValue = '';
  updateConceptImportSelected();
}

function bindConceptImportDropZone() {
  const zone = $('#conceptImportDropZone');
  if (!zone || zone.dataset.ccfConceptImportBound) return;
  zone.dataset.ccfConceptImportBound = '1';
  zone.addEventListener('click', (e) => {
    e.preventDefault();
    openBrowserFileInput('conceptImportFileInput', 'card or image');
  });
  zone.addEventListener('dragenter', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', (e) => { e.preventDefault(); zone.classList.remove('dragover'); });
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (!file) { setStatus('No dropped file was detected.', 'error'); return; }
    setConceptImportFile(file);
  });
  const urlInput = $('#conceptImportUrl');
  if (urlInput && !urlInput.dataset.ccfBoundUrlInput) {
    urlInput.dataset.ccfBoundUrlInput = '1';
    ['input','change','keyup','blur'].forEach(evt => urlInput.addEventListener(evt, () => {
      if (isProbablyUrl(urlInput.value || '') || !(conceptImportFile && urlInput.value === conceptImportFile.name)) {
        conceptImportUrlValue = String(urlInput.value || '').trim();
      }
      updateConceptImportSelected();
    }));
    urlInput.addEventListener('paste', (e) => {
      const pasted = e.clipboardData?.getData('text') || '';
      if (pasted.trim()) conceptImportUrlValue = pasted.trim();
      setTimeout(() => { syncConceptImportUrlFromInput(); updateConceptImportSelected(); }, 0);
      setTimeout(() => { syncConceptImportUrlFromInput(); updateConceptImportSelected(); }, 50);
    });
  }
}

function handleConceptImportFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  setConceptImportFile(file);
}

function conceptImportSourceUrl() {
  const current = syncConceptImportUrlFromInput();
  if (current && isProbablyUrl(current)) return current;
  if (conceptImportUrlValue && isProbablyUrl(conceptImportUrlValue)) return conceptImportUrlValue;
  return '';
}

function conceptImportAnalyzeEnabled() {
  return !!$('#conceptImportAnalyzeBefore')?.checked;
}

function isImageLikeName(value) {
  return /\.(png|jpe?g|webp)(?:[?#].*)?$/i.test(String(value || ''));
}

async function setCardImageFromUrlForImport(url) {
  if (!url || !isImageLikeName(url)) return '';
  const saved = await window.pywebview.api.save_image_from_url(url, 'card');
  if (!saved.ok) throw new Error(saved.error || 'Could not import image URL.');
  const localPath = saved.path || url;
  if ($('#cardImagePath')) $('#cardImagePath').value = localPath;
  setVisionImagePath(localPath);
  settings = collectSettings();
  settings.cardImagePath = localPath;
  settings.visionImagePath = localPath;
  await window.pywebview.api.save_settings(settings);
  updateImportedCardToolsHint();
  return localPath;
}

async function runAnalyzeForImportedImage(imagePath, { toBuilders = false } = {}) {
  const path = (imagePath || $('#cardImagePath')?.value || getVisionImagePath() || '').trim();
  if (!path) throw new Error('Analyze before import is enabled, but no imported image/card image was available.');
  setVisionImagePath(path);
  settings = collectSettings();
  settings.visionImagePath = path;
  await window.pywebview.api.save_settings(settings);
  const settingsError = validateVisionApiSettings(settings);
  if (settingsError) {
    switchToSettingsTab();
    throw new Error(settingsError);
  }
  setBusy(toBuilders ? 'ANALYZE BEFORE IMPORT — analyzing image and filling builders…' : 'ANALYZE BEFORE IMPORT — analyzing image…');
  const res = await window.pywebview.api.analyze_vision_image(path, settings);
  if (!res.ok) throw new Error(res.error || 'Vision analysis failed.');
  if (!(res.description || '').trim()) throw new Error('Vision model returned an empty description.');
  if ($('#visionDescription')) $('#visionDescription').value = res.description || '';
  if (res.imagePath) setVisionImagePath(res.imagePath);
  if (toBuilders) await transferConceptToBuilders();
  return res;
}

async function tryImportImageOnlyForAnalyze({ url = '', file = null, toBuilders = false } = {}) {
  if (!conceptImportAnalyzeEnabled()) return false;
  let imagePath = '';
  if (url && isImageLikeName(url)) {
    imagePath = await setCardImageFromUrlForImport(url);
  } else if (file && isImageLikeName(file.name || '')) {
    const dataUrl = await fileToDataUrl(file);
    const saved = await window.pywebview.api.save_uploaded_image(file.name, dataUrl, 'card');
    if (!saved.ok) throw new Error(saved.error || 'Image import failed.');
    imagePath = saved.path;
    if ($('#cardImagePath')) $('#cardImagePath').value = imagePath;
    setVisionImagePath(imagePath);
  }
  if (!imagePath) return false;
  await runAnalyzeForImportedImage(imagePath, { toBuilders });
  return true;
}

async function runConceptImport(target) {
  if (isInterfaceLocked()) return;
  syncConceptImportUrlFromInput();
  updateConceptImportSelected();
  const url = conceptImportSourceUrl();
  const file = conceptImportFile;
  if (url && !isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// URL.', 'error'); return; }
  if (!url && !file) { setStatus('Choose a file or enter a URL first.', 'error'); return; }
  const analyze = conceptImportAnalyzeEnabled();
  const toBuilders = target === 'builders';
  if (toBuilders && !confirmLoadCardToBuildersWarning()) return;
  if (!toBuilders && !confirmLoadCardToMainConceptWarning()) return;
  settings = collectSettings();
  if (toBuilders) {
    const missing = validateTextApiSettings(settings);
    if (missing) { setStatus(missing, 'error'); switchToSettingsTab(); return; }
  }
  try {
    setBusy(toBuilders ? 'IMPORT CARD / IMAGE — importing into builders…' : 'IMPORT CARD / IMAGE — importing into Main Concept…');
    let res = null;
    let imageForAnalysis = '';
    if (url) {
      if (isImageLikeName(url)) imageForAnalysis = await setCardImageFromUrlForImport(url);
      if (toBuilders) {
        const catalog = collectCompactBuilderFieldCatalog();
        res = await window.pywebview.api.card_url_to_builders(url, catalog, settings);
      } else {
        res = await window.pywebview.api.card_url_to_main_concept(url, settings);
      }
      if (res?.ok) {
        if (toBuilders) await applyCardToBuildersResult(res, url);
        else await applyCardToMainConceptResult(res, url);
        if (url && isImageLikeName(url)) imageForAnalysis = imageForAnalysis || ($('#cardImagePath')?.value || '').trim();
      }
    } else if (file) {
      const dataUrl = await fileToDataUrl(file);
      if (toBuilders) {
        const catalog = collectCompactBuilderFieldCatalog();
        res = await window.pywebview.api.card_upload_to_builders(file.name, dataUrl, catalog, settings);
      } else {
        res = await window.pywebview.api.card_upload_to_main_concept(file.name, dataUrl, settings);
      }
      if (res?.ok) {
        if (toBuilders) await applyCardToBuildersResult(res, file.name);
        else await applyCardToMainConceptResult(res, file.name);
        imageForAnalysis = res.imagePath || ($('#cardImagePath')?.value || '').trim();
      }
    }

    if (!res?.ok) {
      const recovered = await tryImportImageOnlyForAnalyze({ url, file, toBuilders });
      if (!recovered) throw new Error(res?.error || 'Import failed. If this is only an image, enable Analyze before import.');
    } else if (analyze) {
      imageForAnalysis = imageForAnalysis || ($('#cardImagePath')?.value || '').trim() || (url && isImageLikeName(url) ? url : '');
      await runAnalyzeForImportedImage(imageForAnalysis, { toBuilders });
    }

    closeConceptImportModal();
    updateAvailability();
    setStatus(toBuilders ? 'Import complete. Builders updated.' : 'Import complete. Main Concept updated.', 'ok');
  } catch (err) {
    setStatus(err.message || String(err), 'error');
  } finally {
    setBusy('');
    updateAvailability();
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
  if (isInterfaceLocked()) return;
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

async function loadCardToMainConceptUrl() {
  if (isInterfaceLocked()) return;
  if (!confirmLoadCardToMainConceptWarning()) return;
  const url = promptForUrl('V2/V3 character card URL');
  if (!url) return;
  if (!isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// card URL.', 'error'); return; }
  settings = collectSettings();
  setBusy('LOAD CARD URL TO MAIN CONCEPT — downloading V2/V3 card…');
  setStatus('Downloading existing character card URL directly into Main Concept…', '');
  try {
    const res = await window.pywebview.api.card_url_to_main_concept(url, settings);
    await applyCardToMainConceptResult(res, url);
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
  if (isInterfaceLocked()) return;
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
  if (isInterfaceLocked()) return;
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

async function loadCardToBuildersUrl() {
  if (isInterfaceLocked()) return;
  if (!confirmLoadCardToBuildersWarning()) return;
  const url = promptForUrl('V2/V3 character card URL');
  if (!url) return;
  if (!isProbablyUrl(url)) { setStatus('Enter a valid http:// or https:// card URL.', 'error'); return; }
  settings = collectSettings();
  const missing = validateTextApiSettings(settings);
  if (missing) {
    setStatus(missing, 'error');
    switchToSettingsTab();
    return;
  }
  setBusy('LOAD CARD URL TO BUILDERS — downloading V2/V3 card and filling builder fields…');
  setStatus('Downloading existing character card URL into the builders…', '');
  try {
    const catalog = collectCompactBuilderFieldCatalog();
    const res = await window.pywebview.api.card_url_to_builders(url, catalog, settings);
    await applyCardToBuildersResult(res, url);
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
  if (isInterfaceLocked()) return;
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

async function handleConceptCardFileSelected(event) {
  const file = event.target.files && event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importCardToMainConceptFiles([file]);
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
    if (res.ok) { closeExportModal(); setStatus('Exported to: ' + res.path + (res.folder ? ' — folder: ' + res.folder : '') + (res.projectPath ? ' — project: ' + res.projectPath : ''), 'ok'); await saveCurrentWorkspace('silent'); }
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


function installConceptImportModalDelegatedHandlers() {
  if (window.__ccfConceptImportModalDelegated) return;
  window.__ccfConceptImportModalDelegated = true;
  document.addEventListener('click', (event) => {
    const openBtn = event.target?.closest?.('#openConceptImportModalBtn');
    if (openBtn) {
      event.preventDefault();
      event.stopPropagation();
      openConceptImportModal();
      return;
    }
    const closeBtn = event.target?.closest?.('#closeConceptImportModalBtn');
    if (closeBtn) {
      event.preventDefault();
      event.stopPropagation();
      closeConceptImportModal();
      return;
    }
    const clearBtn = event.target?.closest?.('#clearConceptImportSourceBtn');
    if (clearBtn) {
      event.preventDefault();
      event.stopPropagation();
      clearConceptImportSource();
      return;
    }
    const zone = event.target?.closest?.('#conceptImportDropZone');
    if (zone) {
      event.preventDefault();
      event.stopPropagation();
      openBrowserFileInput('conceptImportFileInput', 'card or image');
      return;
    }
    const importMain = event.target?.closest?.('#conceptImportAsMainBtn');
    if (importMain) {
      event.preventDefault();
      event.stopPropagation();
      runConceptImport('main');
      return;
    }
    const importBuilders = event.target?.closest?.('#conceptImportAsBuildersBtn');
    if (importBuilders) {
      event.preventDefault();
      event.stopPropagation();
      runConceptImport('builders');
      return;
    }
    if (event.target?.id === 'conceptImportModal') {
      event.preventDefault();
      closeConceptImportModal();
    }
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('#conceptImportModal')?.classList.contains('hidden')) {
      closeConceptImportModal();
    }
  }, true);

  document.addEventListener('input', (event) => {
    if (event.target?.id === 'conceptImportUrl') {
      syncConceptImportUrlFromInput();
      updateConceptImportSelected();
    }
  }, true);
  document.addEventListener('change', (event) => {
    if (event.target?.id === 'conceptImportUrl') {
      syncConceptImportUrlFromInput();
      updateConceptImportSelected();
    }
  }, true);
  document.addEventListener('paste', (event) => {
    if (event.target?.id === 'conceptImportUrl') {
      const pasted = event.clipboardData?.getData('text') || '';
      if (pasted.trim()) conceptImportUrlValue = pasted.trim();
      setTimeout(() => { syncConceptImportUrlFromInput(); updateConceptImportSelected(); }, 0);
      setTimeout(() => { syncConceptImportUrlFromInput(); updateConceptImportSelected(); }, 60);
    }
  }, true);

  document.addEventListener('dragover', (event) => {
    if (event.target?.closest?.('#conceptImportDropZone')) event.preventDefault();
  }, true);
  document.addEventListener('drop', (event) => {
    if (!event.target?.closest?.('#conceptImportDropZone')) return;
    event.preventDefault();
    event.stopPropagation();
    const file = event.dataTransfer?.files?.[0];
    if (!file) { setStatus('No dropped file was detected.', 'error'); return; }
    setConceptImportFile(file);
  }, true);
}

function installConceptVisionAttachmentDelegatedHandlers() {
  if (window.__ccfConceptVisionAttachmentDelegated) return;
  window.__ccfConceptVisionAttachmentDelegated = true;

  const triggerInput = (inputId, label) => {
    const input = $('#' + inputId);
    if (!input) {
      setStatus(`File input missing for ${label}.`, 'error');
      return false;
    }
    try {
      input.disabled = false;
      input.value = '';
      input.click();
      return true;
    } catch (err) {
      setStatus(`Could not open ${label} picker: ${err?.message || err}`, 'error');
      return false;
    }
  };

  const visionTarget = (event) => event.target?.closest?.('#visionDropZone, #selectVisionImageBtn');
  const attachmentTarget = (event) => event.target?.closest?.('#conceptAttachmentDropZone, #attachConceptFilesBtn');

  document.addEventListener('click', (event) => {
    if (isInterfaceLocked && isInterfaceLocked()) return;
    if (visionTarget(event)) {
      event.preventDefault();
      event.stopPropagation();
      triggerInput('visionFileInput', 'vision image');
      return;
    }
    if (attachmentTarget(event)) {
      event.preventDefault();
      event.stopPropagation();
      triggerInput('conceptAttachmentInput', 'concept attachment files');
      return;
    }
  }, true);

  document.addEventListener('keydown', (event) => {
    if (!(event.key === 'Enter' || event.key === ' ')) return;
    if (visionTarget(event)) {
      event.preventDefault();
      event.stopPropagation();
      triggerInput('visionFileInput', 'vision image');
      return;
    }
    if (attachmentTarget(event)) {
      event.preventDefault();
      event.stopPropagation();
      triggerInput('conceptAttachmentInput', 'concept attachment files');
      return;
    }
  }, true);

  document.addEventListener('change', (event) => {
    if (event.target?.id === 'visionFileInput') {
      event.stopPropagation();
      const files = [...(event.target.files || [])];
      event.target.value = '';
      if (files.length) importVisionFiles(files);
      return;
    }
    if (event.target?.id === 'conceptAttachmentInput') {
      event.stopPropagation();
      const files = [...(event.target.files || [])];
      event.target.value = '';
      if (files.length) importConceptAttachmentFiles(files);
      return;
    }
  }, true);

  const setDropActive = (zone, active) => {
    if (!zone) return;
    zone.classList.toggle('drag-over', !!active);
    zone.classList.toggle('dragover', !!active);
  };

  const resolveDropZone = (event) => {
    const vision = event.target?.closest?.('#visionDropZone');
    if (vision) return { kind: 'vision', zone: vision };
    const attachment = event.target?.closest?.('#conceptAttachmentDropZone');
    if (attachment) return { kind: 'attachment', zone: attachment };
    const quickImport = event.target?.closest?.('#quickImportDropZone');
    if (quickImport) return { kind: 'quickImport', zone: quickImport };
    const cardImage = event.target?.closest?.('#cardImageDropZone');
    if (cardImage) return { kind: 'cardImage', zone: cardImage };
    return null;
  };

  document.addEventListener('click', (event) => {
    const hit = resolveDropZone(event);
    if (!hit || (hit.kind !== 'quickImport' && hit.kind !== 'cardImage')) return;
    event.preventDefault();
    event.stopPropagation();
    const inputId = hit.kind === 'quickImport' ? 'quickImportFileInput' : 'cardImageFileInput';
    openBrowserFileInput(inputId, hit.kind === 'quickImport' ? 'card or project' : 'card image');
  }, true);

  ['dragenter', 'dragover'].forEach(name => document.addEventListener(name, (event) => {
    const hit = resolveDropZone(event);
    if (!hit) return;
    event.preventDefault();
    event.stopPropagation();
    try { event.dataTransfer.dropEffect = 'copy'; } catch (_) {}
    setDropActive(hit.zone, true);
  }, true));

  ['dragleave', 'dragend'].forEach(name => document.addEventListener(name, (event) => {
    const hit = resolveDropZone(event);
    if (!hit) return;
    event.preventDefault();
    event.stopPropagation();
    setDropActive(hit.zone, false);
  }, true));

  document.addEventListener('drop', (event) => {
    const hit = resolveDropZone(event);
    if (!hit) return;
    event.preventDefault();
    event.stopPropagation();
    setDropActive(hit.zone, false);
    const files = getDroppedFiles(event.dataTransfer);
    const paths = getDroppedFilePaths(event.dataTransfer);
    if (hit.kind === 'vision') {
      if (files.length) importVisionFiles(files.slice(0, 1));
      else if (paths.length) importVisionPaths(paths.slice(0, 1));
      else setStatus('No dropped vision image was detected. Try clicking the drop zone to browse instead.', 'error');
      return;
    }
    if (hit.kind === 'attachment') {
      if (files.length) importConceptAttachmentFiles(files);
      else if (paths.length) importConceptAttachmentPaths(paths);
      else setStatus('No dropped concept attachment was detected. Try Attach Files instead.', 'error');
      return;
    }
    if (hit.kind === 'quickImport') {
      if (files.length) importQuickImportFiles(files.slice(0, 1));
      else if (paths.length) importQuickImportPaths(paths.slice(0, 1));
      else setStatus('No dropped card/project file was detected. Try clicking the drop zone to browse instead.', 'error');
      return;
    }
    if (hit.kind === 'cardImage') {
      if (files.length) importCardImageFiles(files.slice(0, 1));
      else if (paths.length) importCardImagePaths(paths.slice(0, 1));
      else setStatus('No dropped card image was detected. Try clicking the drop zone to browse instead.', 'error');
    }
  }, true);
}

installConceptImportModalDelegatedHandlers();
installConceptVisionAttachmentDelegatedHandlers();
window.addEventListener('pywebviewready', init);
