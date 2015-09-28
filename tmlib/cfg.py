'''
TISSUEMAPS LIBRARY CONFIGURATION SETTINGS

Describe the experimental layout (directory structure and filename nomenclature)
by Python format strings. To this end, the following keywords are available::

* *experiment_dir*: Absolute path to the experiment folder (string).

* *experiment*: Name of the experiment folder, i.e. the basename of "experiment_dir" (string).
                 
* *cycle_dir*: Absolute path to the cycle directory (string).

* *cycle*: Name of the cycle folder, i.e. the basename of "cycle_dir" (string).

* *channel*: Name of the corresponding channel or wavelength (string).

* *site*: One-based position index in the acquisition sequence in x, y dimensions (integer).

* *time*: One-based time point index in the acquisition sequence in t dimension (integer).

* *zstack*: One-based z-stack index in the acquisition sequence in z dimension (integer).

* *row*: Y index position of the image in the acquisition grid (integer).

* *column*: X index position of the image in the acquisition grid (integer).

* *well*: Well identifier Id encoding the position in the well plate (string).

* *sep*: Platform-specific path separator ("/" Unix or "\" Windows)
'''


CYCLE_DIR = '{experiment}-{cycle_id}'

IMAGE_UPLOAD_DIR = '{cycle_dir}{sep}image_uploads'
ADDITIONAL_UPLOAD_DIR = '{cycle_dir}{sep}additional_uploads'
OME_XML_DIR = '{cycle_dir}{sep}ome_xml'

IMAGE_DIR = '{cycle_dir}{sep}images'
IMAGE_FILE = '{cycle}_{well}_s{site:0>3}_r{row:0>2}_c{column:0>2}_{channel}.png'

METADATA_DIR = '{cycle_dir}{sep}metadata'
IMAGE_METADATA_FILE = 'images.metadata'

STATS_DIR = '{cycle_dir}{sep}stats'
STATS_FILE = '{cycle}_{channel}.stats'

SHIFT_DIR = '{cycle_dir}{sep}shift'
SHIFT_FILE = '{cycle}.shift'

LAYERS_DIR = '{experiment_dir}{sep}layers'
LAYER_NAME = '{cycle}-{channel}'
DATA_FILE = '{experiment_dir}{sep}data.h5'

USER_CFG_FILE = '{experiment_dir}{sep}user.cfg'