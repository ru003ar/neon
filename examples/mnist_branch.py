#!/usr/bin/env python
# ----------------------------------------------------------------------------
# Copyright 2015 Nervana Systems Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------------------------------------------------------
"""
Example that trains a small multi-layer perceptron with fully connected layers
on MNIST.

This example has some command line arguments that enable different neon features.

Examples:

    python mnist_mlp.py -b gpu -e 10
        Run the example for 10 epochs of mnist data using the nervana gpu
        backend

    python mnist_mlp.py --validation_freq 1
        After each training epoch the validation/test data set will be
        processed through the model and the cost will be displayed.

    python mnist_mlp.py --serialize 1 -s checkpoint.pkl
        After every iteration of training the model will be dumped to a pickle
        file names "checkpoint.pkl".  Increase the serialize parameter to
        change the frequency at which the model is saved.

    python mnist_mlp.py --model_file checkpoint.pkl
        Before starting to train the model, the model state is set to the
        values stored in the checkpoint file named checkpoint.pkl.
"""

import logging
import os

from neon.backends import gen_backend
from neon.callbacks.callbacks import Callbacks
from neon.data import DataIterator, load_mnist
from neon.initializers import Gaussian
from neon.layers import GeneralizedCost, Affine, Sequential, BranchNode, Multicost, Tree
from neon.models import Model
from neon.optimizers import GradientDescentMomentum
from neon.transforms import Rectlin, Logistic, Misclassification, Softmax
from neon.transforms import CrossEntropyBinary, CrossEntropyMulti
from neon.util.argparser import NeonArgparser


# parse the command line arguments
parser = NeonArgparser(__doc__)

args = parser.parse_args()

logger = logging.getLogger()
logger.setLevel(args.log_thresh)

# hyperparameters
batch_size = 128
num_epochs = args.epochs

# setup backend
be = gen_backend(backend=args.backend,
                 batch_size=batch_size,
                 rng_seed=args.rng_seed,
                 device_id=args.device_id,
                 default_dtype=args.datatype,
                 stochastic_round=False)


# load up the mnist data set
# split into train and tests sets
(X_train, y_train), (X_test, y_test), nclass = load_mnist(path=args.data_dir)

# setup a training set iterator
train_set = DataIterator(X_train, y_train, nclass=nclass)
# setup a validation data set iterator
valid_set = DataIterator(X_test, y_test, nclass=nclass)

# setup weight initialization function
init_norm = Gaussian(loc=0.0, scale=0.01)

normrelu = dict(init=init_norm, activation=Rectlin())
normsigm = dict(init=init_norm, activation=Logistic(shortcut=True))
normsoft = dict(init=init_norm, activation=Softmax())

# setup model layers
b1 = BranchNode(name="b1")
b2 = BranchNode(name="b2")


p1 = [Affine(nout=100, linear_name="m_l1", **normrelu),
      b1,
      Affine(nout=32, linear_name="m_l2", **normrelu),
      Affine(nout=16, linear_name="m_l3", **normrelu),
      b2,
      Affine(nout=10, linear_name="m_l4", **normsoft)]

p2 = [b1,
      Affine(nout=16, linear_name="b1_l1", **normrelu),
      Affine(nout=10, linear_name="b1_l2", **normsigm)]

p3 = [b2,
      Affine(nout=16, linear_name="b2_l1", **normrelu),
      Affine(nout=10, linear_name="b2_l2", **normsigm)]

alphas = [1, 0.25, 0.25]

# setup cost function as CrossEntropy
cost = Multicost(costs=[GeneralizedCost(costfunc=CrossEntropyMulti()),
                        GeneralizedCost(costfunc=CrossEntropyBinary()),
                        GeneralizedCost(costfunc=CrossEntropyBinary())],
                 weights=alphas)

# setup optimizer
optimizer = GradientDescentMomentum(0.1, momentum_coef=0.9, stochastic_round=args.rounding)

# initialize model object
mlp = Model(layers=Tree([p1, p2, p3], alphas=alphas))

if args.model_file:
    assert os.path.exists(args.model_file), '%s not found' % args.model_file
    logger.info('loading initial model state from %s' % args.model_file)
    mlp.load_weights(args.model_file)

# setup standard fit callbacks
callbacks = Callbacks(mlp, train_set, output_file=args.output_file,
                      progress_bar=args.progress_bar)

if args.validation_freq:
    # setup validation trial callbacks
    callbacks.add_validation_callback(valid_set, args.validation_freq)

if args.serialize > 0:
    # add callback for saving checkpoint file
    # every args.serialize epchs
    checkpoint_schedule = args.serialize
    checkpoint_model_path = args.save_path
    callbacks.add_serialize_callback(checkpoint_schedule, checkpoint_model_path)

# run fit
mlp.fit(train_set, optimizer=optimizer, num_epochs=num_epochs, cost=cost, callbacks=callbacks)

print('Misclassification error = %.1f%%' % (mlp.eval(valid_set, metric=Misclassification())*100))
