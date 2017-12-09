
def BuildDistributedCommandWorker(run_config, worker_hosts, ps_hosts,
                                  task_index):
  """Build command to start distributed worker."""

  run_script = 'python tf_cnn_benchmarks.py'

  # Prepends environment variables
  if 'env_vars' in run_config:
    run_script = '{} {}'.format(run_config['env_vars'], run_script)

  # Build command line
  run_cmd_list = []

  # Arguments with no name change that are passed through from the configs.
  pass_through_args = [
      'data_format', 'batch_size', 'num_batches', 'model', 'data_dir',
      'optimizer', 'learning_rate', 'sync_on_finish', 'weight_decay',
      'data_name', 'variable_update', 'num_intra_threads',
      'num_inter_threads', 'mkl', 'num_warmup_batches', 'forward_only',
      'kmp_blocktime', 'device', 'staged_vars', 'staged_grads',
      'cross_replica_sync', 'all_reduce_spec', 'use_datasets',
      'batch_group_size', 'use_nccl'
  ]

  for arg in pass_through_args:
    if arg in run_config:
      run_cmd_list.append('--{}={}'.format(arg, run_config[arg]))

  if 'ps_server' in run_config:
    run_cmd_list.append(
        '--local_parameter_device={}'.format(run_config['ps_server']))

  if 'gpus' in run_config:
    run_cmd_list.append('--num_gpus={}'.format(run_config['gpus']))

  # Setting the train_dir results in summaries and checkpoints
  # being written unless turned off.
  if 'train_dir' in run_config and task_index == 0:
    run_cmd_list.append('--train_dir={}'.format(run_config['train_dir']))
    if 'save_model_secs' in run_config:
      run_cmd_list.append(
          '--save_model_secs={}'.format(run_config['save_model_secs']))
    else:
      # Defaults to saving every 10 minutes (10*60).
      run_cmd_list.append('--save_model_secs=600')

    if 'summary_verbosity' in run_config:
      run_cmd_list.append(
          '--summary_verbosity={}'.format(run_config['summary_verbosity']))
    else:
      # Defaults to 1 for basic summaries
      run_cmd_list.append('--summary_verbosity=1')

    if 'save_summaries_steps' in run_config:
      run_cmd_list.append('--save_summaries_steps={}'.format(
          run_config['save_summaries_steps']))
    else:
      # This is local not global steps.
      run_cmd_list.append('--save_summaries_steps=500')

  # Set to pickup training from a checkpoint
  if 'pretrain_dir' in run_config and task_index == 0:
    run_cmd_list.append('--pretrain_dir={}'.format(run_config['pretrain_dir']))

  # Forces no distortions, which is the most common for benchmarks.
  run_cmd_list.append('--nodistortions')
  if 'display_every' in run_config:
    run_cmd_list.append(
        '--display_every={}'.format(run_config['display_every']))
  else:
    run_cmd_list.append('--display_every=10')

  # Creates a trace file for each model+gpu combo
  if 'trace_file' in run_config:
    trace_file = '{}_{}'.format(run_config['trace_file'], run_config['model'])
    if 'gpus' in run_config:
      trace_file = trace_file + '_' + str(run_config['gpus']) + '.txt'
    else:
      trace_file = trace_file + '.txt'
    run_cmd_list.append('--trace_file=' + trace_file)

  if ps_hosts:
    # Set flags needed for running in distributed mode.
    run_cmd_list.append('--worker_hosts=' + worker_hosts)
    run_cmd_list.append('--ps_hosts=' + ps_hosts)
    run_cmd_list.append('--job_name=worker')
    run_cmd_list.append('--task_index={}'.format(task_index))

  run_cmd = '{} {}'.format(run_script, ' '.join(run_cmd_list))

  return run_cmd


def BuildDistributedCommandPS(run_config, worker_hosts, ps_hosts, task_index):
  """Build command to start distributed parameter server.

  """
  print('Build Distributed Parameter Run Command')

  run_script = "CUDA_VISIBLE_DEVICES='' python tf_cnn_benchmarks.py"
  # Build command line
  run_cmd_list = []

  if 'sync_on_finish' in run_config:
    run_cmd_list.append(
        '--sync_on_finish={}'.format(run_config['sync_on_finish']))

  run_cmd_list.append('--local_parameter_device=' + run_config['ps_server'])
  run_cmd_list.append('--worker_hosts=' + worker_hosts)
  run_cmd_list.append('--ps_hosts=' + ps_hosts)
  run_cmd_list.append('--job_name=ps')
  run_cmd_list.append('--task_index={}'.format(task_index))

  run_cmd = '{} {}'.format(run_script, ' '.join(run_cmd_list))

  return run_cmd


def WorkerUtil(workers):
  """Handles different entries options for workers and ps_servers"""
  if (type(workers) is int):
    if workers == 0:
      return '0'
    else:
      return ','.join(str(n) for n in range(workers))
  else:
    return workers


def GpuDecode(raw_gpu_input):
  """Handles different entries options for workers and ps_servers"""
  if type(raw_gpu_input) is int:
    return str(raw_gpu_input)
  else:
    return raw_gpu_input.split(',')


def LoadYamlRunConfig(full_config, debug_level):
  """Processes config file into list of configs

  Reads the config made up of repeating 'run_configs'  The first first config as
  is treated as the base. Each config entry after the first is merged with the
  base (first) config.  The idea being the first config is the base and the
  subsequent configs are variations that override the base config

  Additionally, multiple configs are created based on the the following fields:
  'model' (list of models to test), gpu (list of number of GPUs to test), and
  repeat (number of times to run the test).

  Args:
    full_config: full run_config normally loaded from yaml
    debug_level: controls level of output
  """

  # base config that subsequent configs merge with
  base_config = None
  suite = []
  for config in full_config['run_configs']:
    test_configs = []
    suite.append(test_configs)
    if base_config is None:
      base_config = config
    else:
      # merges config with base config
      base = base_config.copy()
      base.update(config)
      config = base

    # Copy root settings into config.  Anything
    # at the root with override anything in run_configs
    for k, v in full_config.iteritems():
      if k != 'run_configs':
        base_config[k] = v

    if config.get('repeat') is not None:
      repeat = int(config['repeat'])
      for i in range(repeat):
        # Creates copy so each one can have an index, e.g. 'copy'
        repeat_model_config = config.copy()
        repeat_model_config['copy'] = i
        test_configs.append(repeat_model_config)
    else:
      test_configs.append(model_config)
    if debug_level > 0:
      print('Config:{} \n{}'.format(config['test_id'], config))
  return suite
