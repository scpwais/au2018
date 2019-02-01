import os

from au import util
from au.experiments.data_ablation import util as exp_util
from au.fixtures.tf import mnist

class AblatedDataset(mnist.MNISTDataset):
  
  SPLIT = 'train'
  TARGET_DISTRIBUTION = {}
    # Ablate dataset on a per-class basis to these class frequencies
  KEEP_FRAC = -1
    # Uniformly ablate the dataset to this fraction
  SEED = 1337

  @classmethod
  def as_imagerow_df(cls, spark):
    df = spark.read.parquet(cls.table_root())
    if cls.SPLIT is not '':
      df = df.filter(df.split == cls.SPLIT)

    if 1.0 >= cls.KEEP_FRAC >= 0:
      df = df.sample(
              withReplacement=False,
              fraction=cls.KEEP_FRAC,
              seed=cls.SEED)
    elif cls.TARGET_DISTRIBUTION:
      df = df.sampleBy(
              "label",
              fractions=cls.TARGET_DISTRIBUTION,
              seed=cls.SEED)
    util.log.info("Ablated to %s examples" % df.count())
    util.log.info("New class frequencies:")
    cls.get_class_freq(spark, df=df).show()

    return df



class ExperimentConfig(object):
  DEFAULTS = {
    'exp_basedir': exp_util.experiment_basedir('mnist'),
    'run_name': 'default.' + util.fname_timestamp(),

    'params_base':
      mnist.MNIST.Params(
        TRAIN_EPOCHS=100,
        TRAIN_WORKER_CLS=util.WholeMachineWorker,
      ),
    
    'trials_per_treatment': 10,

    'uniform_ablations': (
        0.9999,
        0.9995,
        0.999,
        0.995,
        0.99,
        0.95,
        0.9,
        0.5,
        0,
      ),
  }

  def __init__(self, **conf):
    for k, v in self.DEFAULTS.iteritems():
      setattr(self, k, v)
    for k, v in conf.iteritems():
      setattr(self, k, v)

  def iter_model_params(self):
    import copy
    for ablate_frac in self.uniform_ablations:
      keep_frac = 1.0 - ablate_frac
      params = copy.deepcopy(self.params_base)

      params.MODEL_NAME = 'ablated_mnist_keep_%s' % keep_frac
      params.MODEL_BASEDIR = os.path.join(
                                self.exp_basedir,
                                self.run_name,
                                params.MODEL_NAME)
      params.TRAIN_WORKER_CLS = util.WholeMachineWorker

      for i in range(self.trials_per_treatment):
        class ExpTable(AblatedDataset):
          KEEP_FRAC = keep_frac
          SEED = AblatedDataset.SEED + i
        params.TRAIN_TABLE = ExpTable
        params.MODEL_NAME = params.MODEL_NAME + '_trial_' + str(i)
        yield params



"""
need to extract generator -> tf.Dataset thingy to make ImageTables have a
as_tf_dataset() method mebbe ?

then just generate ablations and train.

for test, we just use same test set and can do test ablations after the fact

finally let's do activation tables of each model and see if we can 
generate embeddings with each model and then plot test data in those embeddings.

so, like, maybe there's a function(model, embedding, test_data_slice_1) that predicts
error on test_data_slice_2.  

build the above with mscoco / segmentation in mind, as well as bdd100k segmentation


"""

if __name__ == '__main__':
  mnist.MNISTDataset.setup()
  
  from au.spark import Spark
  paramss = ExperimentConfig().iter_model_params()
  cs = (lambda: mnist.MNIST.load_or_train(params=p) for p in paramss)
  with Spark.sess() as spark:
    res = Spark.run_callables(spark, cs)
