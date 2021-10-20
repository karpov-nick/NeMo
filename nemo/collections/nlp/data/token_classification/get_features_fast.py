# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
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

from typing import List, Optional

import torch
from torch.nn.utils.rnn import pad_sequence

from nemo.collections.common.tokenizers.tokenizer_spec import TokenizerSpec
from nemo.collections.nlp.data.data_utils.data_preprocessing import get_stats
from nemo.utils import logging


def bucketize_map(tensor, mapping):
    keys, values = zip(*sorted(mapping.items()))
    keys, values = torch.tensor(keys), torch.tensor(values)
    index = torch.bucketize(tensor, keys)
    return values[index]


def encode_labels(label_lines, ids, pad_label, subtokens_mask, not_text_mask):
    pad_id = ids[pad_label]
    label_ids = pad_sequence(
        [torch.tensor([ids[lbl] for lbl in line]) for line in label_lines],
        batch_first=True,
        padding_value=pad_id,
    )
    row_queries = torch.arange(label_ids.shape[0], dtype=torch.int64, device=label_ids.device).tile(
        1, subtokens_mask.shape[1]
    )
    col_queries = subtokens_mask[:, 1:].cumsum(1) - 1
    result = torch.cat(
        [
            torch.full([label_ids.shape[0], 1], pad_id, dtype=label_ids.dtype, device=label_ids.device),
            label_ids[row_queries, col_queries]
        ],
        1
    )
    result[not_text_mask] = pad_id
    return result


def get_features(
    queries: List[str],
    max_seq_length: int,
    tokenizer: TokenizerSpec,
    punct_label_ids: dict = None,
    capit_label_ids: dict = None,
    pad_label: str = 'O',
    punct_labels_lines=None,
    capit_labels_lines=None,
    ignore_extra_tokens=False,
    ignore_start_end: Optional[bool] = False,
):
    """
    Processes the data and returns features.
    Args:
        queries: text sequences
        max_seq_length: max sequence length minus 2 for [CLS] and [SEP]
        tokenizer: such as AutoTokenizer
        pad_label: pad value use for labels. By default, it's the neutral label.
        punct_label_ids: dict to map punctuation labels to label ids.
            Starts with pad_label->0 and then increases in alphabetical order.
            Required for training and evaluation, not needed for inference.
        capit_label_ids: dict to map labels to label ids. Starts
            with pad_label->0 and then increases in alphabetical order.
            Required for training and evaluation, not needed for inference.
        punct_labels: list of labels for every word in a sequence (str)
        capit_labels: list of labels for every word in a sequence (str)
        ignore_extra_tokens: whether to ignore extra tokens in the loss_mask
        ignore_start_end: whether to ignore bos and eos tokens in the loss_mask
    Returns:
        all_input_ids: input ids for all tokens
        all_segment_ids: token type ids
        all_input_mask: attention mask to use for BERT model
        all_subtokens_mask: masks out all subwords besides the first one
        all_loss_mask: loss mask to mask out tokens during training
        punct_all_labels: all labels for punctuation task (ints)
        capit_all_labels: all labels for capitalization task (ints)
        punct_label_ids: label (str) to id (int) map for punctuation task
        capit_label_ids: label (str) to id (int) map for capitalization task
    """
    vocab = tokenizer.tokenizer.get_vocab()
    token_id_2_whether_word_starts = {
        v: not k.startswith('##') and not(len(k) > 1 and k[0] == '[') for k, v in vocab.items()
    }
    input_ids, segment_ids, input_mask = tokenizer.tokenizer(
        queries, return_tensors='pt', truncation=True, max_length=max_seq_length, padding=True
    )
    subtokens_mask = bucketize_map(input_ids, token_id_2_whether_word_starts)
    special_tokens_mask = input_ids.eq(tokenizer.cls_id) | input_ids.eq(tokenizer.sep_id)
    if ignore_extra_tokens:
        if ignore_start_end:
            loss_mask = subtokens_mask.detach().clone()
        else:
            loss_mask = subtokens_mask | special_tokens_mask
    else:
        if ignore_start_end:
            loss_mask = input_mask.bool() & ~special_tokens_mask
        else:
            loss_mask = input_mask.bool()
    not_text_mask = ~input_mask.bool() | special_tokens_mask
    punct_labels = encode_labels(punct_labels_lines, punct_label_ids, pad_label, subtokens_mask, not_text_mask)
    capit_labels = encode_labels(capit_labels_lines, capit_label_ids, pad_label, subtokens_mask, not_text_mask)
    return input_ids, segment_ids, input_mask, subtokens_mask, loss_mask, punct_labels, capit_labels