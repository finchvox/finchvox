// Tests for ui/js/log_message_formatter.js, run with: node --test scripts/test_log_formatter.cjs
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../ui/js/log_message_formatter.js'), 'utf8');

function loadFormatter() {
    const context = {};
    vm.runInNewContext(source, context);
    return context.logMessageFormatter;
}

const log = text => ({ body: { string_value: text } });

test('a plain one-line message is shown unchanged', () => {
    const formatter = loadFormatter();
    const text = 'event loop blocked for 136ms importing anyio.abc._eventloop';
    assert.equal(formatter.formatLogBody(formatter.getLogBodyValue(log(text))), text);
    assert.equal(formatter.getPreviewText(log(text)), text);
});

test('a Python dictionary in a message is laid out over several lines', () => {
    const formatter = loadFormatter();
    const formatted = formatter.formatLogBody("Tool result: {'order': {'item': 'latte', 'size': None}, 'ok': True}");

    assert.ok(formatted.startsWith('Tool result:'), formatted);
    assert.ok(formatted.split('\n').length > 3, formatted);
    assert.match(formatted, /latte/);
    assert.match(formatted, /size/);
});

test('escaped newlines become real line breaks', () => {
    const formatter = loadFormatter();
    assert.equal(formatter.getSearchText(log('first\\nsecond')), 'first\nsecond');
});

test('the table preview is one line and cut at 220 characters', () => {
    const formatter = loadFormatter();
    const preview = formatter.getPreviewText(log(`start\n${'x'.repeat(400)}`));

    assert.ok(!preview.includes('\n'));
    assert.equal(preview.length, 222);
    assert.ok(preview.endsWith('...'));
});

test('messages without a text body still work', () => {
    const formatter = loadFormatter();
    assert.equal(formatter.getLogBodyValue(null), '');
    assert.equal(formatter.getLogBodyValue({ body: 'plain string' }), 'plain string');
    assert.equal(formatter.getLogBodyValue({ body: { int_value: '5' } }), '{"int_value":"5"}');
});
