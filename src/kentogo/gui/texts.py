"""The texts shown on the screens, in the chosen language, and functions that build them.

TEXTS holds the Japanese texts, which are the source of the translations. The
other languages are in kentogo/locales/<language>.json, with the same keys and
the same {values} (see LANGUAGES; the codes are KaTrain's). English is used until
another language is chosen; a text missing from a language is shown in English.

The texts use Kivy markup, such as [b]...[/b] and [color=...]...[/color].
Colored texts use light colors, so that they are easy to read on the dark
background of the panel (contrast ratio of about 4.5 or more).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from kentogo.analysis_run import AnalysisPlan, AnalysisSummary
from kentogo.common.types import Move
from kentogo.katago.estimate import Standing
from kentogo.mistakes.extract import PUNISH, SHARED
from kentogo.mistakes.problem import Problem
from kentogo.notice import Notice
from kentogo.quiz.area_change import AREAS_BEST, AREAS_PLAYED, AreaChange
from kentogo.quiz.collect import SkippedGame
from kentogo.quiz.score import Comparison, compare_with_actual
from kentogo.quiz.session import AnswerResult
from kentogo.report import RECENT, GameAverages, Recent, TodaySummary, Totals
from kentogo.review.record import AnswerRecord
from kentogo.seichi.arrangement import FillStep
from kentogo.seichi.count_check import CountCheck

# The languages, in the order of their flags (KaTrain's order, with Spanish after Ukrainian).
LANGUAGES = ("en", "de", "fr", "ua", "es", "ru", "cn", "tw", "ko", "jp", "tr")
DEFAULT_LANGUAGE = "en"
SOURCE_LANGUAGE = "jp"  # The language of TEXTS.
LOCALES_FOLDER = Path(__file__).resolve().parent.parent / "locales"
# Languages that write lists with "、" and put a full-width space between parts of a line.
_CJK_PUNCTUATION = ("jp", "cn", "tw")

TEXTS = {
    "black": "黒",
    "white": "白",
    "problem_info": "[b]{game}[/b]\n{move_number}手目　{color}番　問題 {index} / {total}",
    "punish_hint": "咎め問題：直前の相手の手は {loss}目の損",
    "shared_hint": "相手も見落とした大きな場所があります",
    "asking": "{color}番です。打つ点をクリックしてください。",
    "correct": "[color=5be37d][b]正解[/b][/color]",
    "wrong": "[color=ff8a80][b]不正解[/b][/color]",
    "not_judged": "[b]判定待ち[/b]\n{reason}",
    "evaluating": "この手の損失をKataGoで計算しています…",
    "evaluation_failed": "KataGoで計算できませんでした：{reason}",
    "no_engine": "KataGoを使えないため、この手は判定できません：{reason}",
    "comparison": "実戦 {actual:.1f}目損 → 打った手 {move} {answer:.1f}目損（{improvement:+.1f}目）\n取り戻した割合 {ratio:.0%}",
    "comparison_unknown": "実戦 {actual:.1f}目損 → 打った手 {move}（損失はわかりません）",
    "moves": "打った手 {answer}　実戦 {actual}　最善 {best}",
    # The marks have their own colors and shapes, so they can be told apart without the colors.
    "legend": "[color=6cc0ff]○打った手[/color]　[color=ff8a80]△実戦[/color]　[color=5be37d]□最善[/color]",
    "legend_compare": "　[color=d070f0]☆比較用モデル[/color]",
    "moves_compare": "　比較 {compare}",
    "compare_move_gain": "[color=d070f0]比較用モデルの手 {move}：{loss:.1f}目損（実戦より {gain:.1f}目得）[/color]",
    "compare_move_loss": "[color=d070f0]比較用モデルの手 {move}：{loss:.1f}目損（実戦より {gain:.1f}目損）[/color]",
    "sequence": "[color=f2c94c][b]表示中：{name}[/b][/color]\n{explanation}\n手順 {index} / {count}　　{step} / {total} 手目",
    "source_katrain": "最善手の手順（KaTrain）",
    "source_katago": "あなたの手の続き（KataGoの予想）",
    "source_katago_actual": "実戦の手の続き（KataGoの予想）",
    "source_katago_compare": "比較用モデルの最善手順",
    "explain_katrain": "KaTrainが棋譜に残した、この局面の最善手からの手順です。",
    "explain_katago": "あなたが打った手の後、KataGoが予想する進行です。",
    "explain_katago_actual": "実戦で打った手の後、KataGoが予想する進行です。",
    "explain_katago_compare": "比較用モデル（通常モデルなど）が考える、この局面の最善手からの手順です。",
    "switch_sequence": "手順を切り替え（Tab）",
    # Short names of the sequences, for the line that shows the order of Tab.
    "short_katrain": "棋譜(KaTrain)",
    "short_katago": "あなたの手",
    "short_katago_actual": "実戦の手",
    "short_katago_compare": "比較用モデル",
    "estimate_button": "地と形勢 (T)",
    "estimate_running": "地と形勢を計算しています…",
    "estimate_not_here": "地と形勢は、実戦以外の手順を最後の手まで進めたときに表示できます（T）。",
    "estimate_no_engine": "KataGoが使えないため、地と形勢を計算できません。",
    "estimate_failed": "地と形勢を計算できませんでした：{reason}",
    "area_button": "地の違い (D)",
    "area_played": "地の違い（D）：実戦の手 {move} の後の地　{lead}",
    "area_best": "地の違い（D）：最善手 {move} の後の地　{lead}",
    "area_change": "地の違い（D）：最善手 {best} と実戦の手 {played} で持ち主が変わる点\n{color}から見て {points}点、形勢 {gain}目",
    "area_change_no_lead": "地の違い（D）：最善手 {best} と実戦の手 {played} で持ち主が変わる点\n{color}から見て {points}点",
    "area_not_analyzed": "この問題には KentoGo の検討データがありません。棋譜を「KataGoで棋譜を解析」で解析すると見られます。",
    "area_not_answered": "地の違いは、回答した後に見られます（D）。",
    "area_failed": "地の違いを読めませんでした：{reason}",
    "standing": "形勢：{leader} {ahead:.1f}目リード（{moves}手後）\n実戦の同じ手数と比べて：{player} {gain:+.1f}目",
    "compare_running": "比較用モデルで解析しています…",
    "compare_no_sequence": "比較用モデルが手順を返しませんでした",
    "short_waiting": "{name}(考え中 {seconds}秒)",
    "short_failed": "{name}(失敗)",
    "short_offered": "{name}(選ぶと計算)",
    "sequence_order": "Tabで切替：{names}",
    "sequence_waiting": "KataGoが考えています…",
    "sequence_failed": "KataGoが計算できませんでした。",
    "sequence_offered": "選ぶと計算を始めます。",
    "notice_compare_line_failed": "比較用モデルの手順を計算できませんでした。\n\n理由：{reason}",
    "no_sequence": "推奨手順はありません",
    "ai_commentary": "【AI解説】",
    "illegal_move": "そこには打てません：{reason}",
    "no_problems": "問題がありません。\n棋譜のフォルダと出題条件を確認してください。",
    "folder_missing": "棋譜フォルダが見つかりません：\n{folder}\n「設定」で棋譜フォルダを指定し、KentoGoを起動し直してください。",
    "nothing_today": "今日の問題はありません。\n新しい問題も、今日が予定日の復習もありません。",
    "daily_done": "本日の問題は完了しました。\n1日の上限は午前0時にリセットされます。",
    "finished": "すべての問題が終わりました。",
    "back": "◀ 戻る",
    "forward": "進む ▶",
    "next_problem": "次の問題（Enter）",
    "unknown_move": "不明",
    # The start screen.
    "splash_title": "KentoGo",
    "splash_subtitle": "自分の対局の悪手から学ぶ",
    "splash_loading": "棋譜を読み込んでいます… {done} / {total}",
    "splash_preparing": "準備しています…",
    "splash_today": "今日の問題\n\n[size=22sp]新しい問題　[b]{new}[/b] 問\n復習　[b]{review}[/b] 問[/size]",
    "splash_limit": "（今日はあと最大 {left} 問）",
    "splash_stage": "段階 {index}/{count}：{threshold} 目以上損した問題（あと {left} 問）",
    "splash_only_punish": "咎め問題だけを出題します",
    "splash_skipped": "出題できない棋譜：{details}",
    "splash_show_skipped": "出題できない棋譜を見る",
    "skipped_title": "出題できない棋譜",
    "skipped_game_unknown_color": "{name}：自分の色がわからない（設定画面の「自分の名前」を確認してください）",
    "skipped_game_no_analysis": "{name}：KaTrainの分析が無い",
    "skipped_game_cannot_read": "{name}：読めない（{detail}）",
    "skipped_unknown_color": "自分の色がわからない {count}局",
    "skipped_no_analysis": "KaTrainの分析が無い {count}局",
    "skipped_cannot_read": "読めない {count}局",
    "splash_start": "始める（Enter）",
    "splash_failed": "棋譜を読み込めませんでした：{reason}",
    "history_first": "この問題：初めて",
    "history_again": "この問題：{count}回目（前回 {last}）",
    "history_correct": "[color=5be37d]正解[/color]",
    "history_wrong": "[color=ff8a80]不正解[/color]",
    "history_not_judged": "判定なし",
    # The settings screen. Labels that KaTrain also has use KaTrain's Japanese texts.
    "settings": "設定",
    "page_general": "一般・エンジン設定",
    "page_quiz": "出題・判定設定",
    "page_review": "復習設定",
    "page_seichi": "整地練習設定",
    "general_settings": "一般設定",
    "katago_settings": "KataGo設定",
    "local_engine": "ローカルエンジン",
    "read_katrain": "KaTrainから読み込む",
    "file_not_found": "ファイルがありません",
    "quiz_settings": "出題設定",
    "engine_settings": "エンジン設定",
    "judge_settings": "判定設定",
    "review_settings": "復習設定",
    "seichi_settings": "整地練習設定",
    "update_settings": "設定を更新",
    "close": "閉じる",
    "reread_title": "確認",
    "reread_question": (
        "この変更（棋譜フォルダ、または出題条件）を保存すると、次に悪手問題を始めるときに棋譜を"
        "すべて読み直します。\n棋譜は{count}局あります。多いと時間がかかります"
        "（1000局で十数秒ほど）。\n\n保存しますか？"
    ),
    "yes_save": "はい（保存する）",
    "no_cancel": "いいえ",
    "ratio_offer_raise": (
        "直近 {total} 問の平均の取り戻し率は {average}% です。\n"
        "合格ラインを {current}% から {proposed}% に上げますか？\n（完了した問題がまた出ることはありません）"
    ),
    "ratio_offer_lower": (
        "直近 {total} 問の平均の取り戻し率は {average}% です。\n"
        "合格ラインを {current}% から {proposed}% に下げますか？\n（完了した問題や過去の判定は変わりません）"
    ),
    "ratio_offer_no": "いいえ（今のまま）",
    "ok": "OK",
    "error_title": "エラー",
    # Dialogs about problems, so that the user does not need to look at the console.
    "notice_title": "お知らせ",
    "notice_settings_broken": (
        "設定ファイルを読めないため、初期設定で起動しました。\n"
        "設定画面で保存すると、設定ファイルは作り直されます。\n\n理由：{reason}"
    ),
    "notice_history_failed": (
        "解答の記録（履歴）を開けません。今回の解答は記録されず、復習も出題されません。\n\n"
        "ファイル：{path}\n理由：{reason}"
    ),
    "notice_cache_failed": (
        "問題のキャッシュを使えないため、毎回すべての棋譜を読み込みます（時間がかかります）。\n\n"
        "ファイル：{path}\n理由：{reason}"
    ),
    "notice_katago_failed": (
        "KataGoを起動できませんでした。棋譜に無い手の損失は判定できません。\n"
        "設定画面のKataGoの設定を確認してください。\n\n理由：{reason}"
    ),
    "notice_compare_failed": (
        "比較用モデルでKataGoを起動できませんでした。比較用モデルの読み筋は表示されません。\n"
        "設定画面の比較用モデルを確認してください。\n\n理由：{reason}"
    ),
    "notice_judge_fallback": "比較用モデルが動いていないため、損失はメインのモデルで計算します。",
    "notice_history_error": "解答の記録（履歴）を読み書きできませんでした。\n\n理由：{reason}",
    "settings_cancelled": "保存しませんでした。",
    "settings_invalid": "[color=ff8a80]正しくない値があります：{labels}[/color]",
    "settings_save_failed": "[color=ff8a80]保存できませんでした：{reason}[/color]",
    "katrain_read": "KaTrainの設定を読み込みました。「設定を更新」で保存されます。",
    "katrain_read_failed": "[color=ff8a80]KaTrainの設定を読めませんでした：{reason}[/color]",
    "field_katrain_config": "KaTrainの設定ファイル（config.json）",
    "field_katrain_folder": "KaTrainのプログラムフォルダ（空欄なら自動で探す）",
    "field_katago": "KataGo実行ファイル （フルパス）",
    "field_model": "KataGoモデルファイルの場所",
    "field_humanlike_model": "人間らしいモデルのパス",
    "field_config": "KataGo設定ファイルの場所",
    "field_compare_model": "比較用モデル（通常モデル）のパス",
    "field_use_compare": "比較用モデルも使う（KataGoをもう1つ起動）",
    "field_judge_model": "損失の計算に使うモデル",
    "judge_model_main": "KataGoモデル（上の欄）",
    "judge_model_compare": "比較用モデル",
    "field_games_folder": "棋譜フォルダ（空欄ならKentoGoのgamesフォルダ）",
    "field_my_names": "自分の名前（カンマ区切り）",
    "field_problems_per_game": "1局の問題数",
    "field_min_points_lost": "最低損失目数",
    "field_loss_stages": "段階出題の目数（例 20,10,5,3。空欄で使わない）",
    "field_skip_opening_moves": "序盤の除外手数",
    "field_include_undone_moves": "待ったの手も出題",
    "field_order": "出題順",
    "field_rotate": "盤を回転・反転",
    "field_use_seichi": "整地練習も使う（トップ画面にボタンを出す）",
    # The dialog at the start that asks which practice to do (when the territory counting practice is on).
    "mode_quiz": "悪手問題",
    "mode_seichi": "整地練習",
    "mode_viewer": "棋譜を見る",
    "mode_report": "成績表",
    "report_title": "成績表",
    "report_loading": "成績を集計しています…",
    "report_totals": (
        "これまで\n解いた問題 {answered}（正解 {correct}）　完了した問題 {finished}\n"
        "取り戻した目数 {recovered} 目　練習した日 {days} 日"
    ),
    "report_recent": (
        "最近 {count} 回の練習\n正答率 {rate}{rate_trend}　平均の取り戻し率 {average}{average_trend}\n"
        "（その前の {count} 回：正答率 {earlier_rate}　取り戻し率 {earlier_average}）"
    ),
    "report_recent_none": "最近の練習\nまだ記録がありません",
    "report_days_title": "練習した日ごとの成績",
    "report_chart_note": "棒の上は正答率と取り戻し率、棒の下は練習した日と解いた問題数。左が古く、右が新しい（最大 {count} 回）",
    "report_day_count": "{count} 問",
    "report_games_title": "対局ごとの悪手の数（{low} 目以上）",
    "report_games_note": (
        "自分の手を全部数えます（問題にならなかった手も含む）。棒の上は悪手の数（0 は悪手のなかった対局）、"
        "棒の下は対局した日時。左が古く、右が新しい（最大 {count} 局）"
    ),
    "legend_correct": "正答率",
    "legend_average": "平均の取り戻し率",
    "legend_pass": "点線：合格ライン {ratio}%",
    "band_top": "{low}目以上",
    "band_range": "{low}〜{high}目",
    "report_games_recent": "直近 {count} 局の平均：{latest}\n（その前の {count} 局：{earlier}）",
    "report_games_none": "まだ対局がありません",
    "trend_up": " ↑",
    "trend_down": " ↓",
    "no_value": "—",
    "today_summary_title": "今日のまとめ",
    "today_summary": "解いた問題 {answered}（正解 {correct}）\n取り戻した目数 {recovered} 目\n練習した日 {day} 日目",
    "achievement_stage_cleared": "★ {value} 目の段階をクリアしました",
    "achievement_correct_milestone": "★ 正解が通算 {value} 問になりました",
    "achievement_recovered_milestone": "★ 取り戻した目数が通算 {value} 目になりました",
    "viewer_only_ai": "AI解説のある棋譜だけ",
    "viewer_no_games": "棋譜がありません",
    "viewer_choose_game": "「棋譜を選ぶ」で棋譜を選んでください",
    "viewer_choose": "棋譜を選ぶ",
    "copy_file_name": "コピー",
    "viewer_loading_list": "棋譜の一覧を読み込んでいます…",
    "viewer_loading": "棋譜を読み込んでいます…",
    "viewer_load_failed": "棋譜を読めませんでした: {reason}",
    "viewer_start": "対局開始（全{total}手）",
    "viewer_move": "{number}手目 / 全{total}手　{color} {point}",
    "viewer_pass": "パス",
    "viewer_loss": "損失 {loss}目　最善 {best}",
    "viewer_first": "|◀ 最初",
    "viewer_last": "最後 ▶|",
    "viewer_previous_ai": "▲ 前のAI解説",
    "viewer_next_ai": "次のAI解説 ▼",
    "viewer_review": "総評",
    "viewer_no_review": "この棋譜には総評がありません",
    "open_game": "この棋譜を見る",
    "mode_commentary": "棋譜解析",
    "commentary_title": "棋譜解析（AI解説）",
    "commentary_paste": "貼り付けモード（1局ずつ）",
    "back_to_commentary": "棋譜解析のメニューに戻る",
    "commentary_no_game": "「棋譜を選ぶ」で棋譜を選んでください",
    "commentary_reading": "棋譜を読み込んでいます…",
    "commentary_my_color": "自分の手番",
    "commentary_my_rank": "自分の段級位",
    "commentary_relation": "相手",
    "color_none": "選んでください",
    "rank_kyu": "{number}級",
    "rank_dan": "{number}段",
    "rank_none": "指定なし",
    "relation_same": "同ランク",
    "relation_higher": "1つ上",
    "relation_lower": "1つ下",
    "relation_none": "指定なし",
    "commentary_make_prompt": "プロンプトを作る",
    "commentary_prompt_title": "プロンプト（コピーしてAIの画面に貼り付けてください）",
    "commentary_copy": "コピー",
    "commentary_copied": "プロンプトをコピーしました",
    "commentary_answer_title": "AIの回答（ここに貼り付けてください）",
    "commentary_apply": "反映",
    "commentary_cancel": "中止",
    "commentary_not_analyzed": "この棋譜はKaTrainで解析されていません。KaTrainでこの棋譜を開いて解析し、保存してから、もう一度選んでください。",
    "commentary_replace_question": "この棋譜にはすでにAI解説が付いています。差し替えますか？",
    "commentary_replace": "差し替える",
    "commentary_choose_color": "自分の手番を選んでください",
    "commentary_written": "棋譜に書き込みました（{moves}手目）。\n書き込む前のファイルの控え: {backup}",
    "commentary_not_written": "回答に問題があるため、書き込んでいません。直した回答を貼り付けて、もう一度「反映」を押してください。",
    "commentary_write_failed": "書き込めませんでした: {reason}",
    "commentary_read_failed": "棋譜を読めませんでした: {reason}",
    "answer_problem_not_json": "回答の中にJSONが見つかりません（{detail}）",
    "answer_problem_missing_move": "{move}手目の解説がありません",
    "answer_problem_no_summary": "総評がありません",
    "answer_problem_unknown_move": "頼んでいない{move}手目の解説は使いません",
    "answer_problem_empty_field": "{where}の「{field}」が空です",
    "answer_problem_unknown_category": "{move}手目の分類「{detail}」は決まった5種類のどれでもありません",
    "answer_summary": "総評",
    "answer_move": "{move}手目",
    "prompt_file_unreadable": "{path} を読めないため、標準のプロンプトを使います（{detail}）",
    "prompt_file_missing": "{path} に [[{section}]] がないため、その部分は標準の内容を使います",
    "prompt_file_unknown": "{path} の [[{section}]] は使われません",
    "seichi_searching": "終局まで打たれた棋譜を探しています…",
    "seichi_no_game": "終局まで打たれた棋譜がありません。\n（投了・時間切れの棋譜は整地練習に使えません）",
    "seichi_info": ("[size=22sp][b]整地練習[/b][/size]\n\n棋譜：{name}\n結果：{result}\n手数：{moves}手"),
    "seichi_no_result": "記録なし（両者のパスで終局）",
    "back_to_top": "トップ画面に戻る",
    "seichi_good": "できた",
    "seichi_bad": "できなかった",
    "seichi_progress": "今日 {number} 局目{limit}{review}",
    "seichi_progress_limit": " / 1日の上限 {limit} 局",
    "seichi_progress_review": "（復習）",
    "seichi_session_done": "本日の問題は完了しました（今日 {count} 局）。\n1日の上限は午前0時にリセットされます。上限はメニューの「整地練習設定」で変えられます。",
    "seichi_none_left": "今日整地する棋譜はもうありません（{count} 局できました）。",
    "notice_seichi_history_failed": "整地練習の記録を保存できません。結果は保存されず、復習もされません。\n{reason}",
    "seichi_undo": "一つ戻す",
    "seichi_remove_dead": "死に石を取り除く（アゲハマにする）",
    "seichi_ready": "死に石の取り上げとダメ詰めが済みました。「終局を確認して整地に入る」を押してください。",
    "seichi_not_ready": "死に石の取り上げとダメ詰めがまだです。",
    "seichi_in_seichi": (
        "整地中：石は自由に動かせます（境界の石も）。"
        "どちらの地かわからなくなった空き点は、クリックすると 黒地→白地→どちらでもない の順に決められます。"
    ),
    "seichi_confirm": "終局を確認して整地に入る",
    "seichi_finish": "整地終了",
    "seichi_counts_hidden": "地の目数は「整地終了」のあとに表示します",
    "count_result_title": "整地の結果",
    "count_passed": "正解",
    "count_failed": "間違い",
    "count_seichi_ok": "整地：正解（地は変わっていません）",
    "count_seichi_wrong": "整地：間違い（盤上の地　黒 {black}目　白 {white}目）",
    "count_prisoners_left": "　（残ったアゲハマ {count} 個を地から差し引いて数えました）",
    "count_answer": "正しい地　黒 {black}目　白 {white}目\n{result}",
    "confirm_not_ready": "先に死に石を取り上げて、ダメを詰めてください。",
    "mark_not_seichi": "地を決められるのは、終局を確認して整地に入ってからです。",
    "mark_not_empty": "地を決められるのは空き点だけです。",
    "seichi_territory_now": (
        "地　黒 [b]{black}[/b] 目　白 [b]{white}[/b] 目\n（終局確認時　黒 {confirmed_black} 目　白 {confirmed_white} 目）"
    ),
    "seichi_dead_pending": (
        "\n死に石を取り除くと：黒のアゲハマ +{black}（計 {black_total}）　白のアゲハマ +{white}（計 {white_total}）"
    ),
    "seichi_margin": "\n地＋取った石の差：{lead}（整地の前後で変わりません）\n{result}",
    "lead_black": "黒が {points} 目多い",
    "lead_white": "白が {points} 目多い",
    "lead_even": "差なし",
    "lead_komi_black": "コミ {komi} 目を入れると、黒の {points} 目勝ち",
    "lead_komi_white": "コミ {komi} 目を入れると、白の {points} 目勝ち",
    "lead_komi_even": "コミ {komi} 目を入れると、持碁",
    "seichi_undecided": "\nどちらの地か決まっていない空き点：{count} 点（クリックして決めてください）",
    "dame_not_dame": "そこはダメではありません。\n（どちらかの地の点か、石のある点です）",
    "dame_atari": "そこを先に詰めると取られてしまいます。\n（詰めるとアタリになる石があります。先に別のダメを詰めてください）",
    "auto_not_ready": "先に死に石を取り上げて、ダメを詰めてください。",
    "seichi_auto": "コンピュータの整地を見る",
    "seichi_thinking": "コンピュータが整地の手順を考えています（考え中 {seconds}秒）",
    "seichi_auto_failed": "コンピュータの整地を作れませんでした。\n\n{detail}",
    "seichi_auto_stray": "整地すると相手の地の中に石が残るため、コンピュータの整地を作れません。\n死に石が残っていないか確かめてください。",
    "seichi_steps": "整地の手順 {number} / {total}：{step}",
    "seichi_steps_start": "整地の前の盤面です。",
    "seichi_step_capture": "ダメのない{color}石 {count} 個を取り上げる（アゲハマにする）",
    "seichi_step_place": "{color}のアゲハマを {point} に置く",
    "seichi_step_move": "{color}石を △{source} から ○{target} へ動かす",
    "seichi_step_exchange": "石の色替え：△{source} の{color}石を碁笥に戻し、{new}の碁笥から{new}石を ○{target} に置く",
    "seichi_step_recolor": "石の色替え：○{point} の{color}石を碁笥に戻し、{new}の碁笥から{new}石を {point} に置く",
    "seichi_step_swap": "石の交換：△{source} の{color}石と ○{target} の{new}石を入れ替える",
    "seichi_steps_first": "最初へ",
    "seichi_steps_back": "◀ 1手戻る",
    "seichi_steps_forward": "1手進む ▶",
    "seichi_steps_last": "最後へ",
    "seichi_steps_play": "▶ 自動再生",
    "seichi_steps_stop": "■ 停止",
    "seichi_tray_B": "黒のアゲハマ（白が取った石）",
    "seichi_tray_W": "白のアゲハマ（黒が取った石）",
    "seichi_territory": "地（日本ルール、死に石を除く）　黒 [b]{black}[/b] 目　白 [b]{white}[/b] 目",
    "seichi_seki": "\nセキ（と欠け目）のため地に数えない点：{count} 点",
    "seichi_warning": "その操作はできません",
    "seichi_refused": (
        "この移動をすると、地の目数が変わってしまいます。\n\n"
        "黒 {black} 目 → {new_black} 目\n白 {white} 目 → {new_white} 目\n\n"
        "石を元の位置に戻しました。"
    ),
    "seichi_reset": "終局図に戻す",
    "field_swap_colors": "色を入れ替える",
    "field_use_katago": "KataGoで計算する",
    "field_max_visits": "分析時の最大探索手数（メインのモデル）",
    "field_compare_max_visits": "分析時の最大探索手数（比較用モデル）",
    "field_wide_root_noise": "Wide root noise (考慮する手の範囲を広げる)",
    "field_small_problem_threshold": "小さい問題の境目（目）",
    "field_pass_ratio": "合格ライン（取り戻した割合 0〜1）",
    "field_tolerance": "許容幅（目）",
    "field_max_answer_loss": "正解とする答えの損の上限（目、0 で上限なし）",
    "field_ratio_offer": "正答率に合わせて、合格ラインの上げ下げを提案する",
    "order_file_name": "ファイル名順",
    "order_newest": "新しい順",
    "order_random": "ランダム",
    "field_review_mode": "復習の方法",
    "review_mode_curve": "忘却曲線（連続正解で終了）",
    "review_mode_once": "一度正解したら終了",
    "field_review_streak": "連続正解の回数（忘却曲線のとき。0：復習しない）",
    "field_priority": "先に出す問題",
    "priority_new_first": "新しい問題",
    "priority_review_first": "間違えた問題の復習",
    "priority_mix": "Mix（復習2問→新しい問題1問）",
    "field_session_limit": "1日の最大問題数（復習を含む。午前0時にリセット。0：上限なし）",
    "field_seichi_session_limit": "1日の最大局数（午前0時にリセット。0：上限なし）",
    "field_seichi_order": "出題順",
    "seichi_order_file_name": "ファイル名順",
    "seichi_order_newest": "新しい順",
    "seichi_order_random": "ランダム",
    "field_seichi_priority": "先に出す棋譜",
    "seichi_priority_new_first": "まだ整地していない棋譜",
    "seichi_priority_review_first": "できなかった棋譜の復習",
    "seichi_priority_mix": "Mix（復習2局→新しい棋譜1局）",
    "field_seichi_review_mode": "復習の方法",
    "seichi_review_mode_curve": "忘却曲線（連続でできたら終了）",
    "seichi_review_mode_once": "一度できたら終了",
    "field_seichi_review_streak": "連続でできた回数（忘却曲線のとき。0：復習しない）",
    "exclude_all": "今ある問題をすべて対象外にする",
    "include_all": "すべての問題を対象に戻す",
    "exclude_question": (
        "棋譜フォルダにある今の問題を、すべて回答済み（対象外）にします。\n"
        "このあと増えた棋譜の問題は出題されます。\n\n実行しますか？"
    ),
    "include_question": (
        "対象外にした問題も、正解して終わった問題も、すべて新しい問題として出題し直します。\n"
        "回答の記録は消えません。\n\n実行しますか？"
    ),
    "yes_run": "はい（実行する）",
    "working": "処理しています…",
    "excluded_done": "[color=5be37d]{count}問を対象外にしました。[/color]次に悪手問題を始めるときから反映されます。",
    "included_done": "[color=5be37d]すべての問題を対象に戻しました。[/color]次に悪手問題を始めるときから反映されます。",
    "action_failed": "[color=ff8a80]実行できませんでした：{reason}[/color]",
    "notice_language_not_saved": "言語の設定を保存できませんでした。次の起動では前の言語に戻ります。\n\n理由：{reason}",
    "ai_review": "【AI総評】",
    "field_decided_winrate": "勝負が決まったとみなす勝率（%）",
    "field_decided_lead": "勝負が決まったとみなす目差（これを超える）",
    "page_commentary": "AI解説（Claude・ChatGPTなどの文章）",
    "page_analysis": "KataGo棋譜解析（SGFに書き込む）",
    "analysis_settings": "解析",
    "reanalysis_settings": "解析し直す",
    "analysis_comment_settings": "棋譜に書くコメント",
    "analysis_settings_hint": "KataGoで棋譜を解析し、KaTrainでも開ける形で解析データとコメントを棋譜に書き込みます。元の棋譜は先にバックアップします。損失は、打つ前の局面で最善手と比べて出します（KaTrainの方法とは違います。KaTrainと同じ解析が欲しいときはKaTrainで解析してください）。",
    "field_analysis_games_folder": "解析する棋譜のフォルダ（空：出題と同じ）",
    "field_analysis_backup_folder": "元の棋譜のバックアップ先（空：棋譜フォルダの backup）",
    "field_analysis_fast": "最初は高速解析で読む",
    "field_fast_visits": "高速解析の探索数",
    "field_deep_visits": "深く検討する手の探索数（0：エンジンの探索数と同じ）",
    "field_settle_radius": "一段落の判定：打った手の周りの広さ（路）",
    "field_settle_change": "一段落の判定：地の色の変化がこれより小さい（0：使わない）",
    "field_settle_step": "一段落の判定：何手ずつ進めて読むか",
    "field_settle_max_moves": "一段落までの手順の最長（手）",
    "field_reanalyze": "解析し直す（KaTrainの「棋譜を再解析」）",
    "field_reanalyze_visits": "解析し直す探索数（0：前回の探索数＋エンジンの探索数）",
    "field_mistakes_only": "悪手だけを解析し直す",
    "field_move_from": "解析し直す最初の手（0：最初から）",
    "field_move_to": "解析し直す最後の手（0：最後まで）",
    "field_reanalyze_threshold": "解析し直す悪手の損失（目）",
    "field_retries": "失敗した局面をやり直す回数",
    "field_analysis_language": "コメントの言語",
    "field_eval_show_ai": "AIの手にもコメントを付ける",
    "field_save_marks": "最善手に印（×・□）を付ける",
    "analyze_games_button": "KataGoで棋譜を解析",
    "analysis_title": "棋譜の解析",
    "analysis_starting": "KataGoを準備しています…",
    "analysis_game": "{number} / {total}　{name}",
    "analysis_step_first": "解析　{done} / {total} 局面",
    "analysis_step_again": "解析し直し　{done} / {total} 局面",
    "analysis_step_played": "打った手の読み直し　{done} / {total} 局面",
    "analysis_step_deep": "深い読み　{done} / {total} 局面",
    "analysis_step_tenuki": "手抜きの読み　{done} / {total} 局面",
    "analysis_step_lines": "一段落までの読み　{done} / {total} 手順",
    "analysis_step_end": "最後の局面の読み　{done} / {total} 局面",
    "analysis_outcome_written": "書き込みました：{name}",
    "analysis_outcome_skipped": "解析済みのため飛ばしました：{name}",
    "analysis_outcome_failed": "失敗しました：{name}（{detail}）",
    "analysis_outcome_incomplete": "書き込みました（解析できなかった局面があります）：{name}",
    "analysis_stop": "中止",
    "analysis_stopping": "この棋譜が終わったら止めます…",
    "analysis_summary": "終わりました：書き込み {written} 局、解析済み {skipped} 局、失敗 {failed} 局",
    "analysis_summary_stopped": "中止しました：書き込み {written} 局、解析済み {skipped} 局、失敗 {failed} 局",
    "analysis_problem": "解析できません：{reason}",
    "analysis_page_intro": "[b]このページは、KataGo（囲碁AIエンジン）で棋譜を読み、損失目数などの解析データとコメントをSGFファイルに書き込む設定です。[/b]Claude・ChatGPTなどの言語AIが文章で解説する設定は「AI解説」のページです。",
    "commentary_page_intro": "[b]このページは、Claude・ChatGPTなどの言語AIが問題の局面を文章で解説する設定です。[/b]KataGoで棋譜を解析してSGFファイルに書き込む設定は「KataGo棋譜解析」のページです。",
    "analysis_counting": "棋譜を数えています…",
    "analysis_confirm": "{folder} の {count} 局をKataGoで解析し、解析データとコメントを棋譜に書き込みます（上書きします）。\n元の棋譜は先に {backup} にコピーします。",
    "analysis_confirm_skip": "全部で {games} 局のうち、解析済みの {analyzed} 局は飛ばします。",
    "analysis_confirm_again": "「解析し直す」がオンなので、解析済みの {analyzed} 局も解析し直します。",
    "analysis_confirm_question": "始めますか？",
    "analysis_start": "はい（解析を始める）",
    "analysis_no_folder_set": "解析する棋譜のフォルダが設定されていません。",
    "analysis_no_folder": "解析する棋譜のフォルダがありません：{folder}",
    "analysis_no_games": "{folder} にSGFファイルがありません。",
    "analysis_all_analyzed": "{folder} の {games} 局はすべて解析済みです。解析し直すときは「解析し直す」をオンにしてください。",
    "analysis_kentogo_question": "KataGoで解析済みです（{count} 局。KentoGoの方法の解析ではありません）。KentoGo用にもう一度解析しますか？\n「はい」にすると、解析済みのデータはそのまま使い、打った手をKentoGoの方法で読み足して書き込みます。",
    "analysis_kentogo_yes": "はい（KentoGo用に解析する）",
    "analysis_kentogo_no": "いいえ（飛ばす）",
    "analysis_confirm_kentogo": "KataGoで解析済みの {count} 局は、KentoGo用に打った手を読み足して書き込みます。",
    "field_problem_kind": "出題する問題",
    "problem_kind_all": "すべての問題",
    "problem_kind_punish": "咎め問題だけ",
    "field_punish_opponent_loss": "咎め問題：直前の相手の手の損失（目）",
    "field_punish_my_loss": "咎め問題：自分の手の損失（目）",
    "analysis_language_cn": "中国語（簡体字）",
    "analysis_language_de": "ドイツ語",
    "analysis_language_en": "英語",
    "analysis_language_es": "スペイン語",
    "analysis_language_fr": "フランス語",
    "analysis_language_jp": "日本語",
    "analysis_language_ko": "韓国語",
    "analysis_language_ru": "ロシア語",
    "analysis_language_tr": "トルコ語",
    "analysis_language_tw": "中国語（繁体字）",
    "analysis_language_ua": "ウクライナ語",
    "commentary_settings": "AI解説設定",
    "field_ai_provider": "AIの種類（API）",
    "ai_provider_anthropic": "Claude（Anthropic）",
    "ai_provider_openai_compatible": "OpenAI互換（ChatGPT・Geminiなど）",
    "field_ai_model": "モデル名",
    "field_ai_base_url": "APIのアドレス（空欄で標準）",
    "field_ai_api_key_env": "APIキーの環境変数名",
    "field_ai_max_tokens": "回答の最大トークン数",
    "commentary_settings_hint": "AIの種類・モデル名・アドレスは、各AIが公開している値をそのまま入力してください（入力した値をそのまま使います）。\n例　Claude: 種類 Claude（Anthropic）、モデル名 claude-sonnet-5-5、アドレス 空欄、環境変数 ANTHROPIC_API_KEY\n例　ChatGPT: 種類 OpenAI互換、アドレス 空欄、環境変数 OPENAI_API_KEY\n例　Gemini: 種類 OpenAI互換、アドレス https://generativelanguage.googleapis.com/v1beta/openai/、環境変数 GEMINI_API_KEY\n例　DeepSeek: 種類 OpenAI互換、アドレス https://api.deepseek.com、環境変数 DEEPSEEK_API_KEY\n例　Ollama: 種類 OpenAI互換、アドレス http://localhost:11434/v1\nAPIキーそのものは保存しません。環境変数に設定してからKentoGoを起動してください。\nAIのAPIを使うには、`uv sync --extra ai` でパッケージを入れておく必要があります。",
    "commentary_edit_prompt": "プロンプトファイルを開く",
    "commentary_prompt_opened": "プロンプトファイルを開きました: {path}",
    "commentary_prompt_open_failed": "プロンプトファイルを開けませんでした: {reason}",
    "commentary_api": "APIモード（1局ずつ）",
    "commentary_batch": "APIモード（新しい棋譜をまとめて）",
    "commentary_run": "AIに解説させる",
    "commentary_stop": "中止",
    "commentary_answer_stream": "AIの回答",
    "commentary_asking": "{model} に問い合わせています…",
    "commentary_tokens": "入力 {input} トークン / 出力 {output} トークン",
    "commentary_truncated": "回答が最大トークン数で途切れました。「AI解説設定」の「回答の最大トークン数」を増やしてください。",
    "commentary_backup": "書き込む前のファイルの控え: {backup}",
    "commentary_players": "黒 {black} / 白 {white}　{result}",
    "commentary_status_done": "書き込みました",
    "commentary_status_not_analyzed": "KaTrain未解析",
    "commentary_status_nothing": "解説する手がありません（悪手問題の条件に合う手がありません）",
    "commentary_status_failed": "失敗: {detail}",
    "commentary_status_bad_answer": "回答に問題があり書き込んでいません",
    "commentary_status_cancelled": "中止しました",
    "commentary_status_waiting": "待機中",
    "commentary_status_running": "解説中…",
    "provider_error_no_package": "AIのAPIを使うパッケージが入っていません。`uv sync --extra ai` を実行してください。",
    "provider_error_no_key": "環境変数 {env} にAPIキーが設定されていません。設定してからKentoGoを起動し直してください。",
    "provider_error_authentication": "APIキーが正しくありません（{detail}）",
    "provider_error_credit": "AIのクレジット（残高）がありません（{detail}）",
    "provider_error_permission": "このAPIキーではこのモデルを使えません（{detail}）",
    "provider_error_not_found": "モデルまたはアドレスが見つかりません。「AI解説設定」のモデル名とアドレスを確認してください（{detail}）",
    "provider_error_rate_limit": "問い合わせが多すぎるか、利用上限に達しました。しばらく待ってから試してください（{detail}）",
    "provider_error_overloaded": "AIが混み合っているか、問題が起きています。しばらく待ってから試してください（{detail}）",
    "provider_error_connection": "AIにつながりません。ネット接続を確認してください（{detail}）",
    "provider_error_other": "AIに問い合わせられませんでした（{detail}）",
    "commentary_batch_loading": "新しい棋譜を探しています…",
    "commentary_batch_empty": "解説する新しい棋譜はありません",
    "commentary_batch_count": "新しい棋譜 {count} 局（チェックした棋譜を上から順に解説します）",
    "commentary_exclude": "除外",
    "commentary_since_title": "初めての実行",
    "commentary_since_question": "いつ以降に変更された棋譜を一覧に出しますか？",
    "since_week": "1週間",
    "since_month": "1か月",
    "since_three_months": "3か月",
    "since_all": "すべて",
    "since_date": "日付を指定",
    "commentary_since_date_question": "日付を入力してください（例 2026-10-01）。その日以降に変更された棋譜を一覧に出します。",
    "commentary_since_date_wrong": "日付を読めません: {reason}",
    "commentary_batch_none_checked": "解説する棋譜にチェックを付けてください",
    "commentary_batch_progress": "{number} / {total} 局目: {name}",
    "commentary_batch_finished": "終わりました（書き込み {done} 局 / {total} 局）",
    "cancel": "キャンセル",
    "viewer_variations": "この手の代わりの手順が {count} つあります（Tab：予想進行に切替）",
    "viewer_no_variations": "この手には予想進行がありません",
    "viewer_variation_moves": "{number}手目の代わり：{moves}",
    "viewer_switch": "進行切替（Tab）",
    "viewer_main_line": "本譜に戻る（Esc）",
    "source_sgf_branch": "棋譜の分岐",
    "short_sgf_branch": "分岐",
    "explain_sgf_branch": "棋譜に保存されている、この手の代わりの変化です（KaTrainが待ったで戻した手や、自分で検討した手）。",
    # The words written into the SGF file with the AI's answer (see commentary.language.CommentLabels).
    "comment_bullet": "・",
    "comment_situation": "局面",
    "comment_category": "分類",
    "comment_what_happened": "何が起きたか",
    "comment_aim": "最善手と予想手順の狙い",
    "comment_lesson": "教訓",
    "comment_category_counts": "分類の集計",
    "comment_main_issue": "一番の課題",
    "comment_next_focus": "次の対局で意識すること",
    "comment_loss_comparison": "損失の回数",
    "comment_move_line": "({played} {move} → 最善 {best},損失 {loss}目)",
    "comment_actual": "実戦",
    "comment_taken_back": "待ったの手",
    "comment_no_best": "記載なし",
    "comment_review_title": "損失目数が大きい上位{count}手を特定しました.",
    "comment_review_move": " - 第 {number} 手目 ({color}{taken_back}) (損失: {loss}目 / 最善手: {best})",
    "comment_loss_title": "■ この対局の損失の回数",
    "comment_loss_note": "(KaTrainの損失目数で数えた,この対局のあなたの手の回数.形勢が決まった後の手も含みます)",
    "comment_loss_line": "{size}目以上: {count}回{targets}",
    "comment_loss_targets": "(目標 {goal}回,超えてはいけない {limit}回)",
    "comment_no_targets": "({rank}の行が目標表に無いため,目標との比較はありません)",
    "comment_no_rank": "段級位",
    "comment_category_missed_urgent_point": "急場の見逃し",
    "comment_category_no_pressure": "響かない手",
    "comment_category_misjudged_size": "大きさの判断ミス",
    "comment_category_misread": "読み違い",
    "comment_category_wrong_direction": "方向違い",
    # The recommended settings for each kind of computer (see katago.presets).
    "field_estimate_visits": "地と形勢の探索手数",
    "field_ready_timeout": "KataGoの準備を待つ最長時間（秒）",
    "page_presets": "推奨設定",
    "presets_hint": "下の中から使用しているマシンを選んでください。推奨値を設定します。不明な場合は最下段の測るボタンを押して下さい。GPUのないパソコンや「Mac・標準」の段では、tf3などの大きいモデルは時間がかかります。b18などの軽いモデルをお勧めします。",
    "preset_cpu_old": "GPUなし・古いCPU",
    "preset_cpu_old_examples": "例：Intel Core 第4〜7世代（Core i5-4590、i7-6700、i5-7200U など）、Celeron、Pentium、AMD Ryzen 1000シリーズ、FXシリーズ",
    "preset_cpu_new": "GPUなし・新しめのCPU（内蔵GPUで動かしている場合も）",
    "preset_cpu_new_examples": "例：Intel Core 第8世代以降（Core i5-8250U、i5-10400、i7-1165G7、i5-12400 など）、Core Ultra、AMD Ryzen 2000以降（Ryzen 5 3600、Ryzen 7 5700U など）",
    "preset_gpu_middle": "GPUあり・入門〜中級",
    "preset_gpu_middle_examples": "例：GeForce GTX 1070・1650・1660、RTX 2060・3050・3060・4060、Radeon RX 580・5500 XT・6600",
    "preset_gpu_high": "GPUあり・上位",
    "preset_gpu_high_examples": "例：GeForce RTX 3060 Ti・3070・3080・4060 Ti・4070・5060・5070 以上、Radeon RX 6700 XT・6800・7800 XT 以上",
    "preset_mac_standard": "Mac・標準",
    "preset_mac_standard_examples": "例：Metal版以外のKataGoのMac全般、Metal版でM1・M2の無印",
    "preset_mac_fast": "Mac・速い",
    "preset_mac_fast_examples": "例：Metal版でM3・M4の無印、M1〜M4のPro",
    "preset_mac_faster": "Mac・とても速い",
    "preset_mac_faster_examples": "例：Metal版でM1〜M4のMax・Ultra",
    "preset_mac_fastest": "Mac・最速",
    "preset_mac_fastest_examples": "例：Metal版でM5以降",
    "preset_measure": "使用しているマシンが分からない場合",
    "preset_measure_note": "このパソコンでKataGoの速さを測って、1回の解析が約1.6秒になるように探索手数を決めます。比較用モデルも別に測ります。",
    "preset_measure_button": "測る",
    "preset_measuring": "KataGoの速さを測っています…（KataGoの起動を含めて、数十秒かかることがあります）",
    "preset_measured": "このパソコンのKataGoは、1秒に約{speed}手読めました。\n探索手数を 判定 {main}　地と形勢 {estimate}　棋譜解析の深い読み {deep} にします。よろしいですか？",
    "preset_measured_compare": "このパソコンのKataGoは、1秒に約{speed}手（比較用モデルは約{compare_speed}手）読めました。\n探索手数を 判定 {main}　比較用モデル {compare}　地と形勢 {estimate}　棋譜解析の深い読み {deep} にします。よろしいですか？",
    "preset_measure_failed": "KataGoの速さを測れませんでした：{reason}",
    "preset_values": "探索手数：判定 {main}　比較用モデル {compare}　地と形勢 {estimate}　棋譜解析の深い読み {deep}",
    "preset_apply": "設定",
    "preset_question": "推奨設定で現在の設定を置き換えます。よろしいですか？",
    "loading_title": "KataGoを準備しています",
    "loading_main": "メインモデルを読み込み中…",
    "loading_compare": "比較用モデルを読み込み中…",
    "loading_elapsed": "{seconds}秒経過",
    "loading_remaining": "残り約{seconds}秒",
    "loading_hide": "待たずに使う",
}


def load_texts(language: str) -> dict[str, str]:
    """Return all texts of a language. Texts that the language does not have are in English.

    Args:
        language: One of LANGUAGES.

    Raises:
        ValueError: If the language is not one of LANGUAGES.
        OSError: If the file of the language cannot be read.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unknown language: {language}")
    if language == SOURCE_LANGUAGE:
        return dict(TEXTS)
    english = _read_locale(DEFAULT_LANGUAGE)
    own = _read_locale(language) if language != DEFAULT_LANGUAGE else english
    # Japanese is the last fallback, so that a key added to TEXTS but not yet translated still works.
    return {key: own.get(key) or english.get(key) or value for key, value in TEXTS.items()}


def _read_locale(language: str) -> dict[str, str]:
    """Read the texts of one language from its file in LOCALES_FOLDER."""
    path = LOCALES_FOLDER / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))


_language = DEFAULT_LANGUAGE
_texts = load_texts(DEFAULT_LANGUAGE)


def set_language(language: str) -> None:
    """Use another language for all texts from now on.

    Widgets that already show texts are not changed here (see gui.widgets.relabel_all).

    Raises:
        ValueError: If the language is not one of LANGUAGES.
        OSError: If the file of the language cannot be read.
    """
    global _language, _texts
    _texts = load_texts(language)
    _language = language


def language() -> str:
    """Return the language that is used now."""
    return _language


def text(key: str, **values) -> str:
    """Return the text for a key in the language used now, with the values filled in."""
    return _texts[key].format(**values)


def template(key: str) -> str:
    """Return the text for a key in the language used now, with its {values} not filled in."""
    return _texts[key]


def notice_text(notice: Notice | None) -> str:
    """Return a message given by a part without screens (see kentogo.notice) in words, or "" for None."""
    return text(notice.key, **notice.values) if notice is not None else ""


def notices_text(notices) -> str:
    """Return several messages (see notice_text), with an empty line between them."""
    return "\n\n".join(notice_text(notice) for notice in notices)


def lazy(key: str, **values) -> Callable[[], str]:
    """Return a function that makes the text, so that it can be made again in another language."""
    return lambda: text(key, **values)


def list_text(items: list[str]) -> str:
    """Join the parts of a list in the way of the language ("A、B" or "A, B")."""
    return ("、" if _language in _CJK_PUNCTUATION else ", ").join(items)


def gap() -> str:
    """Return the space between two parts of a line (a full-width space in Japanese and Chinese)."""
    return "　" if _language in _CJK_PUNCTUATION else "  "


def fill_step_text(step: FillStep | None, number: int, total: int) -> str:
    """Return the line that tells one step of the computer's seichi (None: the board before it)."""
    if step is None:
        return text("seichi_steps", number=0, total=total, step=text("seichi_steps_start"))
    names = [Move(step.color or "B", point).gtp() for point in step.points]
    color = color_name(step.color) if step.color else ""
    if step.kind == "capture":
        line = text("seichi_step_capture", color=color, count=len(names))
    elif step.kind == "place":
        line = text("seichi_step_place", color=color, point=names[0])
    elif step.kind == "move":
        line = text("seichi_step_move", color=color, source=names[0], target=names[1])
    else:
        line = _exchange_text(step, names, color)
    return text("seichi_steps", number=number, total=total, step=line)


def _exchange_text(step: FillStep, names: list[str], color: str) -> str:
    """Return the words of a step that exchanges stones with the other player (a color change or a swap)."""
    new = color_name("W" if step.color == "B" else "B")
    if step.kind == "swap":
        return text("seichi_step_swap", color=color, new=new, source=names[0], target=names[1])
    if len(names) == 1:
        return text("seichi_step_recolor", color=color, new=new, point=names[0])
    return text("seichi_step_exchange", color=color, new=new, source=names[0], target=names[1])


def lead_text(lead: float, komi: float | None = None) -> str:
    """Return who is ahead by how many points (black's lead; with komi, who wins after komi)."""
    prefix = "lead_" if komi is None else "lead_komi_"
    key = prefix + ("black" if lead > 0 else "white" if lead < 0 else "even")
    return text(key, points=f"{abs(lead):g}", komi=f"{komi:g}" if komi is not None else "")


def color_name(color: str) -> str:
    """Return the name of a color ("B" or "W")."""
    return text("black") if color == "B" else text("white")


def sequence_name(source: str) -> str:
    """Return the name of a sequence from its source, such as "katrain" or "katago"."""
    key = f"source_{source}"
    return text(key) if key in TEXTS else source


def sequence_order_text(choices: list[tuple[str, str]], selected: int, seconds: int = 0) -> str:
    """Return the line that shows the order of the sequences for Tab, with the shown one marked.

    Args:
        choices: (source, status) of each sequence in order. status is "" when the sequence
            is ready, "waiting" while KataGo is calculating it, or "failed".
        selected: The index of the shown sequence.
        seconds: How long KataGo has been calculating, shown with the sequences it is calculating.
    """
    names = []
    for index, (source, status) in enumerate(choices):
        key = f"short_{source}"
        name = text(key) if key in TEXTS else source
        if status:
            name = text(f"short_{status}", name=name, seconds=seconds)
        names.append(f"[color=f2c94c][b]▶{name}[/b][/color]" if index == selected else name)
    return text("sequence_order", names=" → ".join(names))


def sequence_text(source: str, index: int, count: int, step: int, total: int, status: str = "") -> str:
    """Return the text about the sequence that is shown: what it is, and how far it is played.

    Args:
        source: Where the sequence came from, such as "katrain" or "katago".
        index: The number of the sequence, starting from 1.
        count: The number of sequences.
        step: How many moves of the sequence are shown.
        total: The number of moves in the sequence.
        status: "" when the sequence is ready, "waiting" while KataGo is calculating it, or "failed".
    """
    key = f"explain_{source}"
    explanation = text(key) if key in TEXTS else ""
    name = sequence_name(source)
    shown = text("sequence", name=name, explanation=explanation, index=index, count=count, step=step, total=total)
    if status:
        # The first two lines (the name and the explanation), and what KataGo is doing instead of the moves.
        shown = "\n".join(shown.split("\n")[:2] + [text(f"sequence_{status}")])
    return shown


def notes_text(notes: str, ai_comment: str = "") -> str:
    """Return the AI commentary and the notes to show ("" when there are none).

    Args:
        notes: The user's notes (already rewritten if the board is changed, see quiz.notes_transform).
        ai_comment: The AI commentary (already rewritten in the same way), shown first under a heading.
    """
    parts = ([f"{text('ai_commentary')}\n{ai_comment}"] if ai_comment else []) + ([notes] if notes else [])
    return "\n\n".join(parts)


def skipped_text(skipped: dict[str, int]) -> str:
    """Return the line about the games that gave no problems, or "" if there are none.

    Args:
        skipped: How many games gave no problems, for each reason (such as "no_analysis").
    """
    details = []
    for reason, count in sorted(skipped.items()):
        key = f"skipped_{reason}"
        details.append(text(key, count=count) if key in TEXTS else f"{reason} {count}")
    return text("splash_skipped", details=list_text(details)) if details else ""


def skipped_games_text(games: list[SkippedGame]) -> str:
    """Return one line for each game that gave no problems, to show in a dialog.

    Args:
        games: The games that gave no problems.
    """
    lines = []
    for game in games:
        key = f"skipped_game_{game.reason}"
        lines.append(text(key, name=game.name, detail=game.detail) if key in TEXTS else f"{game.name}: {game.reason}")
    return "\n".join(lines)


def history_text(previous: list[AnswerRecord]) -> str:
    """Return the line about the earlier answers to a problem: how many times, and the last result.

    Args:
        previous: The earlier answers to the problem, the oldest first.
    """
    if not previous:
        return text("history_first")
    last = previous[-1].correct
    if last is None:
        result = text("history_not_judged")
    else:
        result = text("history_correct") if last else text("history_wrong")
    return text("history_again", count=len(previous) + 1, last=result)


def analysis_step_text(step: str, done: int, total: int) -> str:
    """Return the progress of a step of the analysis of a game (see analysis.game_analysis)."""
    return text(f"analysis_step_{step}", done=done, total=total)


def analysis_outcome_text(name: str, outcome: str, detail: str) -> str:
    """Return how the analysis of a game ended (see analysis_run), with the reason of a failure."""
    if outcome == "written" and "could not be analyzed" in detail:
        return text("analysis_outcome_incomplete", name=name)
    return text(f"analysis_outcome_{outcome}", name=name, detail=detail)


def analysis_summary_text(summary: AnalysisSummary) -> str:
    """Return how a run of the analysis ended: the games written, skipped and failed, or why it could not run."""
    if summary.problem:
        return text("analysis_problem", reason=summary.problem)
    counts = summary.outcomes
    key = "analysis_summary_stopped" if summary.stopped else "analysis_summary"
    return text(key, written=counts["written"], skipped=counts["skipped"], failed=counts["failed"])


def analysis_plan_problem(plan: AnalysisPlan, redo_kentogo: bool = False) -> str:
    """Return why a run of the analysis has nothing to do (no folder, no games, all analyzed), or "".

    Games that can be analyzed again for KentoGo (plan.kentogo_redo) are something to do until the
    user says no to them (redo_kentogo is then False and the question has been asked).
    """
    if plan.folder is None:
        return text("analysis_no_folder_set")
    if not plan.folder.is_dir():
        return text("analysis_no_folder", folder=plan.folder)
    if not plan.games:
        return text("analysis_no_games", folder=plan.folder)
    if not plan.count(redo_kentogo):
        return text("analysis_all_analyzed", folder=plan.folder, games=plan.games)
    return ""


def analysis_kentogo_question(plan: AnalysisPlan) -> str:
    """Return the question whether the games analyzed by KaTrain are analyzed again for KentoGo."""
    return text("analysis_kentogo_question", count=plan.kentogo_redo)


def analysis_plan_text(plan: AnalysisPlan, redo_kentogo: bool = False) -> str:
    """Return what a run of the analysis will do, asked before it starts: the folder and the number of
    games that are overwritten, the backup folder, and the analyzed games that are skipped, analyzed
    again, or analyzed again for KentoGo (redo_kentogo: the user said yes to it)."""
    redo = plan.kentogo_redo if redo_kentogo else 0
    lines = [text("analysis_confirm", folder=plan.folder, count=plan.count(redo_kentogo), backup=plan.backup)]
    if plan.reanalyze and plan.analyzed:
        lines.append(text("analysis_confirm_again", games=plan.games, analyzed=plan.analyzed))
    elif plan.analyzed - redo:
        lines.append(text("analysis_confirm_skip", games=plan.games, analyzed=plan.analyzed - redo))
    if redo:
        lines.append(text("analysis_confirm_kentogo", count=redo))
    lines.append(text("analysis_confirm_question"))
    return "\n".join(lines)


def problem_info(problem: Problem, index: int, total: int) -> str:
    """Return the text about the problem: the game, the move number, the player, and the count.

    Args:
        problem: The problem as it is shown.
        index: The number of the problem, starting from 1.
        total: The number of problems.
    """
    info = text(
        "problem_info",
        game=Path(problem.sgf_path).stem,
        move_number=problem.move_number,
        color=color_name(problem.position.next_color),
        index=index,
        total=total,
    )
    hint = punishment_hint(problem)
    return f"{info}{gap()}{hint}" if hint else info


def punishment_hint(problem: Problem) -> str:
    """Return the hint of a punishment problem (or of a point that both missed), or "" for other problems."""
    if problem.punishment == PUNISH:
        return text("punish_hint", loss=f"{problem.opponent_loss or 0:.1f}")
    if problem.punishment == SHARED:
        return text("shared_hint")
    return ""


def count_check_text(check: CountCheck, komi: float) -> str:
    """Return the result of 整地終了: right or wrong, the territory on the board, and the right one with komi."""
    seichi = text("count_seichi_ok")
    if not check.passed:
        seichi = text("count_seichi_wrong", black=check.counted.black, white=check.counted.white)
    left = sum(check.prisoners_left.values())
    if left:
        seichi += text("count_prisoners_left", count=left)
    right = check.right
    answer = text(
        "count_answer", black=right.black, white=right.white, result=lead_text(right.black - right.white - komi, komi)
    )
    verdict = text("count_passed" if check.passed else "count_failed")
    return "\n".join([verdict, seichi, answer])


def area_text(change: AreaChange, mode: int) -> str:
    """Return the line of the "地の違い" view (see quiz.area_change), for the board as it is shown."""
    if mode == AREAS_PLAYED:
        return text("area_played", move=change.played.gtp(), lead=_lead_or_empty(change.played_lead))
    if mode == AREAS_BEST:
        return text("area_best", move=change.best.gtp(), lead=_lead_or_empty(change.best_lead))
    color = change.played.color
    values = {"best": change.best.gtp(), "played": change.played.gtp(), "color": color_name(color)}
    gain = change.lead_gain(color)
    points = f"{change.gained(color):+d}"
    if gain is None:
        return text("area_change_no_lead", **values, points=points)
    return text("area_change", **values, points=points, gain=f"{gain:+.1f}")


def _lead_or_empty(lead: float | None) -> str:
    return "" if lead is None else lead_text(round(lead, 1))


def standing_text(standing: Standing, moves: int) -> str:
    """Return the standing at the end of a sequence of some moves, and how it compares with the game."""
    lead = standing.end.lead
    return text(
        "standing",
        leader=color_name("B" if lead >= 0 else "W"),
        ahead=abs(lead),
        moves=moves,
        player=color_name(standing.color),
        gain=standing.gain,
    )


def _comparison_line(comparison: Comparison, move: Move, other: bool, loss: float | None) -> str:
    """Return the line of the losses: the game move against the answer, or against another move (other)."""
    if not other:
        loss = comparison.answer_loss
    elif loss is None:
        return text("comparison_unknown", actual=comparison.actual_loss, move=move.gtp())
    shown = compare_with_actual(comparison.actual_loss, loss)
    return text(
        "comparison",
        actual=shown.actual_loss,
        move=move.gtp(),
        answer=shown.answer_loss,
        improvement=shown.improvement,
        ratio=shown.recovered_ratio,
    )


def result_text(
    problem: Problem,
    result: AnswerResult,
    waiting_reason: str = "",
    compare_best: Move | None = None,
    by_compare: bool = False,
    compare_best_loss: float | None = None,
    sequence: tuple[Move, float | None] | None = None,
    show_verdict: bool = True,
) -> str:
    """Return the text about the result of an answer.

    Args:
        problem: The problem in the original direction and colors.
        result: The result of the answer.
        waiting_reason: Why the answer is not judged yet (used only when result.correct is None),
            such as text("evaluating").
        compare_best: The comparison model's best move, or None if it is not known.
        by_compare: True while the comparison model's sequence is shown (with its losses).
        compare_best_loss: Points lost by the comparison model's best move. With by_compare, its line
            (how much it gains or loses against the game move) is the only line of the losses.
        sequence: The first move of the shown sequence and its loss (None if unknown), when it is
            not the answer: the line of the losses then tells about that move (see QuizSession.sequence_loss).
        show_verdict: False to leave out whether the answer is correct (or why it is not judged yet),
            while another sequence than the answer's is shown.

    Returns:
        Whether the answer is correct, the losses, the moves, and the legend of the marks.
    """
    best = problem.best_move.gtp() if problem.best_move else text("unknown_move")
    shown_move, shown_loss = sequence if sequence is not None else (result.answer, None)
    moves = text("moves", answer=result.answer.gtp(), actual=problem.actual_move.gtp(), best=best)
    legend = text("legend")
    if compare_best is not None:
        moves += text("moves_compare", compare=compare_best.gtp())
        legend += text("legend_compare")
    if result.correct is None:
        waiting = [text("not_judged", reason=waiting_reason)] if show_verdict else []
        return "\n".join([*waiting, moves, legend])
    comparison = result.comparison
    if by_compare and compare_best is not None and compare_best_loss is not None:
        losses = _compare_line(comparison.actual_loss, compare_best, compare_best_loss)
    else:
        losses = _comparison_line(comparison, shown_move, sequence is not None, shown_loss)
    verdict = [text("correct") if result.correct else text("wrong")] if show_verdict else []
    return "\n".join([*verdict, losses, moves, legend])


def _compare_line(actual_loss: float, compare_best: Move, compare_best_loss: float) -> str:
    """Return the line of the comparison model's move: its loss, and how much it gains (or loses) against the game."""
    gain = actual_loss - compare_best_loss
    key = "compare_move_gain" if gain >= 0 else "compare_move_loss"
    return text(key, move=compare_best.gtp(), loss=compare_best_loss, gain=abs(gain))


def _percent(value: float | None) -> str:
    """Return a part (0.0 to 1.0) as a percentage such as "72%", or a dash when it is not known."""
    return text("no_value") if value is None else f"{round(100 * value)}%"


def _per_game(value: float | None) -> str:
    """Return an average number of mistakes per game with one decimal, or a dash when it is not known."""
    return text("no_value") if value is None else f"{value:.1f}"


def _trend(now: float | None, before: float | None) -> str:
    """Return an arrow when a part went up or down by at least TREND_STEP, else ""."""
    if now is None or before is None or abs(now - before) < TREND_STEP:
        return ""
    return text("trend_up") if now > before else text("trend_down")


TREND_STEP = 0.02  # A change smaller than this (2 points of percentage) shows no arrow.


def totals_text(totals: Totals) -> str:
    """Return the lines of the report about all the practice."""
    return text(
        "report_totals",
        answered=totals.answered,
        correct=totals.correct,
        finished=totals.finished,
        recovered=f"{totals.recovered:,.0f}",
        days=totals.days,
    )


def recent_text(recent: Recent) -> str:
    """Return the lines of the report about the latest practice days, compared with the ones before."""
    if recent.correct_rate is None:
        return text("report_recent_none")
    return text(
        "report_recent",
        count=RECENT,
        rate=_percent(recent.correct_rate),
        rate_trend=_trend(recent.correct_rate, recent.earlier_correct_rate),
        average=_percent(recent.average),
        average_trend=_trend(recent.average, recent.earlier_average),
        earlier_rate=_percent(recent.earlier_correct_rate),
        earlier_average=_percent(recent.earlier_average),
    )


def points(value: float) -> str:
    """Return a number of points without a needless decimal, such as "3" or "2.5"."""
    return f"{value:g}"


def band_key(bands: Sequence[float], index: int) -> tuple[str, dict]:
    """Return the text key and its values naming one band of mistakes (bands: the lower ends, the biggest first)."""
    if index == 0:
        return "band_top", {"low": points(bands[0])}
    return "band_range", {"low": points(bands[index]), "high": points(bands[index - 1])}


def band_names(bands: Sequence[float]) -> list[str]:
    """Return the names of the bands of mistakes, such as "20目以上" and "10〜20目"."""
    return [text(key, **values) for key, values in (band_key(bands, index) for index in range(len(bands)))]


def game_averages_text(averages: GameAverages, bands: Sequence[float]) -> str:
    """Return the lines of the report about the mistakes per game in each band, the latest games and the ones before."""
    if averages.latest is None:
        return text("report_games_none")
    names = band_names(bands)

    def joined(values: Sequence[float] | None) -> str:
        if values is None:
            return text("no_value")
        return "　".join(f"{name} {_per_game(value)}" for name, value in zip(names, values, strict=True))

    return text("report_games_recent", count=RECENT, latest=joined(averages.latest), earlier=joined(averages.earlier))


def today_summary_text(summary: TodaySummary) -> str:
    """Return the summary of the day, with a line for each thing achieved today."""
    lines = [
        text(
            "today_summary",
            answered=summary.answered,
            correct=summary.correct,
            recovered=f"{summary.recovered:,.0f}",
            day=summary.day_number,
        )
    ]
    lines += [text(f"achievement_{item.key}", value=f"{item.value:,.0f}") for item in summary.achievements]
    return "\n".join(lines)
