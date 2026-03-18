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

    function parseIdentifier(state, allowBareWord = false) {
        const start = state.index;

        if (!isIdentifierStart(currentChar(state))) {
            throw new Error('Unexpected token');
        }

        advanceParser(state);
        while (state.index < state.input.length && isIdentifierPart(currentChar(state))) {
            advanceParser(state);
        }

        const identifier = state.input.slice(start, state.index);

        if (identifier === 'None' || identifier === 'null') return null;
        if (identifier === 'True' || identifier === 'true') return true;
        if (identifier === 'False' || identifier === 'false') return false;
        if (allowBareWord) return identifier;

        throw new Error(`Unsupported identifier: ${identifier}`);
    }

    function parseLiteralValue(state) {
        skipWhitespace(state);

        if (state.index >= state.input.length) {
            throw new Error('Unexpected end of input');
        }

        const char = currentChar(state);

        if (char === '\'' || char === '"') return parseQuotedString(state);
        if (char === '[') return parseArrayLiteral(state);
        if (char === '{') return parseObjectLiteral(state);
        if (char === '-' || /\d/.test(char)) return parseNumberLiteral(state);

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

    function parseObjectLiteral(state) {
        const result = {};
        advanceParser(state);
        skipWhitespace(state);

        if (currentChar(state) === '}') {
            advanceParser(state);
            return result;
        }

        while (state.index < state.input.length) {
            const key = parseObjectKey(state);
            skipWhitespace(state);

            if (currentChar(state) !== ':') {
                throw new Error('Expected ":"');
            }

            advanceParser(state);
            result[String(key)] = parseLiteralValue(state);
            skipWhitespace(state);

            if (currentChar(state) === ',') {
                advanceParser(state);
                skipWhitespace(state);
                continue;
            }

            if (currentChar(state) === '}') {
                advanceParser(state);
                return result;
            }

            throw new Error('Expected "," or "}"');
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

    function formatLogBody(value, depth = 0) {
        if (value === null || value === undefined) return '';
        if (isStructuredValue(value)) return formatStructuredValue(value, depth + 1);

        const text = normalizeLogText(value);
        if (!text) return '';

        const parsedLiteral = tryParseStructuredLiteral(text);
        if (parsedLiteral) {
            if (typeof parsedLiteral.value === 'string') {
                return formatLogBody(parsedLiteral.value, depth + 1);
            }
            return formatStructuredValue(parsedLiteral.value, depth + 1);
        }

        const structuredSuffix = findStructuredSuffix(text);
        if (structuredSuffix) {
            const formattedValue = formatStructuredValue(structuredSuffix.value, depth + 1);
            if (!structuredSuffix.prefix) return formattedValue;
            return `${structuredSuffix.prefix}\n${formattedValue}`;
        }

        return decodeLikelyEscapes(text);
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
