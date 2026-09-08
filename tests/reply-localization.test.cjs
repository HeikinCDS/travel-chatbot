const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/chat.js'), 'utf8');
const functions = source.slice(source.indexOf('const LOCALIZED_LABELS ='), source.indexOf('function resizeMessageInput'));
function render(language, data) {
  const context = {currentLanguage: language, data};
  vm.createContext(context);
  vm.runInContext(functions, context);
  return vm.runInContext('localizeReply(data)', context);
}
const response = {
  reply: 'Your interest is already set to beach. No matching records.',
  action: 'no_results',
  context: {state:'Penang', interests:['beach'], wheelchair_accessible:true, maximum_fee:30},
  unchanged_preferences: {interests:['beach']},
};
test('English keeps the backend acknowledgement exactly once', () => {
  assert.equal(render('en', response), response.reply);
});
test('Malay includes the repeated interest and wheelchair-budget requirements', () => {
  const reply = render('ms', response);
  for(const term of ['sudah ditetapkan','Pantai','Penang','kerusi roda','RM30']) assert.ok(reply.includes(term), term);
});
test('Chinese includes the repeated interest and wheelchair-budget requirements', () => {
  const reply = render('zh', response);
  for(const term of ['已经设为','海滩','Penang','轮椅','RM30']) assert.ok(reply.includes(term), term);
});
test('new preferences do not get an already-saved acknowledgement', () => {
  assert.ok(!render('ms', {...response, unchanged_preferences:{}}).includes('sudah ditetapkan'));
});
test('older saved replies without metadata still render', () => {
  const {unchanged_preferences, ...oldResponse} = response;
  assert.ok(render('zh',oldResponse).includes('轮椅'));
});
