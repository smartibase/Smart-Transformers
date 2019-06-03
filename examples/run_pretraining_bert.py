import argparse
import logging
import math
import time
import torch
import random
import os

from apex import amp
from apex.fp16_utils import FP16_Optimizer
from apex.parallel import DistributedDataParallel as DDP
from logging.handlers import RotatingFileHandler
from tqdm import tqdm
from torch.utils.data import DataLoader
from torch.utils.data.dataset import random_split, Subset
from torch.utils.data.sampler import RandomSampler, BatchSampler
from torch.utils.data.distributed import DistributedSampler

from pytorch_pretrained_bert.datasets import LazyDataset, JSONDataset, BertDataset, PreprocessedBertDataset
from pytorch_pretrained_bert.modeling import BertForPreTraining, BertConfig
from pytorch_pretrained_bert.tokenization import BertTokenizer


def get_args():
    parser = argparse.ArgumentParser()

    exp_group = parser.add_argument_group('exp', 'exp configuration')
    exp_group.add_argument('--data-path', type=str, default='/home/hdvries/data/preprocessed_all.txt',
                           help='path to dataset')
    exp_group.add_argument('--exp-dir', type=str, default='/home/hdvries/experiments/test',
                           help='path to dataset')
    exp_group.add_argument('--report-iter', type=int, default=100,
                           help='Report statistics every `report_iter` iterations')
    exp_group.add_argument('--save-iter', type=int, default=10000,
                           help='Save checkpoint every `save_iter` iterations')
    exp_group.add_argument('--seed', type=int, default=1,
                           help='Random seed of experiment..')

    model_group = parser.add_argument_group('model', 'model configuration')

    model_group.add_argument('--attention-dropout', type=float, default=0.1,
                       help='dropout probability for attention weights')
    model_group.add_argument('--num-attention-heads', type=int, default=16,
                       help='num of transformer attention heads')
    model_group.add_argument('--hidden-size', type=int, default=1024,
                       help='transformer hidden size')
    model_group.add_argument('--intermediate-size', type=int, default=4096,
                       help='transformer embedding dimension for FFN')
    model_group.add_argument('--num-layers', type=int, default=24,
                       help='number of layers')
    model_group.add_argument('--layernorm-epsilon', type=float, default=1e-12,
                       help='layer norm epsilon')
    model_group.add_argument('--hidden-dropout', type=float, default=0.0,
                       help='dropout probability for hidden state transformer')
    model_group.add_argument('--max-position-embeddings', type=int, default=512,
                       help='maximum number of position embeddings to use')

    opt_group = parser.add_argument_group('train', 'optimization configuration')

    opt_group.add_argument('--batch-size', type=int, default=4,
                       help='Data Loader batch size')
    opt_group.add_argument('--num-workers', type=int, default=1,
                           help='Number of workers in DataLoader')
    opt_group.add_argument('--weight-decay', type=float, default=0.01,
                       help='weight decay coefficient for L2 regularization')
    opt_group.add_argument('--train-iters', type=int, default=1000000,
                           help='Number of training iterations')
    opt_group.add_argument('--use-fp16', action='store_true',
                           help='Training with FP16?')

    return parser.parse_args()


def calc_loss(scores, labels):
    loss_fn = torch.nn.CrossEntropyLoss(ignore_index=-1)
    flat_scores = scores.view(-1, scores.shape[-1])
    flat_labels = labels.view(-1)
    # _, ind = flat_scores.max(1)
    # accuracy = 0.0
    # if float((sum(flat_labels != -1))) > 0.0:
    #     accuracy = float(sum(flat_labels==ind))/float((sum(flat_labels != -1)))
    loss = loss_fn(flat_scores, flat_labels)
    return loss


def eval_epoch(model, iterator):
    model.eval()

    total_loss = 0.0
    n_iters = 0

    with torch.no_grad():
        for batch in tqdm(iterator):
            n_iters += 1

            # move to batch to gpu
            for k, v in batch.items():
                batch[k] = batch[k].cuda()

            # forward pass
            loss = model.forward(batch['input_tokens'],
                                 batch['segment_ids'],
                                 batch['attention_mask'],
                                 batch['lm_labels'],
                                 batch['is_random_next'])
            total_loss += loss.item()
    return total_loss/n_iters


def create_logger(save_path):
    logger = logging.getLogger()
    # Debug = write everything
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    file_handler = RotatingFileHandler(save_path, 'a', 1000000, 1)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

    return logger


if __name__ == '__main__':
    args = get_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed(args.seed)

    rank = 0
    local_rank = 0
    world_size = 1

    distributed = ('WORLD_SIZE' in os.environ) and (int(os.environ['WORLD_SIZE']) > 1)
    if 'WORLD_SIZE' in os.environ:
        torch.distributed.init_process_group(backend='nccl',
                                             init_method='env://')
        local_rank = int(os.environ['LOCAL_RANK'])
        torch.cuda.set_device(local_rank)
        rank = int(os.environ['RANK'])

    if os.path.exists(args.exp_dir):
        raise ValueError('Experiment directory `%s` already exists' % args.exp_dir)

    # create directories to store logs and checkpoints
    os.mkdir(args.exp_dir)
    os.mkdir(os.path.join(args.exp_dir, 'checkpoints'))
    os.mkdir(os.path.join(args.exp_dir, 'logs'))

    logger = create_logger(os.path.join(args.exp_dir, 'logs', 'log.%s.txt' % rank))
    logger.info(args)

    logger.info('Loading tokenizer...')
    tokenizer = BertTokenizer.from_pretrained('bert-large-uncased', cache_dir='./data')
    vocab_size = len(tokenizer.vocab)

    logger.info('Building model...')
    model_config = BertConfig(vocab_size,
                              hidden_size=args.hidden_size,
                              num_hidden_layers=args.num_layers,
                              num_attention_heads=args.num_attention_heads,
                              intermediate_size=args.intermediate_size)
    model = BertForPreTraining(model_config)
    logger.info(' > number of parameters: {}'.format(
        sum([p.nelement() for p in model.parameters()])))
    if args.use_fp16:
        model = model.half()
    model.cuda()

    # optimizer = FusedAdam(model.parameters(), lr=1e-5)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-6, weight_decay=args.weight_decay)
    if args.use_fp16:
        optimizer = FP16_Optimizer(optimizer, dynamic_loss_scale=True)

    if distributed:
        model = DDP(model, delay_allreduce=True)

    logger.info('Loading data and creating iterators...')
    dataset = LazyDataset(args.data_path, use_mmap=True)
    dataset = JSONDataset(dataset)
    dataset = PreprocessedBertDataset(dataset, tokenizer)

    num_train_examples = math.ceil(len(dataset)*0.9)
    train_set, valid_set = random_split(dataset, [num_train_examples, len(dataset) - num_train_examples])
    # train_set = Subset(dataset, range(12))
    # valid_set = Subset(dataset, [i+12 for i in range(12)])

    if distributed:
        train_sampler = DistributedSampler(train_set)
        valid_sampler = DistributedSampler(valid_set)
    else:
        train_sampler = RandomSampler(train_set)
        valid_sampler = RandomSampler(valid_set)

    train_sampler = BatchSampler(train_sampler, args.batch_size, drop_last=True)
    train_loader = DataLoader(train_set, batch_sampler=train_sampler, num_workers=args.num_workers, pin_memory=True)

    valid_sampler = BatchSampler(valid_sampler, args.batch_size, drop_last=True)
    valid_loader = DataLoader(valid_set, batch_sampler=valid_sampler, num_workers=args.num_workers, pin_memory=True)

    n_iters = args.train_iters
    epoch = 1

    train_iterator = iter(train_loader)
    train_lm_loss, train_nsp_loss, process_time = 0.0, 0.0, time.time()
    for it in range(1, n_iters+1):
        try:
            batch = next(train_iterator)
        except StopIteration:
            train_iterator = iter(train_loader)
            logger.info("End of epoch %s" % str(epoch))
            epoch += 1
            batch = next(train_iterator)

        # move to batch to gpu
        for k, v in batch.items():
            batch[k] = batch[k].cuda()

        lm_scores, nsp_scores = model.forward(batch['input_tokens'],
                                              batch['segment_ids'],
                                              batch['attention_mask'])
        lm_loss = calc_loss(lm_scores.view(-1, lm_scores.shape[-1]), batch['lm_labels'].view(-1))
        nsp_loss = calc_loss(nsp_scores.view(-1, 2), batch['is_random_next'].view(-1))
        loss = lm_loss + nsp_loss
        train_nsp_loss += nsp_loss.item()
        train_lm_loss += lm_loss.item()

        if args.use_fp16:
            # backward pass
            optimizer.backward(loss)
        else:
            loss.backward()

        # optimizer step
        optimizer.step()
        optimizer.zero_grad()

        # report statistics every `args.report_iter` iterations
        if it % args.report_iter == 0:
            log_str  = ' epoch{:2d} |'.format(epoch)
            log_str += ' iteration: {:7d} |'.format(it)
            log_str += ' train_lm_loss: {:.3E} |'.format(train_lm_loss/args.report_iter)
            log_str += ' train_nsp_loss: {:.3E} |'.format(train_nsp_loss/args.report_iter)
            log_str += ' time per batch: {:4F}ms |'.format(1000*(time.time() - process_time)/args.report_iter)
            logger.info(log_str)
            train_lm_loss, train_nsp_loss, process_time = 0.0, 0.0, time.time()

        # save checkpoint every `args.save_iter` iterations
        if it % args.save_iter == 0 and rank == 0:
            save_dict = dict()
            save_dict['model'] = model.state_dict()
            save_dict['opt'] = optimizer.state_dict()
            save_dict['it'] = it
            save_path = os.path.join(args.exp_dir, 'checkpoints', 'chkpt.%s.pt' % str(it))
            torch.save(save_dict, save_path)
            logger.info('Saved checkpoint to `%s`' % save_path)











