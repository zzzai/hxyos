const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

const orderHtml = read('docs/wellness-menu/order.html');
const adminHtml = read('docs/wellness-menu/admin.html');
const apiMain = read('api/main.py');
const menuDesign = read('docs/wellness-menu/DESIGN.md');

for (const asset of [
  'docs/wellness-menu/assets/hxy-wellness/placeholder-qing.svg',
  'docs/wellness-menu/assets/hxy-wellness/placeholder-bu.svg',
  'docs/wellness-menu/assets/hxy-wellness/placeholder-yang.svg',
]) {
  assert(fs.existsSync(path.join(root, asset)), `missing placeholder asset: ${asset}`);
}

assert(!orderHtml.includes('ⓘ'), 'price info icon should be removed or implemented');
assert(menuDesign.includes('Open Design'), 'menu design contract should document Open Design source usage');
assert(menuDesign.includes('WeChat Design System'), 'menu design contract should reference the WeChat mobile service language');
assert(menuDesign.includes('Clean Design System'), 'menu design contract should reference Clean spacing/readability rules');
assert(menuDesign.includes('不把 open-design 仓库整体 vendoring'), 'menu design contract should forbid vendoring Open Design wholesale');
assert(orderHtml.includes('Open Design menu bridge'), 'customer menu should expose the local Open Design token bridge');
assert(orderHtml.includes('--od-accent: #07c160'), 'customer menu should include the WeChat/Open Design accent token');
assert(orderHtml.includes('--focus-ring'), 'customer menu should define a consistent focus-visible ring');
assert(orderHtml.includes(':focus-visible'), 'customer menu should expose keyboard/touch accessibility focus states');
assert(orderHtml.includes('overscroll-behavior: contain'), 'customer menu should contain mobile overscroll/pull refresh behavior');
assert(orderHtml.includes('@media (hover: hover)'), 'customer menu should expose desktop hover affordances without relying on them for mobile');
assert(orderHtml.includes('function hapticTap'), 'customer menu should provide light haptic feedback for important mobile confirmations');
assert(orderHtml.includes('.plus {') && orderHtml.includes('height: 44px'), 'customer menu selection button should meet 44px mobile touch target guidance');
assert(!orderHtml.includes('id="searchInput"'), 'customer menu should not render a fixed search input');
assert(!orderHtml.includes('.search {'), 'customer menu should not keep fixed search-box styling');
assert(orderHtml.includes('calc(100dvh - 104px)'), 'customer menu main height should match the compact top bar');
assert(!orderHtml.includes('${p.durationMinutes || 0}分钟'), 'detail summary should not render 0分钟 blindly');
assert(!adminHtml.includes('${p.durationMinutes || 0}分钟'), 'admin project list should not render 0分钟 blindly');
assert(orderHtml.includes('function durationSummary'), 'missing category-aware duration summary');
assert(adminHtml.includes('function adminDurationLabel'), 'admin missing category-aware duration label');
assert(orderHtml.includes('function renderQptyRows'), 'missing filtered qing-pao-tiao-bu-yang renderer');
assert(orderHtml.includes('function renderPaoOptionPanel'), 'pao detail page should use dedicated card-style option panel');
assert(!orderHtml.includes('function recommendedProjects'), 'formula-based recommended section should be removed from customer menu');
assert(!orderHtml.includes('recommend-section'), 'formula-based recommended section markup should be removed from customer menu');
assert(!orderHtml.includes('function solutionProfiles'), 'solution profiles should be removed from customer menu');
assert(!orderHtml.includes('function renderSolutionGuide'), 'solution guide renderer should be removed from customer menu');
assert(!orderHtml.includes('function renderSolutionPrescription'), 'solution prescription renderer should be removed from customer menu');
assert(!orderHtml.includes('function scoreProjectForSolution'), 'formula scoring should be removed from customer menu');
assert(!orderHtml.includes('function jumpToSolutionCategory'), 'formula category jump should be removed from customer menu');
assert(!orderHtml.includes('solution-guide'), 'solution guide visual layer should be removed from customer menu');
assert(!orderHtml.includes('formula-selector'), 'formula selector layout should be removed from customer menu');
assert(!orderHtml.includes('formula-panel'), 'formula panel should be removed from customer menu');
assert(!orderHtml.includes('section-solution'), 'solution guide scroll target should be removed');
assert(!orderHtml.includes('data-cat="solution"'), 'left navigation should not include solution guide entry');
assert(!orderHtml.includes('<span class="cat-icon">方</span><span class="cat-name">选方案</span>'), 'left navigation should not show 方/选方案');
assert(!orderHtml.includes('五行草本调养'), 'customer menu should not render the removed formula guide');
assert(!orderHtml.includes('养生导购，不作诊断'), 'customer menu should not render removed formula-guide disclaimer');
for (const removedCopy of ['体质数据参考', '五行对应脏腑', '产品组合落地', '眼疲、肩颈紧', '胃胀、乏力', '咽干、皮肤干', '腰腿沉、脚冷', '气血通畅']) {
  assert(!orderHtml.includes(removedCopy), `customer menu should not expose low-value or symptom-heavy copy: ${removedCopy}`);
}
for (const staleFormulaProduct of ['麦芽山楂饮', '香囊足贴', '暖腹养护贴', '银耳百合羹', '清润香包']) {
  assert(!orderHtml.includes(staleFormulaProduct), `formula route should not expose stale or unavailable product: ${staleFormulaProduct}`);
}
for (const projectName of ['草本泡脚 25分钟', '草本泡脚加钟', '草本足道 60分钟', '荷小推 60分钟', '悦SPA 60分钟', '采耳 20分钟', '拔罐 20分钟', '刮痧 20分钟']) {
  assert(apiMain.includes(projectName), `default project system missing ${projectName}`);
}
for (const comboName of ['五行茶饮', '五行泡脚液', '草本足道', '热敷包', '草本功效膏贴', '养生小吃']) {
  assert(apiMain.includes(comboName), `default product combo missing ${comboName}`);
}
assert(/"id": "tiao-yue-spa-60"[\s\S]*?"categoryId": "tiao"[\s\S]*?"name": "悦SPA 60分钟"/.test(apiMain), '悦SPA 60分钟 should belong to 调 series');
for (const buProduct of ['山药茯苓羹', '百合莲子羹', '芝麻核桃糊']) {
  assert(apiMain.includes(buProduct), `补 series missing product ${buProduct}`);
}
for (const yangProduct of ['草本泡脚包', '草本功效膏贴', '艾灸暖贴', '肩颈热敷贴']) {
  assert(apiMain.includes(yangProduct), `养 series missing take-away product ${yangProduct}`);
}
assert(!orderHtml.includes('按状态选方案'), 'removed formula guide copy should not remain in customer menu');
assert(!orderHtml.includes('今晚放松推荐'), 'customer menu should not use vague tonight recommendation copy');
assert(!orderHtml.includes('mood-scroll'), 'customer menu should not hide state choices in a horizontal scroll');
assert(!orderHtml.includes('featured-pick'), 'customer menu should not rely on a decorative first-card anchor');
assert(orderHtml.includes('function renderSelectedPlanSummary'), 'detail page should render selected plan summary');
assert(orderHtml.includes('plan-summary'), 'detail page should expose the selected plan summary card');
assert(orderHtml.includes('function rerenderDetailPreservingScroll'), 'detail option changes should preserve scroll position');
assert(orderHtml.includes('rerenderDetailPreservingScroll();'), 'detail option click handlers should not call bare renderDetail');
assert(orderHtml.includes('function requestSheetBack'), 'confirm/login sheet should support browser-back closing');
assert(orderHtml.includes('hxySheet'), 'confirm/login sheet should own a history state instead of surviving back navigation');
assert(orderHtml.includes('closeTransientLayers'), 'customer menu should clear transient sheets before opening detail/history flows');
assert(orderHtml.includes('closeSheet({ clearHistory: true })'), 'order submit and flow switches should clear sheet history state');
assert(orderHtml.indexOf("document.getElementById('sheet').classList.contains('open')") < orderHtml.indexOf("document.getElementById('historyPage').classList.contains('open')"), 'popstate should close open sheet before history/detail pages');
assert(orderHtml.includes('pao-choice-card'), 'pao option panel missing card layout class');
assert(orderHtml.includes('REQUIRED'), 'pao option panel missing required badge');
assert(orderHtml.includes('Add-ons'), 'pao option panel missing add-ons label');
assert(adminHtml.includes('id="optionEditor"'), 'admin missing structured option editor');
assert(adminHtml.includes('function renderOptionEditor'), 'admin missing option editor renderer');
assert(adminHtml.includes('function renderOptionRows'), 'admin option editor should render row-based controls');
assert(adminHtml.includes('function addOptionRow'), 'admin option editor should support adding rows');
assert(adminHtml.includes('function removeOptionRow'), 'admin option editor should support removing rows');
assert(adminHtml.includes('data-option-input'), 'admin option editor should use form inputs, not raw JSON/text only');
assert(!adminHtml.includes('每行一个选项组。格式'), 'admin option editor should not rely on pipe-format instructions');
assert(adminHtml.includes('function saveOptionsToCurrent'), 'admin missing option persistence');
assert(adminHtml.includes('id="featured"'), 'admin should let operators mark recommended projects');
assert(adminHtml.includes('id="recommendationReason"'), 'admin should edit recommendation reason');
assert(adminHtml.includes('id="recommendFor"'), 'admin should edit recommendation target');
assert(adminHtml.includes('id="recommendRank"'), 'admin should edit recommendation rank');

for (const marker of [
  'placeholder-qing.svg',
  'placeholder-bu.svg',
  'placeholder-yang.svg',
  'recommendationReason',
  'recommendFor',
  'recommendRank',
  '泡脚方',
  '疏肝方',
  '传统拔罐',
]) {
  assert(apiMain.includes(marker), `default catalog missing ${marker}`);
}

console.log('wellness menu polish checks passed');
