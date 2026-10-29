"""The language of the AI commentary: of the prompt, of the AI's answer, and of the words KentoGo writes.

There are two prompts: the Japanese one (PROMPT_JAPANESE), used when the screens are in
Japanese, and the English one (PROMPT_ENGLISH), used for every other language. The English
prompt asks the AI to answer in the language of the screens. The words that KentoGo itself
writes into the SGF file with the answer (the labels of the fields, the table of losses, the
names of the categories) are in the language of the screens too: the screens make them from
their texts (see gui.commentary_texts), and the Japanese ones are the default.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.record.ai_comment import AI_HEADER, AI_HEADER_EN, REVIEW_HEADER, REVIEW_HEADER_EN

PROMPT_JAPANESE = "jp"
PROMPT_ENGLISH = "en"
PROMPT_LANGUAGES = (PROMPT_JAPANESE, PROMPT_ENGLISH)

# The categories of mistakes. The AI answers with these names, whatever its language; the
# prompt and the SGF file show them in words (in the same order).
CATEGORIES = ("missed_urgent_point", "no_pressure", "misjudged_size", "misread", "wrong_direction")

# The headers of the commentary and of the review in the SGF file (see record.ai_comment), for each prompt:
# Japanese with the Japanese prompt, English with the English one. KentoGo finds both.
COMMENT_HEADERS = {PROMPT_JAPANESE: (AI_HEADER, REVIEW_HEADER), PROMPT_ENGLISH: (AI_HEADER_EN, REVIEW_HEADER_EN)}


@dataclass(frozen=True)
class CommentLabels:
    """The words that KentoGo writes into the SGF file around the AI's answer (see commentary.sgf_writer).

    The texts with {values} are filled in by the writer. The defaults are the Japanese words.

    Attributes:
        bullet: The mark at the start of each line of a field and of each count of losses.
        situation, category, what_happened, aim, lesson: The labels of the fields of a move.
        category_counts, main_issue, next_focus, loss_comparison: The labels of the fields of the review.
        move_line: The first line of a move: {played} (actual or taken_back), {move}, {best} and {loss}.
        actual: A move played in the game.
        taken_back: A move that KaTrain took back in its teaching mode.
        no_best: Instead of a best move that is not known.
        review_title: The first line of the review: {count} moves.
        review_move: A line of the review for a move: {number}, {color}, {taken_back} (" " + taken_back, or ""),
            {loss} and {best}.
        loss_title, loss_note: The title of the counts of losses, and the line that explains them.
        loss_line: A count of losses (after the bullet): {size} points or more, {count} times, and {targets} (loss_targets or "").
        loss_targets: The targets of the rank: {goal} and {limit}.
        no_targets: Instead of the targets, when the rank is not in the table: {rank}.
        no_rank: The rank in no_targets when it was not given.
        black, white: The names of the colors.
        categories: The names of CATEGORIES, in the same order.
        move_header, review_header: The headers of the commentary and of the review (see COMMENT_HEADERS).
    """

    bullet: str = "・"
    situation: str = "局面"
    category: str = "分類"
    what_happened: str = "何が起きたか"
    aim: str = "最善手と予想手順の狙い"
    lesson: str = "教訓"
    category_counts: str = "分類の集計"
    main_issue: str = "一番の課題"
    next_focus: str = "次の対局で意識すること"
    loss_comparison: str = "損失の回数"
    move_line: str = "({played} {move} → 最善 {best},損失 {loss}目)"
    actual: str = "実戦"
    taken_back: str = "待ったの手"
    no_best: str = "記載なし"
    review_title: str = "損失目数が大きい上位{count}手を特定しました."
    review_move: str = " - 第 {number} 手目 ({color}{taken_back}) (損失: {loss}目 / 最善手: {best})"
    loss_title: str = "■ この対局の損失の回数"
    loss_note: str = "(KaTrainの損失目数で数えた,この対局のあなたの手の回数.形勢が決まった後の手も含みます)"
    loss_line: str = "{size}目以上: {count}回{targets}"
    loss_targets: str = "(目標 {goal}回,超えてはいけない {limit}回)"
    no_targets: str = "({rank}の行が目標表に無いため,目標との比較はありません)"
    no_rank: str = "段級位"
    black: str = "黒"
    white: str = "白"
    categories: tuple[str, ...] = ("急場の見逃し", "響かない手", "大きさの判断ミス", "読み違い", "方向違い")
    move_header: str = AI_HEADER
    review_header: str = REVIEW_HEADER

    def category_name(self, category: str) -> str:
        """Return the name of a category (one of CATEGORIES), or the category itself if it is not one of them."""
        return self.categories[CATEGORIES.index(category)] if category in CATEGORIES else category

    def color_name(self, color: str) -> str:
        """Return the name of a color, "B" or "W"."""
        return self.black if color == "B" else self.white


@dataclass(frozen=True)
class CommentaryLanguage:
    """The language of the AI commentary.

    Attributes:
        prompt: The prompt to use, one of PROMPT_LANGUAGES.
        answer: The language of the AI's answer, in English (such as "German"). The English
            prompt asks for it; the Japanese prompt always asks for Japanese.
        labels: The words that KentoGo writes into the SGF file.
    """

    prompt: str = PROMPT_JAPANESE
    answer: str = "Japanese"
    labels: CommentLabels = CommentLabels()


JAPANESE = CommentaryLanguage()
