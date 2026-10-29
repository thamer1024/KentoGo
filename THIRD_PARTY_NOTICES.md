# Third-Party Notices

KentoGo includes files and data from the projects below.
Each part is under its own license, which is given here.

## 1. KaTrain

- Project: KaTrain 1.20.0 — https://github.com/sanderland/katrain
- License: MIT License (the text is below)
- What KentoGo uses:
  - Images `src/kentogo/images/board.png`, `B_stone.png`, `W_stone.png` and
    `hamburger.png` (from `katrain/img`). KaTrain's `CONTRIBUTIONS.md` credits "nimets123"
    for the board and stone graphics, and "waltheri" for one of the wooden board textures.
  - The shape, sizes and colors of the check box in `src/kentogo/gui/check_box.py`
    (from `katrain/gui/widgets/material/checkbox.py`).
  - Colors and board layout values in `src/kentogo/gui/theme.py` and
    `src/kentogo/gui/board_geometry.py` (from `katrain/gui/theme.py` and `katrain/gui/badukpan.py`).
  - Texts in `src/kentogo/quiz/katrain_texts.py`, made from KaTrain's translation files
    by `tools/gen_katrain_texts.py`, and the labels of the settings screens that KaTrain
    also has (such as "KataGo設定" and "設定を更新"), in `src/kentogo/gui/texts.py` (Japanese)
    and in each language file in `src/kentogo/locales`, taken from KaTrain's translation
    files of that language. The translators are listed in KaTrain's `CONTRIBUTIONS.md`.

```
Copyright 2020 Sander Land and/or other authors of the content in this repository.
(See 'CONTRIBUTIONS.md' file for a list of authors as well as other indirect contributors).

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## 2. Noto Sans JP

- Font: Noto Sans JP Regular, version 1.004 (taken from KaTrain 1.20.0, `katrain/fonts`)
- File: `src/kentogo/fonts/NotoSansJP-Regular.otf`
- Copyright © 2014, 2015 Adobe Systems Incorporated (http://www.adobe.com/).
- License: SIL Open Font License, Version 1.1. The full text is in `src/kentogo/fonts/OFL.txt`.

## 2a. Noto Sans CJK SC

- Font: Noto Sans CJK SC Regular, version 1.004 (taken from KaTrain 1.20.0, `katrain/fonts`),
  used for Chinese and Korean.
- File: `src/kentogo/fonts/NotoSansCJKsc-Regular.otf`
- Copyright © 2014, 2015 Adobe Systems Incorporated (http://www.adobe.com/).
- License: SIL Open Font License, Version 1.1. The full text is in `src/kentogo/fonts/OFL.txt`.

## 2b. DejaVu Sans

- Font: DejaVu Sans, version 2.37 — https://dejavu-fonts.github.io/ — used for Turkish and Ukrainian.
- File: `src/kentogo/fonts/DejaVuSans.ttf`
- Copyright (c) 2003 by Bitstream, Inc. Copyright (c) 2006 by Tavmjong Bah. DejaVu changes are
  in public domain.
- License: the Bitstream Vera Fonts license and the Arev Fonts license. The full text is in
  `src/kentogo/fonts/DejaVu-LICENSE.txt`.

## 2c. region-flags (flags of the languages)

- Project: region-flags — https://github.com/fonttools/region-flags (commit of May 2024)
- License: public domain. The project took the flags from Wikimedia Commons and checked that
  they are in the public domain; the flags used here (GB, DE, FR, UA, ES, RU, CN, TW, KR, JP
  and TR) are not among the ones its `COPYING` lists as exempt only under a national law.
- What KentoGo uses: `src/kentogo/images/flags/flag-*.png`, made from the PNG files of
  region-flags by `tools/make_flags.py` (cut into circles).

## 3. goscorer

- Project: goscorer — https://github.com/lightvector/goscorer
- Version: the `main` branch at commit 0ac5f59962a9e40f39f4667645335ba5068acf86 (April 2025)
- License: MIT License (the text is below)
- What KentoGo uses: the file `python/goscorer.py`, unchanged, as
  `src/kentogo/vendor/goscorer.py`. It finds the points that are not territory because of
  seki (and false eyes) in the territory counting practice (see `src/kentogo/seichi/seki.py`).

```
Copyright 2024 David J Wu ("lightvector").

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
