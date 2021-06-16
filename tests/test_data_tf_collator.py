# Copyright 2020 The HuggingFace Team. All rights reserved.
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

import os
import shutil
import tempfile
import unittest

from transformers import BertTokenizer, is_tf_available, set_seed
from transformers.testing_utils import require_tf


if is_tf_available():
    import tensorflow as tf

    from transformers import TFDataCollatorForLanguageModeling


@require_tf
class TFDataCollatorIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdirname = tempfile.mkdtemp()

        vocab_tokens = ["[UNK]", "[CLS]", "[SEP]", "[PAD]", "[MASK]"]
        self.vocab_file = os.path.join(self.tmpdirname, "vocab.txt")
        with open(self.vocab_file, "w", encoding="utf-8") as vocab_writer:
            vocab_writer.write("".join([x + "\n" for x in vocab_tokens]))

    def tearDown(self):
        shutil.rmtree(self.tmpdirname)

    def _test_no_pad_and_pad(self, no_pad_features, pad_features):
        tokenizer = BertTokenizer(self.vocab_file)
        data_collator = TFDataCollatorForLanguageModeling(tokenizer, mlm=False)
        batch = data_collator(no_pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 10)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 10)))

        batch = data_collator(pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 10)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 10)))

        data_collator = TFDataCollatorForLanguageModeling(tokenizer, mlm=False, pad_to_multiple_of=8)
        batch = data_collator(no_pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 16)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 16)))

        batch = data_collator(pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 16)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 16)))

        tokenizer._pad_token = None
        data_collator = TFDataCollatorForLanguageModeling(tokenizer, mlm=False)
        with self.assertRaises(ValueError):
            # Expect error due to padding token missing
            data_collator(pad_features)

        set_seed(42)  # For reproducibility
        tokenizer = BertTokenizer(self.vocab_file)
        data_collator = TFDataCollatorForLanguageModeling(tokenizer)
        batch = data_collator(no_pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 10)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 10)))

        masked_tokens = batch["input_ids"] == tokenizer.mask_token_id
        self.assertTrue(masked_tokens.numpy().any())
        self.assertTrue(all(x == -100 for x in list(batch["labels"][~masked_tokens].numpy())))

        batch = data_collator(pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 10)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 10)))

        masked_tokens = batch["input_ids"] == tokenizer.mask_token_id
        self.assertTrue(masked_tokens.numpy().any())
        self.assertTrue(all(x == -100 for x in list(batch["labels"][~masked_tokens].numpy())))

        data_collator = TFDataCollatorForLanguageModeling(tokenizer, pad_to_multiple_of=8)
        batch = data_collator(no_pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 16)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 16)))

        masked_tokens = batch["input_ids"] == tokenizer.mask_token_id
        self.assertTrue(masked_tokens.numpy().any())
        self.assertTrue(all(x == -100 for x in list(batch["labels"][~masked_tokens].numpy())))

        batch = data_collator(pad_features)
        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 16)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 16)))

        masked_tokens = batch["input_ids"] == tokenizer.mask_token_id
        self.assertTrue(masked_tokens.numpy().any())
        self.assertTrue(all(x == -100 for x in list(batch["labels"][~masked_tokens].numpy())))

    def test_data_collator_for_language_modeling(self):
        no_pad_features = [{"input_ids": list(range(10))}, {"input_ids": list(range(10))}]
        pad_features = [{"input_ids": list(range(5))}, {"input_ids": list(range(10))}]
        self._test_no_pad_and_pad(no_pad_features, pad_features)

        no_pad_features = [list(range(10)), list(range(10))]
        pad_features = [list(range(5)), list(range(10))]
        self._test_no_pad_and_pad(no_pad_features, pad_features)

    def test_nsp(self):
        tokenizer = BertTokenizer(self.vocab_file)
        features = [
            {"input_ids": [0, 1, 2, 3, 4], "token_type_ids": [0, 1, 2, 3, 4], "next_sentence_label": i}
            for i in range(2)
        ]
        data_collator = TFDataCollatorForLanguageModeling(tokenizer)
        batch = data_collator(features)

        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["token_type_ids"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["next_sentence_label"].shape, tf.TensorShape((2,)))

        data_collator = TFDataCollatorForLanguageModeling(tokenizer, pad_to_multiple_of=8)
        batch = data_collator(features)

        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["token_type_ids"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["next_sentence_label"].shape, tf.TensorShape((2,)))

    def test_sop(self):
        tokenizer = BertTokenizer(self.vocab_file)
        features = [
            {
                "input_ids": tf.constant([0, 1, 2, 3, 4]),
                "token_type_ids": tf.constant([0, 1, 2, 3, 4]),
                "sentence_order_label": i,
            }
            for i in range(2)
        ]
        data_collator = TFDataCollatorForLanguageModeling(tokenizer)
        batch = data_collator(features)

        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["token_type_ids"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 5)))
        self.assertEqual(batch["sentence_order_label"].shape, tf.TensorShape((2,)))

        data_collator = TFDataCollatorForLanguageModeling(tokenizer, pad_to_multiple_of=8)
        batch = data_collator(features)

        self.assertEqual(batch["input_ids"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["token_type_ids"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["labels"].shape, tf.TensorShape((2, 8)))
        self.assertEqual(batch["sentence_order_label"].shape, tf.TensorShape((2,)))
