from au import conf
from au import util
from au.fixtures.datasets import auargoverse as av
from au.test import testconf
from au.test import testutils

import itertools
import os
import unittest

import pytest

# Create a fake argoverse test fixture using only examples listed here
TEST_FIXTURE_URIS = (
  # Has bikes
  'argoverse://tarball_name=tracking_train2.tar.gz&log_id=5c251c22-11b2-3278-835c-0cf3cdee3f44&split=train&camera=ring_front_center&timestamp=315967787401035936',
  
  # Emergency vehicle
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=f9fa3960-537f-3151-a1a3-37a9c0d6d7f7&split=train&camera=ring_rear_right&timestamp=315968463537902224',
  
  # Pedestrians
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=1d676737-4110-3f7e-bec0-0c90f74c248f&split=train&camera=ring_front_left&timestamp=315984810796685856',

  # Night scene
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=53037376_5303_5303_5303_553038557184&split=train&camera=ring_front_left&timestamp=315967820634443792',

  # Lens flare
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=64c12551-adb9-36e3-a0c1-e43a0e9f3845&split=train&camera=ring_front_center&timestamp=315975339670154704',

  # Complex from val
  'argoverse://tarball_name=tracking_val.tar.gz&log_id=15c802a9-0f0e-3c87-b516-a3fa02f1ecb0&split=val&camera=ring_front_center&timestamp=315970757222656344',
  'argoverse://tarball_name=tracking_val.tar.gz&log_id=22160544_2216_2216_2216_722161741824&split=val&camera=ring_front_center&timestamp=315966714291915976',

  # Misc from sample
  'argoverse://tarball_name=tracking_sample.tar.gz&log_id=c6911883-1843-3727-8eaa-41dc8cda8993&split=sample&camera=stereo_front_left&timestamp=315978417887655552',
  'argoverse://tarball_name=tracking_sample.tar.gz&log_id=c6911883-1843-3727-8eaa-41dc8cda8993&split=sample&camera=ring_front_right&timestamp=315978410894656888',

  # Misc from train
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=1d676737-4110-3f7e-bec0-0c90f74c248f&split=train&camera=ring_front_center&timestamp=315984808032785816',
  'argoverse://tarball_name=tracking_train1.tar.gz&log_id=53037376_5303_5303_5303_553038557184&split=train&camera=ring_front_center&timestamp=315967813075342440',
)

FIXTURES_BASE_PATH = os.path.join(conf.AU_ROOT, 'au/test/')

TEST_TEMPDIR = os.path.join(testconf.TEST_TEMPDIR_ROOT, 'test_argoverse')

# class TestFixturesBase(av.Fixtures):
#   ROOT = os.path.join(TEST_TEMPDIR, 'argoverse')

#   def setup(cls):
#     try:
#       os.symlink(av.Fixtures.ROOT, cls.ROOT)
#     except FileExistsError:
#       pass

#   @classmethod
#   def tarballs_dir(cls):
#     # Provide read access to real uncompressed tarballs because
#     # copying them is prohibitive
#     return REAL_TARBALLS_ROOT

class TestImageAnnoTableBase(av.ImageAnnoTable):
  # NB: We will override FIXTURES at test time

  @classmethod
  def _create_uri_rdd(cls, spark, splits=None):
    uri_rdd = spark.sparkContext.parallelize(
                            TEST_FIXTURE_URIS,
                            numSlices=len(TEST_FIXTURE_URIS))
    return uri_rdd

class TestArgoverseImageTable(unittest.TestCase):
  """Exercise utilties in the Argoverse module.  Allow soft failures
  if the user has none of the required tarballs.  We assume exclusively
  one of:
     1) the user emplaced the fixtures correctly using aucli
     2) the user has no fixtures and does not need them
  """

  # We'll set up these classes, if posible, in test setup
  TestFixtures = None
  ImageAnnoTable = None

  @classmethod
  def setUpClass(cls):
    cls.have_fixtures = all(
          os.path.exists(av.Fixtures.tarball_dir(tarball))
          for tarball in av.Fixtures.TRACKING_TARBALLS)

    TEST_FIXTURES_ROOT = os.path.join(TEST_TEMPDIR, 'argoverse_data_root')

    from _pytest.monkeypatch import MonkeyPatch
    monkeypatch = MonkeyPatch()
    testconf.use_tempdir(monkeypatch, TEST_TEMPDIR)
    
    if cls.have_fixtures:
      util.mkdir(TEST_TEMPDIR)
      try:
        os.symlink(av.Fixtures.ROOT, TEST_FIXTURES_ROOT)
      except FileExistsError:
        pass

      class TestFixtures(av.Fixtures):
        # Use patched value
        ROOT = TEST_FIXTURES_ROOT

      class TestImageAnnoTable(TestImageAnnoTableBase):
        FIXTURES = TestFixtures
    
      cls.TestFixtures = TestFixtures
      cls.ImageAnnoTable = TestImageAnnoTable
    
    if cls.ImageAnnoTable:
      with testutils.LocalSpark.sess() as spark:
        cls.ImageAnnoTable.setup(spark)

  def test_fixture_uris(self):
    for s in TEST_FIXTURE_URIS:
      assert s
      uri = av.FrameURI.from_str(s)
      def check(v):
        assert v
        assert str(v) in s
      check(uri.log_id)
      check(uri.camera)
      check(uri.timestamp)

      # Only require the user to have the sample fixture set up
      if self.have_fixtures and uri.split == 'sample':
        loader = av.Fixtures.get_loader(uri)
        assert loader

  @pytest.mark.slow
  def test_image_anno_table_stats(self):
    if not self.ImageAnnoTable:
      return
    
    with testutils.LocalSpark.sess() as spark:
      anno_df = self.ImageAnnoTable.as_df(spark)

      ### Sanity Checks
      expected_num_frames = len(TEST_FIXTURE_URIS)

      actual_frames = anno_df.select('frame_uri').distinct()
      actual_frames = actual_frames.rdd.flatMap(lambda x: x).collect()
      assert sorted(actual_frames) == sorted(TEST_FIXTURE_URIS)

      num_annos = anno_df.count()
      assert num_annos >= expected_num_frames

      ### Stats Checks
      # We'll just do a 'binary' diff of stats for now because it's easy
      # and sanity-checks of fixture updates (i.e. adding a URI) should
      # be easy to check / fix.
      title_pdf = self.ImageAnnoTable.get_stats_dfs(spark)
      actual_report = '\n\n'.join(
                        '%s\n%s' % (title, str(pdf))
                          for title, pdf in title_pdf)
      util.log.info(
        'test_image_anno_table_stats actual report: \n\n' + actual_report)
      
      # Save the actual report
      FIXTURE_NAME = 'test_image_anno_table_stats.txt'
      actual_path = os.path.join(TEST_TEMPDIR, 'actual_' + FIXTURE_NAME)
      with open(actual_path, 'w') as f:
        f.write(actual_report)
      FIXTURE_PATH = os.path.join(FIXTURES_BASE_PATH, FIXTURE_NAME)
      expected_report = open(FIXTURE_PATH, 'r').read()

      assert expected_report == actual_report, """
        Report mismatch; to update fixture use:
        cp %s %s""" % (actual_path, FIXTURE_PATH)


  # def test_samplexxxxxxx(self):
  #   # if not self.have_fixtures:
  #   #   return


  #   if True: # Returnme
  #     # test_uri = av.FrameURI(
  #     #               tarball_name=av.Fixtures.TRACKING_SAMPLE,
  #     #               log_id='c6911883-1843-3727-8eaa-41dc8cda8993')

  #     # loader = av.Fixtures.get_loader(test_uri)
  #     # print('Loaded', loader)
  #     # assert loader.image_count == 3441

  #     # all_uris = list(itertools.chain.from_iterable(
  #     #   av.Fixtures.get_frame_uris(log_uri)
  #     #   for log_uri in av.Fixtures.get_log_uris('sample')))
  #     # assert len(all_uris) == 3441
      
  #     # EXPECTED_URI = 'argoverse://tarball_name=tracking_sample.tar.gz&log_id=c6911883-1843-3727-8eaa-41dc8cda8993&split=sample&camera=ring_front_center&timestamp=315978419252956672'
  #     # assert EXPECTED_URI in set(str(uri) for uri in all_uris)

  #     frame = av.AVFrame(uri='argoverse://tarball_name=tracking_train2.tar.gz&log_id=5c251c22-11b2-3278-835c-0cf3cdee3f44&split=train&camera=ring_front_center&timestamp=315967787401035936&track_id=f53345d4-b540-45f4-8d55-777b54252dad')#EXPECTED_URI)
  #     import imageio
  #     # TODO create fixture
  #     imageio.imwrite('/opt/au/tastttt.png', frame.get_debug_image(),format='png')

  #     hnm = av.HardNegativeMiner(frame)
  #     for i in range(10):
  #       bbox = hnm.next_sample()
  #       imageio.imwrite(
  #         '/opt/au/tastttt_%s.png' % i,
  #         frame.get_cropped(bbox).get_debug_image(),
  #         format='png')
  #       print('/opt/au/tastttt_%s.png' % i)


  #   if True:
  #     with testutils.LocalSpark.sess() as spark:
  #       # av.CroppedObjectImageTable.setup(spark=spark)

  #       # av.Fixtures.run_import(spark=spark)
  #       av.ImageAnnoTable.setup(spark)

  #       av.ImageAnnoTable.show_stats(spark)
  #       # av.CroppedObjectImageTable.setup(spark=spark)
        
        
  #       # df = av.Fixtures.label_df(spark, splits=('sample','train','test', 'val'))
  #       # df.write.parquet(
  #       #   '/tmp/av_yay_df',
  #       #   mode='overwrite',
  #       #   compression='lz4')
  #       # df = spark.read.parquet('/tmp/av_yay_df')
  #       # df = df.toPandas()
  #       # df.to_pickle('/tmp/av_yay_pdf')
  #       # assert False
  #       # import pdb; pdb.set_trace()
  #       # df.show()

  #   # import pandas as pd
  #   # df = pd.read_pickle('/tmp/av_yay_pdf')

    
  #       # df = spark.read.parquet(av.AnnoTable.table_root())
  #       # h = av.HistogramWithExamples()
  #       # h.run(spark, df)



