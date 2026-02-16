"""
Gemini AIクライアント
Google Gemini APIとの通信を担当
標準形式の履歴をGemini形式に変換して送信
"""

# 必要なパッケージを宣言
REQUIRED_PACKAGES = [
    "google-genai>=1.0.0",
    "python-dotenv>=1.0.0",
]

import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator, Tuple
from dotenv import load_dotenv


class GeminiClient:
    """Gemini API用のクライアント"""
    
    def __init__(self):
        """
        Geminiクライアントを初期化
        APIキーは ai_client/.env.local から取得
        """
        # ai_client/.env.local を読み込み
        env_path = Path(__file__).parent.parent / '.env.local'
        load_dotenv(env_path)
        
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError(
                f"GEMINI_API_KEY not found in {env_path}\n"
                "Please create ai_client/.env.local and add your API key"
            )
        
        # Geminiクライアントを初期化
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            print(f"Gemini client initialized (API Key: {self.get_masked_api_key()})")
        except Exception as e:
            raise ValueError(f"Failed to initialize Gemini client: {e}")
    
    def get_masked_api_key(self) -> str:
        """マスクされたAPIキーを返す（ログ出力用）"""
        if not self.api_key:
            return "NOT_SET"
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"
    
    @staticmethod
    def get_provider_name() -> str:
        """プロバイダー名を返す"""
        return "gemini"
    
    @staticmethod
    def get_profile_dir() -> Path:
        """プロファイルディレクトリのパスを返す"""
        return Path(__file__).parent / "ai_profile"
    
    def convert_standard_to_gemini(self, history: Dict, system_prompt: str = None) -> Tuple[List[Any], str]:
        """
        標準形式の履歴をGemini形式に変換
        
        Args:
            history: 標準形式の履歴（schema_version: "2.0"）
            system_prompt: システムプロンプト
        
        Returns:
            Tuple[contents, system_instruction]
        """
        from google.genai import types as gemini_types
        
        contents = []
        collected_system_prompt = system_prompt or ""
        
        # 標準形式かどうかを判定
        if history.get("schema_version") == "2.0":
            # mappingを辿って会話スレッドを取得
            thread = self._get_conversation_thread(history)
        else:
            # 旧形式の場合はmessages配列をそのまま使用
            thread = history.get("messages", [])
        
        for msg in thread:
            role = msg.get("role")
            content = msg.get("content")
            
            # systemメッセージはsystem_instructionに追加
            if role == "system":
                if content:
                    if collected_system_prompt:
                        collected_system_prompt += "\n\n" + content
                    else:
                        collected_system_prompt = content
                continue
            
            # userメッセージ
            if role == "user":
                parts = []
                
                # テキストコンテンツ
                if content:
                    parts.append(gemini_types.Part.from_text(text=content))
                
                # 添付ファイル
                if msg.get("attachments"):
                    for att in msg["attachments"]:
                        part = self._convert_attachment_to_part(att)
                        if part:
                            parts.append(part)
                
                if parts:
                    contents.append(gemini_types.Content(role="user", parts=parts))
            
            # assistantメッセージ
            elif role == "assistant":
                parts = []
                
                # テキストコンテンツ
                if content:
                    parts.append(gemini_types.Part.from_text(text=content))
                
                # tool_callsがある場合
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        parts.append(gemini_types.Part.from_function_call(
                            name=tc["function_name"],
                            args=tc.get("arguments", {})
                        ))
                
                if parts:
                    contents.append(gemini_types.Content(role="model", parts=parts))
            
            # toolメッセージ
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                
                # 対応するfunction_nameを探す
                function_name = self._find_function_name_for_tool_call(thread, tool_call_id)
                
                if function_name:
                    # contentをパース
                    try:
                        result = json.loads(content) if content else {}
                    except (json.JSONDecodeError, TypeError):
                        result = {"output": content}
                    
                    parts = [gemini_types.Part.from_function_response(
                        name=function_name,
                        response={"result": result}
                    )]
                    contents.append(gemini_types.Content(role="tool", parts=parts))
        
        return contents, collected_system_prompt
    
    def _get_conversation_thread(self, history: Dict) -> List[Dict]:
        """mappingを辿って会話スレッドを取得"""
        current_node = history.get("current_node")
        mapping = history.get("mapping", {})
        messages = history.get("messages", [])
        
        if not current_node or not mapping:
            return messages
        
        # current_nodeからルートまで遡る
        path = []
        current = current_node
        
        while current:
            path.append(current)
            entry = mapping.get(current)
            if not entry:
                break
            current = entry.get("parent")
        
        path.reverse()
        
        # メッセージIDからメッセージを取得
        messages_by_id = {msg["message_id"]: msg for msg in messages}
        
        return [messages_by_id[msg_id] for msg_id in path if msg_id in messages_by_id]
    
    def _find_function_name_for_tool_call(self, thread: List[Dict], tool_call_id: str) -> Optional[str]:
        """tool_call_idに対応するfunction_nameを探す"""
        for msg in thread:
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if tc.get("tool_call_id") == tool_call_id:
                        return tc["function_name"]
        return None
    
    def _convert_attachment_to_part(self, attachment: Dict) -> Optional[Any]:
        """添付ファイルをGemini Partに変換"""
        from google.genai import types as gemini_types
        import base64
        
        att_type = attachment.get("type")
        url = attachment.get("url", "")
        mime_type = attachment.get("mime_type", "application/octet-stream")
        
        # data URLの場合
        if url.startswith("data:"):
            try:
                header, data = url.split(",", 1)
                binary_data = base64.b64decode(data)
                return gemini_types.Part.from_bytes(
                    data=binary_data,
                    mime_type=mime_type
                )
            except Exception as e:
                print(f"Failed to convert data URL: {e}")
                return None
        
        # http/https URLの場合
        elif url.startswith("http://") or url.startswith("https://"):
            return gemini_types.Part.from_uri(
                file_uri=url,
                mime_type=mime_type
            )
        
        return None
    
    def send_request(
        self,
        model_id: str,
        history: Dict,
        current_text_input: str,
        current_file_paths: List[str],
        temperature: float = 0.8,
        thinking_budget: Optional[int] = None,
        tools: Optional[List] = None,
        system_prompt: str = None,
        debug_mode: bool = False,
        **kwargs
    ) -> Any:
        """
        Gemini APIにリクエストを送信（非ストリーミング）
        
        Args:
            model_id: モデルID
            history: 標準形式の履歴
            current_text_input: 現在の入力テキスト
            current_file_paths: ファイルパスのリスト
            temperature: 温度パラメータ
            thinking_budget: 思考予算
            tools: ツール定義
            system_prompt: システムプロンプト
            debug_mode: デバッグモード
        
        Returns:
            Gemini API応答
        """
        from google.genai import types as gemini_types
        
        # 標準形式からGemini形式に変換
        gemini_contents, final_system_prompt = self.convert_standard_to_gemini(
            history, system_prompt
        )
        
        # 現在の入力を追加
        if current_text_input or current_file_paths:
            parts = self._create_parts_from_input(current_text_input, current_file_paths)
            if parts:
                gemini_contents.append(gemini_types.Content(role="user", parts=parts))
        
        # 生成設定を作成
        config = self._create_generation_config(
            temperature=temperature,
            thinking_budget=thinking_budget,
            tools=tools,
            system_prompt=final_system_prompt
        )
        
        if debug_mode:
            print(f"[DEBUG] Sending request to {model_id}")
            print(f"[DEBUG] Contents count: {len(gemini_contents)}")
            print(f"[DEBUG] System prompt length: {len(final_system_prompt) if final_system_prompt else 0}")
        
        # リクエストを送信
        try:
            response = self.client.models.generate_content(
                model=model_id,
                contents=gemini_contents,
                config=config
            )
            return response
        except Exception as e:
            print(f"Gemini API error: {e}")
            raise
    
    def send_request_stream(
        self,
        model_id: str,
        history: Dict,
        current_text_input: str,
        current_file_paths: List[str],
        temperature: float = 0.8,
        thinking_budget: Optional[int] = None,
        tools: Optional[List] = None,
        abort_signal: Optional[Any] = None,
        system_prompt: str = None,
        debug_mode: bool = False,
        **kwargs
    ) -> Iterator:
        """
        Gemini APIにストリーミングリクエストを送信
        
        Args:
            model_id: モデルID
            history: 標準形式の履歴
            current_text_input: 現在の入力テキスト
            current_file_paths: ファイルパスのリスト
            temperature: 温度パラメータ
            thinking_budget: 思考予算
            tools: ツール定義
            abort_signal: 中断シグナル
            system_prompt: システムプロンプト
            debug_mode: デバッグモード
        
        Yields:
            ストリームチャンク
        """
        from google.genai import types as gemini_types
        
        # 標準形式からGemini形式に変換
        gemini_contents, final_system_prompt = self.convert_standard_to_gemini(
            history, system_prompt
        )
        
        # 現在の入力を追加
        if current_text_input or current_file_paths:
            parts = self._create_parts_from_input(current_text_input, current_file_paths)
            if parts:
                gemini_contents.append(gemini_types.Content(role="user", parts=parts))
        
        # 生成設定を作成
        config = self._create_generation_config(
            temperature=temperature,
            thinking_budget=thinking_budget,
            tools=tools,
            system_prompt=final_system_prompt
        )
        
        if debug_mode:
            print(f"[DEBUG] Starting stream to {model_id}")
            print(f"[DEBUG] Contents count: {len(gemini_contents)}")
        
        try:
            stream = self.client.models.generate_content_stream(
                model=model_id,
                contents=gemini_contents,
                config=config
            )
            
            for chunk in stream:
                if abort_signal and hasattr(abort_signal, 'is_set') and abort_signal.is_set():
                    print("Stream aborted by user")
                    break
                yield chunk
                
        except Exception as e:
            print(f"Gemini streaming error: {e}")
            raise
    
    def send_function_response(
        self,
        model_id: str,
        history: Dict,
        function_response_parts: List[Any],
        system_prompt: str = None,
        tools: Optional[List] = None
    ) -> Any:
        """
        Function Callの結果をAIに送信
        
        Args:
            model_id: モデルID
            history: 標準形式の履歴（tool messagesを含む）
            function_response_parts: 追加のFunction Responseパーツ（空の場合は履歴から構築）
            system_prompt: システムプロンプト
            tools: ツール定義
        
        Returns:
            AI応答
        """
        from google.genai import types as gemini_types
        
        # 標準形式からGemini形式に変換
        gemini_contents, final_system_prompt = self.convert_standard_to_gemini(
            history, system_prompt
        )
        
        # 追加のfunction_response_partsがあれば追加
        if function_response_parts:
            gemini_contents.append(gemini_types.Content(
                role="tool",
                parts=function_response_parts
            ))
        
        # 生成設定を作成
        config = self._create_generation_config(
            temperature=0.7,
            thinking_budget=None,
            tools=tools,
            system_prompt=final_system_prompt
        )
        
        # リクエストを送信
        response = self.client.models.generate_content(
            model=model_id,
            contents=gemini_contents,
            config=config
        )
        
        return response
    
    def handle_function_calls(
        self,
        response: Any,
        model_id: str,
        history: List[Dict],
        context: dict = None
    ) -> tuple:
        """
        Function Callを処理（非ストリーミング）
        
        Args:
            response: Gemini API応答
            model_id: モデルID
            history: 会話履歴
            context: 実行コンテキスト
        
        Returns:
            (最終応答, 実行結果リスト)
        """
        return response, []
    
    def handle_function_calls_stream(
        self,
        stream_response: Iterator,
        model_id: str,
        history: Dict,
        context: dict = None
    ) -> Iterator:
        """
        ストリーミング版のFunction Call処理
        
        Args:
            stream_response: ストリームイテレータ
            model_id: モデルID
            history: 標準形式の履歴
            context: 実行コンテキスト
        
        Yields:
            処理済みイベント
        """
        from google.genai import types as gemini_types
        
        tool_loader = context.get('tool_loader') if context else None
        abort_event = context.get('abort_event') if context else None
        chat_id = context.get('chat_id') if context else None
        chat_manager = context.get('chat_manager') if context else None
        system_prompt = context.get('system_prompt', '') if context else ''
        
        accumulated_text = ""
        pending_function_calls = []
        
        # ストリームを処理
        for chunk in stream_response:
            # 中断チェック
            if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                yield {'type': 'aborted', 'text': accumulated_text}
                return
            
            # テキストチャンクの処理
            if hasattr(chunk, 'text') and chunk.text:
                accumulated_text += chunk.text
                yield {'type': 'text_chunk', 'text': chunk.text, 'is_follow_up': False}
            
            # Function Callの検出
            if hasattr(chunk, 'candidates') and chunk.candidates:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        function_name = fc.name
                        args = dict(fc.args) if fc.args else {}
                        
                        tool_info = tool_loader.loaded_tools.get(function_name, {}) if tool_loader else {}
                        
                        # UIサーバーを起動
                        from tool_ui_manager import tool_ui_manager
                        try:
                            ui_info = tool_ui_manager.start_tool_ui(function_name, tool_info)
                        except Exception as e:
                            print(f"Failed to start UI server: {e}")
                            ui_info = None
                        
                        yield {
                            'type': 'function_call_start',
                            'function_name': function_name,
                            'tool_name': tool_info.get('name', function_name),
                            'args': args,
                            'ui_info': ui_info
                        }
                        
                        pending_function_calls.append({
                            'function_call': fc,
                            'function_name': function_name,
                            'args': args,
                            'tool_info': tool_info,
                            'ui_info': ui_info
                        })
        
        # Function Callsがあれば実行
        if pending_function_calls and tool_loader:
            yield {'type': 'function_execution_start', 'count': len(pending_function_calls)}
            
            execution_results = []
            function_response_parts = []
            
            for fc_info in pending_function_calls:
                function_name = fc_info['function_name']
                args = fc_info['args']
                tool_info = fc_info['tool_info']
                
                # コンテキストを準備
                enhanced_context = context.copy() if context else {}
                enhanced_context['execution_id'] = context.get('execution_id', str(time.time()))
                
                # ツールを実行
                try:
                    result = tool_loader.execute_tool(function_name, args, enhanced_context)
                except Exception as e:
                    print(f"Tool execution error: {e}")
                    result = {"success": False, "error": str(e)}
                
                execution = {
                    'tool_name': tool_info.get('name', function_name),
                    'function_name': function_name,
                    'args': args,
                    'result': result,
                    'has_ui': tool_info.get('has_ui', False),
                    'ui_info': fc_info['ui_info'],
                    'icon': tool_info.get('icon', ''),
                    'execution_id': enhanced_context.get('execution_id')
                }
                execution_results.append(execution)
                
                # Function Response Partを作成
                function_response_parts.append(
                    gemini_types.Part.from_function_response(
                        name=function_name,
                        response={"result": result}
                    )
                )
                
                yield {'type': 'function_execution_complete', 'execution': execution}
            
            # Function Responseを送信
            yield {'type': 'sending_function_response'}
            
            # 標準形式からGemini形式に変換
            gemini_contents, final_system_prompt = self.convert_standard_to_gemini(
                history, system_prompt
            )
            
            # Function Response Contentを追加
            gemini_contents.append(gemini_types.Content(
                role="tool",
                parts=function_response_parts
            ))
            
            # 生成設定
            config = self._create_generation_config(
                temperature=0.7,
                thinking_budget=None,
                tools=None,
                system_prompt=final_system_prompt
            )
            
            # 次の応答を取得（ストリーミング）
            follow_up_stream = self.client.models.generate_content_stream(
                model=model_id,
                contents=gemini_contents,
                config=config
            )
            
            follow_up_text = ""
            for chunk in follow_up_stream:
                if abort_event and hasattr(abort_event, 'is_set') and abort_event.is_set():
                    yield {'type': 'aborted', 'text': accumulated_text + follow_up_text}
                    return
                
                if hasattr(chunk, 'text') and chunk.text:
                    follow_up_text += chunk.text
                    yield {'type': 'text_chunk', 'text': chunk.text, 'is_follow_up': True}
            
            yield {
                'type': 'complete',
                'text': accumulated_text + follow_up_text,
                'executions': execution_results
            }
        else:
            yield {
                'type': 'complete',
                'text': accumulated_text,
                'executions': []
            }
    
    def extract_response_text(self, response: Any) -> str:
        """
        Gemini応答からテキストを抽出
        
        Args:
            response: Gemini API応答
        
        Returns:
            テキスト
        """
        response_text = ""
        
        if hasattr(response, 'text'):
            response_text = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text'):
                    response_text += part.text
        
        return response_text
    
    def _create_parts_from_input(self, text_input: str, file_paths: List[str]) -> List[Any]:
        """
        テキストとファイルからGemini用のPartsを作成
        
        Args:
            text_input: テキスト入力
            file_paths: ファイルパスのリスト
        
        Returns:
            Gemini Partのリスト
        """
        from google.genai import types as gemini_types
        
        parts = []
        
        # テキストを追加
        if text_input:
            parts.append(gemini_types.Part.from_text(text=text_input))
        
        # ファイルを追加
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"Warning: File not found: {file_path}")
                continue
            
            try:
                # ファイルをアップロード
                uploaded_file = self.client.files.upload(path=file_path)
                print(f"File uploaded: {uploaded_file.name}")
                
                parts.append(gemini_types.Part.from_uri(
                    file_uri=uploaded_file.uri,
                    mime_type=uploaded_file.mime_type
                ))
            except Exception as e:
                print(f"Failed to upload file {file_path}: {e}")
        
        return parts
    
    def _create_generation_config(
        self,
        temperature: float = 0.8,
        thinking_budget: Optional[int] = None,
        tools: Optional[List] = None,
        system_prompt: str = None
    ) -> Any:
        """
        生成設定を作成
        
        Args:
            temperature: 温度パラメータ
            thinking_budget: 思考予算
            tools: ツール定義
            system_prompt: システムプロンプト
        
        Returns:
            GenerateContentConfig
        """
        from google.genai import types as gemini_types
        
        config_params = {
            'temperature': temperature
        }
        
        # システムプロンプト
        if system_prompt:
            config_params['system_instruction'] = system_prompt
        
        # 思考予算の設定
        if thinking_budget and thinking_budget > 0:
            config_params['thinking_config'] = gemini_types.ThinkingConfig(
                thinking_budget=thinking_budget
            )
        
        # ツールの設定
        if tools:
            config_params['tools'] = tools
            # 手動処理のため自動実行を無効化
            config_params['automatic_function_calling'] = gemini_types.AutomaticFunctionCallingConfig(
                disable=True
            )
        
        return gemini_types.GenerateContentConfig(**config_params)
    
    def abort_streaming(self):
        """現在のストリーミングを中断"""
        pass
    
    def _merge_tools(self, tools1: List, tools2: List) -> List:
        """
        2つのツールリストをマージ（Gemini形式）
        
        Args:
            tools1: ツールリスト1
            tools2: ツールリスト2
        
        Returns:
            マージされたツールリスト
        """
        if not tools1:
            return tools2
        if not tools2:
            return tools1
        
        from google.genai import types as gemini_types
        
        merged_declarations = []
        
        for tool in tools1:
            if isinstance(tool, gemini_types.Tool):
                merged_declarations.extend(tool.function_declarations)
        
        for tool in tools2:
            if isinstance(tool, gemini_types.Tool):
                merged_declarations.extend(tool.function_declarations)
        
        if merged_declarations:
            return [gemini_types.Tool(function_declarations=merged_declarations)]
        
        return []
