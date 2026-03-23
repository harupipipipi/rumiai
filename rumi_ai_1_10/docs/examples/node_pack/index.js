/**
 * Rumi AI OS — Node.js Pack サンプル
 *
 * このサンプルは 2 つの機能を提供します:
 *   - hello: 挨拶を返す
 *   - kv_store: インメモリ KV ストア
 *
 * stdin/stdout JSON プロトコルに従い、Kernel からの入力を受け取り、
 * 処理結果を JSON で返します。
 */

'use strict';

process.stdin.setEncoding('utf8');

let inputData = '';

process.stdin.on('data', (chunk) => {
    inputData += chunk;
});

process.stdin.on('end', () => {
    try {
        const input = JSON.parse(inputData);
        const context = input.context || {};
        const args = input.args || {};

        let result;

        switch (context.function_id) {
            case 'hello':
                result = handleHello(context, args);
                break;
            case 'kv_store':
                result = handleKvStore(context, args);
                break;
            default:
                result = {
                    error: 'Unknown function_id: ' + (context.function_id || '(empty)'),
                    error_type: 'unknown_function',
                };
                break;
        }

        process.stdout.write(JSON.stringify(result));
    } catch (e) {
        process.stderr.write('Error: ' + e.message);
        process.exit(1);
    }
});

process.stdin.on('error', (err) => {
    process.stderr.write('Failed to read stdin: ' + err.message);
    process.exit(1);
});

/**
 * hello: 挨拶を返す
 * @param {Object} context - リクエストコンテキスト
 * @param {Object} args - 引数 { name?: string }
 * @returns {Object} 出力 JSON
 */
function handleHello(context, args) {
    const name = args.name || 'World';
    return {
        message: 'Hello, ' + name + '!',
        greeted_by: context.pack_id + ':' + context.function_id,
        principal: context.principal_id,
        timestamp: context.ts,
    };
}

/**
 * kv_store: キー-バリューストア操作
 * @param {Object} context - リクエストコンテキスト
 * @param {Object} args - 引数 { action: string, key?: string, value?: any }
 * @returns {Object} 出力 JSON
 */
function handleKvStore(context, args) {
    const action = args.action || '';

    switch (action) {
        case 'set':
            return {
                action: 'set',
                key: args.key || '',
                value: args.value !== undefined ? args.value : null,
                success: true,
            };
        case 'get':
            // 注: サンプルのため実際のストレージはない
            return {
                action: 'get',
                key: args.key || '',
                value: null,
                success: true,
            };
        case 'list':
            return {
                action: 'list',
                entries: {},
                success: true,
            };
        case 'delete':
            return {
                action: 'delete',
                key: args.key || '',
                success: true,
            };
        default:
            process.stderr.write('Unknown action: ' + action);
            process.exit(1);
    }
}
