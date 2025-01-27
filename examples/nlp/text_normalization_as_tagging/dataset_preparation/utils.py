# Copyright (c) 2022, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import re
from typing import Tuple

from nemo.collections.nlp.data.text_normalization_as_tagging.utils import split_text_by_isalpha, spoken_preprocessing

"""Utility functions for Thutmose Tagger data preparation."""


def get_src_and_dst_for_alignment(
    semiotic_class: str, written: str, spoken: str, lang: str
) -> Tuple[str, str, str, str]:
    """Tokenize written and spoken span.
        Args:
            semiotic_class: str - lowercase semiotic class, ex. "cardinal"
            written: str - written form, ex. "2015 году"
            spoken: str - spoken form, ex. "две тысячи пятнадцатом году"
            lang: str - language
        Return:
            src: str - written part, where digits and foreign letters are tokenized by characters, ex. "2 0 1 5"
            dst: str - spoken part tokenized by space, ex. "две тысячи пятнадцатом"
            same_begin: str
            same_end: str
    """
    written = written.casefold()
    # ATTENTION!!! This is INPUT transformation! Need to do the same at inference time!
    spoken = spoken_preprocessing(spoken)

    # remove same fragments at the beginning or at the end of spoken and written form
    written_parts = written.split()
    spoken_parts = spoken.split()
    same_from_begin = 0
    same_from_end = 0
    for i in range(min(len(written_parts), len(spoken_parts))):
        if written_parts[i] == spoken_parts[i]:
            same_from_begin += 1
        else:
            break
    for i in range(min(len(written_parts), len(spoken_parts))):
        if written_parts[-i - 1] == spoken_parts[-i - 1]:
            same_from_end += 1
        else:
            break
    same_begin = written_parts[0:same_from_begin]
    same_end = []
    if same_from_end == 0:
        written = " ".join(written_parts[same_from_begin:])
        spoken = " ".join(spoken_parts[same_from_begin:])
    else:
        written = " ".join(written_parts[same_from_begin:-same_from_end])
        spoken = " ".join(spoken_parts[same_from_begin:-same_from_end])
        same_end = written_parts[-same_from_end:]

    fragments = list(split_text_by_isalpha(written))
    written_tokens = []
    for frag in fragments:
        if frag.isalpha():
            if semiotic_class == "plain" or semiotic_class == "letters" or semiotic_class == "electronic":
                chars = list(frag.strip())
                chars[0] = "_" + chars[0]  # prepend first symbol of a word with underscore
                chars[-1] = chars[-1] + "_"  # append underscore to the last symbol
                written_tokens += chars
            else:
                written_tokens.append("_" + frag + "_")
        else:
            chars = list(frag.strip().replace(" ", ""))
            if len(chars) > 0:
                chars[0] = "_" + chars[0]  # prepend first symbol of a non-alpha fragment with underscore
                chars[-1] = chars[-1] + "_"  # append underscore to the last symbol of a non-alpha fragment
                written_tokens += chars
    written_str = " ".join(written_tokens)

    # _н_ _._ _г_ _._ => _н._ _г._
    written_str = re.sub(
        r"([abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя])_ _\._", r"\g<1>._", written_str
    )
    # _тыс_ _. $ => _тыс._ _$
    written_str = re.sub(
        r"([abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя])_ _\. ([^_])]", r"\g<1>._ _\g<2>", written_str
    )

    if semiotic_class == "ordinal":
        #  _8 2 -_ _ом_  =>  _8 2-ом_
        written_str = re.sub(
            r"([\d]) -_ _([abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя]+)_",
            r"\g<1>-\g<2>_",
            written_str,
        )
        #  _8 8_ _й_       _8 8й_
        written_str = re.sub(
            r"([\d])_ _([abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя]+)_", r"\g<1>\g<2>_", written_str
        )

    if semiotic_class == "cardinal":
        #  _2 5 -_ _ти_ => _2 5-ти_
        written_str = re.sub(r"([\d]) -_ _(ти)_", r"\g<1>-\g<2>_", written_str)
        written_str = re.sub(r"([\d]) -_ _(и)_", r"\g<1>-\g<2>_", written_str)
        written_str = re.sub(r"([\d]) -_ _(мя)_", r"\g<1>-\g<2>_", written_str)
        written_str = re.sub(r"([\d]) -_ _(ех)_", r"\g<1>-\g<2>_", written_str)

    #  _i b m_ _'_ _s_ =>  _i b m's_
    if lang == "en":
        written_str = re.sub(r"_ _'_ _s_", r"'s_", written_str)

    if semiotic_class == "date" and lang == "en":
        #  _1 9 8 0_ _s_ =>  _1 9 8 0s_
        written_str = re.sub(r"([\d])_ _s_", r"\g<1>s_", written_str)
        #  _1 9 5 0 '_ _s_ =>  _1 9 5 0's_
        written_str = re.sub(r"([\d]) '_ _s_", r"\g<1>'s_", written_str)
        #  _wednesday_ _2 6_ _th_ _september_ _2 0 1 2_ =>  _wednesday_ _2 6th_ _september_ _2 0 1 2_
        written_str = re.sub(r"([\d])_ _th_", r"\g<1>th_", written_str)
        #  _wednesday_ _may_ _2 1_ _st_ _, 2 0 1 4_ => _wednesday_ _may_ _2 1st_ _, 2 0 1 4_
        written_str = re.sub(r"([\d])_ _st_", r"\g<1>st_", written_str)
        # _wednesday_ _2 3_ _rd_ _july_ _2 0 1 4_ => _wednesday_ _2 3rd_ _july_ _2 0 1 4_
        written_str = re.sub(r"([\d])_ _rd_", r"\g<1>rd_", written_str)
        # _wednesday_ _2 2_ _nd_ _july_ _2 0 1 4_ => _wednesday_ _2 2nd_ _july_ _2 0 1 4_
        written_str = re.sub(r"([\d])_ _nd_", r"\g<1>nd_", written_str)

        written_str = re.sub(r"_mon_ _\. ", r"_mon._ ", written_str)
        written_str = re.sub(r"_tue_ _\. ", r"_tue._ ", written_str)
        written_str = re.sub(r"_wen_ _\. ", r"_wen._ ", written_str)
        written_str = re.sub(r"_thu_ _\. ", r"_thu._ ", written_str)
        written_str = re.sub(r"_fri_ _\. ", r"_fri._ ", written_str)
        written_str = re.sub(r"_sat_ _\. ", r"_sat._ ", written_str)
        written_str = re.sub(r"_sun_ _\. ", r"_sun._ ", written_str)

        written_str = re.sub(r"_jan_ _\. ", r"_jan._ ", written_str)
        written_str = re.sub(r"_feb_ _\. ", r"_feb._ ", written_str)
        written_str = re.sub(r"_mar_ _\. ", r"_mar._ ", written_str)
        written_str = re.sub(r"_apr_ _\. ", r"_apr._ ", written_str)
        written_str = re.sub(r"_may_ _\. ", r"_may._ ", written_str)
        written_str = re.sub(r"_jun_ _\. ", r"_jun._ ", written_str)
        written_str = re.sub(r"_jul_ _\. ", r"_jul._ ", written_str)
        written_str = re.sub(r"_aug_ _\. ", r"_aug._ ", written_str)
        written_str = re.sub(r"_sep_ _\. ", r"_sep._ ", written_str)
        written_str = re.sub(r"_oct_ _\. ", r"_oct._ ", written_str)
        written_str = re.sub(r"_nov_ _\. ", r"_nov._ ", written_str)
        written_str = re.sub(r"_dec_ _\. ", r"_dec._ ", written_str)

    if semiotic_class == "date" and lang == "ru":
        # _1 8 . 0 8 . 2 0 0 1_  =>  _1 8_ .08. _2 0 0 1_
        # _1 8 / 0 8 / 2 0 0 1_  =>  _1 8_ /08/ _2 0 0 1_
        # _1 8 - 0 8 - 2 0 0 1_  =>  _1 8_ -08- _2 0 0 1_
        written_str = re.sub(r"([\d]) \. ([01]) ([0123456789]) \. ([\d])", r"\g<1>_ .\g<2>\g<3>. _\g<4>", written_str)
        written_str = re.sub(r"([\d]) / ([01]) ([0123456789]) / ([\d])", r"\g<1>_ /\g<2>\g<3>/ _\g<4>", written_str)
        written_str = re.sub(r"([\d]) - ([01]) ([0123456789]) - ([\d])", r"\g<1>_ -\g<2>\g<3>- _\g<4>", written_str)
        # _1 8 . 8 . 2 0 0 1_  =>  _1 8_ .8. _2 0 0 1_
        # _1 8 / 8 / 2 0 0 1_  =>  _1 8_ /8/ _2 0 0 1_
        # _1 8 - 8 - 2 0 0 1_  =>  _1 8_ -8- _2 0 0 1_
        written_str = re.sub(r"([\d]) \. ([123456789]) \. ([\d])", r"\g<1>_ .\g<2>. _\g<3>", written_str)
        written_str = re.sub(r"([\d]) / ([123456789]) / ([\d])", r"\g<1>_ /\g<2>/ _\g<3>", written_str)
        written_str = re.sub(r"([\d]) - ([123456789]) - ([\d])", r"\g<1>_ -\g<2>- _\g<3>", written_str)

    if semiotic_class == "money":
        # if a span start with currency, move it to the end
        #  "_$ 2 5_"  => "_2 5_ _$<<"    #<< means "at post-processing move to the beginning of th semiotic span"
        written_str = re.sub(
            r"^(_[^0123456789abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя]) ([\d].*)$",
            r"_\g<2> \g<1><<",
            written_str,
        )

        #  "_us_ _$ 7 0 0_"  => "_us__$ 7 0 0_"
        written_str = re.sub(r"^_us_ _\$ ([\d].*)$", r"_\g<1> _us__$<<", written_str)

        #  "_2 5 $_"  => "_2 5_ _$_"    #insert space between last digit and dollar sign
        written_str = re.sub(
            r"([\d]) ([^0123456789abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя_]_)",
            r"\g<1>_ _\g<2>",
            written_str,
        )

    if semiotic_class == "time":
        # "_pm_ _1 0_" => "_1 0_ _pm_<<"
        written_str = re.sub(r"^(_[ap]m_) (_[\d].*)$", r"\g<2> \g<1><<", written_str)

        # "_8 : 0 0_ _a._ _m._  => _8:00_ _a._ _m._"
        # "_1 2 : 0 0_ _a._ _m._  => _1 2:00_ _a._ _m._"
        written_str = re.sub(r"(\d) [:.] 0 0_", r"\g<1>:00_", written_str)

        # "_2 : 4 2 : 4 4_" => "_2: 4 2: 4 4_"
        written_str = re.sub(r"(\d) [:.] ", r"\g<1>: ", written_str)

    if semiotic_class == "measure":
        #  "_6 5 8_ _см_ _³ ._" => " _6 5 8_ _³> _см._"
        #  > means "at post-processing swap with the next token to the right"
        written_str = re.sub(
            r"(_[abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя.]+_) (_[³²]_?)",
            r"\g<2>> \g<1>",
            written_str,
        )

    return written_str, spoken, " ".join(same_begin), " ".join(same_end)
