
import klepto # For a cache of NuScenes readers

from au.fixtures.datasets import av

## Utils

def transform_from_record(rec):
  from pyquaternion import Quaternion
  return av.Transform(
          rotation=Quaternion(rec['rotation']).rotation_matrix,
          translation=np.array(rec['translation']).reshape((3, 1)))

def get_camera_normal(K, extrinstic):
    """FMI see au.fixtures.datasets.auargoverse.get_camera_normal()"""

    # Build P
    # P = K * | R |T|
    #         |000 1|
    P = K.dot(extrinsic)

    # Zisserman pg 161 The principal axis vector.
    # P = [M | p4]; M = |..|
    #                   |m3|
    # pv = det(M) * m3
    pv = np.linalg.det(P[:3,:3]) * P[2,:3].T
    pv_hat = pv / np.linalg.norm(pv)
    return pv_hat

## Data

class Fixtures(object):

  ROOT = os.path.join(conf.AU_DATA_CACHE, 'nuscenes')

  TARBALLS = (
    'v1.0-mini.tar',
    
    'v1.0-test_meta.tar',
    'v1.0-test_blobs.tar',

    'v1.0-trainval01_blobs.tar',
    'v1.0-trainval02_blobs.tar',
    'v1.0-trainval03_blobs.tar',
    'v1.0-trainval04_blobs.tar',
    'v1.0-trainval05_blobs.tar',
    'v1.0-trainval06_blobs.tar',
    'v1.0-trainval07_blobs.tar',
    'v1.0-trainval08_blobs.tar',
    'v1.0-trainval09_blobs.tar',
    'v1.0-trainval10_blobs.tar',

    'nuScenes-map-expansion.zip',
  )

  MINI_TARBALL = 'v1.0-mini.tar'

  SPLITS = ('train', 'val', 'test', 'mini')
  
  TRAIN_TEST_SPLITS = ('train', 'val')

  ## Source Data

  @classmethod
  def tarballs_dir(cls):
    return os.path.join(cls.ROOT, 'tarballs')

  @classmethod
  def tarball_path(cls, fname):
    return os.path.join(cls.tarballs_dir(), fname)

  # @classmethod
  # def tarball_dir(cls, fname):
  #   """Get the directory for an uncompressed tarball with `fname`"""
  #   dirname = fname.replace('.tar.gz', '')
  #   return cls.tarball_path(dirname)

  # @classmethod
  # def all_tarballs(cls):
  #   return list(
  #     itertools.chain.from_iterable(
  #       getattr(cls, attr, [])
  #       for attr in dir(cls)
  #       if attr.endswith('_TARBALLS')))


  ## Derived Data
  
  @classmethod
  def dataroot(cls):
    return os.path.join(cls.ROOT, 'nuscenes_dataroot')

  @classmethod
  def index_root(cls):
    return os.path.join(cls.ROOT, 'index')
  

  ## Setup

  @classmethod
  def run_import(cls, only_mini=False):
    pass

  ## Public API

  @classmethod
  @klepto.inf_cache(ignore=(0, 1))
  def get_loader(cls, version='v1.0-trainval'):
    """Return a (maybe cached) `nuscenes.nuscenes.NuScenes` object
    for the entire dataset."""
    from nuscenes.nuscenes import NuScenes
    nusc = NuScenes(version=version, dataroot=cls.dataroot(), verbose=True)
    return nusc
  
  @classmethod
  def get_split_for_scene(cls, scene):
    if not hasattr(cls, '_scene_to_split'):
      scene_to_split = {}
      for split, scenes in split_to_scenes.items():
        # Ignore mini splits because they duplicate train/val
        if 'mini' not in split:
          for scene in scenes:
            scene_to_split[scene] = split
      cls._scene_to_split = scene_to_split
    return cls._scene_to_split[scene]
        


class FrameTable(av.FrameTableBase):

  FIXTURES = Fixtures

  NUSC_VERSION = 'v1.0-trainval' # E.g. v1.0-mini, v1.0-trainval, v1.0-test

  PROJECT_CLOUDS_TO_CAM = True
  PROJECT_CUBOIDS_TO_CAM = True
  IGNORE_INVISIBLE_CUBOIDS = True
  
  SETUP_URIS_PER_CHUNK = 1000

  ## Subclass API


  
  ## Public API

  @classmethod
  def create_frame(cls, uri):
    nusc = cls.get_nusc() 
    scene_to_ts_to_sample_token = cls._scene_to_ts_to_sample_token()
    sample_token = scene_to_ts_to_sample_token[uri.segment_id][uri.timestamp]
    sample = nusc.get('sample', sample_token)
    return cls._create_frame_from_sample(uri, sample)

  @classmethod
  def get_nusc(cls):
    if not hasattr(cls, '_nusc'):
      cls._nusc = cls.FIXTURES.get_loader(version=cls.NUSC_VERSION)
    return cls._nusc


  ## Support

  @classmethod
  def _get_camera_uris(cls, splits=None):
    nusc = cls.get_nusc()

    if not splits:
      splits = cls.FIXTURES.TRAIN_TEST_SPLITS

    uris = []
    for sample in nusc.sample:
      scene_record = nusc.get('scene', sample['scene_token'])
      scene_split = cls.FIXTURES.get_split_for_scene[scene_record['name']]
      if scene_split not in splits:
        continue

      for sensor, token in sample['data'].items():
        sample_data = nusc.get('sample_data', token)
        if sample_data['sensor_modality'] == 'camera':
          uri = av.URI(
                  dataset='nuscenes',
                  split=scene_split,
                  timestamp=sample['timestamp'],
                  segment_id=scene['name'],
                  camera=sensor)
          uris.append(uri)
    return uris
  
  @classmethod
  def _scene_to_ts_to_sample_token(cls):
    if not hasattr(cls, '__scene_to_ts_to_sample_token'):
      nusc = cls.get_nusc()
      scene_name_to_token = dict(
        (scene['name'], scene['token']) for scene in nusc.scene)
    
      from collections import defaultdict
      scene_to_ts_to_sample_token = defaultdict(dict)
      for sample in nusc.sample:
        scene_name = nusc.get('scene', sample['scene_token'])['name']
        timestamp = sample['timestamp']
        token = sample['token']
        scene_to_ts_to_sample_token[scene_name][timestamp] = token
      
      cls.__scene_to_ts_to_sample_token = scene_to_ts_to_sample_token
    return cls.__scene_to_ts_to_sample_token

  @classmethod
  def _create_frame_from_sample(cls, uri, sample):
    f = av.Frame(uri=uri)
    cls._fill_ego_pose(uri, sample, f)
    cls._fill_camera_images(uri, sample, f)
    return f
  
  @classmethod
  def _fill_ego_pose(cls, uri, sample, f):
    nusc = cls.get_nusc()

    # For now, always set ego pose using the *lidar* timestamp, as is done
    # in nuscenes.  (They probably localize mostly from lidar anyways).
    token = sample['data']['LIDAR_TOP']
    sd_record = nusc.get('sample_data', token)
    sensor_record = nusc.get('sensor', cs_record['sensor_token'])
    pose_record = nusc.get('ego_pose', sd_record['ego_pose_token'])
    
    f.world_to_ego = transform_from_record(pose_record)

  @classmethod
  def _fill_camera_images(uri, sample, f):
    nusc = cls.get_nusc()
    if uri.camera:
      camera_token = sample['data'][uri.camera]
      ci = cls._get_camera_image(uri, camera_token, f)
      f.camera_images.append(ci)
    else:
      raise ValueError("Grouping multiple cameras etc into frames TODO")
  
  @classmethod
  def _get_camera_image(uri, camera_token, f):
    nusc = cls.get_nusc()
    sd_record = nusc.get('sample_data', camera_token)
    cs_record = nusc.get(
      'calibrated_sensor', sd_record['calibrated_sensor_token'])
    sensor_record = nusc.get('sensor', cs_record['sensor_token'])
    pose_record = nusc.get('ego_pose', sd_record['ego_pose_token'])

    data_path, _, cam_intrinsic = nusc.get_sample_data(camera_token)
      # Ignore box_list, we'll get boxes in ego frame later
    
    viewport = uri.get_viewport()
    w, h = sd_record['width'], sd_record['height']
    if not viewport:
      viewport = common.BBox.of_size(w, h)

    timestamp = sd_record['timestamp']

    cam_from_ego = transform_from_record(cs_record)

    principal_axis_in_ego = get_camera_normal(
                              cam_intrinsic,
                              cam_from_ego.get_transformation_matrix())
    
    ci = av.CameraImage(
          camera_name=uri.camera,
          image_jpeg=bytearray(open(data_path, 'rb').read()),
          height=h,
          width=w,
          viewport=viewport,
          timestamp=timestamp,
          cam_from_ego=cam_from_ego,
          K=cam_intrinsic,
          principal_axis_in_ego=principal_axis_in_ego,
        )
    
    if cls.PROJECT_CLOUDS_TO_CAM:
      for sensor in ('LIDAR_TOP',):
        pc = cls._get_point_cloud_in_ego(sample, sensor=sensor)
        
        # Project to image
        pc.cloud = ci.project_ego_to_image(pc.cloud, omit_offscreen=True)
        pc.sensor_name = pc.sensor_name + '_in_cam'
        ci.cloud = pc
      
    if cls.PROJECT_CUBOIDS_TO_CAM:
      sample_data_token = sd_record['token']
      cuboids = cls._get_cuboids_in_ego(sample_data_token)
      for cuboid in cuboids:
        bbox = ci.project_cuboid_to_bbox(cuboid)
        if cls.IGNORE_INVISIBLE_CUBOIDS and not bbox.is_visible:
          continue
        ci.bboxes.append(bbox)

    @classmethod
    def _get_point_cloud_in_ego(cls.sample, sensor='LIDAR_TOP'):
      # Based upon nuscenes.py#map_pointcloud_to_image()
      import os.path as osp
      
      from pyquaternion import Quaternion

      from nuscenes.utils.data_classes import LidarPointCloud
      from nuscenes.utils.data_classes import RadarPointCloud
      
      nusc = cls.get_nusc()
      pointsensor_token = sample['data'][sensor]
      pointsensor = nusc.get('sample_data', pointsensor_token)
      pcl_path = osp.join(nusc.dataroot, pointsensor['filename'])
      if pointsensor['sensor_modality'] == 'lidar':
        pc = LidarPointCloud.from_file(pcl_path)
      else:
        pc = RadarPointCloud.from_file(pcl_path)

      # Points live in the point sensor frame, so transform to ego frame
      cs_record = nusc.get(
        'calibrated_sensor', pointsensor['calibrated_sensor_token'])
      pc.rotate(Quaternion(cs_record['rotation']).rotation_matrix)
      pc.translate(np.array(cs_record['translation']))
      return av.PointCloud(
        sensor_name=sensor,
        timestamp=pointsensor['timestamp'],
        cloud=pc.points,
        ego_to_sensor=transform_from_record(cs_record),
        motion_corrected=False, # TODO interpolation for cam ~~~~~~~~~~~~~~~~~~~~~~~
      )
    
    @classmethod
    def _get_cuboids_in_ego(cls, sample_data_token):
      nusc = cls.get_nusc()
      boxes = nusc.get_boxes(sample_data_token)
    
      # Boxes are in world frame.  Move all to ego frame.
      from pyquaternion import Quaternion
      sd_record = nusc.get('sample_data', sample_data_token)
      pose_record = nusc.get('ego_pose', sd_record['ego_pose_token'])
      for box in boxes:
        # Move box to ego vehicle coord system
        box.translate(-np.array(pose_record['translation']))
        box.rotate(Quaternion(pose_record['rotation']).inverse)

      cuboids = []
      for box in boxes:
        cuboid = av.Cuboid()

        # Core
        sample_anno = nusc.get('sample_annotation', box.token)
        cuboid.track_id = \
          'nuscenes_instance_token:' +sample_anno['instance_token']
        cuboid.category_name = box.name
        cuboid.timestamp = sd_record['timestamp']
        
        attribs = [
          nusc.get('attribute', attrib_token)
          for attrib_token in sample_anno['attribute_tokens']
        ]
        cuboid.extra = {
          'nuscenes_token': box.token,
          'nuscenes_attribs': '|'.join(attrib['name'] for attrib in attribs),
        }

        # Points
        cuboid.box3d = box.corners().T
        cuboid.motion_corrected = False # TODO interpolation ? ~~~~~~~~~~~~~~~~~~~~
        cuboid.distance_meters = np.min(np.linalg.norm(cuboid.box3d, axis=-1))
        
        # Pose
        cuboid.width_meters = float(box.wlh[0])
        cuboid.length_meters = float(box.wlh[1])
        cuboid.height_meters = float(box.wlh[3])

        cuboid.obj_from_ego = av.Transform(
            rotation=box.orientation.rotation_matrix,
            translation=box.center.reshape((3, 1)))
        cuboids.append(cuboid)
      return cuboids