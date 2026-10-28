const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
const layout = vm.runInNewContext(source.slice(0, source.indexOf('/* END READING LAYOUT */')) + '\nReadingLayout');
const block = (id, kind, text, page = 0) => ({
  id, kind, text, page, column: 'left', source_bbox: [50, 50 + id.length * 10, 290, 58 + id.length * 10],
});
const blocks = [
  block('h', 'heading', 'References'),
  block('a', 'reference', '[1] First author. The Con-'),
  block('bb', 'paragraph', 'tinuation. [2] M. Wang. Second title.'),
  block('ccc', 'paragraph', 'More details. [Online]. Available: https://example.org'),
  block('dddd', 'reference', '[3] Third author. Last entry.', 1),
];
const original = JSON.stringify(blocks);
for (const smooth of [false, true]) {
  const units = layout.plan({ pages: [{ blocks: blocks.slice(0, 4) }, { blocks: [blocks[4]] }] }, smooth);
  const references = units.find(unit => unit.type === 'references');
  assert.ok(references);
  assert.deepEqual(Array.from(references.entries, item => item.number), [1, 2, 3]);
  assert.match(references.entries[0].text, /The Continuation\./);
  assert.match(references.entries[1].text, /M\. Wang\. Second title\. More details\./);
  assert.match(references.entries[1].text, /\[Online\]/);
  assert.equal(references.entries[2].blocks[0].page, 1);
}
assert.equal(JSON.stringify(blocks), original);
console.log('Reference entries regrouped without changing source blocks.');
