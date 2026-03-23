// Rumi AI OS — Go Pack サンプル
//
// このサンプルは 2 つの機能を提供します:
//   - hello: 挨拶を返す
//   - kv_store: インメモリ KV ストア
//
// stdin/stdout JSON プロトコルに従い、Kernel からの入力を受け取り、
// 処理結果を JSON で返します。

package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
)

// --- 入力構造体 ---

// Context はリクエストのコンテキスト情報を保持する
type Context struct {
	PrincipalID string `json:"principal_id"`
	PackID      string `json:"pack_id"`
	FunctionID  string `json:"function_id"`
	RequestID   string `json:"request_id"`
	Ts          string `json:"ts"`
}

// Input は stdin から受け取る JSON の構造
type Input struct {
	Context Context                `json:"context"`
	Args    map[string]interface{} `json:"args"`
}

// --- 出力構造体 ---

// HelloOutput は hello 機能の出力
type HelloOutput struct {
	Message   string `json:"message"`
	GreetedBy string `json:"greeted_by"`
	Principal string `json:"principal"`
	Timestamp string `json:"timestamp"`
}

// KvOutput は kv_store 機能の出力
type KvOutput struct {
	Action  string                 `json:"action"`
	Key     string                 `json:"key,omitempty"`
	Value   interface{}            `json:"value,omitempty"`
	Entries map[string]interface{} `json:"entries,omitempty"`
	Success bool                   `json:"success"`
}

// ErrorOutput はエラー時の出力
type ErrorOutput struct {
	Error     string `json:"error"`
	ErrorType string `json:"error_type"`
}

// --- メイン ---

func main() {
	// stdin から全文読み取り
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to read stdin: %v", err)
		os.Exit(1)
	}

	// JSON パース
	var input Input
	if err := json.Unmarshal(data, &input); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to parse input JSON: %v", err)
		os.Exit(1)
	}

	// function_id に応じて処理を分岐
	var result interface{}
	switch input.Context.FunctionID {
	case "hello":
		result = handleHello(&input)
	case "kv_store":
		result = handleKvStore(&input)
	default:
		result = ErrorOutput{
			Error:     fmt.Sprintf("Unknown function_id: %s", input.Context.FunctionID),
			ErrorType: "unknown_function",
		}
	}

	// stdout に結果を出力
	output, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to serialize output: %v", err)
		os.Exit(1)
	}
	fmt.Println(string(output))
}

func handleHello(input *Input) HelloOutput {
	name := "World"
	if v, ok := input.Args["name"]; ok {
		if s, ok := v.(string); ok && s != "" {
			name = s
		}
	}

	return HelloOutput{
		Message:   fmt.Sprintf("Hello, %s!", name),
		GreetedBy: fmt.Sprintf("%s:%s", input.Context.PackID, input.Context.FunctionID),
		Principal: input.Context.PrincipalID,
		Timestamp: input.Context.Ts,
	}
}

func handleKvStore(input *Input) interface{} {
	action, _ := input.Args["action"].(string)

	switch action {
	case "set":
		key, _ := input.Args["key"].(string)
		value := input.Args["value"]
		return KvOutput{
			Action:  "set",
			Key:     key,
			Value:   value,
			Success: true,
		}
	case "get":
		key, _ := input.Args["key"].(string)
		// 注: サンプルのため実際のストレージはない
		return KvOutput{
			Action:  "get",
			Key:     key,
			Success: true,
		}
	case "list":
		return KvOutput{
			Action:  "list",
			Entries: map[string]interface{}{},
			Success: true,
		}
	case "delete":
		key, _ := input.Args["key"].(string)
		return KvOutput{
			Action:  "delete",
			Key:     key,
			Success: true,
		}
	default:
		fmt.Fprintf(os.Stderr, "Unknown action: %s", action)
		os.Exit(1)
		return nil // unreachable
	}
}
