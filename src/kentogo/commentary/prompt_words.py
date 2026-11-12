"""The words of the parts of the prompt that KentoGo makes, in Japanese and in English (see commentary.prompt).

The texts with {values} are filled in by commentary.prompt. The parts that the user can
change are in the prompt files instead (see commentary.prompt_text).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kentogo.commentary.language import CATEGORIES, PROMPT_ENGLISH, PROMPT_JAPANESE
from kentogo.commentary.targets import normalize_rank, rank_label
from kentogo.common.places import CENTER
from kentogo.common.shapes import CONNECT, CUT, HANE, IKKEN, KEIMA, KOSUMI, NOBI, SAGARI, TSUKE, WEDGE


@dataclass(frozen=True)
class PromptWords:
    """The words of the prompt in one language (the names of the attributes tell where each is used)."""

    black: str
    white: str
    pass_move: str
    move: str  # A move: {color} and {point}.
    sequence_arrow: str
    list_separator: str
    none: str  # Instead of something that is not known.
    relation_same: str
    relation_higher: str
    relation_lower: str
    relation_none: str
    rank: Callable[[str], str]  # Writes a rank (such as "18k") in this language ("" if it is not a rank).
    about_me: str
    rank_line: str
    opponent_line: str
    rules_heading: str
    diagram_legend: str
    answer_format: str  # {categories}: the categories that the AI can choose.
    category_choice: str  # One category in answer_format: {name} (one of CATEGORIES) and {words}.
    answer_language: str  # The line that asks for the language of the answer (the English one has {language}).
    category_names: tuple[str, ...]  # The names of CATEGORIES in words, in the same order.
    paste_reminder: str
    loss_heading: str
    loss_note: str
    loss_header: str
    loss_row: str  # {size}, {count}, {goal} and {limit}.
    no_targets: str
    data_heading: str
    move_heading: str  # {number} and {color}.
    move_heading_taken_back: str
    played_line: str  # {move} and {loss}.
    taken_back_line: str
    best_line: str
    last_move_line: str
    candidates_line: str  # {items}: the candidates (candidate), joined with list_separator.
    candidate: str  # {point} and {loss}.
    score_line: str  # {leader} and {points}.
    sequence_line: str
    facts_heading: str
    captures: str  # {group}.
    atari: str  # {group}.
    step_line: str  # {number}, {move} and {events} (joined with list_separator).
    no_steps: str
    shape_names: dict[str, str]  # The names of the shapes (common.shapes) with {stones}.
    region_names: dict[str, str]  # The names of the regions (common.places).
    placed_move: str  # A move with its place: {move}, {region} and {line}.
    shape_separator: str
    no_shape: str
    capture_effect: str  # {group}.
    pon_nuki_effect: str  # {group}.
    ko_effect: str  # {group}.
    atari_effect: str  # {group}.
    ladder_effect: str
    empty_triangle_effect: str
    self_atari_effect: str
    last_move_shape: str  # {move} and {shape}, and the same for the lines below.
    played_shape: str
    best_shape: str
    game_heading: str
    game_line: str
    pv_heading: str
    pv_line: str  # {number}, {move} and {shape}.
    next_near: str  # {color}, {move} and {distance}.
    next_far: str
    cuts_line: str  # {color}, {before}, {game} and {pv}.
    cuts_none: str
    aimed_heading: str
    nearby_heading: str
    nearby_line: str  # {group} and {liberties}.
    group: str  # {color}, {points} and {count}.
    reply_none: str
    reply_line: str
    reply_best_line: str  # {best} and {loss} (reply_loss or "").
    reply_loss: str
    reply_sequence_line: str
    notes_line: str
    katrain_line: str
    before_diagram: str
    zoom_diagram: str
    after_diagram: str

    def color_name(self, color: str) -> str:
        """Return the name of a color, "B" or "W"."""
        return self.black if color == "B" else self.white


def english_rank(rank: str) -> str:
    """Return a rank in English, such as "18 kyu" or "1 dan" ("" if it is not a rank)."""
    rank = normalize_rank(rank)
    if not rank:
        return ""
    return f"{rank[:-1]} {'kyu' if rank.endswith('k') else 'dan'}"


JAPANESE_WORDS = PromptWords(
    black="黒",
    white="白",
    pass_move="パス",
    move="{color}{point}",
    sequence_arrow=" → ",
    list_separator=",",
    none="記載なし",
    relation_same="同ランク(互先)",
    relation_higher="相手が1ランク上",
    relation_lower="相手が1ランク下",
    relation_none="指定なし",
    rank=rank_label,
    about_me="# 私について",
    rank_line="- 段級位: {rank}(この対局の時点)",
    opponent_line="- この対局の相手: {relation}",
    rules_heading="# 守ること(最重要)",
    diagram_legend="""# 盤面図の見方
- X=黒石,O=白石,.=空点.x または o=相手の直前の手.#=私が実際に打った点,*=AIの最善手の点.
- 横の文字(A〜T,Iは無い)と縦の数字が座標.上の行ほど数字が大きい.
- [直前の盤面図]は,その手を打つ直前の局面.
- [拡大図]は,直前の盤面図のうち,実戦の手と最善手の周りだけを切り出したもの.
- [予想手順の後の盤面図]は,予想手順をすべて打ち,取られる石を取り除いた後の局面.""",
    answer_format="""# 回答の形式
次の形のJSONだけを返す.Markdownの記号(#,**,- など)は使わない.文字列の中では改行しない.
{{
  "moves": [
    {{
      "move": 手数(数字),
      "situation": "その時の状況を一言(序盤/右下の戦い/ヨセ など,場所の名前を入れる)",
      "category": "{categories} から一つ.英語の名前をそのまま書く",
      "what_to_see": "打つ前に見るべきだったこと.相手の直前の手の形と狙い,相手が一番打ちたかった点,狙われていた自分の石(1から2文)",
      "what_happened": "実戦の手と最善手の差(損失目数)と,実戦の手で相手に何をさせたか(2から3文)",
      "aim": "最善手の形の名前と目的.予想手順を2から3のまとまりで追い,石のつながり,地,石の強弱がどう変わるか.先手か後手か(3から5文)",
      "lesson": "次に同じ場面で,打つ前に自分に問いかける一文(例:「〜を確かめてから打ちます」).合う格言があれば添える(無理に付けない)"
    }}
  ],
  "summary": {{
    "category_counts": "分類の集計(例: 急場の見逃し 2,響かない手 2,読み違い 1)",
    "main_issue": "今の私の一番の課題を一つ.複数の手に共通する形や考え方の癖として書く",
    "next_focus": "次の対局で意識することを一つだけ.対局中に使えるチェックの一言にする",
    "loss_comparison": "[この対局の損失の回数]を目標とする回数・超えてはいけない回数と比べて一言"
  }}
}}
- moves には,下のデータにある私の手をすべて,手数の昇順(打った順)で入れる.""",
    category_choice="{name}({words})",
    # Also asked in the rules of the default prompt file, but the user can change that file.
    answer_language="- JSONの文章はすべて日本語で書く.",
    category_names=("急場の見逃し", "響かない手", "大きさの判断ミス", "読み違い", "方向違い"),
    paste_reminder="回答は上の[回答の形式]のJSONだけにしてください.前置きや説明は付けないでください.",
    loss_heading="# この対局の損失の回数",
    loss_note="(KaTrainの損失目数で数えた,この対局の私の手の回数.形勢が決まった後の手も含む)",
    loss_header="| 損失の大きさ | この対局の回数 | 目標とする回数 | 超えてはいけない回数 |\n|---|---|---|---|",
    loss_row="| {size}目以上 | {count}回 | {goal} | {limit} |",
    no_targets="(段級位が目標表に無いため,目標との比較はありません)",
    data_heading="# KaTrainの解析データ",
    move_heading="## 第{number}手目({color}番)",
    move_heading_taken_back="## 第{number}手目({color}番,KaTrainの指導碁で待ったをした手)",
    played_line="- 実戦の手: {move},損失: {loss:.1f}目",
    taken_back_line="- 打って取り消した手: {move},損失: {loss:.1f}目(実戦ではこの手の後に打ち直したため,相手の応手はありません)",
    best_line="- AIの最善手: {best}",
    last_move_line="- 相手の直前の手: {move}",
    candidates_line="- 候補手(損失の小さい順): {items}",
    candidate="{point}({loss:.1f}目)",
    score_line="- この手の後の形勢: {leader}が約{points:.1f}目リード",
    sequence_line="- AIの予想手順(最善手から): {sequence}",
    facts_heading="- KentoGoが計算した事実:",
    captures="{group}を取る",
    atari="{group}がアタリになる",
    step_line="  予想手順の{number}手目 {move}: {events}",
    no_steps="  予想手順の中に,石を取る手やアタリにする手はない.",
    shape_names={
        CONNECT: "ツギ({stones}をつなぐ)",
        CUT: "キリ({stones}を切る)",
        WEDGE: "ワリコミ({stones}の間)",
        HANE: "ハネ({stones}から)",
        NOBI: "ノビ({stones}から)",
        SAGARI: "サガリ({stones}から)",
        TSUKE: "ツケ({stones}に)",
        KOSUMI: "コスミ({stones}から)",
        IKKEN: "一間トビ({stones}から)",
        KEIMA: "ケイマ({stones}から)",
    },
    region_names={
        "top_left_corner": "左上隅",
        "top_right_corner": "右上隅",
        "bottom_left_corner": "左下隅",
        "bottom_right_corner": "右下隅",
        "top_left": "左上",
        "top_right": "右上",
        "bottom_left": "左下",
        "bottom_right": "右下",
        "left_side": "左辺",
        "right_side": "右辺",
        "top_side": "上辺",
        "bottom_side": "下辺",
        CENTER: "中央",
    },
    placed_move="{move}({region},{line}線)",
    shape_separator="、",
    no_shape="決まった形の名前なし",
    capture_effect="抜き({group}を取る)",
    pon_nuki_effect="ポン抜き({group}を取る)",
    ko_effect="コウを取る({group}を取る)",
    atari_effect="アテ({group}がアタリ)",
    ladder_effect="シチョウ(アタリにした石はシチョウで取れる)",
    empty_triangle_effect="アキ三角になる",
    self_atari_effect="自分の石がアタリになる",
    last_move_shape="  [形] 相手の直前の手 {move}: {shape}",
    played_shape="  [形] 実戦の手 {move}: {shape}",
    best_shape="  [形] 最善手 {move}: {shape}",
    game_heading="  [実戦の進行] 実戦の手と,相手の次の手(実戦):",
    game_line="  {move}: {shape}",
    pv_heading="  [予想手順の各手の形]",
    pv_line="  {number}手目 {move}: {shape}",
    next_near="  [予想手順の相手の次の手] {color}は最善手の近く({distance}路)の{move}に打つ.",
    next_far="  [予想手順の相手の次の手] {color}は手を抜いて{move}に打つ(最善手から{distance}路).",
    cuts_line="  [切られる点]({color}の石.拡大図の範囲) 直前: {before} / 実戦の進行の後: {game} / 予想手順の後: {pv}",
    cuts_none="なし",
    aimed_heading="  [狙われていた自分の石](実戦の手の後,相手が一番打ちたかった点の近く):",
    nearby_heading="- 実戦の手と最善手の近くの石(直前の局面):",
    nearby_line="  {group}: ダメ{liberties}",
    group="{color}の石 {points}({count}子)",
    reply_none="- 相手の次の手: なし(終局)",
    reply_line="- 相手の次の手(実戦): {move}",
    reply_best_line="- 相手の手番での最善手(相手が一番打ちたかった点): {best}{loss}",
    reply_loss="(相手の実戦の手の損失 {loss:.1f}目)",
    reply_sequence_line="- 相手の手番での予想手順: {sequence}",
    notes_line="- 私のメモ: {notes}",
    katrain_line="- KaTrainの元コメント:\n{text}",
    before_diagram="- 直前の盤面図:",
    zoom_diagram="- 拡大図:",
    after_diagram="- 予想手順の後の盤面図:",
)

ENGLISH_WORDS = PromptWords(
    black="Black",
    white="White",
    pass_move="pass",
    move="{color} {point}",
    sequence_arrow=" → ",
    list_separator=", ",
    none="none",
    relation_same="same rank (even game)",
    relation_higher="one rank above me",
    relation_lower="one rank below me",
    relation_none="not given",
    rank=english_rank,
    about_me="# About me",
    rank_line="- Rank: {rank} (at the time of this game)",
    opponent_line="- Opponent in this game: {relation}",
    rules_heading="# Rules (most important)",
    diagram_legend="""# How to read the diagrams
- X = black stone, O = white stone, . = empty point. x or o = the opponent's previous move. \
# = the point where I played, * = the point of the AI's best move.
- The letters across (A to T, without I) and the numbers up the side are the coordinates. \
The higher the row, the larger its number.
- [Board before the move] is the position just before the move.
- [Zoomed board] is the part of the board before the move around the move played and the best move.
- [Board after the predicted sequence] is the position after all the moves of the predicted sequence, \
with the captured stones removed.""",
    answer_format="""# Answer format
Return only JSON in the following form. Do not use Markdown symbols (#, **, - and so on). \
Do not break lines inside strings.
{{
  "moves": [
    {{
      "move": move number (a number),
      "situation": "the situation at that time in a few words, with the name of the place \
(opening / fight at the bottom right / endgame and so on)",
      "category": "one of {categories}, written as its English name",
      "what_to_see": "what I should have looked at before playing: the shape and aim of the opponent's previous move, \
the point the opponent most wanted to play, and my stones that were aimed at (1 to 2 sentences)",
      "what_happened": "the difference between the move played and the best move (the loss), \
and what the move played let the opponent do (2 to 3 sentences)",
      "aim": "the name of the shape and the aim of the best move. Follow the predicted sequence in two or three parts: \
how the stones connect, and how the territory and the strength of the groups change. Sente or gote (3 to 5 sentences)",
      "lesson": "one question to ask myself before playing in the same kind of position next time \
(for example: 'I check ... before I play'). Add a fitting proverb if there is one (do not force it)"
    }}
  ],
  "summary": {{
    "category_counts": "the count of each category (for example: missed urgent point 2, no pressure 2, misread 1)",
    "main_issue": "my biggest issue now, only one, written as a habit of shape or thinking shared by several moves",
    "next_focus": "only one thing to keep in mind in my next game, as a short check I can use during the game",
    "loss_comparison": "one sentence comparing [Counts of losses in this game] with the target counts \
and the counts not to exceed"
  }}
}}
- In moves, put all my moves in the data below, in ascending order of move number (the order they were played).""",
    category_choice="{name} ({words})",
    answer_language="- Write all the texts of the JSON in {language}. "
    "Keep the keys and the names of the categories (such as missed_urgent_point) as they are.",
    category_names=(
        "missed an urgent point",
        "a move that puts no pressure on the opponent",
        "misjudged the size of a move",
        "misread",
        "wrong direction",
    ),
    paste_reminder="Answer only with the JSON of [Answer format] above. Do not add an introduction or explanations.",
    loss_heading="# Counts of losses in this game",
    loss_note="(The numbers of my moves in this game by KaTrain's point loss, "
    "including the moves after the game was decided)",
    loss_header="| Loss | Times in this game | Target | Not to exceed |\n|---|---|---|---|",
    loss_row="| {size}+ points | {count} | {goal} | {limit} |",
    no_targets="(My rank is not in the table of targets, so there is no comparison with the targets)",
    data_heading="# KaTrain's analysis data",
    move_heading="## Move {number} ({color})",
    move_heading_taken_back="## Move {number} ({color}, taken back in KaTrain's teaching game)",
    played_line="- Move played: {move}, loss: {loss:.1f} points",
    taken_back_line="- Move played and taken back: {move}, loss: {loss:.1f} points "
    "(another move was played instead, so the opponent did not answer it)",
    best_line="- AI's best move: {best}",
    last_move_line="- Opponent's previous move: {move}",
    candidates_line="- Candidate moves (smallest loss first): {items}",
    candidate="{point} ({loss:.1f} points)",
    score_line="- Score after this move: {leader} leads by about {points:.1f} points",
    sequence_line="- AI's predicted sequence (from the best move): {sequence}",
    facts_heading="- Facts worked out by KentoGo:",
    captures="captures {group}",
    atari="puts {group} in atari",
    step_line="  Move {number} of the predicted sequence, {move}: {events}",
    no_steps="  No move of the predicted sequence captures stones or puts stones in atari.",
    shape_names={
        CONNECT: "connect ({stones})",
        CUT: "cut ({stones})",
        WEDGE: "wedge (between {stones})",
        HANE: "hane (from {stones})",
        NOBI: "extend (from {stones})",
        SAGARI: "descend (from {stones})",
        TSUKE: "attach (to {stones})",
        KOSUMI: "diagonal (from {stones})",
        IKKEN: "one-space jump (from {stones})",
        KEIMA: "knight's move (from {stones})",
    },
    region_names={
        "top_left_corner": "top left corner",
        "top_right_corner": "top right corner",
        "bottom_left_corner": "bottom left corner",
        "bottom_right_corner": "bottom right corner",
        "top_left": "top left",
        "top_right": "top right",
        "bottom_left": "bottom left",
        "bottom_right": "bottom right",
        "left_side": "left side",
        "right_side": "right side",
        "top_side": "top side",
        "bottom_side": "bottom side",
        CENTER: "center",
    },
    placed_move="{move} ({region}, line {line})",
    shape_separator=", ",
    no_shape="no fixed shape name",
    capture_effect="captures {group}",
    pon_nuki_effect="pon-nuki (captures {group})",
    ko_effect="takes a ko (captures {group})",
    atari_effect="atari ({group} in atari)",
    ladder_effect="ladder (the stones put in atari are captured in a ladder)",
    empty_triangle_effect="makes an empty triangle",
    self_atari_effect="puts its own stones in atari",
    last_move_shape="  [Shape] Opponent's previous move {move}: {shape}",
    played_shape="  [Shape] Move played {move}: {shape}",
    best_shape="  [Shape] Best move {move}: {shape}",
    game_heading="  [Game] The move played and the opponent's next move (in the game):",
    game_line="  {move}: {shape}",
    pv_heading="  [Shape of each move of the predicted sequence]",
    pv_line="  Move {number} {move}: {shape}",
    next_near="  [Opponent's next move in the predicted sequence] {color} plays {move}, near the best move "
    "({distance} lines away).",
    next_far="  [Opponent's next move in the predicted sequence] {color} plays elsewhere, at {move} "
    "({distance} lines from the best move).",
    cuts_line="  [Cutting points] ({color} stones, in the zoomed board) before: {before} / "
    "after the game's moves: {game} / after the predicted sequence: {pv}",
    cuts_none="none",
    aimed_heading="  [My stones that were aimed at] (after the move played, near the point the opponent most wanted "
    "to play):",
    nearby_heading="- Stones near the move played and the best move (before the move):",
    nearby_line="  {group}: {liberties} liberties",
    group="{color} stones {points} (count: {count})",
    reply_none="- Opponent's next move: none (end of the game)",
    reply_line="- Opponent's next move (in the game): {move}",
    reply_best_line="- Best move for the opponent (the point the opponent most wanted to play): {best}{loss}",
    reply_loss=" (loss of the opponent's move in the game: {loss:.1f} points)",
    reply_sequence_line="- Predicted sequence for the opponent: {sequence}",
    notes_line="- My notes: {notes}",
    katrain_line="- KaTrain's comment:\n{text}",
    before_diagram="- Board before the move:",
    zoom_diagram="- Zoomed board:",
    after_diagram="- Board after the predicted sequence:",
)

_WORDS = {PROMPT_JAPANESE: JAPANESE_WORDS, PROMPT_ENGLISH: ENGLISH_WORDS}


def words_for(prompt_language: str) -> PromptWords:
    """Return the words of a prompt language (one of language.PROMPT_LANGUAGES)."""
    return _WORDS[prompt_language]


def category_by_name() -> dict[str, str]:
    """Return the categories by their names in words in every prompt language, for answers that use them."""
    return {name: category for words in _WORDS.values() for category, name in zip(CATEGORIES, words.category_names)}
