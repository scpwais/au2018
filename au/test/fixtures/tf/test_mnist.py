import os

from au import conf
from au import util
from au.fixtures import nnmodel
from au.fixtures.tf import mnist
from au.test import testconf

import pytest

TEST_TEMPDIR = os.path.join(testconf.TEST_TEMPDIR_ROOT, 'test_mnist') 

# @pytest.mark.slow
# def test_mnist_train(monkeypatch):
#   testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)

#   params = mnist.MNIST.Params()
#   params.TRAIN_EPOCHS = 1
#   params.LIMIT = 10
#   model = mnist.MNIST.load_or_train(params)
  
#   # TODO: test with more rigor
#   assert model.igraph

@pytest.mark.slow
def test_mnist_dataset(monkeypatch):
  testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  
  params = mnist.MNIST.Params()
  params.LIMIT = 100
  
  mnist.MNISTDataset.setup(params=params)
  
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


  mnist.MNISTDataset.save_datasets_as_png(params=params)
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
def test_mnist_igraph(monkeypatch):
  testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  
  # TODO: model fixture
  params = mnist.MNIST.Params()
  params.TRAIN_EPOCHS = 1
  params.LIMIT = 10
  model = mnist.MNIST.load_or_train(params)
  assert model.get_inference_graph() != nnmodel.TFInferenceGraphFactory()

  params = mnist.MNIST.Params()
  params.LIMIT = 100
  mnist.MNISTDataset.setup(params=params)
  rows = list(mnist.MNISTDataset.iter_all_rows())

  filler = nnmodel.FillActivationsTFDataset(model=model)
  out_rows = list(filler(rows))
  assert len(out_rows) == len(rows)
  for row in out_rows:
    assert 'activation_to_val' in row.attrs
    activation_to_val = row.attrs['activation_to_val']
    for tensor_name in model.igraph.output_names:
      assert tensor_name in activation_to_val
      
      # Check that we have a non-empty array
      assert activation_to_val[tensor_name].shape
