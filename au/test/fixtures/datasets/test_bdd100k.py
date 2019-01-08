from au.test import testutils
from au.fixtures.datasets import bdd100k

import unittest
import os

import pytest

class BDD100kTests(unittest.TestCase):
  """Exercise utiltiies in the bdd100k module.  Allow soft failures
  if the user has none of the required zip files.  We assume exclusively
  one of:
     1) the user emplaced the fixtures correctly using aucli
     2) the user has no fixtures and does not need them
  """

  @classmethod
  def setUpClass(cls):
    cls.fixtures = None
    try:
      bdd100k.Fixtures.create_test_fixtures()

      class TestFixtures(bdd100k.Fixtures):
        ROOT = bdd100k.Fixtures.TEST_FIXTURE_DIR
      
      cls.fixtures = TestFixtures
    except Exception as e:
      print "Failed to create test fixtures: %s" % (e,)
  
  INFO_FIXTURE_VIDEOS = set((
    'b9d24e81-a9679e2a.mov',
    'c2bc5a4c-b2bc828b.mov',
    'c6a4abc9-e999da65.mov',
    'b7f75fad-1c1c419b.mov',
    'b2752cd6-12ba5588.mov',
    'be986afd-f734d33e.mov',
    'c53c9807-1eadf674.mov'
  ))

  @pytest.mark.slow
  def test_info_dataset(self):
    if not self.fixtures:
      return
    
    class TestInfoDataset(bdd100k.InfoDataset):
      NAMESPACE_PREFIX = 'test'
      FIXTURES = self.fixtures
    
    with testutils.LocalSpark.sess() as spark:
      meta_rdd = TestInfoDataset.create_meta_rdd(spark)
      metas = meta_rdd.collect()
      videos = set(meta.video for meta in metas)
      videos = self.INFO_FIXTURE_VIDEOS

  @pytest.mark.slow
  def test_video_datset(self):
    if not self.fixtures:
      return
    
    class TestInfoDataset(bdd100k.InfoDataset):
      NAMESPACE_PREFIX = 'test'
      FIXTURES = self.fixtures

    class TestVideoDataset(bdd100k.VideoDataset):
      FIXTURES = self.fixtures
      INFO = TestInfoDataset

    EXPECTED_VIDEOS = set(self.INFO_FIXTURE_VIDEOS)
    EXPECTED_VIDEOS.add('video_with_no_info.mov')

    with testutils.LocalSpark.sess() as spark:
      videometa_df = TestVideoDataset.load_videometa_df(spark)
      videometa_df.show()

      rows = videometa_df.collect()
      assert set(r.video for r in rows) == EXPECTED_VIDEOS

      for row in rows:
        if row.video == 'video_with_no_info.mov':
          # We don't know the epoch time of this video (no BDD100k info) ...
          assert row.startTime == -1
          assert row.endTime == -1
          
          # ... but we can glean some data from the video itself.
          assert row.duration != float('nan')
          assert row.nframes > 0
          assert row.width > 0 and row.height > 0


    #   ts_row_rdd = TestInfoDataset._info_table_from_zip(spark)
    #   # df = ts_row_rdd#spark.createDataFrame(ts_row_rdd)
    #   # import ipdb; ipdb.set_trace()
    #   df = TestInfoDataset._ts_table_from_info_table(spark, ts_row_rdd)
    #   df.printSchema()
    #   df.registerTempTable('moof')
    #   spark.sql('select * from moof').show()
    #   # spark.sql('select * from moof').write.parquet('/tmp/yyyyyy', partitionBy=['split', 'video'], compression='gzip')
    
