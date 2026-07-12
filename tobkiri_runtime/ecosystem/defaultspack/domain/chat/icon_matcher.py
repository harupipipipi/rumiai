import re
import hashlib
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+|[\u3040-\u30ff\u3400-\u9fff]+")
_JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

TEMPLATES = [
    {
        "id": "chat",
        "keywords": "chat talk speech discussion chat message question help ask outline conversation hello greeting feedback social list topic chatroom bubble speak dialogue チャット トーク 対話 会話 雑談 相談 質問 ヘルプ 挨拶 メッセージ コミュニケーション おしゃべり",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    },
    {
        "id": "code",
        "keywords": "code program coding developer program script javascript python rust go html css compile function syntax bug dev code block software algorithm webapp frontend backend logic source typescript cpp ruby java compile build code block syntax error compiler parser web development react node rails django flask コード プログラム プログラミング 開発 デベロッパー 関数 バグ スクリプト ソースコード 実装 エンジニア 開発者",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/><line x1="14" y1="4" x2="10" y2="20"/></svg>'
    },
    {
        "id": "terminal",
        "keywords": "terminal shell bash console execution run command unix prompt process linux cli environment tool commandline executing executing shell script execute test run deploy docker git terminal prompt ターミナル コンソール コマンド 実行 シェル コマンドライン シェルスクリプト テスト デプロイ 起動",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>'
    },
    {
        "id": "database",
        "keywords": "database db sql server storage table postgresql mysql mongodb data memory redis storage query index schema records backups collection storage space warehouse data model database management sql query migration seed sync データベース テーブル クエリ レコード 保存 ストレージ データ スキーマ 接続 検索 インデックス バックアップ",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>'
    },
    {
        "id": "globe",
        "keywords": "globe world web website url internet network online domain browser navigation global search google link browse page online access connection browser address cloud web server network security proxy dns dns records domain host hosting ip address link proxy グローバル インターネット ウェブ サイト ネットワーク オンライン ブラウザ ドメイン リンク 接続 ブラウジング",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
    },
    {
        "id": "book",
        "keywords": "book doc documentation readme tutorial learn study read library education reference paper manual textbook guide literature wiki bibliography note study materials research paper article notes novel story history dictionary guide guide book standard specs specifications 本 ドキュメント 説明書 リードミー ガイド チュートリアル 勉強 学習 論文 リファレンス 資料 教科書",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'
    },
    {
        "id": "briefcase",
        "keywords": "business work brief briefcase project management job office resume career plan portfolio task manager schedule enterprise company project workspace resume recruiting hiring contract legal agreement sales pitch marketing plan presentation roadmap ビジネス 仕事 プロジェクト 管理 タスク オフィス キャリア 計画 履歴書 ワークスペース 会社 スケジュール",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>'
    },
    {
        "id": "chart",
        "keywords": "chart graph analytics analysis stats metrics data visualization dashboard report spreadsheet diagram math numbers calculation business intelligence report metrics survey dashboard user metrics conversion rate growth sales performance chart trend data analysis dataset グラフ 分析 統計 メトリクス ダッシュボード レポート 集計 データ 可視化 数値 計算 売上 推移",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>'
    },
    {
        "id": "paint",
        "keywords": "design art paint brush color creative vector sketch icon layout UI UX image canvas illustration draw mockup graphics css style theme color theme background font design logo webdesign styling component aesthetic branding illustration typography graphics assets デザイン アート ペイント カラー クリエイティブ スケッチ イラスト レイアウト 画像 テーマ 背景 スタイル ロゴ",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><circle cx="7.5" cy="10.5" r="1.5"/><circle cx="11.5" cy="7.5" r="1.5"/><circle cx="16.5" cy="9.5" r="1.5"/><circle cx="15.5" cy="14.5" r="1.5"/></svg>'
    },
    {
        "id": "music",
        "keywords": "music audio sound song play podcast mp3 voice speech wave speak volume record radio media instrument sing track album artist melody lyric noise chord speaker listener headphones mix master audio editing sound wave microphone 音楽 音楽リスト 音 曲 再聴 オーディオ サウンド ソング 再生 プレイ ボイス 声 音声 録音 歌 メロディ",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>'
    },
    {
        "id": "shopping",
        "keywords": "shopping buy cart bag checkout store price product sell checkout order deal marketplace purchase ecommerce cost payment billing money retail stripe cart item shipping delivery discount coupon inventory checkout transaction ショッピング 買い物 カート 購入 販売 注文 決済 料金 価格 店舗 商品 支払い コスト",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>'
    },
    {
        "id": "settings",
        "keywords": "settings gear configuration setup customize options control system service engine preference config tweak debug administration tool adjust properties control panel settings page environment configuration files configs build setup 設定 システム 設定画面 構成 オプション 調整 管理 コントロール カスタマイズ セットアップ 環境設定",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
    },
    {
        "id": "security",
        "keywords": "security key lock shield safe password auth crypt private protect secure login token credential secret certificate firewall hack permission privacy login flow authentication authorization jwt oauth ssh encryption decryption token keypair keys セキュリティ キー 鍵 ロック パスワード 認証 プライバシー 保護 暗号化 トークン ログイン 秘密",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.778-7.778zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>'
    },
    {
        "id": "calendar",
        "keywords": "calendar schedule date time event appointment agenda watch clock reminder history plan timeline deadline milestone scheduling organizer anniversary meet meeting call reminder clock hourglass stopwatch timer timezone カレンダー 日程 スケジュール 日付 時間 予定 期限 締め切り リマインダー タイムライン イベント 会議",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
    },
    {
        "id": "email",
        "keywords": "email mail letter message inbox envelope send receive contact post newsletter notifications correspondence mailroom newsletter subscribe sender list mailing gmail outlook メール 送信 受信 メールボックス 連絡 ニュースレター 通知 返信 宛先 添付ファイル",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>'
    },
    {
        "id": "ai",
        "keywords": "ai robot brain intelligence neural smart computer agent automation machine learning deep model LLM assistant helper automation artificial artificial intelligence copilot mind cognitive prompt engineering openai gemini claude gpt anthropic lora finetune model config weights parameters tokens inference 人工知能 脳 ニューラル ロボット エージェント 自動化 コパイロット アシスタント モデル プロンプト クラウド",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1 0-4.12 2.5 2.5 0 0 1 0-4.88 2.5 2.5 0 0 1 0-4.12A2.5 2.5 0 0 1 9.5 2z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 0-4.12 2.5 2.5 0 0 0 0-4.88 2.5 2.5 0 0 0 0-4.12A2.5 2.5 0 0 0 14.5 2z"/></svg>'
    },
    {
        "id": "write",
        "keywords": "write pencil pen edit note paper blog document post draft creative notebook author article translation translate dictionary writing diary text input compose summary transcribe transcription grammar syntax prose manuscript copywriting edit layout text document word document pdf converter 書く 執筆 編集 ノート ブログ メモ ドキュメント 翻訳 要約 下書き 記事 テキスト 作成 入力 文章",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>'
    },
    {
        "id": "search",
        "keywords": "search find query lookup magnifying glass browse scan locate seek filter inspect research check explore lookup index examine query optimization engine index log search pattern matching regex scan audit scan logs lookup table grep ripgrep 検索 調査 探す クエリ フィルタ 抽出 ログ 検査 検出 見つける チェック 履歴",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
    },
    {
        "id": "coffee",
        "keywords": "coffee tea cup cafe break rest drink warm mug morning relax food chef cafe kitchen breakfast beverage cocoa barista restaurant cafeteria snack break time chat over coffee coffee shop lounge コーヒー カフェ お茶 ドリンク 休憩 リラックス 飲み物 朝食 朝 カップ レストラン 食事",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>'
    },
    {
        "id": "cloud",
        "keywords": "cloud online backup upload download server network remote hosting saas sky drive storage network weather server cluster virtual virtualization s3 s3 bucket cloud computing aws azure gcp cloud services cloud deployment クラウド 保存 アップロード ダウンロード サーバー ネットワーク 仮想 バックアップ ストレージ ドライブ",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M18 10h-.79A7 7 0 1 0 4 10.5M4 10.5a5 5 0 0 0 8 8h6a7 7 0 0 0 0-14z"/></svg>'
    },
    {
        "id": "folder",
        "keywords": "folder file directory workspace project document store archive local repository path organization organizer collection structure library root package modules folder structure workspace file explorer tree files folders listing navigation hierarchy paths フォルダ ディレクトリ ファイル 保管 整理 パス ツリー 階層 構造 ライブラリ フォルダ構成",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    },
    {
        "id": "video",
        "keywords": "video movie media camera record film player stream youtube tv watch screen streaming recording mp4 clip animation editor clip visual editing film director lens video recording video edit camera configuration video feed stream camera capture play stop pause 動画 映像 ビデオ カメラ 録画 映画 再生 編集 配信 YouTube 画面 収録 クリップ",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>'
    },
    {
        "id": "tools",
        "keywords": "tool wrench hammer fix repair construction build developer engineer inspect utility maintenance configuration installation mechanic hardware toolbox setup fix build debug repairs maintenance task system check settings hardware tool set ツール 工具 修理 整備 調整 組み立て メンテナンス 開発 ユーティリティ ハードウェア 設置",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
    },
    {
        "id": "heart",
        "keywords": "heart health love favorite like rating medical doctor exercise care fitness donation volunteer hospital medical emergency passion romance health tracker pulse heart rate clinic healthcare diagnosis patient wellness ハート お気に入り 好き ライク 評価 健康 医療 フィットネス 脈拍 ライフ サポート 支援",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>'
    },
    {
        "id": "lightning",
        "keywords": "lightning bolt electric energy power flash fast speed run performance optimization quick zap charge battery powerup boost swift active action rush performance tuning high speed acceleration latency fast response time optimizations cache speedup load time CDN 雷 ライトニング 高速 パフォーマンス 速度 急ぎ 充電 性能 最適化 加速 バッテリー キャッシュ 対策",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
    },
    {
        "id": "bug",
        "keywords": "bug debug fix error crash exception issue logs tracking report test quality diagnostic debugging insect antivirus fail glitch troubleshoot memory leak segmentation fault stack trace error logs error report test suite failing tests bugfix fix issue logs バグ デバッグ エラー クラッシュ 不具合 修正 問題 ログ テスト 調査 障害 失敗 警告",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="8" y="2" width="8" height="14" rx="4"/><path d="M6 8h2"/><path d="M16 8h2"/><path d="M6 12h2"/><path d="M16 12h2"/><path d="M12 2v2"/><path d="M8 18c0 1.1.9 2 2 2h4c1.1 0 2-.9 2-2"/><path d="M4 5c0 3 2 5 2 5"/><path d="M20 5c0 3-2 5-2 5"/></svg>'
    },
    {
        "id": "map",
        "keywords": "map pin location address travel direction compass navigation gps destination route place geolocation geographic tracking area coordinates tour path voyage map coordinate region travel itinerary road map destination location marker directions guide travel planning マップ 地図 場所 住所 旅行 目的地 ルート 位置情報 ナビ 座標 エリア ガイド",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>'
    },
    {
        "id": "shield",
        "keywords": "shield protect defense security guard safekeeping safe locker authenticate trust privacy policy rules verify check validation rules check checks security audit guard compliance compliance check firewall policy シールド 盾 保護 防御 安全 信頼 監査 ルール 検証 許可 脆弱性 ポリシー",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    },
    {
        "id": "science",
        "keywords": "science math lab physics chemistry flask formula research biology calculation academic classroom statistic formula logic matrix equations geometry calculation mathematics algorithm statistics plotting scientific paper chart data analysis lab report 科学 数学 ラボ 物理 化学 実験 計算 数式 理科 幾何学 統計 学術 論文 分析",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><path d="M10 2v7.586a1 1 0 0 1-.293.707l-6.414 6.414A2 2 0 0 0 4.707 20h14.586a2 2 0 0 0 1.414-3.414l-6.414-6.414A1 1 0 0 1 14 9.586V2z"/><line x1="6" y1="20" x2="18" y2="20"/><line x1="8.5" y1="2" x2="15.5" y2="2"/></svg>'
    },
    {
        "id": "server",
        "keywords": "server infrastructure hosting cloud platform backend deploy network hosting devops systems microservice cluster containers docker kubernetes nodes virtualization cluster administration load balancing proxies hardware setup configuration サーバー ホスティング バックエンド デプロイ インフラ ネットワーク クラウド 仮想化 コンテナ 構築",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>'
    },
    {
        "id": "image",
        "keywords": "image picture photo graphic screenshot photography wallpaper frame poster visual art background avatar png jpeg svg media gallery album image processing thumbnail ocr visual recognition vision model vision OCR describe image describe picture 画像 写真 イラスト スクショ スクリーンショット 背景 アバター 画像処理 画像認識 ギャラリー アルバム",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-full h-full"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
    }
]

def get_vector(text):
    normalized = str(text or "").casefold()
    vector = Counter()
    for token in _TOKEN_RE.findall(normalized):
        token = token.strip(" \t\r\n.,!?()[]{}")
        if not token:
            continue
        vector[token] += 2
        if "_" in token:
            for part in token.split("_"):
                if part:
                    vector[part] += 1
        if _JA_RE.search(token):
            if len(token) <= 2:
                vector[token] += 1
            else:
                for index in range(len(token) - 1):
                    vector[token[index:index + 2]] += 1
    return vector

def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    overlap = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in overlap)
    if numerator <= 0:
        return 0.0
    left_norm = sum(value * value for value in left.values()) ** 0.5
    right_norm = sum(value * value for value in right.values()) ** 0.5
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)

def match_icon(title: str, conversation_id: str) -> dict:
    if not title or title.strip() == "New Conversation":
        # Deterministic default based on conversation_id hash
        h = int(hashlib.md5(conversation_id.encode("utf-8")).hexdigest(), 16)
        best_template = TEMPLATES[h % len(TEMPLATES)]
        return {
            "icon_id": best_template["id"],
            "icon_svg": best_template["svg"]
        }

    title_vector = get_vector(title)
    best_score = 0.0
    best_template = None

    for template in TEMPLATES:
        template_vector = get_vector(template["keywords"])
        score = cosine_similarity(title_vector, template_vector)
        if score > best_score:
            best_score = score
            best_template = template

    if best_score <= 0.0 or best_template is None:
        # Deterministic fallback based on conversation_id hash
        h = int(hashlib.md5(conversation_id.encode("utf-8")).hexdigest(), 16)
        best_template = TEMPLATES[h % len(TEMPLATES)]

    return {
        "icon_id": best_template["id"],
        "icon_svg": best_template["svg"]
    }
