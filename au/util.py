import itertools
import os
import shutil
import subprocess
import sys
import threading
import time

from contextlib import contextmanager

### Logging
_LOGS = {}
def create_log(name='au'):
  global _LOGS
  if name not in _LOGS:
    import logging
    LOG_FORMAT = "%(asctime)s\t%(name)-4s %(process)d : %(message)s"
    log = logging.getLogger("au")
    log.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    log.addHandler(console_handler)
    _LOGS[name] = log
  return _LOGS[name]
log = create_log()


### Pythonisms

def ichunked(seq, n):
  """Generate chunks of `seq` of size (at most) `n`.  More efficient
  and less junk than itertools recipes version using izip_longest...
  """
  n = max(1, n)
  seq = iter(seq)
  while True:
    chunk = tuple(itertools.islice(seq, n))
    if chunk:
      yield chunk
    else:
      break

class Proxy(object):
  __slots__ = ('instance',)
  
  def __init__(self, instance):
    self.instance = instance
  
  def __getattr__(self, name):
    return getattr(self.instance, name)
  
  def _on_delete(self):
    pass

  def __del__(self):
    self._on_delete()
    del self.instance

class ThruputObserver(object):
  
  def __init__(self, name='', log_on_del=False, only_stats=None):
    self.n = 0
    self.num_bytes = 0
    self.ts = []
    self.name = name
    self.log_on_del = log_on_del
    self.only_stats = only_stats or []
    self._start = None
  
  @contextmanager
  def observe(self, n=0, num_bytes=0):
    """
    NB: contextmanagers appear to be expensive due to object creation.
    Use ThurputObserver#{start,stop}_block() for <10ms ops. 
    FMI https://stackoverflow.com/questions/34872535/why-contextmanager-is-slow
    """

    start = time.time()
    yield
    end = time.time()
    
    self.n += n
    self.num_bytes += num_bytes
    self.ts.append(end - start)
  
  def start_block(self):
    self._start = time.time()
  
  def update_tallies(self, n=0, num_bytes=0):
    self.n += n
    self.num_bytes += num_bytes
  
  def stop_block(self, n=0, num_bytes=0):
    end = time.time()
    self.n += n
    self.num_bytes += num_bytes
    self.ts.append(end - self._start)
    self._start = None
  
  @staticmethod
  def union(thruputs):
    u = ThruputObserver()
    for t in thruputs:
      u += t
    return u
  
  def __iadd__(self, other):
    self.n += other.n
    self.num_bytes += other.num_bytes
    self.ts.extend(other.ts)
    return self

  def __str__(self):
    import numpy as np
    import tabulate

    gbytes = 1e-9 * self.num_bytes
    total_time = sum(self.ts) or float('nan')

    stats = (
      ('N thru', self.n),
      ('N chunks', len(self.ts)),
      ('total time (sec)', total_time),
      ('total GBytes', gbytes),
      ('overall GBytes/sec', gbytes / total_time if total_time else '-'),
      ('Hz', float(self.n) / total_time if total_time else '-'),
      ('Latency (per chunk)', ''),
      ('avg (sec)', np.mean(self.ts) if self.ts else '-'),
      ('p50 (sec)', np.percentile(self.ts, 50) if self.ts else '-'),
      ('p95 (sec)', np.percentile(self.ts, 95) if self.ts else '-'),
      ('p99 (sec)', np.percentile(self.ts, 99) if self.ts else '-'),
    )
    if self.only_stats:
      stats = tuple(
        (name, value)
        for name, value in stats
        if name in self.only_stats
      )

    summary = tabulate.tabulate(stats)
    if self.name:
      summary = self.name + '\n' + summary
    return summary
  
  def __del__(self):
    if self.log_on_del:
      log = create_log()
      log.info('\n' + str(self) + '\n')

@contextmanager
def quiet():
  old_stdout = sys.stdout
  old_stderr = sys.stderr
  f = open(os.devnull, 'w')
  new_stdout = sys.stdout = f
  new_stderr = sys.stderr = f
  try:
    yield new_stdout, new_stderr
  finally:
    new_stdout.seek(0)
    new_stderr.seek(0)
    sys.stdout = old_stdout
    sys.stderr = old_stderr


@contextmanager
def imageio_ignore_warnings():
  # Imageio needs some fix: https://github.com/imageio/imageio/issues/376
  import imageio.core.util
  def silence_imageio_warning(*args, **kwargs):
    pass
  old = imageio.core.util._precision_warn
  imageio.core.util._precision_warn = silence_imageio_warning
  try:
    yield
  finally:
    imageio.core.util._precision_warn = old


def run_cmd(cmd, collect=False, nolog=False):
  dolog = not nolog
  cmd = cmd.replace('\n', '').strip()
  
  if dolog:
    log = create_log()
    log.info("Running %s ..." % cmd)
  
  if collect:
    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
  else:
    subprocess.check_call(cmd, shell=True)
    out = None
  
  if dolog:
    log.info("... done with %s " % cmd)
  
  return out


def get_non_loopback_iface():
  # https://stackoverflow.com/a/1267524
  import socket
  non_loopbacks = [
    ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")
  ]
  if non_loopbacks:
    return non_loopbacks[0]

  # Get an iface that can connect to Google DNS ...
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.connect(("8.8.8.8", 80))
  ifrace = s.getsockname()[0]
  s.close()
  return iface


_SYS_INFO_LOCK = threading.Lock()
def get_sys_info():
  global _SYS_INFO_LOCK
  log = create_log()

  log.info("Listing system info ...")

  info = {}
  info['filepath'] = os.path.abspath(__file__)
  info['PYTHONPATH'] = ':'.join(sys.path)
  
  @contextmanager
  def atomic_ignore_exceptions():
    with _SYS_INFO_LOCK:
      try:
        yield
      except Exception:
        pass

  def safe_cmd(cmd):
    with atomic_ignore_exceptions():
      return run_cmd(cmd, collect=True) or ''

  info['nvidia_smi'] = safe_cmd('nvidia-smi')
  info['cpuinfo'] = safe_cmd('cat /proc/cpuinfo')
  info['disk_free'] = safe_cmd('df -h')
  info['ifconfig'] = safe_cmd('ifconfig')
  info['memory'] = safe_cmd('free -h')

  import socket
  info['hostname'] = socket.gethostname()
  info['host'] = get_non_loopback_iface()

  import multiprocessing
  info['n_cpus'] = multiprocessing.cpu_count()
  
  log.info("... got all system info.")

  return info

### ArchiveFileFlyweight

class _IArchive(object):
  __slots__ = ('archive_path', 'thread_data')
  
  def __init__(self, path):
    self.archive_path = path
    self.thread_data = threading.local()

  def _setup(self, archive_path):
    pass

  @classmethod
  def list_names(cls, archive_path):
    return []

  def _archive_get(self, name):
    raise KeyError("Interface stores no data")

  def get(self, name):
    self._setup(self.archive_path)
    return self._archive_get(name)

class _ZipArchive(_IArchive):
  
  def _setup(self, archive_path):
    if not hasattr(self.thread_data, 'zipfile'):
      import zipfile
      self.thread_data.zipfile = zipfile.ZipFile(archive_path)
  
  def _archive_get(self, name):
    return self.thread_data.zipfile.read(name)

  @classmethod
  def list_names(cls, archive_path):
    import zipfile
    return zipfile.ZipFile(archive_path).namelist()

class ArchiveFileFlyweight(object):

  __slots__ = ('name', 'archive')

  def __init__(self, name='', archive=None):
    self.name = name
    self.archive = archive

  @staticmethod
  def fws_from(archive_path):
    if archive_path.endswith('zip'):
        archive = _ZipArchive(archive_path)
        names = _ZipArchive.list_names(archive_path)
        return [
          ArchiveFileFlyweight(name=name, archive=archive)
          for name in names
        ]
    else:
      raise ValueError("Don't know how to read %s" % archive_path)

  @property
  def data(self):
    return self.archive.get(self.name)
  
def copy_n_from_zip(src, dest, n):
  log.info("Copying %s of %s -> %s ..." % (n, src, dest))

  mkdir(os.path.split(dest)[0])

  import zipfile
  with zipfile.ZipFile(src) as zin:
    with zipfile.ZipFile(dest, mode='w') as zout:
      for name in itertools.islice(sorted(zin.namelist()), n):
        zout.writestr(name, zin.read(name))
  
  log.info("... done")



### I/O

try:
  import pathlib
except ImportError:
  import pathlib2 as pathlib
  # TODO use six?

def mkdir(path):
  pathlib.Path(path).mkdir(parents=True, exist_ok=True)

def rm_rf(path):
  shutil.rmtree(path)

def all_files_recursive(root_dir):
  for path in pathlib.Path(root_dir).glob('**/*'):
    path = str(path) # pathlib uses PosixPath thingies ...
    if os.path.isfile(path):
      yield path

def cleandir(path):
  mkdir(path)
  rm_rf(path)
  mkdir(path)

def missing_or_empty(path):
  if not os.path.exists(path):
    return True
  else:
    for p in all_files_recursive(path):
      return False
    return True

def is_stupid_mac_file(path):
  fname = os.path.basename(path)
  return fname.startswith('._') or fname in ('.DS_Store',)

def download(uri, dest, try_expand=True):
  """Fetch `uri`, which is a file or archive, and put in `dest`, which
  is either a destination file path or destination directory."""
  
  # Import urllib
  try:
    import urllib.error as urlliberror
    import urllib.request as urllib
    HTTPError = urlliberror.HTTPError
    URLError = urlliberror.URLError
  except ImportError:
    import urllib2 as urllib
    HTTPError = urllib.HTTPError
    URLError = urllib.URLError
  
  import tempfile
  
  import patoolib
 
  if os.path.exists(dest):
    return
  
  def show_progress(percentage):
    COLS = 70
    full = int(COLS * percentage / 100)
    bar = full * "#" + (COLS - full) * " "
    sys.stdout.write(u"\u001b[1000D[" + bar + "] " + str(percentage) + "%")
    sys.stdout.flush()
  
  fname = os.path.split(uri)[-1]
  tempdest = tempfile.NamedTemporaryFile(suffix='_' + fname)
  try:
    log.info("Fetching %s ..." % uri)
    response = urllib.urlopen(uri)
    size = int(response.info().get('Content-Length').strip())
    log.info("... downloading %s MB ..." % (float(size) * 1e-6))
    chunk = min(size, 8192)
    downloaded = 0
    while True:
      data = response.read(chunk)
      if not data:
        break
      tempdest.write(data)
      downloaded += len(data)
      show_progress(100 * downloaded / size)
    sys.stdout.write("")
    sys.stdout.flush()
    log.info("... fetched!")
  except HTTPError as e:
    raise Exception("[HTTP Error] {code}: {reason}."
                        .format(code=e.code, reason=e.reason))
  except URLError as e:
    raise Exception("[URL Error] {reason}.".format(reason=e.reason))
  
  tempdest.flush()
  
  if try_expand:
    try:
      # Is it an archive? expand!
      mkdir(dest)
      patoolib.extract_archive(tempdest.name, outdir=dest)
      log.info("Extracted archive.")
    except Exception:
      # Just move the file
      shutil.move(tempdest.name, dest)
      tempdest.delete = False
  else:
    shutil.move(tempdest.name, dest)
    tempdest.delete = False
  log.info("Downloaded to %s" % dest)


### Tensorflow

class GPUInfo(object):
  __slots__ = (
    'index',
    'name',
    'mem_util_frac',
    'mem_free',
    'mem_used',
    'mem_total'
  )

  def __str__(self):
    data = ', '.join(
      (k + '=' + str(getattr(self, k)))
      for k in self.__slots__)
    return 'GPUInfo(' + data + ')'

  def __eq__(self, other):
    return all(getattr(self, k) == getattr(other, k) for k in self.__slots__)

  @staticmethod
  def from_nvidia_smi(row):
    info = GPUInfo()
    info.index = int(row['index'])
    info.name = row['name']
    
    info.mem_util_frac = float(row['utilization.memory [%]']) / 100.
    def to_num_bytes(s):
      return int(s) * int(1e6)
    info.mem_free = to_num_bytes(row['memory.free [MiB]'])
    info.mem_used = to_num_bytes(row['memory.used [MiB]'])
    info.mem_total = to_num_bytes(row['memory.total [MiB]'])

    return info

  @staticmethod
  def get_infos(only_visible=True):
    # Much safer than pycuda and Tensorflow, which can both segfault if the
    # nvidia driver is absent :P
    try:
      cmd = "nvidia-smi --query-gpu=index,name,utilization.memory,name,memory.total,memory.free,memory.used --format=csv,nounits"
      out = run_cmd(cmd, collect=True)
    except Exception as e:
      log.info("No GPUs found")
      return []

    # NB: nvidia doesn't actually return *valid* csv.
    # Why would they? They make hardware, not software!
    out = out.replace(', ', ',')

    import csv
    rows = list(csv.DictReader(out.split('\n')))
    infos = [GPUInfo.from_nvidia_smi(row) for row in rows]
    
    log.info("Found GPUs: %s" % ([str(info) for info in infos],))

    if only_visible:
      if 'CUDA_VISIBLE_DEVICES' in os.environ:
        allowed_gpus = set(
          int(g) for g in
          os.environ['CUDA_VISIBLE_DEVICES'].split(',')
          if g)
        log.info("... restricting to GPUs %s ..." % (allowed_gpus,))
        infos = [
          info for info in infos
          if info.index in allowed_gpus
        ]
    return infos
  
  @staticmethod
  def num_total_gpus():
    return len(GPUInfo.get_infos())

import fasteners
import pickle
class GPUPool(object):
  """
  An arbiter providing system-wide mutually exclusive handles to GPUs.  Mutual
  exclusion is via file locks and cooperative use; handles emitted from this
  utility have no impact on the underlying GPU devices.  Useful for restricting
  individual pyspark worker processes to distinct GPUs.  (Otherwise, a Spark
  executor can easily cause GPU OOMs when launching multiple worker processes
  or threads).
  
  Other context:
  Tensorflow nortoriously enjoys comandeering all available GPU memory,
  which can result in OOMs when Sessions try to run concurrently.  Morevoer,
  nvidia-smi offers a feature to support "exclusive use" mode, but we don't
  necessarily want to lock out other processes (e.g. the OS) and nvidia
  software (especially drivers) typically have bugs or fragmentation issues.
  This utility provides mutual exclusion that is concise and independent of
  nvidia software as well as any cuda-wrapping framework (e.g. pycuda or 
  Tensorflow) which can even segfault when devices / drivers are missing.
  """
  
  # Users need only keep a GPUInfo (proxy) in scope to maintain ownership
  class _InfoProxy(Proxy):
    __slots__ = ('instance', '_parent')
    def _on_delete(self):
      self._parent._release(self.instance)

  def get_free_gpu(self):
    """Return a handle to a free GPU or None if none available"""
    with self.lock:
      gpus = self._get_gpus()
      handle = None
      if gpus:
        gpu = gpus.pop(0)
        handle = GPUPool._InfoProxy(gpu)
        handle._parent = self
      self._set_gpus(gpus)
      return handle

  # Make pickle-able for interop with Spark
  def __getstate__(self):
    return {'path': self.lock.path}
  def __setstate__(self, d):
    self.lock = fasteners.InterProcessLock(d['path'])

  def __init__(self, path=''):
    import tempfile
    if not path:
      path = os.path.join(tempfile.gettempdir(), 'au.GPUPool.' + str(id(self)))
    self.lock = fasteners.InterProcessLock(path)
    with self.lock:
      gpus = GPUInfo.get_infos()
      self._set_gpus(gpus)

  def _set_gpus(self, lst):
    with open(self.lock.path, 'w') as f:
      pickle.dump(lst, f, protocol=pickle.HIGHEST_PROTOCOL)

  def _get_gpus(self):
    with open(self.lock.path, 'r') as f:
      return pickle.load(f)

  def _release(self, gpu):
    with self.lock:
      gpus = self._get_gpus()
      gpus.append(gpu)
      print 'release', gpu
      self._set_gpus(gpus)


def tf_create_session_config(restrict_gpus=None, extra_opts=None):
  extra_opts = extra_opts or {}
  
  import tensorflow as tf
  config = tf.ConfigProto()

  tf_session_config_restrict_gpus(config, restrict_gpus=restrict_gpus)
  config.log_device_placement = False
  
  # Let the system pick number of threads
#   config.intra_op_parallelism_threads = 0
#   config.inter_op_parallelism_threads = 0
  
  for k, v in extra_opts.iteritems():
    setattr(config, k, v)
  return config

def tf_session_config_restrict_gpus(config, restrict_gpus=None):
  if restrict_gpus is None:
    config.gpu_options.allow_growth = True
    config.allow_soft_placement = True
  else:
    config.device_count['GPU'] = len(restrict_gpus)
    config.gpu_options.visible_device_list = ','.join(str(g) for g in restrict_gpus)

def tf_create_session(config=None):
  config = config or tf_create_session_config()

  import tensorflow as tf
  sess = tf.Session(config=config)
  return sess

def tf_cpu_session(config=None):
  if not config:
    config = tf_create_session_config(restrict_gpus=[])
  else:
    tf_session_config_restrict_gpus(config, restrict_gpus=[])
  return tf_create_session(config=config)

@contextmanager
def tf_data_session(dataset, sess=None, config=None):
  import tensorflow as tf

  # Must declare these before the graph gets finalized below
  iterator = dataset.make_one_shot_iterator()
  next_element = iterator.get_next()
  
  # Silly way to iterate over a tf.Dataset
  # https://stackoverflow.com/a/47917849
  sess = sess or tf_cpu_session()
  with sess as sess:
    def iter_dataset():
      # see MonitoredTrainingSession.StepContext
      while True:
        try:
      # with loop_until_data_exausted():
          yield sess.run(next_element)
        except (tf.errors.OutOfRangeError, StopIteration):
          break
    yield sess, iter_dataset

# NB: we must use a multiprocessing.Process for Tensorflow GPU usage.  Keeping
# this commented cruft as a reminder.
# class TFSessionPool(object):
#   """
#   TODO docs
#   https://github.com/tensorflow/tensorflow/issues/15880
#   https://github.com/tensorflow/tensorflow/issues/20387
#   https://github.com/tensorflow/tensorflow/blob/a14adaa2329fb46cb472b949ee52546c2516a21e/tensorflow/core/common_runtime/gpu/gpu_device.cc#L1095
#   https://github.com/tensorflow/tensorflow/issues/15880#issuecomment-378336673

#   """
#   _gpu_pool = GPUPool()
#   _lock = threading.Lock()
  
#   class ManagedSession(Proxy):
#     __slots__ = ('sess', 'gpus')
#     def __init__(self, sess=None, gpus=None):
#       self.sess = sess
#       self.gpus = gpus or []
  
#   class _SessHandle(Proxy):
#     __slots__ = ('instance', '_parent')
#     def _on_delete(self):
#       self._parent._reclaim(self.instance)

#   _sessions = []
#   ALL_GPUS = -1

#   @classmethod
#   def get_best_session(cls, num_gpus=0, config=None):
#     if num_gpus == cls.ALL_GPUS:
#       num_gpus = GPUInfo.num_total_gpus()
    
#     with cls._lock:
#       # Try to find a good session
#       for msess in cls._sessions:
#         if len(msess.gpus) == num_gpus:
#           cls._sessions.remove(msess)
#           h = cls._SessHandle(msess)
#           h._parent = cls
#           return h
      
#       # Can't find one! Create it.
#       gpus = [cls._gpu_pool.get_free_gpu() for _ in range(num_gpus)]
#       if gpus and not all(g is not None for g in gpus):
#         raise ValueError("Can't get %s GPUs" % num_gpus)

#       config = config or tf_create_session_config()
#       tf_session_config_restrict_gpus(config, restrict_gpus=(gpus or None))
#       sess = tf_create_session(config=config)

#       msess = cls.ManagedSession(sess=sess, gpus=gpus)
#       h = cls._SessHandle(msess)
#       h._parent = cls
#       return h

#   @classmethod
#   def _reclaim(cls, managed_sess):
#     with cls._lock:
#       cls._sessions.append(managed_sess)

#   @classmethod
#   def register_session(cls, sess):
#     with cls._lock:
#       cls._sessions.append(cls.ManagedSession(sess=sess))


def give_me_frozen_graph(
          checkpoint,
          nodes=None,
          blacklist=None,
          base_graph=None,
          sess=None,
          saver=None):
  """
  Tensorflow has several ways to load checkpoints / graph artifacts.
  It's impossible to know if some API is stable or if tomorrow somebody
  will invent something new and break everything becaus PyTorch is shiny
  (e.g. TF Eager).  Sam Abrahams wrote a book on Tensorflow
  ( https://www.amazon.com/TensorFlow-Machine-Intelligence-hands--introduction-ebook/dp/B01IZ43JV4/ )
  and one time couldn't tell me definitively which API to use.  What's more is
  that freeze_graph.py is an optional script instead of a library module in
  Tensorflow.  Chaos!!

  So, based upon spark-dl's `strip_and_freeze_until()`
  ( https://github.com/databricks/spark-deep-learning/blob/4daa1179f498df4627310afea291133539ce7001/python/sparkdl/graph/utils.py#L199 ),
  here's a utility for getting a frozen, serializable, pyspark-friendly
  graph from a checkpoint artifact metagraph thingy I have no idea.
  """

  def op_name(v):
    name = v
    if hasattr(v, 'name'):
      name = v.name
    if ':' not in name:
      return name
    toks = name.split(':')
    assert len(toks) <= 2, (toks, v, name)
    return toks[0]

  import tensorflow as tf
  graph = base_graph or tf.Graph()
  if nodes:
    ops = [graph.get_operation_by_name(op_name(n)) for n in nodes]
  else:
    ops = graph.get_operations()
  # if blacklist:
  #   for n in blacklist:
  #     ops.remove(graph.get_operation_by_name(op_name(n)))

  with graph.as_default():
    with (sess or tf_cpu_session()) as sess:
      saver = saver or tf.train.Saver()
      log.info("Reading from checkpoint %s ..." % checkpoint)
      saver.restore(sess, checkpoint)
      log.info("... done.")

      gdef_frozen = tf.graph_util.convert_variables_to_constants(
        sess,
        graph.as_graph_def(add_shapes=True),
        [op.name for op in ops])
        # variable_names_blacklist=blacklist)
  g = tf.Graph()
  with g.as_default():
    tf.import_graph_def(gdef_frozen, name='')
  return g
  
