import os

from au import conf
from au import util
from au.fixtures import nnmodel
from au.fixtures.tf import mnist
from au.test import testconf
from au.test import testutils

import unittest

import pytest

TEST_TEMPDIR = os.path.join(testconf.TEST_TEMPDIR_ROOT, 'test_mnist') 

# @pytest.mark.slow
# def test_mnist_train(monkeypatch):
#   testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)

#   params = mnist.MNIST.Params()
#   params.TRAIN_EPOCHS = 10
#   params.LIMIT = 1000
#   model = mnist.MNIST.load_or_train(params)

class TestMNISTDataset(unittest.TestCase):

  @classmethod
  def setUpClass(cls):

    # Use /tmp for test fixtures
    from _pytest.monkeypatch import MonkeyPatch
    monkeypatch = MonkeyPatch()
    testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  
    cls.params = mnist.MNIST.Params()
    cls.params.LIMIT = 100
    
    mnist.MNISTDataset.setup(params=cls.params)

  @pytest.mark.slow
  def test_get_rows(self):  
    rows = mnist.MNISTDataset.get_rows_by_uris(
                                    ('mnist_train_0',
                                    'mnist_test_0',
                                    'not_in_mnist'))
    assert len(rows) == 2
    rows = sorted(rows)
    assert rows[0].uri == 'mnist_test_0'
    assert rows[1].uri == 'mnist_train_0'
    expected_bytes = open(testconf.MNIST_TEST_IMG_PATH, 'rb').read()
    assert rows[0].image_bytes == expected_bytes

  @pytest.mark.slow
  def test_image_contents(self):
    mnist.MNISTDataset.save_datasets_as_png(params=self.params)
    TEST_PATH = os.path.join(
                  TEST_TEMPDIR,
                  'data/MNIST/test/MNIST-test-label_7-mnist_test_0.png') 
    assert os.path.exists(TEST_PATH)

    import imageio
    expected = imageio.imread(testconf.MNIST_TEST_IMG_PATH)

    import numpy as np
    image = imageio.imread(TEST_PATH)
    np.testing.assert_array_equal(image, expected)

  @pytest.mark.slow
  def test_spark_df(self):
    # Test smoke!
    with testutils.LocalSpark.sess() as spark:
      df = mnist.MNISTDataset.as_imagerow_df(spark)
      df.show()
      assert df.count() == 2 * self.params.LIMIT
  
  @pytest.mark.slow
  def test_to_tf_dataset_no_spark(self):
    d = mnist.MNISTDataset.to_mnist_tf_dataset()
    with util.tf_data_session(d) as (sess, iter_dataset):
      tuples = list(iter_dataset())
    assert len(tuples) == 2 * self.params.LIMIT
  
  @pytest.mark.slow
  def test_to_tf_dataset_spark(self):
    with testutils.LocalSpark.sess() as spark:
      d = mnist.MNISTDataset.to_mnist_tf_dataset(spark=spark)
      with util.tf_data_session(d) as (sess, iter_dataset):
        tuples = list(iter_dataset())
      assert len(tuples) == 2 * self.params.LIMIT




@pytest.mark.slow
def test_mnist_igraph(monkeypatch):
  testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  
  # TODO: model fixture
  params = mnist.MNIST.Params()
  params.TRAIN_EPOCHS = 1
  params.LIMIT = 10
  model = mnist.MNIST.load_or_train(params)
  igraph = model.get_inference_graph()
  assert igraph != nnmodel.TFInferenceGraphFactory()

  # params = mnist.MNIST.Params()
  # params.LIMIT = 100 # num images
  mnist.MNISTDataset.setup(params=params)
  rows = list(mnist.MNISTDataset.iter_all_rows())

  filler = nnmodel.FillActivationsTFDataset(model=model)
  out_rows = list(filler(rows))
  assert len(out_rows) == len(rows)
  for row in out_rows:
    acts = row.attrs['activations']
    act = acts[0]
    assert act.model_name == igraph.model_name
    tensor_to_value = act.tensor_to_value
    for tensor_name in model.igraph.output_names:
      assert tensor_name in tensor_to_value
      
      # Check that we have a non-empty array
      assert tensor_to_value[tensor_name].shape
