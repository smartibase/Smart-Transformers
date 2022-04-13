import json
import os
import torch
import unittest

import numpy as np

from datasets import load_dataset
from transformers import AutoTokenizer

from utils_test_tokenizer import MMapIndexedDataset

# TO PORT ON transformers.test_utils ?

class BigScienceTokenizationTest(unittest.TestCase):
    """
        The goal here is to compare some text that has been tokenized by a model trained 
        using Megatron-LM. For now:
            - Read the tokenized text (.bin file) + the raw text
            - Load a tokenizer from the hub (fast tokenizer or python tokenizer)
        
        Tokenizer used during training:
            - https://huggingface.co/bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles
        Tokenizer that has been pushed to the hub:
            - https://huggingface.co/bigscience/tokenizer/
        
        # TODO design a test that loads both tokenizers and gets a dataset from datasets to compare the tokenizations
        
        This code is not device agnostic --> figure out what to do? / for now I am adding some decorators to check whether the data/tokenizers exists
    """

    def setUp(self):
        super().setUp()
        self.path_tokenizer = "bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles"
        self.path_bin_data = "/home/thomwolf/bigscience/megatron-debug/preprocessed_dataset_text_document"
        self.path_json_dataset = "/home/thomwolf/bigscience/megatron-debug/train_dataset.jsonl"
        self.path_local_tokenizer = "/home/younes/Desktop/Work/data/megatron-debug/bigscience176b-tokenizer"
        self.NB_SENTENCES = 2
    
    def file_exists(self):
        return os.path.isfile(self.path_bin_data+'.idx') and os.path.isfile(self.path_bin_data+'.bin') and os.path.isfile(self.path_json_dataset)
    
    def local_tokenizer_exists(self):
        return os.path.isfile(os.path.join(self.path_local_tokenizer, 'tokenizer.json'))

    def test_load_tokenizer(self):
        """
            Assert that we can correctly load the tokenizer that is available on the Hub
        """
        try:
            _ = AutoTokenizer.from_pretrained(self.path_tokenizer)
        except:
            self.fail("Failed loading tokenizer")
    
    @unittest.skipUnless(local_tokenizer_exists, "requires tokenizer stored in the local machine!")
    def test_load_local_tokenizer(self):
        """
            Try to load the tokenizer from: https://huggingface.co/bigscience/tokenizer/ that I have copied in my local directory
        """
        try:
            _ = AutoTokenizer.from_pretrained(self.path_local_tokenizer)
        except:
            self.fail("Failed loading tokenizer")

    @unittest.skipUnless(file_exists, "requires data stored in the local machine!")
    def test_load_custom_text_and_bin_data(self):
        """
            Assert that we can correctly load the bin and json data (Thomas Wolf's data)
        """
        with open(self.path_json_dataset) as f:
            json_data = [json.loads(line) for line in f]
            self.assertTrue(json_data)
        with open(self.path_bin_data+'.bin', mode='rb') as file: # b is important -> binary
            bin_data = file.read()
            self.assertTrue(bin_data)
        with open(self.path_bin_data+'.idx', mode='rb') as file: # b is important -> binary
            bin_data = file.read()
            self.assertTrue(bin_data)
    
    # @unittest.skip("demonstrating skipping")
    @unittest.skipUnless(file_exists, "requires data stored in the local machine!")
    def test_encodings_from_bin_data(self):
        """
            Assert that the created tokens are the same than the one created statically on the test data (Thomas Wolf's data)
        """
        tokenizer = AutoTokenizer.from_pretrained(self.path_tokenizer)

        with open(self.path_json_dataset) as f:
            input_text = [json.loads(line)['text']+tokenizer.eos_token for line in f][:self.NB_SENTENCES]
        
        mmapdataset = MMapIndexedDataset(self.path_bin_data)

        computed_tokens = list(map(tokenizer.encode, input_text))
        _ = list(map(np.testing.assert_equal, mmapdataset[:self.NB_SENTENCES], computed_tokens)) # if this passes then the tests pass
        # self.assertListEqual(computed_tokens, mmapdataset[:self.NB_SENTENCES])

        decoded_tokens = list(map(tokenizer.decode, mmapdataset[:self.NB_SENTENCES]))
        self.assertListEqual(decoded_tokens, input_text)

        
    @unittest.skipUnless(file_exists and local_tokenizer_exists, "requires data stored in the local machine!")
    def test_local_tokenizer_with_bin_data(self):
        """
            Tests the tokenizer available on the hub:
                - bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles
            On the bin data (local test data from Thomas Wolf)
        """
        local_tokenizer = AutoTokenizer.from_pretrained(self.path_local_tokenizer)

        with open(self.path_json_dataset) as f:
            input_text = [json.loads(line)['text']+local_tokenizer.eos_token for line in f][:self.NB_SENTENCES]
        
        mmapdataset = MMapIndexedDataset(self.path_bin_data)

        computed_tokens_with_local_tokenizer = list(map(local_tokenizer.encode, input_text))
        _ = list(map(np.testing.assert_equal, mmapdataset[:self.NB_SENTENCES], computed_tokens_with_local_tokenizer))

        decoded_tokens_with_local_tokenizer = list(map(local_tokenizer.decode, mmapdataset[:self.NB_SENTENCES]))
        self.assertListEqual(decoded_tokens_with_local_tokenizer, input_text)

    def test_encodings_from_xnli_dataset(self):
        """
            Tests the tokenizer downloaded from here:
                - https://huggingface.co/bigscience/tokenizer/ 
            On the bin data (local test data from Thomas Wolf)
        """
        tokenizer = AutoTokenizer.from_pretrained(self.path_tokenizer)
        ds = load_dataset("xnli", "all_languages", split="test", streaming=True)
        
        sample_data = next(iter(ds))['premise'] # pick up one data
        input_text = list(sample_data.values())

        output_tokens = list(map(tokenizer.encode, input_text))
        predicted_text = list(map(lambda x : tokenizer.decode(x, clean_up_tokenization_spaces=False), output_tokens))
        self.assertListEqual(predicted_text, input_text)
    
    @unittest.skipUnless(local_tokenizer_exists, "requires tokenizer stored in the local machine!")
    def test_encodings_from_xnli_dataset_with_local_tokenizer(self):
        """
            Tests the tokenizer downloaded from here:
                - https://huggingface.co/bigscience/tokenizer/ 
            On one sample of xnli dataset, that contains sentences in various languages
        """
        tokenizer = AutoTokenizer.from_pretrained(self.path_local_tokenizer)
        ds = load_dataset("xnli", "all_languages", split="test", streaming=True)
        
        sample_data = next(iter(ds))['premise'] # pick up one data
        input_text = list(sample_data.values())

        output_tokens = list(map(tokenizer.encode, input_text))
        predicted_text = list(map(lambda x : tokenizer.decode(x, clean_up_tokenization_spaces=False), output_tokens))
        self.assertListEqual(predicted_text, input_text) 


if __name__ == '__main__':
    unittest.main()