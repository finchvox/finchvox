(function initializeLogMessageFormatter(globalScope) {
    const INDENT = '  ';
    const PREVIEW_MAX_LENGTH = 220;
    const SIMPLE_ESCAPES = {
        n: '\n',
        r: '\n',
        t: '    ',
        b: '\b',
        f: '\f',
        '\\': '\\',
        '\'': '\'',
        '"': '"'
    };
    const IDENTIFIER_VALUES = {
        None: null,
        null: null,
        True: true,
        true: true,
        False: false,
        false: false
    };

    function normalizeLogText(value) {
        return String(value ?? '').replace(/\r\n?/g, '\n');
    }

    function getLogBodyValue(log) {
        if (!log) return '';
        if (typeof log.body?.string_value === 'string') return log.body.string_value;
        if (typeof log.body === 'string') return log.body;
        if (log.body === null || log.body === undefined) return '';
        return JSON.stringify(log.body);
    }

    function decodeLikelyEscapes(value) {
        const text = normalizeLogText(value);
        if (!text.includes('\\')) return text;

        return text
            .replace(/\\r\\n/g, '\n')
            .replace(/\\n/g, '\n')
            .replace(/\\r/g, '\n')
            .replace(/\\t/g, '    ')
            .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
            .replace(/\\"/g, '"')
            .replace(/\\'/g, '\'')
            .replace(/\\\\/g, '\\');
    }

    function indentLogBlock(text, indent = INDENT) {
        return String(text)
            .split('\n')
            .map(line => `${indent}${line}`)
            .join('\n');
    }

    function isPlainObject(value) {
        return Object.prototype.toString.call(value) === '[object Object]';
    }

    function isStructuredValue(value) {
        return Array.isArray(value) || isPlainObject(value);
    }

    function createParserState(input) {
        return { input, index: 0 };
    }

    function currentChar(state) {
        return state.input[state.index];
    }

    function advanceParser(state, step = 1) {
        state.index += step;
    }

    function sliceParser(state, length) {
        return state.input.slice(state.index, state.index + length);
    }

    function skipWhitespace(state) {
        while (state.index < state.input.length && /\s/.test(currentChar(state))) {
            advanceParser(state);
        }
    }

    function isIdentifierStart(char) {
        return /[A-Za-z_]/.test(char);
    }

    function isIdentifierPart(char) {
        return /[A-Za-z0-9_]/.test(char);
    }

    function isQuotedValueStart(char) {
        return char === '\'' || char === '"';
    }

    function isNumericValueStart(char) {
        return char === '-' || /\d/.test(char);
    }

    function parseUnicodeEscape(state) {
        const hex = sliceParser(state, 4);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
            return 'u';
        }

        advanceParser(state, 4);
        return String.fromCharCode(parseInt(hex, 16));
    }

    function parseEscapedCharacter(state) {
        if (state.index >= state.input.length) return '\\';

        const escaped = currentChar(state);
        advanceParser(state);

        if (escaped === 'u') {
            return parseUnicodeEscape(state);
        }

        return SIMPLE_ESCAPES[escaped] ?? escaped;
    }

    function parseQuotedString(state) {
        const quote = currentChar(state);
        const parts = [];
        advanceParser(state);

        while (state.index < state.input.length) {
            const char = currentChar(state);
            advanceParser(state);

            if (char === quote) {
                return parts.join('');
            }

            if (char === '\\') {
                parts.push(parseEscapedCharacter(state));
                continue;
            }

            parts.push(char);
        }

        throw new Error('Unterminated string literal');
    }

    function parseNumberLiteral(state) {
        const match = state.input
            .slice(state.index)
            .match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);

        if (!match) {
            throw new Error('Invalid number literal');
        }

        advanceParser(state, match[0].length);
        return Number(match[0]);
    }

    function readIdentifierToken(state) {
        if (!isIdentifierStart(currentChar(state))) {
            throw new Error('Unexpected token');
        }

        const start = state.index;
        advanceParser(state);
        while (state.index < state.input.length && isIdentifierPart(currentChar(state))) {
            advanceParser(state);
        }

        return state.input.slice(start, state.index);
    }

    function parseKnownIdentifierValue(identifier) {
        if (Object.prototype.hasOwnProperty.call(IDENTIFIER_VALUES, identifier)) {
            return { matched: true, value: IDENTIFIER_VALUES[identifier] };
        }
        return { matched: false, value: identifier };
    }

    function parseIdentifier(state, allowBareWord = false) {
        const identifier = readIdentifierToken(state);
        const parsed = parseKnownIdentifierValue(identifier);
        if (parsed.matched) return parsed.value;
        if (allowBareWord) return identifier;
        throw new Error(`Unsupported identifier: ${identifier}`);
    }

    function getCurrentValueStart(state) {
        skipWhitespace(state);
        if (state.index >= state.input.length) {
            throw new Error('Unexpected end of input');
        }
        return currentChar(state);
    }

    function getPrefixedLiteralParser(char) {
        if (isQuotedValueStart(char)) return parseQuotedString;
        if (char === '[') return parseArrayLiteral;
        if (char === '{') return parseObjectLiteral;
        if (isNumericValueStart(char)) return parseNumberLiteral;
        return null;
    }

    function parseLiteralValue(state) {
        const char = getCurrentValueStart(state);
        const parser = getPrefixedLiteralParser(char);
        if (parser) return parser(state);
        return parseIdentifier(state);
    }

    function parseArrayLiteral(state) {
        const items = [];
        advanceParser(state);
        skipWhitespace(state);

        if (currentChar(state) === ']') {
            advanceParser(state);
            return items;
        }

        while (state.index < state.input.length) {
            items.push(parseLiteralValue(state));
            skipWhitespace(state);

            if (currentChar(state) === ',') {
                advanceParser(state);
                skipWhitespace(state);
                continue;
            }

            if (currentChar(state) === ']') {
                advanceParser(state);
                return items;
            }

            throw new Error('Expected "," or "]"');
        }

        throw new Error('Unterminated array literal');
    }

    function parseObjectKey(state) {
        skipWhitespace(state);
        const char = currentChar(state);
        if (char === '\'' || char === '"') return parseQuotedString(state);
        return parseIdentifier(state, true);
    }

    function isEmptyObjectLiteral(state) {
        return currentChar(state) === '}';
    }

    function consumeObjectKeySeparator(state) {
        if (currentChar(state) !== ':') {
            throw new Error('Expected ":"');
        }
        advanceParser(state);
    }

    function parseObjectEntry(state, result) {
        const key = parseObjectKey(state);
        skipWhitespace(state);
        consumeObjectKeySeparator(state);
        result[String(key)] = parseLiteralValue(state);
        skipWhitespace(state);
    }

    function consumeObjectEntrySeparator(state) {
        if (currentChar(state) === ',') {
            advanceParser(state);
            skipWhitespace(state);
            return false;
        }

        if (currentChar(state) === '}') {
            advanceParser(state);
            return true;
        }

        throw new Error('Expected "," or "}"');
    }

    function parseObjectLiteral(state) {
        const result = {};
        advanceParser(state);
        skipWhitespace(state);

        if (isEmptyObjectLiteral(state)) {
            advanceParser(state);
            return result;
        }

        while (state.index < state.input.length) {
            parseObjectEntry(state, result);
            if (consumeObjectEntrySeparator(state)) return result;
        }

        throw new Error('Unterminated object literal');
    }

    function tryParseJsonLiteral(text) {
        try {
            return { value: JSON.parse(text) };
        } catch {
            return null;
        }
    }

    function tryParsePythonLiteral(text) {
        try {
            const state = createParserState(text);
            const value = parseLiteralValue(state);
            skipWhitespace(state);

            if (state.index !== text.length) {
                return null;
            }

            return { value };
        } catch {
            return null;
        }
    }

    function tryParseStructuredLiteral(text) {
        const trimmed = normalizeLogText(text).trim();
        if (!trimmed) return null;

        const jsonLiteral = tryParseJsonLiteral(trimmed);
        if (jsonLiteral) return jsonLiteral;

        if (!['{', '[', '"', '\''].includes(trimmed[0])) {
            return null;
        }

        return tryParsePythonLiteral(trimmed);
    }

    function looksLikeStructuredPrefix(text, index) {
        if (index <= 0) return true;
        return /[\s|:=>(,]/.test(text[index - 1]);
    }

    function findStructuredSuffix(text) {
        for (let index = 0; index < text.length; index += 1) {
            const char = text[index];
            if (char !== '{' && char !== '[') continue;
            if (!looksLikeStructuredPrefix(text, index)) continue;

            const parsed = tryParseStructuredLiteral(text.slice(index));
            if (!parsed || !isStructuredValue(parsed.value)) continue;

            return {
                prefix: text.slice(0, index).trimEnd(),
                value: parsed.value
            };
        }

        return null;
    }

    function formatStructuredArray(value, depth) {
        if (value.length === 0) return '[]';

        const items = value
            .map(item => indentLogBlock(formatStructuredValue(item, depth + 1)))
            .join(',\n');

        return `[\n${items}\n]`;
    }

    function formatStructuredEntry(key, value, depth) {
        const renderedValue = formatStructuredValue(value, depth + 1);
        if (!renderedValue.includes('\n')) {
            return `${JSON.stringify(key)}: ${renderedValue}`;
        }

        if (renderedValue.startsWith('{') || renderedValue.startsWith('[')) {
            const [firstLine, ...restLines] = renderedValue.split('\n');
            return `${JSON.stringify(key)}: ${firstLine}\n${restLines.join('\n')}`;
        }

        return `${JSON.stringify(key)}:\n${indentLogBlock(renderedValue)}`;
    }

    function formatStructuredObject(value, depth) {
        const entries = Object.entries(value);
        if (entries.length === 0) return '{}';

        const lines = entries
            .map(([key, entryValue]) => formatStructuredEntry(key, entryValue, depth))
            .join(',\n');

        return `{\n${indentLogBlock(lines)}\n}`;
    }

    function formatStructuredString(value, depth) {
        const beautified = formatLogBody(value, depth + 1);
        if (beautified.includes('\n')) return beautified;
        return JSON.stringify(beautified);
    }

    function formatStructuredScalar(value) {
        if (value === null) return 'null';
        return JSON.stringify(value);
    }

    function formatStructuredValue(value, depth = 0) {
        if (depth > 8) return JSON.stringify(String(value));
        if (Array.isArray(value)) return formatStructuredArray(value, depth);
        if (isPlainObject(value)) return formatStructuredObject(value, depth);
        if (typeof value === 'string') return formatStructuredString(value, depth);
        return formatStructuredScalar(value);
    }

    function formatParsedLiteralResult(parsedLiteral, depth) {
        if (!parsedLiteral) return null;
        if (typeof parsedLiteral.value === 'string') {
            return formatLogBody(parsedLiteral.value, depth + 1);
        }
        return formatStructuredValue(parsedLiteral.value, depth + 1);
    }

    function formatStructuredSuffixResult(structuredSuffix, depth) {
        if (!structuredSuffix) return null;

        const formattedValue = formatStructuredValue(structuredSuffix.value, depth + 1);
        if (!structuredSuffix.prefix) return formattedValue;
        return `${structuredSuffix.prefix}\n${formattedValue}`;
    }

    function formatNormalizedTextBody(text, depth) {
        if (!text) return '';

        const parsedLiteralResult = formatParsedLiteralResult(
            tryParseStructuredLiteral(text),
            depth
        );
        if (parsedLiteralResult !== null) return parsedLiteralResult;

        const structuredSuffixResult = formatStructuredSuffixResult(
            findStructuredSuffix(text),
            depth
        );
        if (structuredSuffixResult !== null) return structuredSuffixResult;

        return decodeLikelyEscapes(text);
    }

    function formatLogBody(value, depth = 0) {
        if (value === null || value === undefined) return '';
        if (isStructuredValue(value)) return formatStructuredValue(value, depth + 1);
        return formatNormalizedTextBody(normalizeLogText(value), depth);
    }

    function getSearchText(log) {
        return decodeLikelyEscapes(getLogBodyValue(log));
    }

    function getPreviewText(log) {
        const compact = getSearchText(log).replace(/\s+/g, ' ').trim();
        if (compact.length <= PREVIEW_MAX_LENGTH) return compact;
        return `${compact.slice(0, PREVIEW_MAX_LENGTH - 1)}...`;
    }

    globalScope.logMessageFormatter = {
        formatLogBody,
        getLogBodyValue,
        getPreviewText,
        getSearchText
    };
})(globalThis);
