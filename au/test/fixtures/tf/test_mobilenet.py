from au import util
from au.fixtures import dataset
from au.fixtures import nnmodel
from au.fixtures.tf import mobilenet
from au.test import testconf
from au.test import testutils

import os

import numpy as np
import pytest

TEST_TEMPDIR = os.path.join(testconf.TEST_TEMPDIR_ROOT, 'test_mobilenet')

@pytest.mark.slow
def test_mobilenet_inference_graph(monkeypatch):
  testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  dataset.ImageTable.setup()

  params = mobilenet.Mobilenet.Small()
  model = mobilenet.Mobilenet.load_or_train(params)
  igraph = model.get_inference_graph()

  rows = dataset.ImageTable.iter_all_rows()
  filler = nnmodel.FillActivationsTFDataset(model=model)
  out_rows = list(filler(rows))

  # Test for smoke: logits for each image should be different ;)
  all_preds = set()
  for row in out_rows:
    acts = row.attrs['activations']
    tensor_to_value = acts[0].tensor_to_value
    for tensor_name in model.igraph.output_names:
      assert tensor_name in tensor_to_value
      
      # Check that we have a non-empty array
      assert tensor_to_value[tensor_name].shape

      # If weights fail to load, the net will predict uniformly for
      # everything.  Make sure that doesn't happen!
      if tensor_name == 'MobilenetV2/Predictions/Reshape_1:0':
        preds = tuple(tensor_to_value[tensor_name])
        assert preds not in all_preds
        all_preds.add(preds)
      
        # The Small model consistently gets this one right
        assert '202228408_eccfe4790e.jpg' in ' '.join(row.uri for row in out_rows)
        if '202228408_eccfe4790e.jpg' in row.uri:
          from slim.datasets import imagenet
          label_map = imagenet.create_readable_names_for_imagenet_labels()
          predicted = label_map[np.array(preds).argmax()]
          assert predicted == 'soccer ball'



    # For debugging, this is a Panda that the model predicts correctly per
    # https://colab.research.google.com/github/tensorflow/models/blob/master/research/slim/nets/mobilenet/mobilenet_example.ipynb
    # import imageio
    # im = imageio.imread('https://upload.wikimedia.org/wikipedia/commons/f/fe/Giant_Panda_in_Beijing_Zoo_1.JPG')
    # import cv2
    # imr = cv2.resize(im, (96, 96))
    # print imr
    # y = self.endpoints['Predictions'].eval(feed_dict={input_image:[imr]})
    # print y, y.max()

# FIXME: CI only has 8GB of RAM, and that's not enough for this test.  We tried
# to profile but discovered no clear Python memory issue; might be Tensorflow.
@pytest.mark.slow
def test_mobilenet_activation_tables(monkeypatch):
  testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
  dataset.ImageTable.setup()
  
  with testutils.LocalSpark.sess() as spark:
    for params_cls in mobilenet.Mobilenet.ALL_PARAMS_CLSS:
      params = params_cls()

      class TestTable(nnmodel.ActivationsTable):
        TABLE_NAME = 'Mobilenet_test_' + params_cls.__name__
        NNMODEL_CLS = mobilenet.Mobilenet
        MODEL_PARAMS = params
        IMAGE_TABLE_CLS = dataset.ImageTable
    
      TestTable.setup(spark=spark)


