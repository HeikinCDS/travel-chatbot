// Run with node --test tests/design.test.cjs (no additional packages required).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/design.js'), 'utf8');

function setup(withObserver = true) {
  const observed = [];
  const properties = {};
  const header = { offsetHeight: 94 };
  const composer = { offsetHeight: 150 };
  const root = { dataset: {}, style: {setProperty: (key, value) => { properties[key] = value; }} };
  let ready;
  let resized;
  class ResizeObserver {
    constructor(callback) { resized = callback; }
    observe(element) { observed.push(element); }
  }
  vm.runInNewContext(source, {
    document: {
      documentElement: root,
      querySelector: selector => selector === '.top-bar' ? header : composer,
      addEventListener: (_, fn) => { ready = fn; },
    },
    // Access fails: the visual layer must not touch legacy design or chat settings.
    localStorage: new Proxy({}, {get() { throw Error('Unexpected storage access'); }}),
    ResizeObserver,
    window: withObserver ? {ResizeObserver} : {},
  });
  ready();
  return {root, properties, observed, header, composer, resize: () => resized()};
}
test('modern design initializes without accessing stored preferences', () => {
  assert.equal(setup().root.dataset.design, 'modern');
});
test('observes both header and composer without a design selector', () => {
  const s = setup();
  assert.deepEqual(s.observed, [s.header, s.composer]);
});
test('wrapped controls update the layout dimensions', () => {
  const s = setup();
  s.resize();
  assert.equal(s.properties['--header-height'], '94px');
  assert.equal(s.properties['--composer-height'], '150px');
  s.header.offsetHeight = 180;
  s.resize();
  assert.equal(s.properties['--header-height'], '180px');
});
test('layout initialization works without ResizeObserver', () => {
  assert.equal(setup(false).root.dataset.design, 'modern');
});
