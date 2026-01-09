# message_handler.py
import os
import json
import base64
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from flask import Response
import threading

# chat_manager から標準形式ヘルパーをインポート
from chat_manager import (
    create_standard_history,
    create_standard_message,
    add_message_to_history,
    get_conversation_thread,
    generate_message_id,
    generate_tool_call_id,
    get_iso_timestamp
)
from tool_ui_manager import tool_ui_manager


class MessageHandler:
    def __init__(self, ai_manager, chat_manager, prompt_loader=None, relationship_manager=None, supporter_loader=None):
        """
        メッセージハンドラーを初期化
        
        Args:
            ai_manager: AIマネージャーインスタンス
            chat_manager: チャットマネージャーインスタンス
            prompt_loader: プロンプトローダーインスタンス（オプション）
            relationship_manager: リレーションシップマネージャーインスタンス（オプション）
            supporter_loader: サポーターローダーインスタンス（オプション）
        """
        self.ai_manager = ai_manager
        self.chat_manager = chat_manager
        self.prompt_loader = prompt_loader
        self.relationship_manager = relationship_manager
        self.supporter_loader = supporter_loader
        self.current_abort_event = None
        self.is_aborted = False
        self.current_execution_id = None
    
    def _invoke_ai_for_agent(
        self,
        chat_id: str,
        message: str,
        model_id: str,
        system_prompt: str = None
    ) -> str:
        """
        AgentRuntimeから呼び出されるAI実行コールバック
        
        他のチャットのAIを起動し、応答を取得する。
        ツールは使用せず、シンプルな1ターンの会話のみ。
        
        Args:
            chat_id: 対象チャットID
            message: ユーザーメッセージ
            model_id: モデルID
            system_prompt: システムプロンプト
        
        Returns:
            AIの応答テキスト
        """
        # 履歴を読み込む
        try:
            history = self.chat_manager.load_chat_history(chat_id)
        except FileNotFoundError:
            history = create_standard_history(conversation_id=chat_id)
        
        # AIリクエストを送信（ツールなし、シンプルな応答）
        try:
            api_response = self.ai_manager.send_request(
                model_id=model_id,
                history=history,
                current_text_input=message,
                current_file_paths=[],
                system_prompt=system_prompt or self._get_default_system_prompt(),
                temperature=0.7,
                thinking_budget=None,
                tools=None,
                use_loaded_tools=False  # ツールは使用しない
            )
            
            # 応答テキストを抽出
            return self._extract_response_text(api_response)
            
        except Exception as e:
            print(f"[AgentCallback] AI呼び出しエラー: {e}")
            import traceback
            traceback.print_exc()
            return f"エラー: {str(e)}"
    
    def _create_agent_runtime(self, chat_id: str):
        """AgentRuntimeインスタンスを作成"""
        from agent_runtime import AgentRuntime
        return AgentRuntime(
            chat_manager=self.chat_manager,
            relationship_manager=self.relationship_manager,
            ai_invoke_callback=self._invoke_ai_for_agent,
            current_chat_id=chat_id
        )
    
    def _run_pre_supporters(
        self,
        active_supporters: List[str],
        context: Dict[str, Any],
        turn_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], str]:
        """
        Pre-Generation サポーターを実行
        
        Args:
            active_supporters: 有効なサポーターリスト（順序付き）
            context: 実行コンテキスト
            turn_data: turnスコープのデータ
        
        Returns:
            (修正された入力, 更新されたturn_data, コンテキスト追加文字列)
        """
        if not self.supporter_loader or not active_supporters:
            return context.get('user_input', ''), turn_data, ''
        
        modified_input = context.get('user_input', '')
        context_additions = []
        
        for supporter_name in active_supporters:
            supporter_info = self.supporter_loader.get_supporter(supporter_name)
            if not supporter_info:
                continue
            
            # timingがpre または both のサポーターのみ実行
            timing = supporter_info.get('timing', 'pre')
            if timing not in ('pre', 'both'):
                continue
            
            # コンテキストを準備
            supporter_context = {
                **context,
                'user_input': modified_input,
                'timing': 'pre',
                'turn_data': turn_data,
                'current_model_id': context.get('model', 'gemini-2.5-flash')
            }
            
            try:
                result = self.supporter_loader.execute_supporter(
                    supporter_name,
                    supporter_context,
                    self.ai_manager
                )
                
                if result.get('error'):
                    print(f"サポーターエラー ({supporter_name}): {result['error']}")
                    continue
                
                # 結果を適用
                if result.get('modified_input'):
                    modified_input = result['modified_input']
                
                if result.get('context_additions'):
                    context_additions.append(result['context_additions'])
                
                if result.get('turn_data'):
                    turn_data.update(result['turn_data'])
                
                # permanentデータは履歴に保存（後で処理）
                if result.get('permanent_data'):
                    context['_permanent_data'] = context.get('_permanent_data', {})
                    context['_permanent_data'][supporter_name] = result['permanent_data']
                    
            except Exception as e:
                print(f"サポーター実行エラー ({supporter_name}): {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return modified_input, turn_data, '\n'.join(context_additions)
    
    def _run_post_supporters(
        self,
        active_supporters: List[str],
        context: Dict[str, Any],
        ai_response: str,
        turn_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Post-Generation サポーターを実行
        
        Args:
            active_supporters: 有効なサポーターリスト（順序付き）
            context: 実行コンテキスト
            ai_response: AIの応答テキスト
            turn_data: turnスコープのデータ
        
        Returns:
            (修正された応答, 更新されたturn_data)
        """
        if not self.supporter_loader or not active_supporters:
            return ai_response, turn_data
        
        modified_response = ai_response
        
        for supporter_name in active_supporters:
            supporter_info = self.supporter_loader.get_supporter(supporter_name)
            if not supporter_info:
                continue
            
            # timingがpost または both のサポーターのみ実行
            timing = supporter_info.get('timing', 'pre')
            if timing not in ('post', 'both'):
                continue
            
            # コンテキストを準備
            supporter_context = {
                **context,
                'ai_response': modified_response,
                'timing': 'post',
                'turn_data': turn_data,
                'current_model_id': context.get('model', 'gemini-2.5-flash')
            }
            
            try:
                result = self.supporter_loader.execute_supporter(
                    supporter_name,
                    supporter_context,
                    self.ai_manager
                )
                
                if result.get('error'):
                    print(f"サポーターエラー ({supporter_name}): {result['error']}")
                    continue
                
                # 結果を適用
                if result.get('modified_response'):
                    modified_response = result['modified_response']
                
                if result.get('turn_data'):
                    turn_data.update(result['turn_data'])
                
                # permanentデータは履歴に保存
                if result.get('permanent_data'):
                    context['_permanent_data'] = context.get('_permanent_data', {})
                    context['_permanent_data'][supporter_name] = result['permanent_data']
                    
            except Exception as e:
                print(f"サポーター実行エラー ({supporter_name}): {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return modified_response, turn_data
    
    def process_message(self, chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """メッセージを処理してAI応答を取得（ReActループ対応）"""
        
        # ストリーミングモードの場合は別処理
        if payload.get('streaming', False):
            return self._handle_streaming_response_new(chat_id, payload)
        
        # 設定から max_iterations を取得
        from settings_manager import SettingsManager
        settings_manager = SettingsManager()
        user_settings = settings_manager.get_user_settings()
        max_iterations = user_settings.get('max_iterations', 15)
        debug_mode = user_settings.get('debug_mode', False)
        
        # チャットパスを取得または作成
        chat_path = self.chat_manager.find_chat_path(chat_id)
        if not chat_path:
            chat_path = Path('chats') / chat_id
            chat_path.mkdir(parents=True, exist_ok=True)
            (chat_path / 'user_input').mkdir(exist_ok=True)
        
        # 標準形式の履歴を読み込み
        try:
            history = self.chat_manager.load_chat_history(chat_id)
        except FileNotFoundError:
            history = create_standard_history(conversation_id=chat_id)
        
        # ファイル処理
        user_message = payload.get('message')
        current_file_paths, temp_files = self._process_files(user_message.get('files', []))
        
        try:
            # システムプロンプトを取得
            system_prompt = self._get_system_prompt(payload.get('prompt', 'normal_prompt'))
            
            # ユーザーメッセージを標準形式で作成
            attachments = None
            if user_message.get('files'):
                attachments = self._convert_files_to_attachments(user_message['files'])
            
            user_msg = create_standard_message(
                role="user",
                content=user_message.get('text', ''),
                parent_id=history.get('current_node'),
                attachments=attachments
            )
            history = add_message_to_history(history, user_msg)
            
            # タイトル自動生成
            if history.get('title') == '新しいチャット':
                title = user_message.get('text', '')[:30] or (
                    user_message.get('files') and user_message['files'][0]['name']
                )
                if title:
                    history['title'] = title
            
            # モデル情報を保存
            model_id = payload.get('model', 'gemini-2.5-flash')
            history['model'] = model_id
            history['platform'] = 'gemini'
            
            # コンテキスト作成
            context = self._create_context(payload, chat_path)
            context['debug_mode'] = debug_mode
            
            # AgentRuntime を作成してコンテキストに追加
            if self.relationship_manager:
                runtime = self._create_agent_runtime(chat_id)
                context['runtime'] = runtime
            
            # ツールフィルタリング
            use_loaded_tools = True
            filtered_tools = None
            active_tools = history.get('active_tools')
            
            if active_tools is not None:
                if len(active_tools) == 0:
                    use_loaded_tools = False
                else:
                    filtered_tools = self._filter_tools_by_allowlist(active_tools)
                    use_loaded_tools = False
            
            # サポーター設定を取得
            active_supporters = history.get('active_supporters', [])
            turn_data = {}  # turnスコープのデータ
            
            # 現在の入力テキストを保持
            current_text_input = user_message.get('text', '')
            
            # Pre-Generation サポーターを実行
            if active_supporters and self.supporter_loader:
                modified_input, turn_data, context_additions = self._run_pre_supporters(
                    active_supporters,
                    {
                        'user_input': current_text_input,
                        'history': history,
                        'chat_id': chat_id,
                        'model': model_id,
                        'supporter_settings': {}
                    },
                    turn_data
                )
                
                # 入力を更新
                if modified_input != current_text_input:
                    current_text_input = modified_input
                
                # システムプロンプトにコンテキスト追加
                if context_additions:
                    system_prompt = system_prompt + "\n\n" + context_additions
            
            # === ReAct ループ開始 ===
            iteration = 0
            final_response_text = ""
            api_response = None
            
            while iteration < max_iterations:
                iteration += 1
                print(f"[ReAct] イテレーション {iteration}/{max_iterations}")
                
                # API呼び出し
                api_response = self.ai_manager.send_request(
                    model_id=model_id,
                    history=history,
                    current_text_input=current_text_input if iteration == 1 else "",
                    current_file_paths=current_file_paths if iteration == 1 else [],
                    system_prompt=system_prompt,
                    temperature=0.7,
                    thinking_budget=int(payload.get('thinking_budget', 0)) or None,
                    tools=filtered_tools,
                    use_loaded_tools=use_loaded_tools,
                    debug_mode=debug_mode
                )
                
                # Function Call があるかチェック
                if self._has_function_calls(api_response):
                    # Function Call 処理
                    api_response, history = self._handle_function_calls_react(
                        api_response,
                        model_id,
                        history,
                        context,
                        chat_id,
                        system_prompt,
                        filtered_tools,
                        use_loaded_tools
                    )
                    # ループ継続（次のイテレーションでAIが再度応答）
                    continue
                else:
                    # テキスト応答 → ループ終了
                    final_response_text = self._extract_response_text(api_response)
                    break
            
            # max_iterations に達した場合
            if iteration >= max_iterations and api_response and self._has_function_calls(api_response):
                final_response_text = self._extract_response_text(api_response)
                final_response_text += "\n\n⚠️ 反復回数上限に達したため、処理を終了しました。"
            
            # Post-Generation サポーターを実行
            if active_supporters and self.supporter_loader:
                final_response_text, turn_data = self._run_post_supporters(
                    active_supporters,
                    {
                        'user_input': user_message.get('text', ''),
                        'history': history,
                        'chat_id': chat_id,
                        'model': model_id,
                        'supporter_settings': {}
                    },
                    final_response_text,
                    turn_data
                )
            
            # turnスコープのデータはここで破棄（ループ終了）
            
            # AIメッセージを標準形式で追加
            ai_msg = create_standard_message(
                role="assistant",
                content=final_response_text,
                parent_id=history.get('current_node')
            )
            history = add_message_to_history(history, ai_msg)
            
            # 保存
            self.chat_manager.save_chat_history(chat_id, history)
            
            return {
                'response': final_response_text,
                'metadata': {
                    'title': history.get('title', '新しいチャット'),
                    'is_pinned': history.get('is_pinned', False),
                    'folder': history.get('folder')
                },
                'iterations': iteration
            }
            
        finally:
            # 一時ファイルクリーンアップ
            for temp_path in temp_files:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
    
    def _handle_function_calls_react(
        self,
        response,
        model_id: str,
        history: Dict,
        context: dict,
        chat_id: str,
        system_prompt: str,
        filtered_tools,
        use_loaded_tools: bool
    ) -> tuple:
        """
        ReActループ内でのFunction Call処理（1回分）
        
        Returns:
            (次のAPIレスポンス, 更新された履歴)
        """
        function_calls = []
        ai_explanation = ""
        
        # AIの応答からFunction Callと説明を抽出
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                ai_explanation = part.text
            if hasattr(part, 'function_call') and part.function_call:
                function_calls.append(part.function_call)
        
        if not function_calls:
            return response, history
        
        print(f"[ReAct] {len(function_calls)}個の関数呼び出しを検出")
        
        # tool_callsを作成
        tool_calls_data = []
        for fc in function_calls:
            tool_call_id = generate_tool_call_id()
            tool_calls_data.append({
                'tool_call_id': tool_call_id,
                'function_name': fc.name,
                'arguments': dict(fc.args) if fc.args else {}
            })
        
        # assistantメッセージ（tool_calls付き）を追加
        assistant_msg = create_standard_message(
            role="assistant",
            content=ai_explanation if ai_explanation else None,
            parent_id=history.get('current_node'),
            tool_calls=tool_calls_data
        )
        history = add_message_to_history(history, assistant_msg)
        
        # 各ツールを実行してFunction Response Partsを作成
        function_response_parts = []
        for tc in tool_calls_data:
            function_name = tc['function_name']
            args = tc['arguments']
            
            # コンテキストを準備
            enhanced_context = {**context}
            enhanced_context['execution_id'] = str(uuid.uuid4())
            enhanced_context['chat_id'] = chat_id
            enhanced_context['chat_manager'] = self.chat_manager
            
            # ツールを実行
            try:
                result = self.ai_manager.tool_loader.execute_tool(function_name, args, enhanced_context)
            except Exception as e:
                result = {"success": False, "error": str(e)}
            
            # toolメッセージを追加
            tool_msg = create_standard_message(
                role="tool",
                content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                parent_id=history.get('current_node'),
                tool_call_id=tc['tool_call_id']
            )
            history = add_message_to_history(history, tool_msg)
            
            # Gemini用のFunction Response Partを作成
            from google.genai import types as gemini_types
            response_data = {"result": result}
            function_response_parts.append(
                gemini_types.Part.from_function_response(
                    name=function_name,
                    response=response_data
                )
            )
        
        # 次の応答を取得
        next_response = self.ai_manager.current_client.send_function_response(
            model_id=model_id,
            history=history,
            function_response_parts=function_response_parts,
            system_prompt=system_prompt,
            tools=filtered_tools if filtered_tools else (
                self.ai_manager.tool_loader.get_tools_for_provider(self.ai_manager.current_provider)
                if use_loaded_tools else None
            )
        )
        
        return next_response, history
    
    def _handle_streaming_response_new(self, chat_id: str, payload: Dict[str, Any]):
        """ストリーミング応答を処理（ReActループ対応版）"""
        
        # 中断イベントを作成
        abort_event = threading.Event()
        self.current_abort_event = abort_event
        self.is_aborted = False
        
        # 設定から max_iterations を取得
        from settings_manager import SettingsManager
        settings_manager = SettingsManager()
        user_settings = settings_manager.get_user_settings()
        max_iterations = user_settings.get('max_iterations', 15)
        debug_mode = user_settings.get('debug_mode', False)
        
        def generate():
            nonlocal abort_event
            
            try:
                user_message = payload.get('message')
                
                # 標準形式の履歴を読み込み
                try:
                    history = self.chat_manager.load_chat_history(chat_id)
                except FileNotFoundError:
                    history = create_standard_history(conversation_id=chat_id)
                
                # システムプロンプトを取得
                system_prompt = self._get_system_prompt(payload.get('prompt', 'normal_prompt'))
                
                # ファイル処理
                current_file_paths, temp_files = self._process_files(user_message.get('files', []))
                
                try:
                    # ユーザーメッセージを標準形式で追加
                    attachments = None
                    if user_message.get('files'):
                        attachments = self._convert_files_to_attachments(user_message['files'])
                    
                    user_msg = create_standard_message(
                        role="user",
                        content=user_message.get('text', ''),
                        parent_id=history.get('current_node'),
                        attachments=attachments
                    )
                    history = add_message_to_history(history, user_msg)
                    
                    # タイトル自動生成
                    if history.get('title') == '新しいチャット':
                        title = user_message.get('text', '')[:30] or '新しいチャット'
                        history['title'] = title
                        yield f"data: {json.dumps({'type': 'metadata', 'title': title})}\n\n"
                    
                    # モデル情報を保存
                    model_id = payload.get('model', 'gemini-2.5-flash')
                    history['model'] = model_id
                    history['platform'] = 'gemini'
                    
                    # 一旦保存（ユーザーメッセージ）
                    self.chat_manager.save_chat_history(chat_id, history)
                    
                    # チャットパスを取得
                    chat_path = self.chat_manager.find_chat_path(chat_id)
                    context = self._create_context(payload, chat_path)
                    context['abort_event'] = abort_event
                    context['chat_id'] = chat_id
                    context['chat_manager'] = self.chat_manager
                    context['debug_mode'] = debug_mode
                    context['system_prompt'] = system_prompt
                    context['tool_loader'] = self.ai_manager.tool_loader
                    
                    # AgentRuntime を作成してコンテキストに追加
                    if self.relationship_manager:
                        runtime = self._create_agent_runtime(chat_id)
                        context['runtime'] = runtime
                    
                    # ツールフィルタリング
                    use_loaded_tools = True
                    filtered_tools = None
                    active_tools = history.get('active_tools')
                    
                    if active_tools is not None:
                        if len(active_tools) == 0:
                            use_loaded_tools = False
                        else:
                            filtered_tools = self._filter_tools_by_allowlist(active_tools)
                            use_loaded_tools = False
                    
                    # サポーター設定を取得
                    active_supporters = history.get('active_supporters', [])
                    turn_data = {}  # turnスコープのデータ
                    
                    # 現在の入力テキストを保持
                    current_text_input = user_message.get('text', '')
                    
                    # Pre-Generation サポーターを実行
                    pre_context_additions = ''
                    if active_supporters and self.supporter_loader:
                        modified_input, turn_data, pre_context_additions = self._run_pre_supporters(
                            active_supporters,
                            {
                                'user_input': current_text_input,
                                'history': history,
                                'chat_id': chat_id,
                                'model': model_id,
                                'supporter_settings': {}
                            },
                            turn_data
                        )
                        
                        if modified_input != current_text_input:
                            current_text_input = modified_input
                        
                        if pre_context_additions:
                            system_prompt = system_prompt + "\n\n" + pre_context_additions
                    
                    # === ReAct ループ開始 ===
                    iteration = 0
                    full_text = ""
                    tool_calls_buffer = []
                    was_aborted = False
                    
                    while iteration < max_iterations:
                        iteration += 1
                        print(f"[ReAct Stream] イテレーション {iteration}/{max_iterations}")
                        
                        # イテレーション開始通知
                        if iteration > 1:
                            yield f"data: {json.dumps({'type': 'iteration_start', 'iteration': iteration, 'max_iterations': max_iterations})}\n\n"
                        
                        # ストリーミングでAI応答を取得
                        stream = self.ai_manager.send_request_stream(
                            model_id=model_id,
                            history=history,
                            current_text_input=current_text_input if iteration == 1 else "",
                            current_file_paths=current_file_paths if iteration == 1 else [],
                            system_prompt=system_prompt,
                            temperature=0.7,
                            thinking_budget=int(payload.get('thinking_budget', 0)) or None,
                            tools=filtered_tools,
                            use_loaded_tools=use_loaded_tools,
                            abort_signal=abort_event,
                            debug_mode=debug_mode
                        )
                        
                        # Function Call処理を含むストリーム処理
                        enhanced_stream = self.ai_manager.handle_function_calls_stream(
                            stream,
                            model_id=model_id,
                            history=history,
                            context=context
                        )
                        
                        iteration_text = ""
                        iteration_tool_calls = []
                        has_function_calls = False
                        
                        for event in enhanced_stream:
                            event_type = event.get('type')
                            
                            if event_type == 'aborted':
                                was_aborted = True
                                iteration_text = event.get('text', iteration_text)
                                full_text += iteration_text
                                yield f"data: {json.dumps({'type': 'aborted', 'text': full_text, 'reason': 'user_abort'})}\n\n"
                                break
                            
                            elif event_type == 'text_chunk':
                                chunk_text = event.get('text', '')
                                iteration_text += chunk_text
                                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk_text, 'is_follow_up': event.get('is_follow_up', False), 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'function_call_start':
                                has_function_calls = True
                                yield f"data: {json.dumps({'type': 'function_call_start', 'function_name': event['function_name'], 'tool_name': event['tool_name'], 'args': event['args'], 'ui_info': event.get('ui_info'), 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'tool_progress':
                                yield f"data: {json.dumps({'type': 'tool_progress', 'tool': event.get('tool', ''), 'message': event.get('message', ''), 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'function_execution_start':
                                yield f"data: {json.dumps({'type': 'tool_execution_start', 'count': event['count'], 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'function_execution_complete':
                                execution = event['execution']
                                iteration_tool_calls.append(execution)
                                tool_calls_buffer.append(execution)
                                yield f"data: {json.dumps({'type': 'tool_execution_complete', 'tool_name': execution['tool_name'], 'result_summary': str(execution['result'])[:100] if execution['result'] else '', 'has_ui': execution.get('has_ui', False), 'ui_info': execution.get('ui_info'), 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'sending_function_response':
                                yield f"data: {json.dumps({'type': 'processing_tool_results', 'iteration': iteration})}\n\n"
                            
                            elif event_type == 'complete':
                                iteration_text = event.get('text', iteration_text)
                        
                        # 中断された場合はループを抜ける
                        if was_aborted:
                            break
                        
                        # イテレーションのテキストを累積
                        full_text += iteration_text
                        
                        # ツール呼び出しがあった場合
                        if iteration_tool_calls:
                            # tool_callsを含むassistantメッセージを履歴に追加
                            tool_calls_data = []
                            for tc in iteration_tool_calls:
                                tool_call_id = generate_tool_call_id()
                                tool_calls_data.append({
                                    'tool_call_id': tool_call_id,
                                    'function_name': tc['function_name'],
                                    'arguments': tc.get('args', {}),
                                    '_result': tc.get('result')
                                })
                            
                            # assistantメッセージ（tool_calls付き）
                            assistant_tool_msg = create_standard_message(
                                role="assistant",
                                content=iteration_text if iteration_text else None,
                                parent_id=history.get('current_node'),
                                tool_calls=[{
                                    'tool_call_id': tc['tool_call_id'],
                                    'function_name': tc['function_name'],
                                    'arguments': tc['arguments']
                                } for tc in tool_calls_data]
                            )
                            history = add_message_to_history(history, assistant_tool_msg)
                            
                            # 各toolメッセージ
                            for tc in tool_calls_data:
                                result = tc['_result']
                                tool_msg = create_standard_message(
                                    role="tool",
                                    content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                                    parent_id=history.get('current_node'),
                                    tool_call_id=tc['tool_call_id']
                                )
                                history = add_message_to_history(history, tool_msg)
                            
                            # 履歴を保存
                            self.chat_manager.save_chat_history(chat_id, history)
                            
                            # ループ継続
                            continue
                        else:
                            # テキストのみの応答 → ループ終了
                            break
                    
                    # max_iterations に達した場合
                    if iteration >= max_iterations and not was_aborted:
                        warning_msg = "\n\n⚠️ 反復回数上限に達したため、処理を終了しました。"
                        full_text += warning_msg
                        yield f"data: {json.dumps({'type': 'chunk', 'text': warning_msg, 'is_system': True})}\n\n"
                    
                    # Post-Generation サポーターを実行
                    if active_supporters and self.supporter_loader and not was_aborted:
                        full_text, turn_data = self._run_post_supporters(
                            active_supporters,
                            {
                                'user_input': user_message.get('text', ''),
                                'history': history,
                                'chat_id': chat_id,
                                'model': model_id,
                                'supporter_settings': {}
                            },
                            full_text,
                            turn_data
                        )
                    
                    # 最終的なAI応答を履歴に追加
                    if not was_aborted and full_text:
                        ai_msg = create_standard_message(
                            role="assistant",
                            content=full_text,
                            parent_id=history.get('current_node')
                        )
                        history = add_message_to_history(history, ai_msg)
                    
                    # 強制停止の場合
                    if was_aborted and full_text:
                        ai_msg = create_standard_message(
                            role="assistant",
                            content=full_text,
                            parent_id=history.get('current_node'),
                            status="aborted"
                        )
                        history = add_message_to_history(history, ai_msg)
                    
                    # 最終保存
                    self.chat_manager.save_chat_history(chat_id, history)
                    
                    # 完了通知
                    yield f"data: {json.dumps({'type': 'complete' if not was_aborted else 'aborted_complete', 'full_text': full_text, 'metadata': {'title': history.get('title', '新しいチャット'), 'is_pinned': history.get('is_pinned', False), 'folder': history.get('folder')}, 'was_aborted': was_aborted, 'iterations': iteration})}\n\n"
                
                finally:
                    # 一時ファイルクリーンアップ
                    for temp_path in temp_files:
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except:
                            pass
                
            except Exception as e:
                print(f"Streaming error: {e}")
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            finally:
                self.current_abort_event = None
        
        return Response(generate(), mimetype='text/event-stream')
    
    def _handle_function_calls_new(self, response, model_id, history, context, chat_id, system_prompt):
        """Function Callを処理（標準形式対応版）- 後方互換性のため維持"""
        max_iterations = 5
        iteration = 0
        current_response = response
        
        while iteration < max_iterations:
            function_calls = []
            ai_explanation = ""
            
            # AIの応答からFunction Callと説明を抽出
            for part in current_response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    ai_explanation = part.text
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)
            
            if not function_calls:
                break
            
            print(f"\n{len(function_calls)}個の関数呼び出しを検出 (反復: {iteration + 1})")
            
            # tool_callsを作成
            tool_calls_data = []
            for fc in function_calls:
                tool_call_id = generate_tool_call_id()
                tool_calls_data.append({
                    'tool_call_id': tool_call_id,
                    'function_name': fc.name,
                    'arguments': dict(fc.args) if fc.args else {}
                })
            
            # assistantメッセージ（tool_calls付き）を追加
            assistant_msg = create_standard_message(
                role="assistant",
                content=ai_explanation if ai_explanation else None,
                parent_id=history.get('current_node'),
                tool_calls=tool_calls_data
            )
            history = add_message_to_history(history, assistant_msg)
            
            # 各ツールを実行してFunction Response Partsを作成
            function_response_parts = []
            for tc in tool_calls_data:
                function_name = tc['function_name']
                args = tc['arguments']
                
                # ツール情報を取得
                tool_info = self.ai_manager.tool_loader.loaded_tools.get(function_name, {})
                
                # コンテキストを準備
                enhanced_context = {**context}
                enhanced_context['execution_id'] = str(uuid.uuid4())
                enhanced_context['chat_id'] = chat_id
                enhanced_context['chat_manager'] = self.chat_manager
                
                # ツールを実行
                try:
                    result = self.ai_manager.tool_loader.execute_tool(function_name, args, enhanced_context)
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                
                # toolメッセージを追加
                tool_msg = create_standard_message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                    parent_id=history.get('current_node'),
                    tool_call_id=tc['tool_call_id']
                )
                history = add_message_to_history(history, tool_msg)
                
                # Gemini用のFunction Response Partを作成
                from google.genai import types as gemini_types
                response_data = {"result": result}
                function_response_parts.append(
                    gemini_types.Part.from_function_response(
                        name=function_name,
                        response=response_data
                    )
                )
            
            # 次の応答を取得
            current_response = self.ai_manager.current_client.send_function_response(
                model_id=model_id,
                history=history,
                function_response_parts=function_response_parts,
                system_prompt=system_prompt,
                tools=self.ai_manager.tool_loader.get_tools_for_provider(self.ai_manager.current_provider)
            )
            
            iteration += 1
        
        return current_response, history
    
    def abort_current_stream(self):
        """現在のストリーミングを中断"""
        if self.current_abort_event:
            self.current_abort_event.set()
            
        if self.ai_manager:
            self.ai_manager.abort_streaming()
    
    def _get_system_prompt(self, prompt_id: str, context: dict = None) -> str:
        """プロンプトローダーからシステムプロンプトを取得"""
        
        # prompt_loader が設定されている場合はそれを使用
        if self.prompt_loader is not None:
            return self.prompt_loader.get_system_prompt(prompt_id, context)
        
        # フォールバック: 従来の方法でプロンプトファイルを直接読み込む
        import importlib.util
        
        prompt_dir = Path('prompt')
        
        # 新構造: prompt/[name]/[name]_prompt.py
        # prompt_id が "normal_prompt" の場合、prompt/normal/normal_prompt.py を探す
        folder_name = prompt_id.replace('_prompt', '') if prompt_id.endswith('_prompt') else prompt_id
        new_structure_file = prompt_dir / folder_name / f'{prompt_id}.py'
        
        # 旧構造: prompt/[name]_prompt.py（後方互換性）
        old_structure_file = prompt_dir / f'{prompt_id}.py'
        
        # 新構造を優先して探す
        if new_structure_file.exists():
            prompt_file = new_structure_file
        elif old_structure_file.exists():
            prompt_file = old_structure_file
        else:
            # 見つからない場合はデフォルトプロンプトを返す
            return self._get_default_system_prompt()
        
        try:
            spec = importlib.util.spec_from_file_location(prompt_id, prompt_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # SYSTEM_PROMPT変数があればそれを使用
            if hasattr(module, 'SYSTEM_PROMPT'):
                return module.SYSTEM_PROMPT
            
            # create_promptがあれば空文字で呼び出してシステム部分を抽出
            if hasattr(module, 'create_prompt'):
                # 引数の数を確認
                import inspect
                sig = inspect.signature(module.create_prompt)
                params = list(sig.parameters.keys())
                
                if len(params) >= 2:
                    full_prompt = module.create_prompt('', context or {})
                else:
                    full_prompt = module.create_prompt('')
                
                # "## ユーザーの入力" より前の部分をシステムプロンプトとして扱う
                if '## ユーザーの入力' in full_prompt:
                    return full_prompt.split('## ユーザーの入力')[0].strip()
                return full_prompt
        except Exception as e:
            print(f"プロンプト読み込みエラー ({prompt_id}): {e}")
        
        return self._get_default_system_prompt()
    
    def _get_default_system_prompt(self) -> str:
        """デフォルトのシステムプロンプトを返す"""
        from datetime import datetime
        now = datetime.now()
        time_str = now.strftime('%Y年%m月%d日 %H時%M分')
        
        return f"""あなたは親切で知識豊富なAIアシスタントです。
現在時刻: {time_str}

質問に対して正確で分かりやすい回答を心がけてください。
"""
    
    def _convert_files_to_attachments(self, files: List[Dict]) -> List[Dict]:
        """ファイル情報を標準形式のattachmentsに変換"""
        attachments = []
        for f in files:
            file_type = f.get('type', 'application/octet-stream')
            
            if file_type.startswith('image/'):
                att_type = 'image'
            elif file_type.startswith('video/'):
                att_type = 'video'
            elif file_type.startswith('audio/'):
                att_type = 'audio'
            else:
                att_type = 'file'
            
            attachments.append({
                'type': att_type,
                'mime_type': file_type,
                'url': f.get('path', ''),
                'name': f.get('name', 'unknown')
            })
        
        return attachments
    
    def _process_files(self, files_info: List[Dict]) -> Tuple[List[str], List[str]]:
        """ファイルを処理して一時ファイルを作成"""
        current_file_paths = []
        temp_files = []
        
        for file_info in files_info:
            try:
                if 'path' in file_info and file_info['path'].startswith('data:'):
                    # Data URLからファイルデータを抽出
                    header, encoded_data = file_info['path'].split(',', 1)
                    file_data = base64.b64decode(encoded_data)
                    
                    # MIMEタイプを取得
                    mime_type = 'application/octet-stream'
                    if ';' in header:
                        mime_info = header.split(';')[0]
                        if ':' in mime_info:
                            mime_type = mime_info.split(':')[1]
                    
                    # 拡張子を決定
                    ext = self._get_file_extension(mime_type, file_info.get('name'))
                    
                    # 一時ファイル作成
                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=f"_{file_info.get('name', 'tempfile')}" if file_info.get('name') else ext
                    ) as temp_file:
                        temp_file.write(file_data)
                        current_file_paths.append(temp_file.name)
                        temp_files.append(temp_file.name)
            except Exception as e:
                print(f"Error processing file {file_info.get('name')}: {e}")
        
        return current_file_paths, temp_files
    
    def _get_file_extension(self, mime_type: str, file_name: Optional[str]) -> str:
        """MIMEタイプから拡張子を取得"""
        ext_map = {
            'text': '.txt',
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/gif': '.gif',
            'application/pdf': '.pdf',
            'application/json': '.json'
        }
        
        for key, ext in ext_map.items():
            if key in mime_type:
                return ext
        
        if file_name:
            name_parts = file_name.rsplit('.', 1)
            if len(name_parts) > 1:
                return '.' + name_parts[1]
        
        return '.bin'
    
    def _create_context(self, payload: Dict, chat_path: Path) -> Dict[str, Any]:
        """実行コンテキストを作成"""
        return {
            "model": payload.get('model', 'gemini-2.5-flash'),
            "thinking_budget": int(payload.get('thinking_budget', 0)),
            "chat_path": str(chat_path),
            "history_path": str(chat_path / 'history.json'),
            "app_path": os.path.abspath('app.py'),
            "main_port": "5000"
        }
    
    def _has_function_calls(self, response) -> bool:
        """Function Callがあるかチェック"""
        if not hasattr(response, 'candidates') or not response.candidates:
            return False
        content = response.candidates[0].content
        return any(hasattr(part, 'function_call') and part.function_call 
                  for part in content.parts)
    
    def _extract_response_text(self, api_response) -> str:
        """APIレスポンスからテキストを抽出"""
        if self.ai_manager.current_client:
            return self.ai_manager.current_client.extract_response_text(api_response)
        
        # フォールバック（Gemini形式）
        response_text = ""
        if hasattr(api_response, 'text'):
            response_text = api_response.text
        elif hasattr(api_response, 'candidates') and api_response.candidates:
            for part in api_response.candidates[0].content.parts:
                if hasattr(part, 'text'):
                    response_text += part.text
        return response_text
    
    def _filter_tools_by_allowlist(self, allowlist: List[str]) -> Optional[List]:
        """
        許可リストに基づいてツールをフィルタリング
        
        Args:
            allowlist: 許可されたツール名のリスト
        
        Returns:
            フィルタリングされたツール定義のリスト（プロバイダー形式）
        """
        if not self.ai_manager or not self.ai_manager.tool_loader:
            return None
        
        if not allowlist:
            return None
        
        # 現在のプロバイダーを取得
        provider = self.ai_manager.current_provider or 'gemini'
        
        # 全ツールを取得
        all_tools = self.ai_manager.tool_loader.get_tools_for_provider(provider)
        
        if not all_tools:
            return None
        
        # プロバイダーごとにフィルタリング方法が異なる
        if provider == 'gemini':
            return self._filter_gemini_tools(all_tools, allowlist)
        
        elif provider == 'anthropic':
            # Anthropic形式: 辞書のリスト
            filtered = [
                tool for tool in all_tools
                if isinstance(tool, dict) and tool.get('name') in allowlist
            ]
            return filtered if filtered else None
        
        elif provider == 'openai':
            # OpenAI形式: 辞書のリスト（function内にnameがある）
            filtered = [
                tool for tool in all_tools
                if isinstance(tool, dict) and 
                tool.get('function', {}).get('name') in allowlist
            ]
            return filtered if filtered else None
        
        else:
            # その他のプロバイダー: 汎用フィルタリング
            return self._filter_generic_tools(all_tools, allowlist)
    
    def _filter_gemini_tools(self, all_tools: List, allowlist: List[str]) -> Optional[List]:
        """
        Gemini形式のツールをフィルタリング
        
        Args:
            all_tools: 全ツールのリスト
            allowlist: 許可されたツール名のリスト
        
        Returns:
            フィルタリングされたツールのリスト
        """
        filtered = []
        
        # google.genai のインポートを試みる
        gemini_types = None
        try:
            from google.genai import types as gemini_types
        except ImportError:
            # google.genai が利用不可の場合は汎用フィルタリングにフォールバック
            print("[Warning] google.genai not available, using generic tool filtering")
            return self._filter_generic_tools(all_tools, allowlist)
        
        for tool in all_tools:
            # function_declarations を持つ場合（Gemini Tool オブジェクト）
            if hasattr(tool, 'function_declarations') and tool.function_declarations:
                filtered_declarations = [
                    fd for fd in tool.function_declarations
                    if hasattr(fd, 'name') and fd.name in allowlist
                ]
                if filtered_declarations:
                    try:
                        # 新しいToolオブジェクトを作成
                        filtered_tool = gemini_types.Tool(
                            function_declarations=filtered_declarations
                        )
                        filtered.append(filtered_tool)
                    except Exception as e:
                        # Tool オブジェクト作成に失敗した場合は元のツールから該当するものを追加
                        print(f"[Warning] Failed to create filtered Tool object: {e}")
                        for fd in filtered_declarations:
                            filtered.append(fd)
            
            # 辞書形式の場合
            elif isinstance(tool, dict):
                tool_name = tool.get('name')
                if tool_name and tool_name in allowlist:
                    filtered.append(tool)
            
            # FunctionDeclaration オブジェクト単体の場合
            elif hasattr(tool, 'name') and tool.name in allowlist:
                filtered.append(tool)
        
        return filtered if filtered else None
    
    def _filter_generic_tools(self, all_tools: List, allowlist: List[str]) -> Optional[List]:
        """
        汎用的なツールフィルタリング（プロバイダー非依存）
        
        Args:
            all_tools: 全ツールのリスト
            allowlist: 許可されたツール名のリスト
        
        Returns:
            フィルタリングされたツールのリスト
        """
        filtered = []
        
        for tool in all_tools:
            tool_name = None
            
            # 辞書形式
            if isinstance(tool, dict):
                tool_name = (
                    tool.get('name') or 
                    tool.get('function', {}).get('name') or
                    tool.get('function_name')
                )
            
            # オブジェクト形式（name属性を持つ）
            elif hasattr(tool, 'name'):
                tool_name = tool.name
            
            # function_declarations を持つ場合（コンテナオブジェクト）
            elif hasattr(tool, 'function_declarations'):
                # 各 function_declaration を個別にチェック
                for fd in tool.function_declarations:
                    fd_name = fd.name if hasattr(fd, 'name') else fd.get('name') if isinstance(fd, dict) else None
                    if fd_name and fd_name in allowlist:
                        filtered.append(fd)
                continue
            
            if tool_name and tool_name in allowlist:
                filtered.append(tool)
        
        return filtered if filtered else None
