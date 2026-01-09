"""
Web検索ツール
Bingで検索し、上位サイトの情報をスクレイピングして返す
"""

import os
import re
import time
import json
import base64
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import urllib.parse

# UI設定
UI_HTML_FILE = "search_results.html"  # 使用するHTMLファイル名

TOOL_NAME = "Web検索"
TOOL_DESCRIPTION = "Bingで検索し、上位サイトの情報を取得してテキストとして返します"
TOOL_ICON = '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"></path></svg>'

# グローバル変数
screenshots_data = {}
screenshots_lock = threading.Lock()
ui_data = {
    'query': '',
    'results': [],
    'screenshots': {},
    'status': 'ready',
    'last_update': 0,
    'progress': {
        'total': 0,
        'completed': 0,
        'current_site': ''
    }
}
ui_data_lock = threading.Lock()
ui_server = None
ui_server_port = None

def get_function_declaration():
    """Gemini Function Calling用の関数定義を返す"""
    return {
        "name": "web_search",
        "description": TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索クエリ"
                },
                "max_results": {
                    "type": "integer",
                    "description": "取得する検索結果の最大数（デフォルト: 3）",
                    "default": 3
                },
                "parallel_workers": {
                    "type": "integer",
                    "description": "並列処理のワーカー数（デフォルト: 3）",
                    "default": 3
                }
            }
        }
    }

def get_settings_schema():
    """設定項目のスキーマを返す"""
    return {
        "headless": {
            "type": "boolean",
            "label": "ヘッドレスモード",
            "description": "ブラウザを非表示で実行（高速化）",
            "default": True
        },
        "timeout": {
            "type": "number",
            "label": "タイムアウト（秒）",
            "description": "各ページの読み込みタイムアウト",
            "default": 10,
            "min": 5,
            "max": 60,
            "step": 5
        },
        "scrape_images": {
            "type": "boolean",
            "label": "画像URLを収集",
            "description": "ページ内の画像URLも取得する",
            "default": True
        },
        "max_text_length": {
            "type": "number",
            "label": "最大テキスト長",
            "description": "各ページから取得する最大文字数",
            "default": 5000,
            "min": 1000,
            "max": 20000,
            "step": 1000
        },
        "capture_screenshots": {
            "type": "boolean",
            "label": "スクリーンショット取得",
            "description": "各ページのスクリーンショットを取得",
            "default": True
        }
    }

def get_ui_info():
    """UI情報を返す（tool_loaderから呼ばれる）"""
    return {
        "has_ui": True,
        "html_file": UI_HTML_FILE,
        "default_port": 6001
    }

class ToolUIHandler(BaseHTTPRequestHandler):
    """ツール専用のHTTPハンドラー"""
    
    def log_message(self, format, *args):
        """ログ出力を抑制"""
        pass
    
    def do_GET(self):
        """GETリクエストを処理"""
        parsed_path = urlparse.urlparse(self.path)
        path = parsed_path.path
        
        # Server-Sent Events エンドポイント
        if path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            # SSEでリアルタイムデータを送信
            last_update = 0
            try:
                while True:
                    with ui_data_lock:
                        if ui_data['last_update'] > last_update:
                            event_data = json.dumps(ui_data)
                            self.wfile.write(f"data: {event_data}\n\n".encode('utf-8'))
                            self.wfile.flush()
                            last_update = ui_data['last_update']
                    
                    time.sleep(0.5)  # 500ms間隔でチェック
            except (BrokenPipeError, ConnectionAbortedError):
                pass  # クライアントが切断した
        
        # ルートまたはHTMLファイルへのアクセス
        elif path == '/' or path.endswith('.html'):
            # HTMLファイルを探す
            tool_dir = Path(__file__).parent
            
            # 指定されたHTMLファイルまたはデフォルト
            if path == '/':
                html_file = tool_dir / UI_HTML_FILE
            else:
                html_file = tool_dir / path.lstrip('/')
            
            if html_file.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # ツールデータを注入
                html_content = self.inject_tool_data(html_content)
                self.wfile.write(html_content.encode('utf-8'))
            else:
                self.send_error(404, "HTML file not found")
        
        # API エンドポイント
        elif path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            with ui_data_lock:
                status_data = {
                    "status": "running",
                    "data": ui_data,
                    "screenshots_available": len(screenshots_data)
                }
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
        
        # スクリーンショット
        elif path.startswith('/screenshot/'):
            try:
                index = int(path.split('/')[-1])
                screenshot_key = f"screenshot_{index}"
                
                with screenshots_lock:
                    if screenshot_key in screenshots_data:
                        self.send_response(200)
                        self.send_header('Content-Type', 'image/png')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        img_data = base64.b64decode(screenshots_data[screenshot_key])
                        self.wfile.write(img_data)
                        return
            except:
                pass
            self.send_error(404, "Screenshot not found")
        
        else:
            self.send_error(404, "Not found")
    
    def inject_tool_data(self, html_content):
        """HTMLにツールデータを注入"""
        inject_script = f"""
        <script>
            window.TOOL_DATA = {json.dumps(ui_data)};
            window.TOOL_PORT = {ui_server_port};
        </script>
        """
        
        if '</head>' in html_content:
            html_content = html_content.replace('</head>', inject_script + '</head>')
        else:
            html_content = inject_script + html_content
        
        return html_content

def start_ui_server(port=None):
    """UIサーバーを起動"""
    global ui_server, ui_server_port
    
    if ui_server:
        return ui_server_port  # 既に起動している
    
    # 空きポートを探す
    if not port:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            port = s.getsockname()[1]
    
    try:
        ui_server = HTTPServer(('0.0.0.0', port), ToolUIHandler)
        ui_server_port = port
        
        thread = threading.Thread(
            target=ui_server.serve_forever,
            daemon=True
        )
        thread.start()
        
        print(f"Tool UI server started on port {port}")
        return port
    except Exception as e:
        print(f"Failed to start UI server: {e}")
        return None

def stop_ui_server():
    """UIサーバーを停止"""
    global ui_server, ui_server_port
    
    if ui_server:
        ui_server.shutdown()
        ui_server = None
        ui_server_port = None

def update_ui_data(key, value):
    """UIデータをリアルタイム更新"""
    global ui_data
    with ui_data_lock:
        if key == 'add_result':
            ui_data['results'].append(value)
        elif key == 'add_screenshot':
            index, data = value
            ui_data['screenshots'][f"screenshot_{index}"] = True
            screenshots_data[f"screenshot_{index}"] = data
        else:
            ui_data[key] = value
        ui_data['last_update'] = time.time()

def create_driver(headless=True):
    """Seleniumドライバーを作成"""
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # ログを抑制
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
    return driver

def search_bing(driver, query, max_results=5):
    """Bingで検索して結果のURLを取得"""
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    driver.get(search_url)
    
    # 検索結果を待つ
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#b_results")))
    
    # 検索結果のリンクを取得
    results = []
    result_elements = driver.find_elements(By.CSS_SELECTOR, "#b_results .b_algo h2 a")
    
    for element in result_elements[:max_results]:
        try:
            url = element.get_attribute("href")
            title = element.text
            if url and title:
                results.append({"url": url, "title": title})
        except:
            continue
    
    return results

def scrape_page_with_realtime_update(url, title, index, settings, message_callback):
    """個別のページをスクレイピング（リアルタイム更新付き）"""
    # 進捗を更新
    update_ui_data('progress', {
        'total': settings.get('total_sites', 0),
        'completed': index,
        'current_site': title
    })
    
    message_callback(f"[{index + 1}/{settings.get('total_sites', 0)}] {title[:30]}... をスクレイピング中")
    
    driver = None
    try:
        driver = create_driver(settings['headless'])
        driver.set_page_load_timeout(settings['timeout'])
        driver.get(url)
        
        # ページの読み込みを待つ
        WebDriverWait(driver, settings['timeout']).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # JavaScriptで動的コンテンツが読み込まれるのを少し待つ
        time.sleep(2)
        
        # スクリーンショットを取得してリアルタイム更新
        screenshot_base64 = None
        if settings.get('capture_screenshots', True):
            try:
                # ウィンドウサイズを設定
                driver.execute_script("window.scrollTo(0, 0);")
                
                # スクリーンショットを取得
                screenshot_png = driver.get_screenshot_as_png()
                screenshot_base64 = base64.b64encode(screenshot_png).decode('utf-8')
                
                # スクリーンショットをリアルタイム更新
                update_ui_data('add_screenshot', (index, screenshot_base64))
                message_callback(f"📸 {title[:30]}... のスクリーンショットを取得")
                
            except Exception as e:
                print(f"スクリーンショット取得エラー: {e}")
        
        # テキストコンテンツを取得
        text_content = []
        total_length = 0
        max_text_length = settings['max_text_length']
        
        # 主要なテキスト要素を取得
        for tag in ["h1", "h2", "h3", "p", "article", "section", "main", "div"]:
            if total_length >= max_text_length:
                break
                
            elements = driver.find_elements(By.TAG_NAME, tag)
            for element in elements:
                if total_length >= max_text_length:
                    break
                    
                try:
                    text = element.text.strip()
                    if text and len(text) > 20:  # 短すぎるテキストは除外
                        # 重複を避ける
                        if text not in text_content:
                            text_content.append(text)
                            total_length += len(text)
                except:
                    continue
        
        # 画像URLを取得
        image_urls = []
        if settings['scrape_images']:
            img_elements = driver.find_elements(By.TAG_NAME, "img")
            for img in img_elements[:30]:  # 最大30個まで
                try:
                    src = img.get_attribute("src")
                    alt = img.get_attribute("alt") or ""
                    
                    if src and src.startswith("http"):
                        # データURLや小さすぎる画像を除外
                        if not src.startswith("data:") and "1x1" not in src and "pixel" not in src.lower():
                            image_urls.append({"url": src, "alt": alt})
                except:
                    continue
        
        # テキストを結合（最大文字数まで）
        combined_text = "\n\n".join(text_content)
        if len(combined_text) > max_text_length:
            combined_text = combined_text[:max_text_length] + "..."
        
        result = {
            "index": index,
            "url": url,
            "title": title,
            "text": combined_text,
            "images": image_urls[:20],
            "text_length": len(combined_text),
            "image_count": len(image_urls),
            "screenshot": screenshot_base64,
            "success": True
        }
        
        # 結果をリアルタイム更新
        update_ui_data('add_result', result)
        message_callback(f"✅ {title[:30]}... のスクレイピング完了")
        
        return result
        
    except TimeoutException:
        result = {
            "index": index,
            "url": url,
            "title": title,
            "text": f"[タイムアウト: ページの読み込みに時間がかかりすぎました]",
            "images": [],
            "text_length": 0,
            "image_count": 0,
            "screenshot": None,
            "success": False
        }
        
        update_ui_data('add_result', result)
        message_callback(f"⏱️ {title[:30]}... がタイムアウト")
        
        return result
        
    except Exception as e:
        result = {
            "index": index,
            "url": url,
            "title": title,
            "text": f"[エラー: ページの取得に失敗しました - {str(e)}]",
            "images": [],
            "text_length": 0,
            "image_count": 0,
            "screenshot": None,
            "success": False
        }
        
        update_ui_data('add_result', result)
        message_callback(f"❌ {title[:30]}... のスクレイピング失敗")
        
        return result
        
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def execute(args: dict, context: dict) -> dict:
    """
    ツールの実行
    
    Args:
        args: AIから渡された引数
        context: 実行コンテキスト
    """
    query = args.get("query", "")
    max_results = args.get("max_results", 3)
    parallel_workers = args.get("parallel_workers", 3)
    
    if not query:
        return {
            "success": False,
            "error": "検索クエリが指定されていません"
        }
    
    # 設定を取得
    settings = context.get("settings", {})
    settings['headless'] = settings.get("headless", True)
    settings['timeout'] = settings.get("timeout", 10)
    settings['scrape_images'] = settings.get("scrape_images", True)
    settings['max_text_length'] = settings.get("max_text_length", 5000)
    settings['capture_screenshots'] = settings.get("capture_screenshots", True)
    
    # リアルタイムメッセージ
    message_callback = context.get("message_callback", lambda x: None)
    
    # グローバル変数をクリア
    global screenshots_data
    with screenshots_lock:
        screenshots_data = {}
    
    # UIデータを初期化
    update_ui_data('query', query)
    update_ui_data('results', [])
    update_ui_data('screenshots', {})
    update_ui_data('status', 'searching')
    update_ui_data('progress', {'total': 0, 'completed': 0, 'current_site': '検索中...'})
    
    # UIサーバーを起動
    ui_port = start_ui_server()
    ui_info = {}
    if ui_port:
        message_callback(f"🌐 UIサーバー起動: http://localhost:{ui_port}/")
        ui_info = {
            "ui_available": True,
            "ui_port": ui_port,
            "ui_url": f"http://localhost:{ui_port}/{UI_HTML_FILE}",
            "html_file": UI_HTML_FILE
        }
    else:
        ui_info = {"ui_available": False}
    
    driver = None
    try:
        message_callback(f"検索を開始: {query}")
        
        # Bing検索用のドライバー
        driver = create_driver(settings['headless'])
        
        # Bingで検索
        message_callback(f"Bingで「{query}」を検索中...")
        search_results = search_bing(driver, query, max_results)
        
        if not search_results:
            update_ui_data('status', 'no_results')
            return {
                "success": False,
                "error": "検索結果が見つかりませんでした",
                "ui_info": ui_info
            }
        
        message_callback(f"{len(search_results)}件の検索結果を取得しました")
        
        # 検索用ドライバーを閉じる
        driver.quit()
        driver = None
        
        # 並列スクレイピング設定
        update_ui_data('status', 'scraping')
        settings['total_sites'] = len(search_results)
        
        # 並列スクレイピング
        message_callback(f"{parallel_workers}個のワーカーで並列スクレイピングを開始...")
        
        scraped_results = []
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            # タスクを投入
            futures = []
            for i, result in enumerate(search_results):
                future = executor.submit(
                    scrape_page_with_realtime_update,
                    result["url"],
                    result["title"],
                    i,
                    settings,
                    message_callback
                )
                futures.append(future)
            
            # 結果を収集
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=settings['timeout'] * 2)
                    scraped_results.append(result)
                except Exception as e:
                    message_callback(f"スクレイピングエラー: {str(e)}")
        
        # インデックス順にソート
        scraped_results.sort(key=lambda x: x['index'])
        
        # 完了状態に更新
        update_ui_data('status', 'completed')
        update_ui_data('progress', {
            'total': len(scraped_results),
            'completed': len(scraped_results),
            'current_site': '完了'
        })
        
        message_callback(f"すべてのスクレイピングが完了しました")
        
        # 結果を整形
        all_scraped_content = []
        scraped_summary = []
        
        for i, result in enumerate(scraped_results, 1):
            page_content = f"""
================================================================================
【検索結果 {i}】
タイトル: {result['title']}
URL: {result['url']}
================================================================================

【本文コンテンツ】
{result["text"]}
"""
            
            if result["images"]:
                page_content += f"""

【画像情報】（{len(result['images'])}個）
"""
                for idx, img_info in enumerate(result["images"][:10], 1):
                    alt_text = f" - {img_info['alt']}" if img_info.get('alt') else ""
                    page_content += f"{idx}. {img_info['url']}{alt_text}\n"
                
                if len(result["images"]) > 10:
                    page_content += f"... 他 {len(result['images']) - 10} 個の画像\n"
            
            all_scraped_content.append(page_content)
            
            scraped_summary.append({
                "title": result["title"],
                "url": result["url"],
                "text_length": result.get("text_length", 0),
                "image_count": result.get("image_count", 0),
                "has_screenshot": result.get("screenshot") is not None
            })
        
        # 結果を結合
        combined_content = f"""
================================================================================
Web検索結果レポート
================================================================================
検索クエリ: {query}
検索日時: {time.strftime("%Y-%m-%d %H:%M:%S")}
取得件数: {len(scraped_summary)}件
検索エンジン: Bing
並列ワーカー数: {parallel_workers}

""" + "\n\n".join(all_scraped_content)
        
        # サマリー情報
        combined_content += f"""

================================================================================
【検索結果サマリー】
================================================================================
"""
        total_text = 0
        total_images = 0
        screenshots_count = sum(1 for s in scraped_summary if s['has_screenshot'])
        
        for i, data in enumerate(scraped_summary, 1):
            screenshot_status = "📸" if data['has_screenshot'] else "❌"
            combined_content += f"""
{i}. {data['title']}
   URL: {data['url']}
   テキスト量: {data['text_length']:,}文字
   画像数: {data['image_count']}個
   スクリーンショット: {screenshot_status}
"""
            total_text += data['text_length']
            total_images += data['image_count']
        
        combined_content += f"""
--------------------------------------------------------------------------------
合計テキスト量: {total_text:,}文字
合計画像数: {total_images}個
スクリーンショット: {screenshots_count}個
================================================================================
"""
        
        # 結果の概要テキスト（短いサマリー）
        result_summary = f"「{query}」の検索結果を{len(scraped_summary)}件取得しました。\n\n"
        for data in scraped_summary:
            result_summary += f"• {data['title'][:50]}{'...' if len(data['title']) > 50 else ''} ({data['text_length']:,}文字)\n"
        
        result_summary += f"\n合計: {total_text:,}文字のテキストと{total_images}個の画像情報を取得"
        
        message_callback(f"検索結果をAIに送信しています...")
        
        # テキストとして直接返す
        return {
            "success": True,
            "result": combined_content,  # スクレイピングしたすべての内容を含む
            "summary": result_summary,
            "scraped_count": len(scraped_summary),
            "total_text_length": len(combined_content),
            "total_images": total_images,
            "screenshots_count": screenshots_count,
            "query": query,
            "sites": [{"title": s["title"], "url": s["url"]} for s in scraped_summary],
            "ui_info": ui_info  # UI情報を追加
        }
        
    except WebDriverException as e:
        error_message = f"""
ブラウザエラーが発生しました。

エラー詳細: {str(e)}

解決方法:
1. Google Chromeがインストールされているか確認してください
2. ChromeDriverが最新版か確認してください
3. 以下のコマンドでChromeDriverをインストール/更新できます:
   pip install --upgrade selenium
   pip install webdriver-manager

それでも解決しない場合は、手動でChromeDriverをダウンロードしてください:
https://chromedriver.chromium.org/
"""
        update_ui_data('status', 'error')
        return {
            "success": False,
            "error": error_message,
            "ui_info": ui_info
        }
    except Exception as e:
        import traceback
        update_ui_data('status', 'error')
        return {
            "success": False,
            "error": f"検索実行エラー: {str(e)}\n\n詳細:\n{traceback.format_exc()}",
            "ui_info": ui_info
        }
    finally:
        if driver:
            try:
                driver.quit()
                message_callback("ブラウザを終了しました")
            except:
                pass
