FROM tensorflow/tensorflow:1.12.0-gpu

# We don't care for __pycache__ and .pyc files; sometimes VSCode doesn't clean
# up properly when deleting things and the cache gets stale.
ENV PYTHONDONTWRITEBYTECODE 1

# Use GCloud mirrors because they're faster, especially in gcloud
COPY docker/sources.list /etc/apt/sources.list

## Required for installing things
RUN apt-get update
RUN apt-get install -y curl git python-dev wget



## Java
RUN \
  apt-get install -y default-jdk && \
  ls -lhat /usr/lib/jvm/java-8-openjdk-amd64 && \
  echo JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 >> /etc/environment
ENV JAVA_HOME /usr/lib/jvm/java-8-openjdk-amd64



## Bazel -- might not need this ...
RUN \
  apt-get install -y bash-completion && \
  wget --progress=bar:force:noscroll https://github.com/bazelbuild/bazel/releases/download/0.16.1/bazel_0.16.1-linux-x86_64.deb && \
  dpkg -i bazel_0.16.1-linux-x86_64.deb 



## Tensorflow
# Fix nvidia stubs and test tensorflow
ENV LD_LIBRARY_PATH $LD_LIBRARY_PATH:/usr/local/cuda/lib64:/usr/local/cuda/lib:/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64/stubs
RUN \
  ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 && \
  ldconfig && \
  python -c 'from tensorflow.python.client import device_lib; device_lib.list_local_devices()' 



## Spark & Hadoop
ENV HADOOP_VERSION 3.1.1
ENV HADOOP_HOME /opt/hadoop
ENV HADOOP_CONF_DIR $HADOOP_HOME/etc/hadoop
ENV PATH $PATH:$HADOOP_HOME/bin
ENV LD_LIBRARY_PATH "$HADOOP_HOME/lib/native/:$LD_LIBRARY_PATH"
RUN curl -L --retry 3 \
  "http://mirrors.ibiblio.org/apache/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION.tar.gz" \
  | gunzip \
  | tar -x -C /opt/ \
 && mv /opt/hadoop-$HADOOP_VERSION $HADOOP_HOME \
 && rm -rf $HADOOP_HOME/share/doc

ENV SPARK_VERSION 2.4.0
ENV SPARK_PACKAGE spark-${SPARK_VERSION}-bin-without-hadoop
ENV SPARK_HOME /opt/spark
ENV SPARK_DIST_CLASSPATH "$HADOOP_HOME/etc/hadoop/*:$HADOOP_HOME/share/hadoop/common/lib/*:$HADOOP_HOME/share/hadoop/common/*:$HADOOP_HOME/share/hadoop/hdfs/*:$HADOOP_HOME/share/hadoop/hdfs/lib/*:$HADOOP_HOME/share/hadoop/hdfs/*:$HADOOP_HOME/share/hadoop/yarn/lib/*:$HADOOP_HOME/share/hadoop/yarn/*:$HADOOP_HOME/share/hadoop/mapreduce/lib/*:$HADOOP_HOME/share/hadoop/mapreduce/*:$HADOOP_HOME/share/hadoop/tools/lib/*"
ENV PATH $PATH:${SPARK_HOME}/bin
RUN curl -L --retry 3 \
  "https://www.apache.org/dyn/mirrors/mirrors.cgi?action=download&filename=spark/spark-${SPARK_VERSION}/${SPARK_PACKAGE}.tgz" \
  | gunzip \
  | tar x -C /opt/ \
 && mv /opt/$SPARK_PACKAGE $SPARK_HOME \
 && pip install findspark
COPY docker/spark-defaults.conf /opt/spark/conf/spark-defaults.conf

## Alluxio
RUN \
  apt-get install -y libfuse-dev && \
  cd /tmp && \
  wget --progress=bar:force:noscroll http://downloads.alluxio.org/downloads/files/1.8.1/alluxio-1.8.1-hadoop-2.9-bin.tar.gz && \
  tar --checkpoint=1000 --checkpoint-action=dot -xzf alluxio-1.8.1-hadoop-2.9-bin.tar.gz -C /opt/ && \
  mv /opt/alluxio-1.8.1-hadoop-2.9 /opt/alluxio && \
  rm /tmp/alluxio-1.8.1-hadoop-2.9-bin.tar.gz && \
  cp -v /opt/alluxio/client/alluxio-1.8.1-client.jar $SPARK_HOME/jars/ && \
  mkdir -p /opt/alluxio-cache && chmod 777 /opt/alluxio-cache && \
  mkdir -p /opt/alluxio-underfs && chmod 777 /opt/alluxio-underfs
#  mkdir -p /mnt/alluxio-ramdisk && mount -t ramfs -o size=1G ramfs /mnt/alluxio-ramdisk
COPY docker/alluxio-site.properties /opt/alluxio/conf/alluxio-site.properties



## Dev tools
COPY docker/.vimrc /root/.vimrc
COPY docker/.screenrc /root/.screenrc
RUN \
  apt-get update && \
  apt-get install -y \
    curl \
    dnsutils \
    git \
    gsutil \
    net-tools \
    screen \
    ssh \
    sudo \
    vim \
    wget && \
  pip install ipdb && \
  curl -LO https://github.com/BurntSushi/ripgrep/releases/download/0.10.0/ripgrep_0.10.0_amd64.deb && \
  dpkg -i ripgrep_0.10.0_amd64.deb


## AU Python
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN python -c 'import imageio; imageio.plugins.ffmpeg.download()'


## TF Models
ENV PYTHONPATH $PYTHONPATH:/opt/au/external/tensorflow_models/research:/opt/au/external/tensorflow_models/research/slim:/opt/au/external/tensorflow_models/official:/opt/au/external/tensorflow_models/
RUN \
  apt-get install -y protobuf-compiler python-pil python-lxml python-tk && \
  pip install Cython contextlib2 matplotlib && \
  cd /tmp && \
  git clone https://github.com/cocodataset/cocoapi.git && \
  cd cocoapi/PythonAPI && \
  python setup.py install


## TF CNN Vis
RUN pip install scipy h5py wget Pillow six scikit-image


## Kubespray
# See docker/kubespray_requirements.txt for notes
COPY docker/kubespray_requirements.txt /tmp/kubespray_requirements.txt
RUN pip install -r /tmp/kubespray_requirements.txt
ENV PATH $PATH:/opt/au/kubespray/inventory/default/artifacts/


## Gcloud
RUN \
  curl https://sdk.cloud.google.com | bash && \
  pip install -U crcmod 

# gcsfuse does NOT support read cache :P
# and s3fs is broken too it seems
#  export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s` && \
#  echo "deb http://packages.cloud.google.com/apt $GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list && \
#  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add - && \
#  apt-get update && \
#  apt-get install -y gcsfuse


## AU
COPY aucli /opt/au/aucli
WORKDIR /opt/au
RUN SPARK_LOCAL_IP=127.0.0.1 SPARK_MASTER=local[4] /opt/au/aucli --test-spark 
