# -*- coding: utf-8 -*-
import tensorflow as tf
import threading
import numpy as np

import signal
import random
import math
import os
import time

from environment import Environment
from model import UnrealModel
from trainer import Trainer
from rmsprop_applier import RMSPropApplier
from constants import *

def log_uniform(lo, hi):
  return np.logspace(math.log(lo), math.loh(hi), PARALLEL_SIZE)

device = "/cpu:0"
if USE_GPU:
  device = "/gpu:0"

initial_learning_rates = log_uniform(INITIAL_ALPHA_LOW,
                                    INITIAL_ALPHA_HIGH)

global_t = 0

stop_requested = False

action_size = Environment.get_action_size()
global_network = UnrealModel(action_size, -1, device)

trainers = []

learning_rate_input = tf.placeholder("float")

grad_applier = RMSPropApplier(learning_rate = learning_rate_input,
                              decay = RMSP_ALPHA,
                              momentum = 0.0,
                              epsilon = RMSP_EPSILON,
                              clip_norm = GRAD_NORM_CLIP,
                              device = device)

for i in range(PARALLEL_SIZE):
  trainer = Trainer(i,
                    global_network,
                    initial_learning_rate[i],
                    learning_rate_input,
                    grad_applier,
                    MAX_TIME_STEP,
                    device = device)
  trainers.append(trainer)

# prepare session
sess = tf.Session(config=tf.ConfigProto(log_device_placement=False,
                                        allow_soft_placement=True))

init = tf.initialize_all_variables()
sess.run(init)

# summary for tensorboard
score_input = tf.placeholder(tf.int32)
tf.scalar_summary("score", score_input)

summary_op = tf.merge_all_summaries()
summary_writer = tf.train.SummaryWriter(LOG_FILE, sess.graph_def)

# init or load checkpoint with saver
saver = tf.train.Saver()
checkpoint = tf.train.get_checkpoint_state(CHECKPOINT_DIR)
if checkpoint and checkpoint.model_checkpoint_path:
  saver.restore(sess, checkpoint.model_checkpoint_path)
  print("checkpoint loaded:", checkpoint.model_checkpoint_path)
  tokens = checkpoint.model_checkpoint_path.split("-")
  # set global step
  global_t = int(tokens[1])
  print(">>> global step set: ", global_t)
  # set wall time
  wall_t_fname = CHECKPOINT_DIR + '/' + 'wall_t.' + str(global_t)
  with open(wall_t_fname, 'r') as f:
    wall_t = float(f.read())
else:
  print("Could not find old checkpoint")
  # set wall time
  wall_t = 0.0


def train_function(parallel_index):
  global global_t
  
  trainer = trainers[parallel_index]
  # set start_time
  start_time = time.time() - wall_t
  trainer.set_start_time(start_time)

  while True:
    if stop_requested:
      break
    if global_t > MAX_TIME_STEP:
      break

    diff_global_t = trainer.process(sess, global_t, summary_writer,
                                    summary_op, score_input)
    global_t += diff_global_t
    
    
def signal_handler(signal, frame):
  global stop_requested
  print('You pressed Ctrl+C!')
  stop_requested = True
  
train_threads = []
for i in range(PARALLEL_SIZE):
  train_threads.append(threading.Thread(target=train_function, args=(i,)))
  
signal.signal(signal.SIGINT, signal_handler)

# set start time
start_time = time.time() - wall_t

for t in train_threads:
  t.start()

print('Press Ctrl+C to stop')
signal.pause()

print('Now saving data. Please wait')
  
for t in train_threads:
  t.join()

if not os.path.exists(CHECKPOINT_DIR):
  os.mkdir(CHECKPOINT_DIR)  

# write wall time
wall_t = time.time() - start_time
wall_t_fname = CHECKPOINT_DIR + '/' + 'wall_t.' + str(global_t)
with open(wall_t_fname, 'w') as f:
  f.write(str(wall_t))

saver.save(sess, CHECKPOINT_DIR + '/' + 'checkpoint', global_step = global_t)


