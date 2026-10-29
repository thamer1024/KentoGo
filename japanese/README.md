<p align="center">
  <img src="../src/kentogo/images/app_icon.png" width="96" alt="KentoGo">
</p>

<h1 align="center">KentoGo</h1>

<p align="center"><b>自分の失敗から学ぶ：KaTrain の対局から作る囲碁の問題。</b></p>

<p align="center"><a href="../README.md">English README</a></p>

<p align="center">
  <a href="https://github.com/thamer1024/KentoGo/releases/latest"><img src="https://img.shields.io/github/v/release/thamer1024/KentoGo?label=download" alt="最新リリース"></a>
  <a href="https://github.com/thamer1024/KentoGo/releases"><img src="https://img.shields.io/github/downloads/thamer1024/KentoGo/total" alt="ダウンロード数"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue" alt="Windows と macOS">
  <a href="../LICENSE"><img src="https://img.shields.io/github/license/thamer1024/KentoGo" alt="MIT ライセンス"></a>
</p>

KentoGo は、KaTrain の対局で大きく目数を損した手を選び、もっと良い手が見つかるまで問題として繰り返し
出題します。対局の終局図を使った整地練習、KataGo の読み筋付きで棋譜を見る機能、任意で使える AI による
棋譜の解説もあります。無料のオープンソースで、Windows と macOS で動きます。KataGo は KaTrain で設定した
ものを使います。

<p align="center"><img src="../screenshots/quiz.gif" width="720" alt="自分の対局から作られた問題を解いているところ"></p>

## できること

- **悪手問題**：大きく目数を損した手が問題になります。盤上に答えを打つと、KataGo が判定します。
  問題は忘却曲線に沿って繰り返し出題されます。間違えた問題は翌日にもう一度出題され、正解するたびに
  3日、7日、14日…と間隔が延びます。決めた回数だけ続けて正解したら終わりです（初期値は少なめの2回で、
  もっと復習したいときは設定で増やせます）。間違えると回数は数え直しになります。
- **整地練習**：自分の対局の終局図を数えます。死に石を取り除き、アゲハマを埋めて地を整え、
  自分の数えた目数を確かめます。地の整え方を KentoGo に見せてもらうこともできます（参考用で、目数は合っていても
  手順に誤りがあったり、人の整地とは違う不自然なやり方になったりすることがあります）。
- **棋譜を見る**：KaTrain が選んだ手、比較用のもう一つのモデルの読み筋、それぞれの読み筋の終わりの
  地と形勢を見ながら、自分の対局を並べ直せます。
- **AI 解説（任意）**：ChatGPT、Claude、Gemini、DeepSeek などの AI に、自分の手と KaTrain が選んだ手の
  違いを、数値だけでなく文章で解説させることができます。それぞれの手のねらいや、どちらがなぜ良いかを
  説明します。KentoGo が作るプロンプトを好きな AI のチャットに貼り付けて答えを貼り戻すか、API キーを
  設定して KentoGo から直接 AI に尋ねさせることもできます。

| 悪手問題 | 整地練習 | 棋譜を見る |
| --- | --- | --- |
| <img src="../screenshots/quiz.png" width="260" alt="悪手問題"> | <img src="../screenshots/counting.png" width="260" alt="整地練習"> | <img src="../screenshots/viewer.png" width="260" alt="棋譜を見る"> |

## ダウンロード

- **Windows**：[最新のリリース](https://github.com/thamer1024/KentoGo/releases/latest)から
  `KentoGo-x.y.z-windows.exe` を入手します。1つのファイルなので、そのまま起動してください。
  （`KentoGo-x.y.z-windows.zip` は同じプログラムのフォルダ版で、起動が速くなります。）
- **macOS**：同じページから `KentoGo-x.y.z-macos.zip` を入手し、展開して KentoGo.app を開きます。
- **Linux**：ソースから起動してください（下の「ソースから起動する」）。

KataGo は含まれていません。KentoGo は [KaTrain](https://github.com/sanderland/katrain) で設定した
KataGo を使います。

KentoGo.exe には署名がありません。初めて起動したとき、Windows が「Windows によって PC が保護されました」
と表示して止めることがあります（ダウンロードした人の少ないプログラムに Microsoft Defender SmartScreen
が出すものです）。「詳細情報」を押してから「実行」を押してください。同じファイルで再び聞かれることは
ありません。

アプリには Apple の署名もありません。GitHub からダウンロードしたアプリは、初回は macOS に止められます。
右クリックから「開く」で開くか、`xattr -dr com.apple.quarantine KentoGo.app` を実行してください。

## はじめ方

1. KaTrain と KataGo を設定し、自分の対局をいくつか KaTrain で解析しておきます。
2. KentoGo を起動します。最初の起動で、KaTrain のエンジン設定を `~/.katrain/config.json` から
   写します。その設定が KaTrain のプログラムの中を指している場合（Windows の KaTrain の初期設定のように
   `katrain/` で始まるパス）は、よくある場所から KaTrain のプログラムのフォルダを探します。見つからない
   ときは、設定画面で「KaTrain のプログラムのフォルダ」を指定するか、KataGo・モデル・KataGo の設定
   ファイルのパスを直接指定してください。
3. 設定画面で SGF ファイルのフォルダを選びます。プログラム版は、別のフォルダを選ぶまでは
   `~/.kentogo/games` を使います。ソースから起動した KentoGo は、その `games` フォルダを使います
   （SGF ファイルが git に入ることはありません）。

### KaTrain での棋譜の準備

KentoGo は、KaTrain が SGF ファイルに保存した内容から問題を作ります。KaTrain で次のようにしておくと、
より良い問題になります。

1. KaTrain の「指導・分析設定」で、自分のレベルに合わせて「SGFに保存」にチェックを入れ、
   「分析結果をSGFに保存」にもチェックを入れます。
2. 終局後に、自分のマシンで快適な範囲の「着手毎の探索手数」を指定して「一局全体を深く分析」で解析させて
   から（「分析を悪手だけに限定」でも構いません）、SGF を保存します。KaTrain の読み筋がより正確に残ります。

### KentoGo での KataGo

KataGo にかかる時間はコンピューターによって大きく違います。読みの数（visits）は設定画面で変えられるほか、
☰ の「推奨設定」で自分のコンピューターの種類（GPU のない古いプロセッサーから高性能な GPU まで）を
選べます。

KataGo は KaTrain と同じく KentoGo と一緒に起動し、KentoGo を閉じるまで動き続けます。読み込み中は、
どのモデルを読み込んでいるかと、2回目の起動からはあとどのくらいかかるかをダイアログで表示します
（読み込みにかかった時間は `~/.kentogo/katago_start_times.json` に記録します）。ダイアログを閉じて先に
進むこともでき、その場合 KataGo への問い合わせは準備ができるまで待ちます。

**比較用モデルについて**：設定画面の「比較用モデルも使う」をオンにすると、標準の KataGo とは別に
もう1つ KataGo を起動します。2つがプロセッサーや GPU を分け合うため、コンピューターによっては KentoGo が
かなり遅くなり、メモリーも多く使います（KataGo はそれぞれモデルとキャッシュを持ち、数百 MB から数 GB に
なります）。オンにすると、比較用モデルの KataGo は標準の KataGo の準備ができた時点で起動し、KentoGo を
閉じるまで動き続けるので、その読み筋を KataGo の起動を待たずに出せます。KataGo を2つ動かす余裕がある
コンピューターでだけオンにしてください。

設定、回答の履歴、整地練習の結果は `~/.kentogo`（Windows では `C:\Users\<名前>\.kentogo`）に保存します。
プログラム版にはコンソールがないため、メッセージは `~/.kentogo/kentogo.log` に書き出します。

## 整地練習

対局の終局図を、日本ルールで整地します。整地が終わったら「整地終了」を押して答え合わせをし、「できた」か
「できなかった」を押すと、次の棋譜に進みます（この2つのボタンは、「整地終了」か「コンピュータの整地を
見る」の後に出ます）。画面には、そのとき使えるボタンだけが出ます。できなかった棋譜は、悪手問題と同じ
ように後日また出題されます。出題順・先に出す棋譜・復習の方法・1日の最大局数は、トップ画面の ☰ メニュー
の「整地練習設定」で変えられます（結果は設定ファイルと同じフォルダの `seichi_history.sqlite3` に保存
されます）。

1. 死に石をクリックしてください（つながった石がまとめて死に石になります。もう一度で元に戻ります）。
2. 死に石を取り上げます。盤の外にドラッグするか、「死に石を取り除く」を押します。
3. ダメ（どちらの地でもない空き点）をクリックして石で詰めます。詰めた石をもう一度クリックすると戻ります。
4. 「終局を確認して整地に入る」を押します。このときの地の目数が、整地で守る目数になります。

地と数えている点には、小さな四角が付きます。

整地に入ると、石は自由に動かせます（境界の石も）。目数は終局確認時の地を覚えているので、境界の石が
動いても変わりません。どちらの地かわからなくなった空き点は、クリックすると 黒地→白地→どちらでもない
の順に決められます。決まっていない空き点の数は右側に出ます。「コンピュータの整地を見る」は、終局確認時の
盤面から整地します（整地に入った後に動かした石は使いません）。

- 石をドラッグして空いている点に置くと動きます。
- 相手の色の石の上に置くと、2つの石が入れ替わります。
- アゲハマは下の置き場から盤にドラッグして、同じ色の地に埋めます。バラの石はまとめて、x10 は10個
  まとめて、置いた場所の空きに端から埋まります。盤の外に出すと置き場に戻ります。
- セキの目や、セキで共有しているダメは地に数えません（goscorer で判定します）。

「コンピュータの整地を見る」を押すと、整地の手順をすぐに一手ずつ再生します。そのあとも、再生ボタンや
←→ キーで手順をたどれます。最後に相手の地の中に石が残るような整地はしません。どうしても残る局面
（死に石を取り忘れたときなど）では、そう知らせて整地しません。動いた石の元の場所に △、石を置いた場所に
○ が付きます。自分の石だけでは十目単位にできないときは、「石の交換」（盤上の黒石と白石を入れ替える）を
します。碁笥を使って石の色を替えることはしません。それが必要な形にしかならないときは、きれいな形を
あきらめて、自分の地の中で石を動かして十目単位に近づけます。

コンピュータの整地はプログラムが作るものなので、参考として見てください。結果の目数は合っていても手順に
誤りがあったり、人が整地するときとは違う、不自然なやり方になったりすることがあります。

## 言語

最初の起動は英語です。悪手問題の開始画面か、トップ画面の ☰ ボタンのメニューにある国旗（KaTrain と同じ）を
押すと、すぐにその言語に切り替わり、次回の起動でもその言語で表示されます。言語は
`~/.kentogo/settings.json`（`"general": {"language": "jp"}`）に保存します。対応言語：英語、ドイツ語、
フランス語、ウクライナ語、スペイン語、ロシア語、中国語（簡体字・繁体字）、韓国語、日本語、トルコ語。

AI 解説も言語に合わせます。日本語では日本語のプロンプトを、それ以外の言語では英語のプロンプトを使い、
画面の言語で答えるように AI に頼みます。答えと一緒に KentoGo が棋譜に書き込む言葉も、その言語になります。
プロンプトはそれぞれ変更用のファイルがあります（☰ の AI 解説の設定）。設定ファイルと同じフォルダの
`commentary_prompt_jp.txt`（日本語）と `commentary_prompt_en.txt`（英語のプロンプト）です。

## ソースから起動する

1. [uv](https://docs.astral.sh/uv/) をインストールします（KentoGo のための Python 3.12 も入れます）。
2. KentoGo を入手します。このリポジトリを `git clone` するか、zip ファイルとしてダウンロードして展開します。
3. KentoGo のフォルダで、次を実行します。

   ```
   uv run kentogo
   ```

   最初の起動ではライブラリをインストールするので、時間がかかります。

## 開発（macOS または WSL）

```
uv sync                  # 環境を作る（Python 3.12 とライブラリ）
uv run pytest            # テストを実行する（KataGo は不要）
uv run ruff check        # コードを検査する
uv run ruff format       # コードを整形する
```

- すべてのシステムで同じコードです。システムによって違うのは
  `src/kentogo/katago/locate.py`（KaTrain と KataGo の場所）と
  `src/kentogo/katago/process.py`（KataGo の起動の仕方）だけです。
- WSL では、プロジェクトを `/mnt/c` の下ではなく Linux のファイルシステム（例：`~/KentoGo`）に置いて
  ください。`/mnt/c` は遅いためです。Windows 11 では WSLg でウィンドウが表示されます。そこで KataGo を
  使うには、Linux 用の KataGo を使ってください（`katago.exe` ではなく）。
- GitHub Actions が、push のたびに Windows・macOS・Linux で検査とテストを実行します
  （`.github/workflows/test.yml`）。

## プログラムを作る（KentoGo.exe と KentoGo.app）

プログラムはそれぞれのシステムで作ります（PyInstaller は macOS で Windows のプログラムを作ることも、
その逆もできません）。

- Windows：KentoGo のフォルダで、PowerShell で次を実行します。

  ```
  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
  ```

  同じファイルから、2つの形の KentoGo.exe を作ります。
  - `dist\KentoGo.exe`：すべてを1つにまとめたファイル。起動のたびに一時フォルダに展開するので、
    起動が少し遅くなります。
  - `dist\KentoGo`（中の `KentoGo.exe` を起動）、`dist\KentoGo-windows.zip` にもまとめます：
    フォルダ版で、起動が速くなります。
- macOS：KentoGo のフォルダで、次を実行します。

  ```
  bash packaging/macos/build.sh
  ```

  `dist/KentoGo.app`（開くか、アプリケーションフォルダに移します）と `dist/KentoGo-macos.zip` を作ります。
  アプリはその Mac のプロセッサー（Apple シリコンか Intel）用に作られます。自分の Mac で作ったアプリは
  そのまま開けます。
- GitHub では、「windows-exe」か「macos-app」の workflow を実行します（Actions > その workflow > Run
  workflow）。プログラムは実行結果のページからダウンロードできます。`v0.1.0` のようなタグでも実行されます。
- プログラムを公開するには、「release」の workflow を実行します（Actions > release > Run workflow）。
  選んだブランチの最後のコミットから両方のプログラムを作り、新しいリリース（Releases）に
  `KentoGo-0.1.0-windows.exe`（1ファイル）、`KentoGo-0.1.0-windows.zip`（フォルダ版）、
  `KentoGo-0.1.0-macos.zip` として置きます。バージョンは、コミットに書かれた時刻の時・分・秒です
  （00:01:00 に作ったコミットは 0.1.0、タグは `v0.1.0`）。プログラムはバージョンをトップ画面の下に表示し、
  KentoGo.exe はファイルのプロパティ（詳細）にも表示します。ソースから起動した KentoGo には表示されません。

アイコン（階段状の石の壁で黒地と白地に分かれた盤）は `packaging/icons` にあり、ウィンドウの同じアイコンは
`src/kentogo/images/app_icon.png` です。
`python tools/make_icon.py packaging/icons --window-icon src/kentogo/images/app_icon.png`
で作ります（Pillow が必要です）。

## 謝辞

KentoGo は2つのプロジェクトの上に作られています。その作者に感謝します。

- David J. Wu（lightvector）さんの [KataGo](https://github.com/lightvector/KataGo)：対局を解析し、
  答えを判定する囲碁エンジン。
- Sander Land（sanderland）さんの [KaTrain](https://github.com/sanderland/katrain)：対局を打ち、解析する
  アプリ。KentoGo はその解析を読み、見た目もそれに合わせています。

KentoGo は独立したプロジェクトです。KaTrain や KataGo の一部ではなく、その作者が推薦しているものでも
ありません。MIT ライセンスで公開しています（`LICENSE` を参照）。ほかのプロジェクトから来た部分は
`THIRD_PARTY_NOTICES.md` に載せています。

## KentoGo の作り方

作者が KentoGo を設計し（機能と構成）、その設計に沿って、作者との対話を通じて Claude Code
（Anthropic の AI コーディングツール）がコードを書きました。
