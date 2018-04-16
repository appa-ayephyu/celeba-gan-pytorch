#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IFT6135: Representation Learning
Assignment 4: Generative Models

Authors:
    Samuel Laferriere <samuel.laferriere.cyr@umontreal.ca>
    Joey Litalien <joey.litalien@umontreal.ca>
"""

from __future__ import print_function

import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim
from dcgan import DCGAN, Generator, Discriminator
import torchvision.utils

import numpy as np
import pickle
import os, sys
import datetime
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import utils
import argparse


class CelebA(object):
    """Implement DCGAN for CelebA dataset"""

    def __init__(self, train_params, ckpt_params, gan_params):
        # Training parameters
        self.root_dir = train_params['root_dir']
        self.gen_dir = train_params['gen_dir']
        self.batch_size = train_params['batch_size']
        self.train_len = train_params['train_len']
        self.learning_rate = train_params['learning_rate']
        self.momentum = train_params['momentum']
        self.optim = train_params['optim']
        self.use_cuda = train_params['use_cuda']

        # Checkpoint parameters (when, where)
        self.batch_report_interval = ckpt_params['batch_report_interval']
        self.ckpts_path = ckpt_params['ckpts_path']
        self.save_stats_interval = ckpt_params['save_stats_interval']

        # Create directories if they don't exist
        if not os.path.isdir(self.stats_path):
            os.mkdir(self.stats_path)
        if not os.path.isdir(self.ckpts_path):
            os.mkdir(self.ckpts_path)
        if not os.path.isdir(self.gen_dir):
            os.mkdir(self.gen_dir)

        # GAN parameters
        self.gan_type = gan_params['gan_type']
        self.latent_dim = gan_params['latent_dim']

        # Make sure report interval divides total num of batches
        self.num_batches = self.train_len // self.batch_size
        #assert self.num_batches % self.batch_report_interval == 0, \
        #    'Batch report interval must divide total number of batches per epoch'

        # Get ready to ruuummmmmmble
        self.compile()


    def compile(self):
        """Compile model (loss function, optimizers, etc.)"""

        # Create new GAN
        self.gan = DCGAN(self.gan_type, self.latent_dim, self.batch_size,
            self.use_cuda)

        # Set optimizers for generator and discriminator
        if self.optim is 'adam':
            self.G_optimizer = optim.Adam(self.gan.G.parameters(),
                lr=self.learning_rate,
                betas=self.momentum)
            self.D_optimizer = optim.Adam(self.gan.D.parameters(),
                lr=self.learning_rate,
                betas=self.momentum)

        else:
            raise NotImplementedError

        # CUDA support
        if torch.cuda.is_available() and self.use_cuda:
            self.gan = self.gan.cuda()


    def save_stats(self, stats):
        """Save model statistics"""

        fname_pkl = '{}/{}-stats.pkl'.format(self.ckpts_path, self.gan_type)
        print('Saving model statistics to: {}'.format(fname_pkl))
        with open(fname_pkl, 'wb') as fp:
            pickle.dump(stats, fp)


    def train(self, nb_epochs, data_loader):
        """Train model on data"""

        # Initialize tracked quantities and prepare everything
        G_all_losses, D_all_losses, times = [], [], utils.AvgMeter()
        utils.format_hdr(self.gan, self.root_dir, self.train_len)
        start = datetime.datetime.now()

        # Train
        for epoch in range(nb_epochs):
            print('EPOCH {:d} / {:d}'.format(epoch + 1, nb_epochs))
            G_losses, D_losses = utils.AvgMeter(), utils.AvgMeter()
            start_epoch = datetime.datetime.now()

            avg_time_per_batch = utils.AvgMeter()
            # Mini-batch SGD
            for batch_idx, (x, _) in enumerate(data_loader):
                if x.shape[0] != self.batch_size:
                    break
                batch_start = datetime.datetime.now()
                # Print progress bar
                utils.progress_bar(batch_idx, self.batch_report_interval,
                    G_losses.avg, D_losses.avg)

                x = Variable(x)
                if torch.cuda.is_available() and self.use_cuda:
                    x = x.cuda()

                # Update generator every 3x we update discriminator
                D_loss = self.gan.train_D(x, self.D_optimizer, self.batch_size)
                if batch_idx % 3 == 0:
                    G_loss = self.gan.train_G(self.G_optimizer, self.batch_size)
                D_losses.update(D_loss, self.batch_size)
                G_losses.update(G_loss, self.batch_size)

                batch_end = datetime.datetime.now()
                batch_time = int((batch_end - batch_start).total_seconds() * 1000)
                avg_time_per_batch.update(batch_time)

                # Report model statistics
                if batch_idx % self.batch_report_interval == 0 and batch_idx:
                    G_all_losses.append(G_losses.avg)
                    D_all_losses.append(D_losses.avg)
                    utils.show_learning_stats(batch_idx, self.num_batches, G_losses.avg, D_losses.avg, avg_time_per_batch.avg)
                    [k.reset() for k in [G_losses, D_losses, avg_time_per_batch]]

                # Save stats
                if batch_idx % self.save_stats_interval == 0 and batch_idx:
                    stats = dict(G_loss=G_all_losses, D_loss=D_all_losses)
                    self.save_stats(stats)

            # Save model
            utils.clear_line()
            print('Elapsed time for epoch: {}'.format(utils.time_elapsed_since(start_epoch)))
            self.gan.save_model(epoch)

        # Print elapsed time
        elapsed = utils.time_elapsed_since(start)
        print('Training done! Total elapsed time: {}\n'.format(elapsed))

        return G_loss, D_loss


if __name__ == '__main__':

    # Argument parser
    parser = argparse.ArgumentParser(description='Generative adversarial network (GAN) implementation in PyTorch')
    parser.add_argument('-c', '--ckpt',
        help='checkpoint path', metavar='PATH', default='./checkpoints')
    parser.add_argument('-p', '--pretrained',
        help='load pretrained model (generator only)', metavar='PATH')
    parser.add_argument('-t', '--type', help='model type (gan or wgan)')
    parser.add_argument('-r', '--redux', help='train on smaller dataset',
        action='store_true')
    args = parser.parse_args()

    # GAN parameters (type and latent dimension size)
    gan_params = {
        'gan_type': args.type,
        'latent_dim': 100
    }

    # Training parameters (saving directory, learning rate, optimizer, etc.)
    train_params = {
        'root_dir': './../data/celebA_{}'.format('redux' if args.redux else 'all'),
        'gen_dir': './../generated',
        'batch_size': 128,
        'train_len': 10000 if args.redux else 202599,
        'learning_rate': 0.0002,
        'momentum': (0.5, 0.999),
        'optim': 'adam',
        'use_cuda': True
    }

    # Checkpoint parameters (report interval size, directories)
    ckpt_params = {
        'batch_report_interval': 100,
        'ckpts_path': args.ckpt,
        'save_stats_interval': 500
    }

    # Ready to train/test
    gan = CelebA(train_params, ckpt_params, gan_params)
    data_loader = utils.load_dataset(train_params['root_dir'],
        train_params['batch_size'])

    if args.pretrained:
        gan.load_model('dcgan-gen', cpu=True)

    """
    if args.latent_play:
        gan.load_model('dcgan-gen', cpu=True)
        torch.manual_seed(442)
        z0 = gan.gan.create_latent_var(1)
        img = gan.gan.generate_img(z0)
        fname_in = '../play/dim_og.png'
        img = utils.unnormalize(img)
        torchvision.utils.save_image(img, fname_in)
        for i in range(100):
            z1 = z0.clone()
            z = z1[0, i, :, :].data[0][0]
            z1[0, i, :, :] = -np.sign(z) * 3
            print('i={:2d}, z={:2.4f}'.format(i, z))
            img = gan.gan.generate_img(z1)
            img = utils.unnormalize(img)
            fname_in = '../play/dim{:d}.png'.format(i)
            torchvision.utils.save_image(img, fname_in)
            #torchvision.utils.save_image(img, fname_out)

    """
    # for i in range(50):
    #     img = gan.gan.generate_img()
    #     img = utils.unnormalize(img)
    #     fname = '../generated/test{:d}.png'.format(i)
    #     torchvision.utils.save_image(img, fname)
